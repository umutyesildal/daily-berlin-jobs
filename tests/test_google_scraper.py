import json
import unittest
from urllib.parse import parse_qs, urlsplit

from daily_jobs.scrapers.done.google_scraper import GoogleScraper, parse_google_ds1


def google_row(job_id, title, location, description):
    return [
        job_id,
        title,
        "https://www.google.com/about/careers/applications/signin?jobId=opaque",
        [None, f"<p>{description}</p>"],
        [None, "<p>Qualifications</p>"],
        "projects/google/company",
        None,
        "Google Cloud",
        "en-US",
        [[location, [location], location.split(",")[0], None, "BE", "DE"]],
        [None, "<p>Role overview</p>"],
    ]


def google_page(rows, page):
    links = "".join(
        f'<a href="jobs/results/{row[0]}-{row[1].lower().replace(" ", "-")}?location=Berlin,+Germany&page={page}"></a>'
        for row in rows
    )
    payload = json.dumps([rows, None, len(rows), 20])
    return (
        f"<html>{links}<script class=\"ds:1\">"
        f"AF_initDataCallback({{key: 'ds:1', hash: '2', data: {payload}, sideChannel: {{}}}});"
        "</script></html>"
    )


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


class GoogleScraperTests(unittest.TestCase):
    def test_empty_ds1_page_is_a_valid_end_of_pagination(self):
        payload = json.dumps([None, None, 17, 20])
        html = (
            '<script class="ds:1">'
            f"AF_initDataCallback({{key: 'ds:1', hash: '2', data: {payload}, sideChannel: {{}}}});"
            "</script>"
        )

        self.assertEqual(parse_google_ds1(html), [])

    def test_ds1_parser_extracts_description_locations_and_detail_link(self):
        row = google_row("12345", "Backend Engineer", "Berlin, Germany", "Build services.")
        html = google_page([row], 1)

        jobs = parse_google_ds1(html)

        self.assertEqual(jobs[0]["id"], "12345")
        self.assertEqual(jobs[0]["location"], "Berlin, Germany")
        self.assertEqual(jobs[0]["description"], "Build services.\nQualifications\nRole overview")
        self.assertEqual(
            jobs[0]["url"],
            "https://www.google.com/about/careers/applications/jobs/results/12345-backend-engineer",
        )

    def test_paginates_and_filters_non_berlin_locations(self):
        page_one = [
            google_row("1", "Backend Engineer", "Berlin, Germany", "Build APIs."),
            google_row("2", "Sales Manager", "New York, United States", "Manage customers."),
        ]
        page_two = [google_row("3", "Data Engineer", "Berlin, Germany", "Build data systems.")]
        page_three = []

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append(url)
                query = parse_qs(urlsplit(url).query)
                page = int(query["page"][0])
                return FakeResponse({
                    1: google_page(page_one, 1),
                    2: google_page(page_two, 2),
                    3: google_page(page_three, 3),
                }[page])

        scraper = GoogleScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://www.google.com/about/careers/applications/jobs/results?location=Berlin%2C%20Germany",
            "Google",
        )

        self.assertEqual([job["Job Title"] for job in jobs], ["Backend Engineer", "Data Engineer"])
        self.assertTrue(all("Berlin" in job["Location"] for job in jobs))
        self.assertEqual(jobs[0]["Job Description"], "Build APIs.\nQualifications\nRole overview")
        self.assertEqual(len(scraper.session.urls), 3)
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })


if __name__ == "__main__":
    unittest.main()

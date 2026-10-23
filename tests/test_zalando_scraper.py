import unittest

from daily_jobs.scrapers.done.zalando_scraper import ZalandoScraper, parse_zalando_listing


def listing_page(jobs, current_page, last_page):
    cards = "".join(
        f"""
        <a href="/en/jobs/{job_id}-{slug}">
          <article>
            <h2>{title}</h2>
            <p>{department}</p>
            <p>{location}</p>
          </article>
        </a>
        """
        for job_id, slug, title, department, location in jobs
    )
    pages = "".join(
        f'<button aria-label="Page {page} button">{page}</button>'
        for page in range(1, last_page + 1)
    )
    return f"<main><section>{pages}</section>{cards}</main>"


class FakeResponse:
    def __init__(self, text, status_code=200, url=""):
        self.text = text
        self.status_code = status_code
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class ZalandoScraperTests(unittest.TestCase):
    def test_listing_parser_reads_card_metadata_and_pagination(self):
        html = listing_page(
            [(1, "backend-engineer", "Backend Engineer", "Software Engineering", "Berlin")],
            1,
            4,
        )
        jobs, page_count = parse_zalando_listing(html, "https://jobs.zalando.com/en/jobs")

        self.assertEqual(page_count, 4)
        self.assertEqual(jobs[0]["title"], "Backend Engineer")
        self.assertEqual(jobs[0]["location"], "Berlin")
        self.assertEqual(jobs[0]["department"], "Software Engineering")
        self.assertEqual(jobs[0]["url"], "https://jobs.zalando.com/en/jobs/1-backend-engineer")

    def test_paginates_and_keeps_only_berlin_jobs(self):
        first_page = listing_page([
            (1, "backend-engineer", "Backend Engineer", "Engineering", "Berlin"),
            (2, "sales-manager", "Sales Manager", "Sales", "Hamburg"),
        ], 1, 2)
        second_page = listing_page([
            (3, "data-engineer", "Data Engineer", "Engineering", "Berlin"),
        ], 2, 2)

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append(url)
                if "/en/jobs?location=Berlin&page=1" in url:
                    return FakeResponse(first_page, url=url)
                if "/en/jobs?location=Berlin&page=2" in url:
                    return FakeResponse(second_page, url=url)
                if url.endswith("/en/jobs/1-backend-engineer"):
                    return FakeResponse(
                        "<main><h1>Backend Engineer</h1><p>Contract Full time Job Category Engineering</p>"
                        "<article><p>Build reliable services.</p></article></main>",
                        url=url,
                    )
                if url.endswith("/en/jobs/3-data-engineer"):
                    return FakeResponse(
                        "<main><h1>Data Engineer</h1><article><p>Build data pipelines.</p></article></main>",
                        url=url,
                    )
                raise AssertionError(url)

        scraper = ZalandoScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://jobs.zalando.com/en/jobs?location=Berlin",
            "Zalando",
        )

        self.assertEqual([job["Job Title"] for job in jobs], ["Backend Engineer", "Data Engineer"])
        self.assertEqual(jobs[0]["Job Description"], "Build reliable services.")
        self.assertEqual(jobs[0]["Employment Type"], "Full time")
        self.assertTrue(all("Berlin" in job["Location"] for job in jobs))
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })
        self.assertEqual(len(scraper.session.urls), 4)


if __name__ == "__main__":
    unittest.main()

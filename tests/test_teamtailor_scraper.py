import unittest

from daily_jobs.scrapers.done.teamtailor_scraper import TeamtailorScraper


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class TeamtailorScraperTests(unittest.TestCase):
    def test_feed_pagination_parses_job_locations_and_descriptions(self):
        first_page = {
            "items": [
                {
                    "title": "Backend Engineer",
                    "url": "https://example.teamtailor.com/jobs/1-backend-engineer",
                    "date_published": "2026-10-20T10:00:00Z",
                    "content_html": "<p>Build APIs.</p>",
                    "_jobposting": {
                        "jobLocation": [{
                            "address": {"addressLocality": "Berlin", "addressCountry": "DE"},
                        }],
                    },
                },
                {
                    "title": "Account Manager",
                    "url": "https://example.teamtailor.com/jobs/2-account-manager",
                    "content_html": "<p>Manage accounts.</p>",
                    "_jobposting": {
                        "jobLocation": [{
                            "address": {"addressLocality": "Munich", "addressCountry": "DE"},
                        }],
                    },
                },
            ],
            "next_url": "/jobs.json?page=2&per_page=100",
        }
        second_page = {
            "items": [{
                "title": "Senior Data Engineer",
                "url": "https://example.teamtailor.com/jobs/3-data-engineer",
                "content_html": "<p>Build data systems.</p>",
                "_jobposting": {
                    "jobLocation": [{
                        "address": {"addressLocality": "Berlin", "addressCountry": "DE"},
                    }],
                },
            }],
        }

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append(url)
                if url.endswith("/jobs.json"):
                    return FakeResponse(first_page)
                if "page=2" in url:
                    return FakeResponse(second_page)
                raise AssertionError(url)

        scraper = TeamtailorScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://example.teamtailor.com/jobs",
            "Example",
            label="teamtailor",
        )

        self.assertEqual(len(jobs), 3)
        self.assertIn("Berlin", jobs[0]["Location"])
        self.assertIn("Munich", jobs[1]["Location"])
        self.assertEqual(jobs[0]["Job Description"], "Build APIs.")
        self.assertEqual(jobs[0]["ATS"], "Teamtailor")
        self.assertEqual(jobs[0]["Posted Date"], "2026-10-20")
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })
        self.assertEqual(len(scraper.session.urls), 2)


if __name__ == "__main__":
    unittest.main()

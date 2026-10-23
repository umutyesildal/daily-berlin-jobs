import unittest

from daily_jobs.scrapers.done.frequenz_scraper import FrequenzScraper, parse_frequenz_listing


class FakeResponse:
    def __init__(self, text, status_code=200, url=""):
        self.text = text
        self.status_code = status_code
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class FrequenzScraperTests(unittest.TestCase):
    def test_listing_parser_extracts_job_pages(self):
        html = """
        <div class="job">
          <a class="jobs-title-link" href="/careers/senior-rust-engineer">
            <h5 class="job__title">Senior Rust Engineer (f/m/d)</h5>
          </a>
          <a href="/careers">Careers</a>
        </div>
        """

        jobs = parse_frequenz_listing(html, "https://www.frequenz.com/careers")

        self.assertEqual(jobs, [{
            "title": "Senior Rust Engineer (f/m/d)",
            "url": "https://www.frequenz.com/careers/senior-rust-engineer",
        }])

    def test_fetches_details_and_filters_to_berlin(self):
        listing = """
        <a href="/careers/senior-rust-engineer"><h5>Senior Rust Engineer</h5></a>
        <a href="/careers/sales-manager"><h5>Sales Manager</h5></a>
        """
        berlin_detail = """
        <div class="main">
          <h1>Senior Rust Engineer</h1>
          <p>Berlin / Hybrid possible Full-time Development</p>
          <h2>Job role insights</h2>
          <p>Date posted November 21, 2025</p><p>Level Senior</p>
          <p>Hiring location Berlin / Hybrid possible</p>
          <h2>About Frequenz</h2><p>About the company.</p>
          <h2>Responsibilities</h2><p>Build the platform.</p>
        </div>
        """
        hamburg_detail = """
        <div class="main">
          <h1>Sales Manager</h1>
          <p>Hamburg Full-time Sales</p><h2>Job role insights</h2>
          <p>Hiring location Hamburg</p><h2>About Frequenz</h2>
        </div>
        """

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append(url)
                if url.endswith("/careers"):
                    return FakeResponse(listing, url=url)
                if url.endswith("/careers/senior-rust-engineer"):
                    return FakeResponse(berlin_detail, url=url)
                if url.endswith("/careers/sales-manager"):
                    return FakeResponse(hamburg_detail, url=url)
                raise AssertionError(url)

        scraper = FrequenzScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs("https://www.frequenz.com/careers", "Frequenz")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["Job Title"], "Senior Rust Engineer")
        self.assertEqual(jobs[0]["Location"], "Berlin / Hybrid possible")
        self.assertEqual(jobs[0]["Employment Type"], "Full-time")
        self.assertEqual(jobs[0]["Department"], "Development")
        self.assertIn("Build the platform", jobs[0]["Job Description"])
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })
        self.assertEqual(len(scraper.session.urls), 3)


if __name__ == "__main__":
    unittest.main()

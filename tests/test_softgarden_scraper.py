import unittest

from daily_jobs.scrapers.done.softgarden_scraper import SoftgardenScraper, parse_softgarden_listing


LISTING = """
<form>
  <div class="matchElement" id="job_id_1">
    <div class="matchValue date">10/20/26</div>
    <div class="matchValue title"><a href="../job/1/backend-engineer">Backend Engineer</a></div>
    <div class="matchValue audience">Experienced Professional</div>
    <div class="matchValue jobcategory">Engineering</div>
    <div class="matchValue ProjectGeoLocationCity">Berlin</div>
  </div>
  <div class="matchElement" id="job_id_2">
    <div class="matchValue date">10/18/26</div>
    <div class="matchValue title"><a href="../job/2/sales-manager">Sales Manager</a></div>
    <div class="matchValue audience">Experienced Professional</div>
    <div class="matchValue jobcategory">Sales</div>
    <div class="matchValue ProjectGeoLocationCity">Hamburg</div>
  </div>
</form>
"""


class FakeResponse:
    def __init__(self, text, status_code=200, url=""):
        self.text = text
        self.status_code = status_code
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class SoftgardenScraperTests(unittest.TestCase):
    def test_parses_job_cards_and_locations(self):
        jobs = parse_softgarden_listing(LISTING, "https://example.softgarden.io/en/vacancies")

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["title"], "Backend Engineer")
        self.assertEqual(jobs[0]["location"], "Berlin")
        self.assertEqual(jobs[0]["department"], "Engineering")
        self.assertEqual(jobs[0]["url"], "https://example.softgarden.io/job/1/backend-engineer")

    def test_fetches_detail_description_only_for_berlin_cards(self):
        detail = """
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"Backend Engineer","description":"<p>Build backend systems.</p>",
         "employmentType":"Full-time","datePosted":"2026-10-20",
         "jobLocation":{"address":{"addressLocality":"Berlin","addressCountry":"DE"}}}
        </script>
        """

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append(url)
                if url.endswith("/en/vacancies"):
                    return FakeResponse(LISTING, url=url)
                if url.endswith("/job/1/backend-engineer"):
                    return FakeResponse(detail, url=url)
                raise AssertionError(url)

        scraper = SoftgardenScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs("https://example.softgarden.io/en/vacancies", "Example")

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["Location"], "Berlin, DE")
        self.assertEqual(jobs[0]["Job Description"], "Build backend systems.")
        self.assertEqual(jobs[0]["Employment Type"], "Full-time")
        self.assertEqual(jobs[1]["Job Description"], "")
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })
        self.assertEqual(len(scraper.session.urls), 2)


if __name__ == "__main__":
    unittest.main()

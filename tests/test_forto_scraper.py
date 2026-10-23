import unittest

from daily_jobs.scrapers.done.forto_scraper import FortoScraper, parse_forto_listing


LISTING = """
<ul>
  <li class="list-item boxBorder">
    <div class="list-item-column"><p class="title h5">Market Intelligence Analyst</p></div>
    <div class="list-item-column">Global Trade Management</div>
    <div class="list-item-column">FullTime</div>
    <div class="list-item-column list-item-column--hasButton">
      <div class="list-item-location">Berlin</div>
      <a class="item-link" href="/forto-jobs/market-intelligence-analyst-8847554b-267e-4c22-881e-fe0638b02ad3/">View Job</a>
    </div>
  </li>
  <li class="list-item boxBorder">
    <div class="list-item-column"><p class="title h5">Salesforce Administrator</p></div>
    <div class="list-item-column">Technology</div>
    <div class="list-item-column">FullTime</div>
    <div class="list-item-column list-item-column--hasButton">
      <div class="list-item-location">Hamburg</div>
      <a class="item-link" href="/forto-jobs/salesforce-administrator-6703a2ce-e298-4aef-8e6d-2570793acc48/">View Job</a>
    </div>
  </li>
</ul>
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


class FortoScraperTests(unittest.TestCase):
    def test_parses_listing_cards(self):
        jobs = parse_forto_listing(LISTING, "https://careers.forto.com/forto-jobs/")

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["title"], "Market Intelligence Analyst")
        self.assertEqual(jobs[0]["location"], "Berlin")
        self.assertEqual(jobs[0]["department"], "Global Trade Management")

    def test_fetches_details_and_filters_non_berlin_jobs(self):
        berlin_detail = """
        <main>
          <h1>Market Intelligence Analyst</h1>
          <p>Location Berlin Department Global Trade Management Employment Type FullTime Overview</p>
          <article><p>Analyze global trade data.</p></article>
        </main>
        """
        hamburg_detail = """
        <main>
          <h1>Salesforce Administrator</h1>
          <p>Location Hamburg Department Technology Employment Type FullTime Overview</p>
          <article><p>Manage Salesforce.</p></article>
        </main>
        """

        class FakeSession:
            def __init__(self):
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append(url)
                if url.endswith("job-location=berlin"):
                    return FakeResponse(LISTING, url=url)
                if "market-intelligence-analyst-" in url:
                    return FakeResponse(berlin_detail, url=url)
                if "salesforce-administrator-" in url:
                    return FakeResponse(hamburg_detail, url=url)
                raise AssertionError(url)

        scraper = FortoScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://careers.forto.com/forto-jobs/?job-location=berlin",
            "Forto",
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["Job Title"], "Market Intelligence Analyst")
        self.assertEqual(jobs[0]["Location"], "Berlin")
        self.assertEqual(jobs[0]["Department"], "Global Trade Management")
        self.assertEqual(jobs[0]["Employment Type"], "FullTime")
        self.assertIn("Analyze global trade data", jobs[0]["Job Description"])
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })
        self.assertEqual(len(scraper.session.urls), 3)


if __name__ == "__main__":
    unittest.main()

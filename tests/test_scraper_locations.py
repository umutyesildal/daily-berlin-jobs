import unittest

from daily_jobs.scrapers.done.ashby_scraper import AshbyScraper
from daily_jobs.scrapers.done.greenhouse_scraper import GreenhouseScraper
from daily_jobs.scrapers.done.smartrecruiters_scraper import SmartRecruitarsScraper


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, **kwargs)


class AshbyLocationTests(unittest.TestCase):
    def _scrape(self, job):
        scraper = AshbyScraper()
        scraper.session = FakeSession(lambda *_args, **_kwargs: FakeResponse({"jobs": [job]}))
        return scraper.scrape_jobs("https://jobs.ashbyhq.com/example", "Example")[0]

    def test_secondary_berlin_location_is_appended(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": "Remote - European Union",
            "secondaryLocations": [{"location": "Berlin, Germany"}],
        })

        self.assertEqual(job["Location"], "Remote - European Union / Berlin, Germany")

    def test_primary_berlin_location_is_kept_unchanged(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": "Berlin, Germany",
            "secondaryLocations": [{"location": "Berlin Remote Hub"}],
        })

        self.assertEqual(job["Location"], "Berlin, Germany")

    def test_address_locality_can_supply_berlin(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": "Remote - EU",
            "address": {"postalAddress": {"addressLocality": "Berlin"}},
        })

        self.assertEqual(job["Location"], "Remote - EU / Berlin")


class GreenhouseLocationTests(unittest.TestCase):
    def _scrape(self, job):
        scraper = GreenhouseScraper()
        scraper.session = FakeSession(lambda *_args, **_kwargs: FakeResponse({"jobs": [job]}))
        return scraper.scrape_jobs("https://boards.greenhouse.io/example", "Example")[0]

    def test_location_name_is_the_base(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": {"name": "Berlin, Germany"},
            "offices": [{"name": "AutoScout24 core", "location": "Munich"}],
        })

        self.assertEqual(job["Location"], "Berlin, Germany")

    def test_berlin_office_location_is_appended(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": {"name": "Munich"},
            "offices": [{"name": "Berlin office", "location": "Berlin, Germany"}],
        })

        self.assertEqual(job["Location"], "Munich / Berlin, Germany")

    def test_berlin_office_name_is_used_when_location_is_not_berlin(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": {"name": "Munich"},
            "offices": [{"name": "Berlin", "location": "DEU"}],
        })

        self.assertEqual(job["Location"], "Munich / Berlin")

    def test_missing_location_name_falls_back_to_office_names(self):
        job = self._scrape({
            "title": "Backend Engineer",
            "location": {"name": ""},
            "offices": [{"name": "AutoScout24 core"}, {"name": "Munich"}],
        })

        self.assertEqual(job["Location"], "AutoScout24 core, Munich")


class SmartRecruitersLocationTests(unittest.TestCase):
    def _posting(self, job_id, name, full_location, *, remote=False):
        return {
            "id": job_id,
            "name": name,
            "location": {
                "fullLocation": full_location,
                "city": full_location.split(",", 1)[0],
                "country": "DE",
                "remote": remote,
            },
            "department": {"label": "Engineering"},
            "typeOfEmployment": {"label": "Full-time"},
            "releasedDate": "2026-10-23T10:00:00Z",
        }

    def test_paginated_public_api_fetches_details_only_for_berlin(self):
        page_one = self._posting("100", "Berlin Engineer", "Berlin, Germany")
        page_two = self._posting("200", "Remote Engineer", "Remote, Europe", remote=True)
        calls = []

        def handler(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/postings"):
                offset = kwargs["params"]["offset"]
                posting = page_one if offset == 0 else page_two
                return FakeResponse({"totalFound": 2, "content": [posting]})
            if url.endswith("/postings/100"):
                return FakeResponse({
                    "postingUrl": "https://jobs.smartrecruiters.com/Example/100-berlin-engineer",
                    "jobAd": {
                        "sections": {
                            "jobDescription": {"text": "<p>Build reliable systems.</p>"},
                        },
                    },
                })
            raise AssertionError(f"Unexpected request: {url}")

        scraper = SmartRecruitarsScraper(delay=0)
        scraper.session = FakeSession(handler)
        jobs = scraper.scrape_jobs(
            "https://careers.smartrecruiters.com/Example/engineering/api/groups",
            "Example",
        )

        self.assertEqual(len(jobs), 2)
        self.assertEqual([call[1]["params"]["offset"] for call in calls if call[0].endswith("/postings")], [0, 1])
        self.assertEqual(sum(call[0].endswith("/postings/100") for call in calls), 1)
        self.assertFalse(any(call[0].endswith("/postings/200") for call in calls))
        self.assertEqual(jobs[0]["Job Link"], "https://jobs.smartrecruiters.com/Example/100-berlin-engineer")
        self.assertEqual(jobs[0]["Job Description"], "Build reliable systems.")
        self.assertEqual(jobs[1]["Job Description"], "")
        self.assertEqual(jobs[1]["Remote"], "Yes")

    def test_generated_link_uses_the_current_smartrecruiters_format(self):
        self.assertEqual(
            SmartRecruitarsScraper._posting_url(
                "DeliveryHero",
                {"id": "744000157441841", "name": "Manager Sales Operations & Strategy"},
            ),
            "https://jobs.smartrecruiters.com/DeliveryHero/"
            "744000157441841-manager-sales-operations-strategy",
        )
        self.assertEqual(
            SmartRecruitarsScraper._posting_url("Example", {"id": "123"}),
            "https://jobs.smartrecruiters.com/Example/123",
        )

    def test_public_api_404_falls_back_to_the_widget(self):
        widget_html = """
        <section class="openings-section">
          <h3 class="opening-title">Berlin, Germany</h3>
          <ul><li class="opening-job">
            <a href="https://jobs.smartrecruiters.com/Example/123-backend-engineer">
              <h4 class="details-title">Backend Engineer</h4>
            </a>
          </li></ul>
        </section>
        """

        def handler(url, **_kwargs):
            if url.endswith("/postings"):
                return FakeResponse(status_code=404)
            if url.endswith("/api/groups"):
                if _kwargs["params"]["page"] == 1:
                    return FakeResponse(text=widget_html)
                return FakeResponse(text="<html></html>")
            raise AssertionError(f"Unexpected request: {url}")

        scraper = SmartRecruitarsScraper(delay=0)
        scraper.session = FakeSession(handler)
        jobs = scraper.scrape_jobs("https://careers.smartrecruiters.com/Example", "Example")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["Job Title"], "Backend Engineer")
        self.assertEqual(jobs[0]["Job Link"], "https://jobs.smartrecruiters.com/Example/123-backend-engineer")

    def test_empty_public_api_content_falls_back_to_the_widget(self):
        widget_html = """
        <section class="openings-section">
          <h3 class="opening-title">Berlin, Germany</h3>
          <ul><li class="opening-job">
            <a href="https://jobs.smartrecruiters.com/Example/123-backend-engineer">
              <h4 class="details-title">Backend Engineer</h4>
            </a>
          </li></ul>
        </section>
        """

        def handler(url, **kwargs):
            if url.endswith("/postings"):
                return FakeResponse({"totalFound": 0, "content": []})
            if url.endswith("/api/groups"):
                if kwargs["params"]["page"] == 1:
                    return FakeResponse(text=widget_html)
                return FakeResponse(text="<html></html>")
            raise AssertionError(f"Unexpected request: {url}")

        scraper = SmartRecruitarsScraper(delay=0)
        scraper.session = FakeSession(handler)
        jobs = scraper.scrape_jobs("https://careers.smartrecruiters.com/Example", "Example")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["Job Link"], "https://jobs.smartrecruiters.com/Example/123-backend-engineer")


if __name__ == "__main__":
    unittest.main()

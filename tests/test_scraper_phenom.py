import json
import unittest

from daily_jobs.scrapers.done.phenom_scraper import PhenomScraper, extract_phapp_ddo


class FakeResponse:
    def __init__(self, payload=None, *, text="", status_code=200):
        self.payload = payload
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


def ddo_html(ddo):
    return f'<html><script>window.phApp = window.phApp || {{}}; phApp.ddo = {json.dumps(ddo)};</script></html>'


def listing_ddo(postings, total):
    return {
        "siteConfig": {"data": {"urlMap": {"job": "job/:jobId/:title"}}},
        "eagerLoadRefineSearch": {
            "hits": len(postings),
            "totalHits": total,
            "data": {"jobs": postings},
        },
    }


class PhenomScraperTests(unittest.TestCase):
    def test_extracts_eager_load_ddo_from_a_trimmed_fixture(self):
        fixture = ddo_html(listing_ddo([{
            "title": "Backend Engineer",
            "cityStateCountry": "Berlin, Germany",
            "jobSeqNo": "ACME1",
        }], 1))

        result = extract_phapp_ddo(fixture)

        self.assertEqual(result["eagerLoadRefineSearch"]["totalHits"], 1)
        self.assertEqual(
            result["eagerLoadRefineSearch"]["data"]["jobs"][0]["cityStateCountry"],
            "Berlin, Germany",
        )

    def test_search_paginates_filters_by_berlin_and_reads_detail_ddo(self):
        berlin = {
            "title": "Backend Engineer",
            "cityStateCountry": "Berlin, Germany",
            "location": "Berlin Office",
            "jobSeqNo": "ACME1",
            "jobId": "R1",
            "postedDate": "2026-10-20",
            "type": "Full time",
            "category": "Engineering",
            "descriptionTeaser": "Short listing.",
        }
        non_berlin = {
            "title": "Backend Engineer",
            "cityStateCountry": "Munich, Germany",
            "location": "Munich",
            "jobSeqNo": "ACME2",
            "postedDate": "2026-10-19",
        }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **_kwargs):
                self.calls.append(url)
                if "search-results?keywords=Berlin&from=0" in url:
                    return FakeResponse(text=ddo_html(listing_ddo([berlin], 2)))
                if "search-results?keywords=Berlin&from=1" in url:
                    return FakeResponse(text=ddo_html(listing_ddo([non_berlin], 2)))
                if url.endswith("/job/ACME1/backend-engineer"):
                    return FakeResponse(text=ddo_html({
                        "jobDetail": {
                            "data": {
                                "job": {
                                    **berlin,
                                    "description": "<p>Build resilient APIs.</p>",
                                },
                            },
                        },
                    }))
                raise AssertionError(f"Unexpected request: {url}")

        scraper = PhenomScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://careers.example.com/global/en/search-results?location=Berlin",
            "Example",
            label="phenom",
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["Location"], "Berlin, Germany / Berlin Office")
        self.assertEqual(jobs[0]["Job Description"], "Build resilient APIs.")
        self.assertEqual(jobs[0]["Posted Date"], "2026-10-20")
        self.assertEqual(
            jobs[0]["Job Link"],
            "https://careers.example.com/global/en/job/ACME1/backend-engineer",
        )
        self.assertEqual(len(scraper.session.calls), 3)


if __name__ == "__main__":
    unittest.main()

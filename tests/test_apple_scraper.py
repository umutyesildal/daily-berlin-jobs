import unittest

from daily_jobs.scrapers.done.apple_scraper import (
    AppleScraper,
    apple_search_payload,
    parse_apple_search_job,
)


class FakeResponse:
    def __init__(self, payload=None, *, headers=None, status_code=200):
        self.payload = payload
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class AppleScraperTests(unittest.TestCase):
    def test_location_filter_uses_apple_berlin_post_location_id(self):
        payload = apple_search_payload(2, "en-us")
        self.assertEqual(payload["filters"]["locations"], ["postLocation-BRL"])
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["locale"], "en-us")

    def test_search_parser_distinguishes_berlin_from_country_level_locations(self):
        berlin = parse_apple_search_job({
            "positionId": "200685888",
            "postingTitle": "Senior iOS Engineer",
            "locations": [{
                "postLocationId": "postLocation-BRL",
                "name": "Berlin",
                "countryName": "Germany",
            }],
        })
        germany = parse_apple_search_job({
            "positionId": "114438043",
            "postingTitle": "DE - Specialist",
            "locations": [{
                "postLocationId": "postLocation-DEU",
                "name": "Germany",
                "countryName": "Germany",
            }],
        })

        self.assertTrue(berlin["berlin"])
        self.assertEqual(berlin["location"], "Berlin, Germany")
        self.assertFalse(germany["berlin"])

    def test_fetches_csrf_paginates_filters_and_loads_berlin_details(self):
        berlin_one = {
            "positionId": "200685888",
            "postingTitle": "Senior iOS Engineer",
            "locations": [{
                "postLocationId": "postLocation-BRL",
                "name": "Berlin",
                "countryName": "Germany",
            }],
        }
        germany = {
            "positionId": "114438043",
            "postingTitle": "DE - Specialist",
            "locations": [{
                "postLocationId": "postLocation-DEU",
                "name": "Germany",
                "countryName": "Germany",
            }],
        }
        berlin_two = {
            "positionId": "200690883",
            "postingTitle": "Backend Engineer",
            "locations": [{
                "postLocationId": "postLocation-BRL",
                "name": "Berlin",
                "countryName": "Germany",
            }],
        }
        details = {
            "200685888": {
                "id": "PIPE-200685888",
                "postingTitle": "Senior iOS Engineer",
                "transformedPostingTitle": "senior-ios-engineer",
                "description": "Build mobile applications.",
                "postDateInGMT": "2026-10-20T10:00:00Z",
                "teamNames": ["Software Engineering"],
                "locations": [{
                    "id": "postLocation-BRL",
                    "name": "Berlin",
                    "countryName": "Germany",
                }],
            },
            "200690883": {
                "id": "PIPE-200690883",
                "postingTitle": "Backend Engineer",
                "transformedPostingTitle": "backend-engineer",
                "description": "Build backend services.",
                "postingDateMeta": "2026-10-21",
                "teamNames": ["Software Engineering"],
                "locations": [{
                    "id": "postLocation-BRL",
                    "name": "Berlin",
                    "countryName": "Germany",
                }],
            },
        }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.get_urls = []
                self.post_payloads = []

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                if url.endswith("/CSRFToken"):
                    return FakeResponse(headers={"x-apple-csrf-token": "test-csrf"})
                job_id = url.rsplit("/", 1)[-1]
                return FakeResponse({"res": details[job_id]})

            def post(self, url, *, json, **_kwargs):
                self.post_payloads.append(json)
                if json["page"] == 1:
                    rows = [berlin_one, germany]
                else:
                    rows = [berlin_two]
                return FakeResponse({"res": {"searchResults": rows, "totalRecords": 21}})

        scraper = AppleScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs("https://jobs.apple.com/en-us/search?location=berlin-BER")

        self.assertEqual([job["Job Title"] for job in jobs], ["Senior iOS Engineer", "Backend Engineer"])
        self.assertEqual(jobs[0]["Location"], "Berlin, Germany")
        self.assertEqual(jobs[0]["Job Description"], "Build mobile applications.")
        self.assertEqual(jobs[0]["Posted Date"], "2026-10-20")
        self.assertEqual(
            jobs[0]["Job Link"],
            "https://jobs.apple.com/en-us/details/200685888/senior-ios-engineer",
        )
        self.assertEqual(len(scraper.session.post_payloads), 2)
        self.assertEqual(
            scraper.session.post_payloads[0]["filters"]["locations"],
            ["postLocation-BRL"],
        )
        self.assertEqual(len(scraper.session.get_urls), 3)
        self.assertEqual(scraper.session.headers["x-apple-csrf-token"], "test-csrf")
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })


if __name__ == "__main__":
    unittest.main()

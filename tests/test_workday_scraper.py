import unittest

from daily_jobs.scrapers.done.workday_scraper import WorkdayScraper, parse_workday_url


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class WorkdayUrlTests(unittest.TestCase):
    def test_parses_workday_jobs_and_locale_paths_and_ignores_queries(self):
        nvidia = parse_workday_url(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite?source=share"
        )
        self.assertEqual(
            (nvidia.host, nvidia.tenant, nvidia.site),
            ("nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"),
        )

        expedia = parse_workday_url("https://expedia.wd108.myworkdayjobs.com/en-US/search")
        self.assertEqual((expedia.tenant, expedia.site), ("expedia", "search"))

        snap = parse_workday_url(
            "https://wd1.myworkdaysite.com/en-US/recruiting/snapchat/snap?source=search"
        )
        self.assertEqual((snap.host, snap.tenant, snap.site), ("wd1.myworkdaysite.com", "snapchat", "snap"))
        self.assertEqual(snap.public_prefix, "/recruiting/snapchat/snap")


class WorkdayScraperTests(unittest.TestCase):
    def test_paginates_fetches_berlin_details_and_filters_non_berlin_jobs(self):
        berlin = {
            "title": "Backend Engineer",
            "locationsText": "Berlin, Germany",
            "externalPath": "/job/Berlin/Backend-Engineer_R1",
            "postedOn": "Posted 2 Days Ago",
        }
        multi_location = {
            "title": "Platform Engineer",
            "locationsText": "2 Locations",
            "externalPath": "/job/Poland-Warsaw/Platform-Engineer_R2",
            "postedOn": "Posted 4 Days Ago",
        }
        munich = {
            "title": "Data Engineer",
            "locationsText": "Munich, Germany",
            "externalPath": "/job/Munich/Data-Engineer_R3",
        }

        class FakeSession:
            def __init__(self):
                self.posts = []
                self.gets = []

            def post(self, url, **kwargs):
                self.posts.append((url, kwargs))
                offset = kwargs["json"]["offset"]
                if offset == 0:
                    return FakeResponse({"total": 3, "jobPostings": [berlin, multi_location]})
                return FakeResponse({"total": 3, "jobPostings": [munich]})

            def get(self, url, **_kwargs):
                self.gets.append(url)
                if url.endswith("/job/Berlin/Backend-Engineer_R1"):
                    return FakeResponse({"jobPostingInfo": {
                        "title": "Backend Engineer",
                        "location": "Berlin, Germany",
                        "jobDescription": "<p>Build APIs.</p>",
                        "startDate": "2026-10-20",
                        "timeType": "Full time",
                        "jobFamily": "Engineering",
                    }})
                if url.endswith("/job/Poland-Warsaw/Platform-Engineer_R2"):
                    return FakeResponse({"jobPostingInfo": {
                        "title": "Platform Engineer",
                        "location": "Poland, Warsaw",
                        "additionalLocations": ["Germany, Berlin"],
                        "jobDescription": "<p>Build platforms.</p>",
                        "startDate": "2026-10-19",
                        "timeType": "Full time",
                    }})
                raise AssertionError(f"Unexpected detail request: {url}")

        scraper = WorkdayScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite?source=share",
            "NVIDIA",
        )

        self.assertEqual([job["Job Title"] for job in jobs], ["Backend Engineer", "Platform Engineer"])
        self.assertEqual(jobs[0]["Location"], "Berlin, Germany")
        self.assertEqual(jobs[1]["Location"], "Poland, Warsaw / Germany, Berlin")
        self.assertEqual(jobs[0]["Job Description"], "Build APIs.")
        self.assertEqual(jobs[0]["Posted Date"], "2026-10-20")
        self.assertEqual(
            jobs[0]["Job Link"],
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Berlin/Backend-Engineer_R1",
        )
        self.assertEqual(len(scraper.session.posts), 2)
        self.assertEqual([call[1]["json"]["offset"] for call in scraper.session.posts], [0, 2])
        self.assertEqual(
            [call[1]["json"] for call in scraper.session.posts],
            [
                {"limit": 20, "offset": 0, "searchText": "Berlin", "appliedFacets": {}},
                {"limit": 20, "offset": 2, "searchText": "Berlin", "appliedFacets": {}},
            ],
        )
        self.assertEqual(len(scraper.session.gets), 2)
        self.assertEqual(set(jobs[0]), {
            "Company Name", "Job Title", "Location", "Job Link", "Job Description",
            "Employment Type", "Department", "Posted Date", "Company Description",
            "Remote", "Label", "ATS",
        })

    def test_403_returns_no_jobs(self):
        class FakeSession:
            def post(self, *_args, **_kwargs):
                return FakeResponse(status_code=403)

        scraper = WorkdayScraper(delay=0)
        scraper.session = FakeSession()

        self.assertEqual(
            scraper.scrape_jobs("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", "NVIDIA"),
            [],
        )

    def test_myworkdaysite_uses_the_public_external_url(self):
        class FakeSession:
            def post(self, *_args, **_kwargs):
                return FakeResponse({
                    "total": 1,
                    "jobPostings": [{
                        "title": "Backend Engineer",
                        "locationsText": "Berlin, Germany",
                        "externalPath": "/job/Berlin/Backend_R1",
                    }],
                })

            def get(self, *_args, **_kwargs):
                return FakeResponse({"jobPostingInfo": {
                    "title": "Backend Engineer",
                    "location": "Berlin, Germany",
                    "externalPath": "/job/Berlin/Backend_R1",
                    "externalUrl": "https://wd1.myworkdaysite.com/recruiting/snapchat/snap/job/Berlin/Backend_R1",
                    "jobDescription": "<p>Build services.</p>",
                }})

        scraper = WorkdayScraper(delay=0)
        scraper.session = FakeSession()
        jobs = scraper.scrape_jobs(
            "https://wd1.myworkdaysite.com/recruiting/snapchat/snap?source=board",
            "Snap Inc.",
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            jobs[0]["Job Link"],
            "https://wd1.myworkdaysite.com/recruiting/snapchat/snap/job/Berlin/Backend_R1",
        )


if __name__ == "__main__":
    unittest.main()

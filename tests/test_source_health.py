import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from daily_jobs.client import JobCrawlerController
from daily_jobs.source_health import next_source_health


class SourceHealthTransitionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)

    def test_ok_resets_error_and_empty_streaks(self):
        previous = {
            "consecutive_errors": 6,
            "consecutive_empty": 4,
            "last_success_at": self.now - timedelta(days=2),
        }

        state, reason = next_source_health(
            previous,
            {"status": "ok", "job_count": 2, "berlin_engineering_count": 1},
            self.now,
        )

        self.assertEqual(state["consecutive_errors"], 0)
        self.assertEqual(state["consecutive_empty"], 0)
        self.assertEqual(state["last_success_at"], self.now)
        self.assertIsNone(reason)

    def test_empty_never_disables_even_after_a_large_error_streak(self):
        previous = {
            "consecutive_errors": 100,
            "consecutive_empty": 99,
            "last_success_at": self.now - timedelta(days=1),
        }

        state, reason = next_source_health(
            previous,
            {"status": "empty", "job_count": 0, "berlin_engineering_count": 0},
            self.now,
        )

        self.assertEqual(state["consecutive_errors"], 0)
        self.assertEqual(state["consecutive_empty"], 100)
        self.assertEqual(state["last_success_at"], previous["last_success_at"])
        self.assertIsNone(state["disabled_at"])
        self.assertIsNone(reason)

    def test_seven_consecutive_404_errors_disable_with_reason(self):
        state = None
        reason = None
        for offset in range(7):
            state, reason = next_source_health(
                state,
                {"status": "error", "status_code": 404, "error": "Not found"},
                self.now + timedelta(seconds=offset),
            )

        self.assertEqual(state["consecutive_errors"], 7)
        self.assertEqual(reason, "auto: 7 consecutive errors (HTTP 404)")
        self.assertEqual(state["disabled_reason"], reason)

    def test_six_consecutive_404_errors_do_not_disable(self):
        state = None
        for offset in range(6):
            state, reason = next_source_health(
                state,
                {"status": "error", "status_code": 404},
                self.now + timedelta(seconds=offset),
            )

        self.assertEqual(state["consecutive_errors"], 6)
        self.assertIsNone(reason)
        self.assertIsNone(state["disabled_at"])

    def test_twenty_one_errors_disable_for_any_status_code(self):
        state = None
        for offset in range(21):
            state, reason = next_source_health(
                state,
                {"status": "error", "status_code": 500},
                self.now + timedelta(seconds=offset),
            )

        self.assertEqual(state["consecutive_errors"], 21)
        self.assertEqual(reason, "auto: 21 consecutive errors (HTTP 500)")

    def test_error_threshold_without_status_code_has_no_http_suffix(self):
        state = None
        for offset in range(21):
            state, reason = next_source_health(
                state,
                {"status": "error"},
                self.now + timedelta(seconds=offset),
            )

        self.assertEqual(reason, "auto: 21 consecutive errors")


class SourceHealthControllerTests(unittest.TestCase):
    def _controller(self, scraper):
        controller = JobCrawlerController(delay=0, output_dir=tempfile.mkdtemp(), max_workers=1)
        controller.compare_and_backup = lambda: None
        controller._load_existing_jobs_by_company = lambda: {}
        controller._load_existing_jobs = lambda: set()
        controller.save_jobs = lambda _jobs: None
        controller.get_timing_trends = lambda: {}
        controller.save_timing_history = lambda: None
        controller.generate_comparison_report = lambda: None
        controller._resolve_scraper_class = lambda _label: scraper
        return controller

    def test_stubbed_scraper_records_source_health_classification(self):
        class StubScraper:
            def scrape_jobs(self, **_kwargs):
                return [
                    {"Job Title": "Backend Engineer", "Location": "Berlin, Germany"},
                    {"Job Title": "Product Manager", "Location": "Berlin, Germany"},
                    {"Job Title": "Backend Engineer", "Location": "Munich, Germany"},
                ]

        controller = self._controller(StubScraper)
        jobs = controller.process_companies(pd.DataFrame([{
            "Source ID": 42,
            "Name": "Example",
            "Career Page": "https://example.com/careers",
            "Description": "",
            "Label": "greenhouse",
        }]))

        self.assertEqual(len(jobs), 3)
        self.assertEqual(controller.source_health_results, [{
            "source_id": 42,
            "status": "ok",
            "job_count": 3,
            "berlin_engineering_count": 1,
            "error": None,
            "status_code": None,
        }])

    def test_successful_empty_scrape_is_empty_not_error(self):
        class StubScraper:
            def scrape_jobs(self, **_kwargs):
                return []

        controller = self._controller(StubScraper)
        controller.process_companies(pd.DataFrame([{
            "Source ID": 43,
            "Name": "Example",
            "Career Page": "https://example.com/careers",
            "Description": "",
            "Label": "greenhouse",
        }]))

        self.assertEqual(controller.source_health_results[0]["status"], "empty")

    def test_rows_without_source_id_are_not_recorded(self):
        class StubScraper:
            def scrape_jobs(self, **_kwargs):
                return []

        controller = self._controller(StubScraper)
        controller.process_companies(pd.DataFrame([{
            "Name": "Example",
            "Career Page": "https://example.com/careers",
            "Description": "",
            "Label": "greenhouse",
        }]))

        self.assertEqual(controller.source_health_results, [])

    def test_http_scrape_error_records_error_status_and_code(self):
        class StubScraper:
            def scrape_jobs(self, **_kwargs):
                response = requests.Response()
                response.status_code = 404
                raise requests.HTTPError("Not found", response=response)

        controller = self._controller(StubScraper)
        controller.process_companies(pd.DataFrame([{
            "Source ID": 44,
            "Name": "Example",
            "Career Page": "https://example.com/careers",
            "Description": "",
            "Label": "greenhouse",
        }]))

        result = controller.source_health_results[0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["status_code"], 404)
        self.assertLessEqual(len(result["error"]), 300)

    def test_source_health_errors_redact_urls_and_secrets(self):
        class StubScraper:
            def scrape_jobs(self, **_kwargs):
                raise RuntimeError("request failed https://example.com/?token=private-value")

        controller = self._controller(StubScraper)
        controller.process_companies(pd.DataFrame([{
            "Source ID": 45,
            "Name": "Example",
            "Career Page": "https://example.com/careers",
            "Description": "",
            "Label": "greenhouse",
        }]))

        error = controller.source_health_results[0]["error"]
        self.assertNotIn("https://", error)
        self.assertNotIn("private-value", error)


if __name__ == "__main__":
    unittest.main()

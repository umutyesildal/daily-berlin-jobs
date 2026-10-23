import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


from daily_jobs.post_process_jobs import (
    classify_jobs,
    filter_published_jobs,
    filter_recent_published_jobs,
    find_daily_new_jobs,
    merge_published_jobs,
)


class DailyNewJobsTests(unittest.TestCase):
    def _find_new(self, previous_rows, current_rows):
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_path = Path(temp_dir) / "previous.csv"
            pd.DataFrame(previous_rows).to_csv(previous_path, index=False)
            return find_daily_new_jobs(pd.DataFrame(current_rows), previous_path)

    def test_changed_url_does_not_make_existing_role_new(self):
        previous = [{
            "Company Name": "München Labs",
            "Job Title": "Junior Software Engineer (m/f/d)",
            "Location": "Berlin, Germany",
            "Job Link": "https://example.com/old",
        }]
        current = [{
            "Company Name": "Munchen Labs",
            "Job Title": "Junior Software Engineer - m/f/d",
            "Location": "Berlin Germany",
            "Job Link": "https://example.com/new",
        }]

        self.assertTrue(self._find_new(previous, current).empty)

    def test_same_title_in_different_location_is_new(self):
        previous = [{
            "Company Name": "Example",
            "Job Title": "Software Engineer",
            "Location": "Munich",
            "Job Link": "https://example.com/old",
        }]
        current = [{
            "Company Name": "Example",
            "Job Title": "Software Engineer",
            "Location": "Berlin",
            "Job Link": "https://example.com/new",
        }]

        self.assertEqual(len(self._find_new(previous, current)), 1)

    def test_real_new_role_is_kept_once(self):
        previous = [{
            "Company Name": "Example",
            "Job Title": "Data Engineer",
            "Location": "Berlin",
            "Job Link": "https://example.com/old",
        }]
        current = [
            {
                "Company Name": "Example",
                "Job Title": "Backend Engineer",
                "Location": "Berlin",
                "Job Link": "https://example.com/new-1",
            },
            {
                "Company Name": "Example",
                "Job Title": "Backend Engineer",
                "Location": "Berlin",
                "Job Link": "https://example.com/new-2",
            },
        ]

        result = self._find_new(previous, current)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Job Link"], "https://example.com/new-1")


class PublishedJobsTests(unittest.TestCase):
    def test_all_jobs_keeps_valid_historical_software_roles(self):
        rows = [{
            "Company Name": "Example",
            "Job Title": "Senior Software Engineer",
            "Location": "Berlin",
            "Job Link": "https://example.com/software",
            "Posted Date": "2026-03-10",
        }, {
            "Company Name": "Example",
            "Job Title": "Partnerships Manager",
            "Location": "Berlin",
            "Job Link": "https://example.com/partnerships",
            "Posted Date": "2026-07-10",
        }]

        result = filter_published_jobs(pd.DataFrame(rows))

        self.assertEqual(result["Job Link"].tolist(), ["https://example.com/software"])

    def test_every_incoming_job_is_classified_before_publishing(self):
        rows = [{
            "Company Name": "Example",
            "Job Title": "Junior Backend Engineer",
            "Location": "Berlin, Germany",
            "Job Description": "Python and Docker",
            "Remote": "Yes",
        }]

        result = classify_jobs(pd.DataFrame(rows))

        self.assertEqual(result.iloc[0]["Role"], "Backend")
        self.assertEqual(result.iloc[0]["Level"], "Junior / Entry")
        self.assertEqual(result.iloc[0]["Work Mode"], "Remote")
        self.assertEqual(result.iloc[0]["Tech Stack"], "Python, Docker")
        self.assertEqual(result.iloc[0]["Classification Version"], "engineering-v2")

    def test_public_collection_stays_engineering_only(self):
        rows = [{
            "Company Name": "Example",
            "Job Title": "Technical Product Manager",
            "Location": "Berlin",
            "Job Link": "https://example.com/product",
        }, {
            "Company Name": "Example",
            "Job Title": "Engineering Manager",
            "Location": "Berlin",
            "Job Link": "https://example.com/engineering",
        }]

        result = filter_published_jobs(pd.DataFrame(rows))

        self.assertEqual(result["Job Link"].tolist(), ["https://example.com/engineering"])
        self.assertEqual(result.iloc[0]["Role"], "Engineering Leadership")

    def test_public_collection_includes_embedded_but_not_physical_engineering(self):
        rows = [{
            "Company Name": "Robotics Co",
            "Job Title": "Embedded Firmware Engineer",
            "Location": "Berlin",
            "Job Link": "https://example.com/embedded",
        }, {
            "Company Name": "Factory Co",
            "Job Title": "Manufacturing Engineer",
            "Location": "Berlin",
            "Job Link": "https://example.com/manufacturing",
        }]

        result = filter_published_jobs(pd.DataFrame(rows))

        self.assertEqual(result["Job Link"].tolist(), ["https://example.com/embedded"])
        self.assertEqual(result.iloc[0]["Role"], "Embedded / Firmware / Robotics")

    def test_new_today_only_includes_today_and_yesterday_with_dates(self):
        rows = [{"Posted Date": "2026-07-10", "Job Title": "Today"},
                {"Posted Date": "July 9, 2026", "Job Title": "Yesterday"},
                {"Posted Date": "2026-03-10", "Job Title": "Old"},
                {"Posted Date": "", "Job Title": "Unknown"}]

        result = filter_recent_published_jobs(pd.DataFrame(rows), today=date(2026, 7, 10))

        self.assertEqual(result["Job Title"].tolist(), ["Today", "Yesterday"])

    def test_all_jobs_preserves_previous_jobs_and_adds_current_jobs(self):
        previous = pd.DataFrame([{
            "Company Name": "Previous Co", "Job Title": "Software Engineer", "Location": "Berlin",
            "Job Link": "https://example.com/previous", "Posted Date": "2026-06-01",
        }])
        current = pd.DataFrame([{
            "Company Name": "Current Co", "Job Title": "Backend Developer", "Location": "Berlin",
            "Job Link": "https://example.com/current", "Posted Date": "2026-07-10",
        }])

        result = merge_published_jobs(current, previous)

        self.assertEqual(set(result["Job Link"]), {
            "https://example.com/previous", "https://example.com/current",
        })


if __name__ == "__main__":
    unittest.main()

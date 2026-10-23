import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from daily_jobs.postgres_storage import _posted_date, canonicalize_url, job_keys, linkedin_duplicate_ids


class PostgresIdentityTests(unittest.TestCase):
    def test_tracking_parameters_and_fragments_do_not_change_url(self):
        first = canonicalize_url("https://EXAMPLE.com/jobs/42/?utm_source=x&lang=en#apply")
        second = canonicalize_url("https://example.com/jobs/42?lang=en")
        self.assertEqual(first, second)

    def test_changed_url_does_not_change_semantic_identity(self):
        base = {
            "Company Name": "München Labs",
            "Job Title": "Junior Software Engineer (m/f/d)",
            "Location": "Berlin, Germany",
        }
        changed = {
            "Company Name": "Munchen Labs",
            "Job Title": "Junior Software Engineer - m/f/d",
            "Location": "Berlin Germany",
        }
        first_identity, first_url, _ = job_keys({**base, "Job Link": "https://example.com/old"})
        second_identity, second_url, _ = job_keys({**changed, "Job Link": "https://example.com/new"})
        self.assertEqual(first_identity, second_identity)
        self.assertNotEqual(first_url, second_url)

    def test_location_is_part_of_identity(self):
        berlin, _, _ = job_keys({
            "Company Name": "Example", "Job Title": "Engineer", "Location": "Berlin"
        })
        munich, _, _ = job_keys({
            "Company Name": "Example", "Job Title": "Engineer", "Location": "Munich"
        })
        self.assertNotEqual(berlin, munich)

    def test_relative_posted_date_is_normalized(self):
        self.assertEqual(
            _posted_date("0 hours ago"),
            datetime.now(ZoneInfo("Europe/Berlin")).date(),
        )


class LinkedInAtsDedupeTests(unittest.TestCase):
    def test_only_linkedin_rows_with_retained_ats_twins_are_deleted(self):
        rows = [
            (1, "Example GmbH", "Backend Engineer (m/w/d)", "greenhouse"),
            (2, "Example", "Backend Engineer", "LinkedIn"),
            (3, "Example", "Data Engineer", "LinkedIn"),
            (4, "Different Company", "Backend Engineer", "LinkedIn"),
            (5, "Doctolib SE", "Fullstack Engineer", "ashby"),
            (6, "Doctolib", "Fullstack Engineer", "LinkedIn"),
        ]

        self.assertEqual(linkedin_duplicate_ids(rows), [2, 6])


if __name__ == "__main__":
    unittest.main()

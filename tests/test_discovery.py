import unittest
from unittest.mock import Mock, patch

from daily_jobs.discovery import (
    career_page,
    extract_boards,
    is_demo_or_test_slug,
    name_similarity,
    norm_name,
    title_overlap,
)
from daily_jobs.discovery.engine import DiscoveryRunner, DiscoveryStore, verify_website


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.connection.query = query
        self.connection.params = params


class RecordingConnection:
    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


class DiscoveryStoreTests(unittest.TestCase):
    def test_save_board_uses_record_name_when_company_name_is_absent(self):
        connection = RecordingConnection()
        store = DiscoveryStore(connection)

        store.save_board({
            "ats": "ashby",
            "slug": "acme",
            "region": "",
            "career_page": "https://jobs.ashbyhq.com/acme",
            "status": "accepted",
            "name": "Acme Labs",
            "llm": None,
        })

        self.assertEqual(connection.params[7], "Acme Labs")


class DiscoveryRecoveryTests(unittest.TestCase):
    def test_recently_auto_disabled_company_is_prioritized_with_empty_titles(self):
        class InputCursor:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, query, _params=()):
                if "FROM jobs" in query:
                    self.rows = []
                elif "SELECT career_page FROM career_sources" in query:
                    self.rows = []
                elif "source_health" in query:
                    self.rows = [("Recovered Company",)]
                else:
                    raise AssertionError(query)

            def fetchall(self):
                return self.rows

        class InputConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return InputCursor()

        class Storage:
            def connect(self):
                return InputConnection()

        class InlinePool:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def map(self, function, values):
                return list(map(function, values))

        runner = DiscoveryRunner(
            Storage(),
            None,
            budget_discovery=10,
            budget_resolve=10,
            dry_run=True,
        )
        linkedin_titles, _existing_boards = runner.load_inputs()
        linkedin_titles["Regular Company"] = ["Backend Engineer"]
        queries = []

        def tavily(query, *_args, **_kwargs):
            queries.append(query)
            return {"results": []}

        runner.tavily = tavily
        with patch("daily_jobs.discovery.engine.ThreadPoolExecutor", InlinePool):
            runner.stage_resolve(linkedin_titles, set())

        self.assertEqual(linkedin_titles["Recovered Company"], [])
        self.assertEqual(queries[0], '"Recovered Company" jobs Berlin')
        self.assertEqual(queries[2], '"Regular Company" jobs Berlin')


class BoardExtractionTests(unittest.TestCase):
    def test_ashby_slug_supports_dots_and_percent_encoded_spaces(self):
        found = extract_boards(
            "https://jobs.ashbyhq.com/finmid.com "
            "https://jobs.ashbyhq.com/Acme%20Labs"
        )

        self.assertEqual(found, {
            ("ashby", "finmid.com", ""),
            ("ashby", "acme labs", ""),
        })

    def test_greenhouse_embed_and_eu_job_board_urls(self):
        found = extract_boards(
            "https://boards.greenhouse.io/embed/job_board?for=example "
            "https://job-boards.eu.greenhouse.io/eu-example/jobs/1"
        )

        self.assertEqual(found, {
            ("greenhouse", "example", ""),
            ("greenhouse", "eu-example", ""),
        })

    def test_lever_region_is_preserved(self):
        self.assertEqual(
            extract_boards("https://jobs.eu.lever.co/Example"),
            {("lever", "example", "eu")},
        )

    def test_personio_regions_are_preserved(self):
        self.assertEqual(
            extract_boards("https://company.jobs.personio.de https://other.jobs.personio.com"),
            {("personio", "company", "de"), ("personio", "other", "com")},
        )

    def test_recruitee_workable_and_smartrecruiters(self):
        found = extract_boards(
            "https://acme.recruitee.com "
            "https://apply.workable.com/api/v1/widget/accounts/workable-account "
            "https://careers.smartrecruiters.com/SmartRecruitersCase"
        )

        self.assertEqual(found, {
            ("recruitee", "acme", ""),
            ("workable", "workable-account", ""),
            ("smartrecruiters", "SmartRecruitersCase", ""),
        })

    def test_bad_slugs_are_dropped(self):
        self.assertEqual(
            extract_boards(
                "https://jobs.ashbyhq.com/api "
                "https://boards.greenhouse.io/embed/job_board?for=api"
            ),
            set(),
        )

    def test_career_page_quotes_slug_spaces(self):
        self.assertEqual(
            career_page("ashby", "acme labs", ""),
            "https://jobs.ashbyhq.com/acme%20labs",
        )


class DiscoveryHeuristicTests(unittest.TestCase):
    def test_name_similarity_uses_the_one_off_normalization(self):
        self.assertEqual(norm_name("Doctolib SE"), "doctolib")
        self.assertEqual(name_similarity("Doctolib SE", "doctolib"), 1.0)
        self.assertLess(name_similarity("STARK", "SKD SE"), 0.8)

    def test_title_overlap_requires_three_exact_normalized_matches(self):
        self.assertFalse(title_overlap(["Backend Engineer", "Frontend Engineer"], [
            "Backend Engineer", "Frontend Engineer",
        ]))
        self.assertTrue(title_overlap([
            "Backend Engineer", "Frontend Engineer", "Data Engineer",
        ], [
            "Backend Engineer", "Frontend Engineer", "Data Engineer",
        ]))

    def test_demo_and_sandbox_filter(self):
        for slug in ("leverdemo-8", "acme-sandbox", "acme-test", "acme.staging"):
            with self.subTest(slug=slug):
                self.assertTrue(is_demo_or_test_slug(slug))
        self.assertFalse(is_demo_or_test_slug("contest-labs"))


class WebsiteVerificationTests(unittest.TestCase):
    def test_parked_marker_is_rejected(self):
        fetch = Mock(return_value=(200, "This domain is for sale.", "https://acme-labs.com"))

        self.assertIsNone(verify_website(
            "acme-labs.com",
            "Acme Labs",
            fetch_page=fetch,
        ))

    def test_redirect_to_different_registrable_domain_is_rejected(self):
        fetch = Mock(return_value=(200, "Welcome to Acme Labs", "https://other-company.org"))

        self.assertIsNone(verify_website(
            "acme-labs.com",
            "Acme Labs",
            fetch_page=fetch,
        ))

    def test_slug_guess_with_low_name_similarity_is_rejected_before_fetch(self):
        fetch = Mock()

        self.assertIsNone(verify_website(
            "example.com",
            "Acme Labs",
            "slug_guess",
            fetch_page=fetch,
        ))
        fetch.assert_not_called()

    def test_valid_homepage_with_company_name_is_accepted(self):
        fetch = Mock(return_value=(200, "<title>Acme Labs</title> Welcome to Acme Labs", "https://acme-labs.com"))

        self.assertEqual(
            verify_website("acme-labs.com", "Acme Labs", fetch_page=fetch),
            "https://acme-labs.com",
        )


if __name__ == "__main__":
    unittest.main()

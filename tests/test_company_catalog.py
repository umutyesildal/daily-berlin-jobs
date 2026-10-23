import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daily_jobs.company_catalog import (
    AtsCatalog,
    audit_companies,
    normalize_url,
    parse_issue_form,
    verify_suggestion,
)
from daily_jobs.data_controller import DataController


class CompanyCatalogTests(unittest.TestCase):
    def test_example_catalog_loads(self):
        path = Path(__file__).resolve().parents[1] / "catalog" / "companies.example.yaml"
        result = DataController().load_data_from_yaml(str(path))
        self.assertEqual(result.iloc[0]["Label"], "greenhouse")

    def test_duplicate_source_is_rejected(self):
        content = """companies:
  - {name: Example, career_page: https://example.com/jobs, ats: lever}
  - {name: example, career_page: https://example.com/jobs/, ats: lever}
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "companies.yaml"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate company source"):
                DataController().load_data_from_yaml(str(path))

    def test_unknown_ats_is_rejected(self):
        content = """companies:
  - {name: Example, career_page: https://example.com/jobs, ats: unknown-ats}
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "companies.yaml"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported ATS"):
                DataController().load_data_from_yaml(str(path))

    def test_ats_alias_normalizes_to_canonical_identifier(self):
        catalog = AtsCatalog.load(Path(__file__).resolve().parents[1] / "catalog" / "ats.yaml")
        self.assertEqual(catalog.resolve("Amazon Jobs"), "amazon")
        self.assertEqual(catalog.resolve("ashby-hq"), "ashby")
        self.assertEqual(catalog.resolve("Eightfold"), "paypal")

    def test_every_canonical_ats_has_a_scraper(self):
        from daily_jobs.client import JobCrawlerController

        catalog = AtsCatalog.load(Path(__file__).resolve().parents[1] / "catalog" / "ats.yaml")
        self.assertTrue(catalog.identifiers().issubset(JobCrawlerController.SCRAPER_MAP))

    def test_legacy_custom_labels_resolve_to_canonical_scrapers(self):
        from daily_jobs.client import JobCrawlerController

        controller = JobCrawlerController()
        for legacy, canonical in (
            ("custom-zalando", "zalando"),
            ("custom-frequenz", "frequenz"),
            ("custom-forto", "forto"),
            ("custom-google", "google"),
            ("api-apple", "apple"),
        ):
            self.assertIs(
                controller._resolve_scraper_class(legacy),
                controller.SCRAPER_MAP[canonical],
            )

    def test_url_normalization_removes_tracking_and_trailing_slash(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.com/jobs/?utm_source=test#open"),
            "https://example.com/jobs",
        )

    def test_audit_reports_duplicate_domains_and_career_urls(self):
        catalog = AtsCatalog.load(Path(__file__).resolve().parents[1] / "catalog" / "ats.yaml")
        rows = [
            {
                "name": "Example One",
                "website": "https://example.com",
                "career_page": "https://jobs.example.com/openings",
                "ats": "lever",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "name": "Example Two",
                "website": "https://www.example.com/about",
                "career_page": "https://jobs.example.com/openings/",
                "ats": "Lever",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        report = audit_companies(rows, catalog)
        codes = {
            finding.code
            for company in report.companies
            for finding in company.findings
        }
        self.assertIn("duplicate_company_domain", codes)
        self.assertIn("duplicate_career_url", codes)
        self.assertEqual(report.summary["failing"], 2)

    def test_audit_distinguishes_stale_and_disabled_sources(self):
        catalog = AtsCatalog.load(Path(__file__).resolve().parents[1] / "catalog" / "ats.yaml")
        now = datetime.now(timezone.utc)
        rows = [
            {
                "name": "Stale",
                "website": "https://stale.example",
                "career_page": "https://stale.example/jobs",
                "ats": "greenhouse",
                "verified_at": (now - timedelta(days=100)).isoformat(),
            },
            {
                "name": "Disabled",
                "website": "https://disabled.example",
                "career_page": "https://disabled.example/jobs",
                "ats": "lever",
                "active": False,
            },
        ]
        report = audit_companies(rows, catalog, now=now, stale_days=90)
        self.assertEqual([company.status for company in report.companies], ["stale", "disabled"])

    def test_issue_form_parses_and_verifies_supported_suggestion(self):
        body = """### Company name
Example GmbH

### Company website
https://example.com

### Careers page
https://jobs.example.com

### ATS platform
Greenhouse

### Berlin role evidence
https://jobs.example.com/berlin

### Notes
Engineering office in Berlin.
"""
        suggestion = parse_issue_form(body)
        catalog = AtsCatalog.load(Path(__file__).resolve().parents[1] / "catalog" / "ats.yaml")
        result = verify_suggestion(suggestion, [], catalog)
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.normalized["ats"], "greenhouse")

    def test_unknown_ats_needs_info_and_scraper(self):
        suggestion = {
            "name": "Example",
            "website": "https://example.com",
            "career_page": "https://example.com/jobs",
            "ats": "Unknown Platform",
            "berlin_evidence": "https://example.com/jobs/berlin",
        }
        catalog = AtsCatalog.load(Path(__file__).resolve().parents[1] / "catalog" / "ats.yaml")
        result = verify_suggestion(suggestion, [], catalog)
        self.assertEqual(result.status, "needs_info")
        self.assertTrue(result.needs_scraper)


if __name__ == "__main__":
    unittest.main()

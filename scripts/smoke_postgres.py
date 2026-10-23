#!/usr/bin/env python3
"""Destructive integration smoke test for a disposable local PostgreSQL DB."""

import os
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from daily_jobs.postgres_storage import PostgresJobStorage


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    host = urlsplit(database_url).hostname
    if host not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("Smoke test is destructive and only accepts a local disposable database")

    storage = PostgresJobStorage(retention_days=30)
    storage.migrate()
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s), to_regclass(%s)", (
            "public.discovery_search_cache",
            "public.discovered_boards",
        ))
        assert all(cursor.fetchone())
        cursor.execute(
            "TRUNCATE company_suggestion_events, company_suggestions, career_sources, companies, "
            "jobs, job_url_aliases, job_fingerprints, crawl_runs RESTART IDENTITY CASCADE"
        )

    today = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    common = {
        "Company Name": "München Labs",
        "Job Title": "Junior Software Engineer (m/f/d)",
        "Location": "Berlin, Germany",
        "Role": "Software Engineering",
        "Classification Version": "engineering-v2",
        "Posted Date": today,
    }
    rows = pd.DataFrame([
        {**common, "Job Link": "https://example.com/jobs/old?utm_source=test"},
        {
            **common,
            "Company Name": "Munchen Labs",
            "Job Title": "Junior Software Engineer - m/f/d",
            "Location": "Berlin Germany",
            "Job Link": "https://example.com/jobs/new#apply",
        },
        {
            "Company Name": "Old Co",
            "Job Title": "Backend Engineer",
            "Location": "Berlin",
            "Job Link": "https://example.com/jobs/expired",
            "Role": "Backend",
            "Classification Version": "engineering-v2",
            "Posted Date": "2020-01-01",
        },
    ])
    stats = storage.upsert_jobs(rows)
    assert (stats.inserted, stats.updated, stats.skipped) == (1, 1, 1), stats

    suggestion = {
        "name": "München Labs",
        "website": "https://example.com",
        "career_page": "https://example.com/careers",
        "ats": "greenhouse",
        "berlin_evidence": "https://example.com/jobs/berlin",
        "notes": "Disposable smoke-test suggestion",
    }
    storage.approve_company_suggestion(
        suggestion,
        source_issue=999001,
        source_url="https://github.com/example/repo/issues/999001",
        actor="smoke-test",
    )
    storage.disable_company_suggestion(
        suggestion,
        source_issue=999001,
        source_url="https://github.com/example/repo/issues/999001",
        actor="smoke-test",
    )
    company_source = pd.DataFrame([{
        "Name": "Discovery Smoke Company",
        "Website": "https://discovery-smoke.example",
        "Career Page": "https://jobs.ashbyhq.com/discovery-smoke",
        "Description": "Disposable discovery smoke-test source",
        "Label": "ashby",
        "Active": True,
    }])
    company_upsert = storage.upsert_companies(company_source, skip_existing_boards=True)
    assert company_upsert == (1, 0), company_upsert
    repeated_company_upsert = storage.upsert_companies(company_source, skip_existing_boards=True)
    assert repeated_company_upsert == (0, 1), repeated_company_upsert
    board_alias_source = company_source.copy()
    board_alias_source.loc[0, "Name"] = "Discovery Smoke Company Alias"
    board_alias_source.loc[0, "Career Page"] = (
        "https://api.ashbyhq.com/posting-api/job-board/discovery-smoke"
    )
    board_alias_upsert = storage.upsert_companies(board_alias_source, skip_existing_boards=True)
    assert board_alias_upsert == (0, 1), board_alias_upsert
    existing_company = pd.DataFrame([{
        "Name": "Acme Systems GmbH",
        "Website": "https://acme-systems.example",
        "Career Page": "https://jobs.ashbyhq.com/acme-systems",
        "Description": "Existing active source",
        "Label": "ashby",
        "Active": True,
    }])
    assert storage.upsert_companies(existing_company) == (1, 0)
    alternate_source = pd.DataFrame([{
        "Name": "Acme Systems",
        "Website": "https://new-acme-systems.example",
        "Career Page": "https://boards.greenhouse.io/acme-systems",
        "Description": "Incoming duplicate company",
        "Label": "greenhouse",
        "Active": True,
    }])
    company_name_skip = storage.upsert_companies(alternate_source, skip_existing_boards=True)
    assert company_name_skip == (0, 1), company_name_skip
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT active FROM companies WHERE name = %s", ("München Labs",))
        assert cursor.fetchone()[0] is False
        cursor.execute(
            "SELECT count(*) FROM career_sources WHERE career_page = %s",
            ("https://jobs.ashbyhq.com/discovery-smoke",),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT website FROM companies WHERE name = %s", ("Acme Systems GmbH",))
        assert cursor.fetchone()[0] == "https://acme-systems.example"
        cursor.execute(
            "SELECT count(*) FROM career_sources WHERE company_id = "
            "(SELECT id FROM companies WHERE name = %s)",
            ("Acme Systems GmbH",),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT count(*) FROM jobs")
        assert cursor.fetchone()[0] == 1, "Disabling a company must preserve historical jobs"
        cursor.execute(
            "SELECT array_agg(status ORDER BY id) FROM company_suggestion_events "
            "WHERE suggestion_id = (SELECT id FROM company_suggestions WHERE source_issue = 999001)"
        )
        assert cursor.fetchone()[0] == ["approved", "disabled"]

    alias_stats = storage.upsert_jobs(pd.DataFrame([{
        **common,
        "Job Title": "Software Engineer II",
        "Job Link": "https://example.com/jobs/old",
    }]))
    assert (alias_stats.inserted, alias_stats.updated) == (0, 1), alias_stats

    api_stats = storage.upsert_jobs(pd.DataFrame([
        {
            **common,
            "Company Name": "LinkedIn API Test",
            "Job Title": "LinkedIn API Test Role",
            "Job Link": "https://www.linkedin.com/jobs/view/123456",
            "Job Description": "This description must not be public.",
            "ATS": "LinkedIn",
        },
        {
            **common,
            "Company Name": "ATS API Test",
            "Job Title": "ATS API Test Role",
            "Job Link": "https://example.com/jobs/ats-api-test",
            "Job Description": "This ATS description is public.",
            "ATS": "greenhouse",
        },
    ]))
    assert api_stats.inserted == 2, api_stats
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SET ROLE daily_jobs_web")
        cursor.execute(
            "SELECT source_type, description FROM api_jobs WHERE title = %s",
            ("LinkedIn API Test Role",),
        )
        linkedin_source, linkedin_description = cursor.fetchone()
        assert linkedin_source == "linkedin"
        assert linkedin_description is None
        cursor.execute(
            "SELECT source_type, description FROM api_jobs WHERE title = %s",
            ("ATS API Test Role",),
        )
        ats_source, ats_description = cursor.fetchone()
        assert ats_source == "ats"
        assert ats_description == "This ATS description is public."
        cursor.execute("RESET ROLE")

    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM jobs")
        assert cursor.fetchone()[0] == 3
        cursor.execute("SELECT title FROM jobs WHERE title = %s", ("Software Engineer II",))
        assert cursor.fetchone()[0] == "Software Engineer II"
        cursor.execute("SELECT count(*) FROM job_fingerprints")
        assert cursor.fetchone()[0] == 4
        cursor.execute("SELECT count(*) FROM job_url_aliases")
        assert cursor.fetchone()[0] == 5
        cursor.execute(
            "UPDATE jobs SET posted_at = NULL, first_seen_at = now() - interval '31 days'"
        )

    retention_stats = storage.upsert_jobs(pd.DataFrame())
    assert retention_stats.deleted == 3, retention_stats
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM jobs")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM job_fingerprints")
        assert cursor.fetchone()[0] == 4
        cursor.execute(
            """
            INSERT INTO crawl_runs(id, started_at, finished_at, status, error)
            VALUES (%s, now() + interval '1 second', now() + interval '2 seconds', 'failed', %s)
            """,
            (uuid4(), "smoke-test error must not be exposed"),
        )
        cursor.execute(
            "SELECT finished_at, discovered_count, inserted_count, updated_count, deleted_count FROM crawl_status"
        )
        public_run = cursor.fetchone()
        cursor.execute(
            """
            SELECT finished_at, discovered_count, inserted_count, updated_count, deleted_count
            FROM crawl_runs WHERE status = 'succeeded' ORDER BY finished_at DESC LIMIT 1
            """
        )
        latest_success = cursor.fetchone()
        assert public_run == latest_success
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'crawl_status'
            """
        )
        crawl_status_columns = {row[0] for row in cursor.fetchall()}
        assert "error" not in crawl_status_columns
        cursor.execute("SET ROLE daily_jobs_web")
        cursor.execute("SELECT job_count FROM data_status")
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT finished_at, discovered_count, inserted_count, updated_count, deleted_count FROM crawl_status"
        )
        assert cursor.fetchone() == latest_success
        cursor.execute("RESET ROLE")

    replacement_rows = pd.DataFrame([
        {
            **common,
            "Company Name": "München Labs GmbH",
            "Job Title": "LinkedIn version of role",
            "Job Link": "https://www.linkedin.com/jobs/view/992200",
            "ATS": "LinkedIn",
        },
        {
            **common,
            "Company Name": "München Labs GmbH",
            "Job Title": "ATS version of role",
            "Job Link": "https://example.com/jobs/ats-version",
            "ATS": "greenhouse",
        },
        {
            **common,
            "Company Name": "Unrelated LinkedIn Company",
            "Job Title": "Unrelated LinkedIn role",
            "Job Link": "https://www.linkedin.com/jobs/view/992201",
            "ATS": "LinkedIn",
        },
    ])
    replacement_stats = storage.upsert_jobs(replacement_rows)
    assert replacement_stats.inserted == 3, replacement_stats
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT identity_key FROM jobs WHERE title = %s",
            ("LinkedIn version of role",),
        )
        linkedin_identity = cursor.fetchone()[0]
    deleted_linkedin = storage.delete_linkedin_jobs_for_companies(["Munchen Labs"])
    assert deleted_linkedin == 1, deleted_linkedin
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM jobs WHERE company_name = %s AND title = %s",
            ("München Labs GmbH", "ATS version of role"),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT count(*) FROM jobs WHERE company_name = %s",
            ("Unrelated LinkedIn Company",),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT count(*) FROM jobs WHERE source = 'LinkedIn'")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT count(*) FROM job_fingerprints WHERE identity_key = %s", (linkedin_identity,))
        assert cursor.fetchone()[0] == 1

    print(
        "PostgreSQL smoke: migrations, moderated company sync, historical-job preservation, "
        "semantic dedup, URL mutation, expiry skip, 30-day deletion, agent API views, "
        "company board skipping, and ATS-over-LinkedIn replacement passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

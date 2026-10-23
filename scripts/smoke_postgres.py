#!/usr/bin/env python3
"""Destructive integration smoke test for a disposable local PostgreSQL DB."""

import os
from datetime import datetime, timedelta
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
        cursor.execute("SELECT to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s)", (
            "public.discovery_search_cache",
            "public.discovered_boards",
            "public.source_health",
            "public.source_health_summary",
            "public.source_health_admin",
            "public.api_companies",
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

    expired_posted_date = (
        datetime.now(ZoneInfo("Europe/Berlin")).date() - timedelta(days=40)
    ).isoformat()
    replacement_rows = pd.DataFrame([
        {
            **common,
            "Company Name": "München Labs GmbH",
            "Job Title": "Backend Engineer (m/w/d)",
            "Job Link": "https://example.com/jobs/backend-ats",
            "ATS": "greenhouse",
        },
        {
            **common,
            "Company Name": "Munchen Labs",
            "Job Title": "Backend Engineer",
            "Job Link": "https://www.linkedin.com/jobs/view/992200",
            "ATS": "LinkedIn",
        },
        {
            **common,
            "Company Name": "München Labs",
            "Job Title": "Data Engineer",
            "Job Link": "https://www.linkedin.com/jobs/view/992201",
            "ATS": "LinkedIn",
        },
        {
            **common,
            "Company Name": "Acme Systems",
            "Job Title": "Senior QA Engineer",
            "Job Link": "https://example.com/jobs/expired-ats-twin",
            "Posted Date": expired_posted_date,
            "ATS": "greenhouse",
        },
        {
            **common,
            "Company Name": "Acme Systems",
            "Job Title": "Senior QA Engineer",
            "Job Link": "https://www.linkedin.com/jobs/view/992202",
            "ATS": "LinkedIn",
        },
    ])
    replacement_stats = storage.upsert_jobs(replacement_rows)
    assert replacement_stats.inserted == 4, replacement_stats
    assert replacement_stats.skipped == 1, replacement_stats
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT identity_key FROM jobs WHERE title = %s",
            ("Backend Engineer",),
        )
        linkedin_identity = cursor.fetchone()[0]
    deleted_linkedin = storage.delete_linkedin_duplicates_of_ats_jobs()
    assert deleted_linkedin == 1, deleted_linkedin
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM jobs WHERE company_name = %s AND title = %s AND source = %s",
            ("München Labs GmbH", "Backend Engineer (m/w/d)", "greenhouse"),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT count(*) FROM jobs WHERE company_name = %s AND title = %s AND source = 'LinkedIn'",
            ("München Labs", "Data Engineer"),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT count(*) FROM jobs WHERE company_name = %s AND title = %s AND source = 'LinkedIn'",
            ("Acme Systems", "Senior QA Engineer"),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT count(*) FROM jobs WHERE company_name = %s AND title = %s AND source = %s",
            ("Acme Systems", "Senior QA Engineer", "greenhouse"),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM job_fingerprints WHERE identity_key = %s", (linkedin_identity,))
        assert cursor.fetchone()[0] == 1

    health_name = f"Source Health Smoke {uuid4().hex[:12]}"
    health_page = f"https://boards.greenhouse.io/source-health-{uuid4().hex[:12]}"
    storage.upsert_companies(pd.DataFrame([{
        "Name": health_name,
        "Website": "https://source-health-smoke.example",
        "Career Page": health_page,
        "Description": "Disposable source health smoke-test source",
        "Label": "greenhouse",
        "Active": True,
    }]))
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM career_sources WHERE career_page = %s", (health_page,))
        source_id = cursor.fetchone()[0]

    error_result = {
        "source_id": source_id,
        "status": "error",
        "job_count": 0,
        "berlin_engineering_count": 0,
        "error": "HTTP 404",
        "status_code": 404,
    }
    for _ in range(7):
        assert storage.record_source_health([error_result]) == 1

    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT active FROM career_sources WHERE id = %s", (source_id,))
        assert cursor.fetchone()[0] is False
        cursor.execute(
            "SELECT consecutive_errors, last_status_code, disabled_at, disabled_reason "
            "FROM source_health WHERE career_source_id = %s",
            (source_id,),
        )
        errors, status_code, disabled_at, disabled_reason = cursor.fetchone()
        assert errors == 7
        assert status_code == 404
        assert disabled_at is not None
        assert disabled_reason == "auto: 7 consecutive errors (HTTP 404)"
        cursor.execute(
            "SELECT active_sources, healthy, empty, failing, unchecked, disabled_last_7_days, last_checked_at "
            "FROM source_health_summary"
        )
        summary = cursor.fetchone()
        cursor.execute(
            """
            SELECT
                count(*) FILTER (WHERE s.active)::integer,
                count(*) FILTER (WHERE s.active AND h.last_status = 'ok')::integer,
                count(*) FILTER (WHERE s.active AND h.last_status = 'empty')::integer,
                count(*) FILTER (WHERE s.active AND h.last_status = 'error')::integer,
                count(*) FILTER (WHERE s.active AND h.career_source_id IS NULL)::integer,
                count(*) FILTER (WHERE h.disabled_at > now() - interval '7 days')::integer,
                max(h.last_run_at)
            FROM career_sources s
            LEFT JOIN source_health h ON h.career_source_id = s.id
            """
        )
        assert summary == cursor.fetchone()
        assert summary[5] >= 1
        assert summary[6] is not None
        cursor.execute("SET ROLE daily_jobs_web")
        cursor.execute("SELECT disabled_last_7_days FROM source_health_summary")
        assert cursor.fetchone()[0] >= 1
        cursor.execute(
            "SELECT company_name, disabled_reason FROM source_health_admin WHERE career_source_id = %s",
            (source_id,),
        )
        assert cursor.fetchone() == (health_name, disabled_reason)
        cursor.execute(
            """
            SELECT company_id, name, website, ats, career_page, health, last_checked_at, open_jobs
            FROM api_companies WHERE name = %s
            """,
            ("Discovery Smoke Company",),
        )
        api_company = cursor.fetchone()
        assert api_company is not None
        assert api_company[1] == "Discovery Smoke Company"
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'api_companies'"
        )
        api_company_columns = {row[0] for row in cursor.fetchall()}
        assert "last_error" not in api_company_columns
        cursor.execute("RESET ROLE")

    print(
        "PostgreSQL smoke: migrations, moderated company sync, historical-job preservation, "
        "semantic dedup, URL mutation, expiry skip, 30-day deletion, agent API views, "
        "company board skipping, retained-job LinkedIn duplicate deletion, source health, "
        "and companies API view passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

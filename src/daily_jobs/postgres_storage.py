"""Portable PostgreSQL storage used by Supabase and local Docker."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from .company_catalog import normalize_url
from .discovery.boards import extract_boards
from .discovery.text import norm_name, norm_title
from .source_health import next_source_health


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "ref", "source", "trackingid"}


def _normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFKD", str(value).casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def canonicalize_url(value: object) -> str:
    """Remove fragments/tracking noise while preserving the actual job URL."""
    raw = "" if value is None or pd.isna(value) else str(value).strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        query = [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_QUERY_KEYS
            and not key.casefold().startswith(TRACKING_QUERY_PREFIXES)
        ]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, urlencode(query), ""))
    except ValueError:
        return raw


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def job_keys(row: dict) -> tuple[str, Optional[str], str]:
    company = _normalize_text(row.get("Company Name") or row.get("Company"))
    title = _normalize_text(row.get("Job Title"))
    location = _normalize_text(row.get("Location"))
    if not company or not title or not location:
        raise ValueError("A published job needs company, title, and location")
    canonical_url = canonicalize_url(row.get("Job Link"))
    identity_key = _digest(company, title, location)
    url_key = _digest(canonical_url) if canonical_url else None
    return identity_key, url_key, canonical_url


def linkedin_duplicate_ids(rows) -> list[int]:
    rows = list(rows)
    ats_keys = set()
    for _job_id, company_name, title, source in rows:
        if str(source or "").lower() != "linkedin":
            key = (norm_name(company_name), norm_title(title))
            if key[0] and key[1]:
                ats_keys.add(key)

    return [
        int(job_id)
        for job_id, company_name, title, source in rows
        if str(source or "").lower() == "linkedin"
        and (norm_name(company_name), norm_title(title)) in ats_keys
    ]


def _split_list(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in re.split(r"[,;|]", str(value)) if item.strip()]


def _posted_date(value: object) -> Optional[date]:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    raw = str(value).strip()
    relative = re.fullmatch(r"(\d+)\s+(hour|hours|day|days)\s+ago", raw, re.IGNORECASE)
    if relative:
        amount = int(relative.group(1))
        today = datetime.now(ZoneInfo("Europe/Berlin")).date()
        return today - timedelta(days=amount if "day" in relative.group(2).casefold() else 0)
    parsed = pd.to_datetime(raw, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


@dataclass
class UpsertStats:
    discovered: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0


class CompanyUpsertStats(NamedTuple):
    inserted: int
    skipped: int


class PostgresJobStorage:
    def __init__(self, database_url: Optional[str] = None, retention_days: int = 30):
        configured_url = database_url or os.getenv("DATABASE_URL", "")
        if not configured_url:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
            configured_url = os.getenv("DATABASE_URL", "")
        self.database_url = configured_url
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for PostgreSQL storage")
        self.retention_days = retention_days

    def connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg") from exc
        return psycopg.connect(self.database_url)

    def migrate(self, migrations_dir: Optional[Path] = None) -> list[str]:
        migrations_dir = migrations_dir or Path(__file__).resolve().parents[2] / "db" / "migrations"
        applied = []
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            cursor.execute("SELECT version FROM schema_migrations")
            existing = {row[0] for row in cursor.fetchall()}
            for migration in sorted(migrations_dir.glob("*.sql")):
                if migration.name in existing:
                    continue
                cursor.execute(migration.read_text(encoding="utf-8"))
                cursor.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (migration.name,))
                applied.append(migration.name)
        return applied

    def load_companies(self) -> pd.DataFrame:
        query = """
            SELECT c.name AS "Name", c.website AS "Website", s.career_page AS "Career Page",
                   s.id AS "Source ID",
                   c.description AS "Description", s.ats_label AS "Label", 'active' AS "Active"
            FROM companies c
            JOIN career_sources s ON s.company_id = c.id
            WHERE c.active AND s.active
            ORDER BY c.name, s.id
        """
        with self.connect() as connection:
            return pd.read_sql_query(query, connection)

    def upsert_companies(
        self,
        dataframe: pd.DataFrame,
        skip_existing_boards: bool = False,
    ) -> CompanyUpsertStats:
        rows = dataframe.fillna("").to_dict(orient="records")
        inserted = skipped = 0

        def normalized_page(value: object) -> str:
            try:
                return normalize_url(value)
            except ValueError:
                return str(value or "").strip()

        with self.connect() as connection, connection.cursor() as cursor:
            existing_board_keys: set[tuple[str, str]] = set()
            existing_pages: set[str] = set()
            existing_company_names: set[str] = set()
            if skip_existing_boards:
                cursor.execute("SELECT career_page FROM career_sources")
                for (page,) in cursor.fetchall():
                    normalized = normalized_page(page)
                    if normalized:
                        existing_pages.add(normalized)
                    existing_board_keys.update(
                        (ats, slug.lower())
                        for ats, slug, _region in extract_boards(str(page or ""))
                    )
                cursor.execute(
                    """
                    SELECT c.name FROM companies c
                    JOIN career_sources s ON s.company_id = c.id
                    WHERE s.active
                    """
                )
                existing_company_names.update(
                    norm_name(name) for (name,) in cursor.fetchall() if norm_name(name)
                )

            for row in rows:
                career_page = row.get("Career Page", row.get("career_page", ""))
                normalized = normalized_page(career_page)
                company_name = row.get("Name", row.get("name", ""))
                normalized_company_name = norm_name(company_name)
                board_keys = {
                    (ats, slug.lower())
                    for ats, slug, _region in extract_boards(str(career_page or ""))
                }
                if skip_existing_boards and (
                    normalized in existing_pages
                    or bool(board_keys & existing_board_keys)
                    or (
                        normalized_company_name
                        and normalized_company_name in existing_company_names
                    )
                ):
                    skipped += 1
                    continue

                active_value = row.get("Active", row.get("active", True))
                active = (
                    active_value
                    if isinstance(active_value, bool)
                    else str(active_value).strip().casefold()
                    not in {"false", "0", "no", "inactive", "disabled"}
                )
                cursor.execute(
                    """
                    INSERT INTO companies(name, website, description, active)
                    VALUES (%s, NULLIF(%s, ''), NULLIF(%s, ''), %s)
                    ON CONFLICT (name) DO UPDATE SET website = EXCLUDED.website,
                        description = EXCLUDED.description, active = EXCLUDED.active, updated_at = now()
                    RETURNING id
                    """,
                    (
                        company_name,
                        row.get("Website", row.get("website", "")),
                        row.get("Description", row.get("description", "")),
                        active,
                    ),
                )
                company_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO career_sources(company_id, career_page, ats_label, active)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (company_id, career_page) DO UPDATE SET
                        ats_label = EXCLUDED.ats_label, active = EXCLUDED.active, updated_at = now()
                    """,
                    (
                        company_id,
                        career_page,
                        row.get("Label", row.get("ats", row.get("ATS", ""))),
                        active,
                    ),
                )
                inserted += 1
                if skip_existing_boards:
                    if normalized:
                        existing_pages.add(normalized)
                    existing_board_keys.update(board_keys)
                    if normalized_company_name:
                        existing_company_names.add(normalized_company_name)
        return CompanyUpsertStats(inserted=inserted, skipped=skipped)

    def delete_linkedin_duplicates_of_ats_jobs(self) -> int:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, company_name, title, source FROM jobs"
            )
            ids = linkedin_duplicate_ids(cursor.fetchall())
            if not ids:
                return 0
            cursor.execute("DELETE FROM jobs WHERE id = ANY(%s)", (ids,))
            return cursor.rowcount

    def record_company_suggestion(
        self,
        suggestion: dict,
        *,
        source_issue: int,
        source_url: str,
        status: str,
        actor: str = "",
        submitted_at: Optional[datetime] = None,
        findings: Optional[list[dict]] = None,
    ) -> int:
        submitted_at = submitted_at or datetime.now(timezone.utc)
        findings = findings or []
        last_error = "; ".join(
            finding.get("message", "")
            for finding in findings
            if finding.get("severity") == "error"
        )
        verified_at = datetime.now(timezone.utc) if status in {"verified", "approved"} else None
        decided_at = datetime.now(timezone.utc) if status in {"approved", "rejected", "disabled"} else None
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO company_suggestions(
                    source_issue, source_url, name, website, career_page, ats_label,
                    berlin_evidence, status, submitted_at, verified_at, decided_at,
                    notes, last_error
                ) VALUES (%s, %s, %s, %s, %s, NULLIF(%s, ''), %s, %s, %s, %s, %s,
                          NULLIF(%s, ''), NULLIF(%s, ''))
                ON CONFLICT (source_issue) DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    name = EXCLUDED.name,
                    website = EXCLUDED.website,
                    career_page = EXCLUDED.career_page,
                    ats_label = EXCLUDED.ats_label,
                    berlin_evidence = EXCLUDED.berlin_evidence,
                    status = EXCLUDED.status,
                    verified_at = COALESCE(EXCLUDED.verified_at, company_suggestions.verified_at),
                    decided_at = COALESCE(EXCLUDED.decided_at, company_suggestions.decided_at),
                    notes = EXCLUDED.notes,
                    last_error = EXCLUDED.last_error,
                    updated_at = now()
                RETURNING id
                """,
                (
                    source_issue,
                    source_url,
                    suggestion.get("name", ""),
                    suggestion.get("website", ""),
                    suggestion.get("career_page", ""),
                    suggestion.get("ats", ""),
                    suggestion.get("berlin_evidence", ""),
                    status,
                    submitted_at,
                    verified_at,
                    decided_at,
                    suggestion.get("notes", ""),
                    last_error,
                ),
            )
            suggestion_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO company_suggestion_events(suggestion_id, status, actor, detail)
                VALUES (%s, %s, NULLIF(%s, ''), %s::jsonb)
                """,
                (suggestion_id, status, actor, json.dumps({"findings": findings})),
            )
        return suggestion_id

    def approve_company_suggestion(
        self,
        suggestion: dict,
        *,
        source_issue: int,
        source_url: str,
        actor: str,
        submitted_at: Optional[datetime] = None,
    ) -> int:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.source_issue
                FROM companies c
                LEFT JOIN career_sources cs ON cs.company_id = c.id
                LEFT JOIN company_suggestions s
                  ON s.name = c.name AND s.status = 'approved'
                WHERE lower(COALESCE(c.website, '')) = lower(%s)
                   OR lower(cs.career_page) = lower(%s)
                   OR lower(c.name) = lower(%s)
                LIMIT 1
                """,
                (
                    suggestion.get("website", ""),
                    suggestion.get("career_page", ""),
                    suggestion.get("name", ""),
                ),
            )
            duplicate = cursor.fetchone()
            if duplicate and duplicate[0] != source_issue:
                raise ValueError("Company domain or careers URL is already approved")
        dataframe = pd.DataFrame(
            [
                {
                    "Name": suggestion.get("name", ""),
                    "Website": suggestion.get("website", ""),
                    "Career Page": suggestion.get("career_page", ""),
                    "Description": suggestion.get("notes", ""),
                    "Label": suggestion.get("ats", ""),
                    "Active": "active",
                }
            ]
        )
        self.upsert_companies(dataframe)
        return self.record_company_suggestion(
            suggestion,
            source_issue=source_issue,
            source_url=source_url,
            status="approved",
            actor=actor,
            submitted_at=submitted_at,
        )

    def disable_company_suggestion(
        self,
        suggestion: dict,
        *,
        source_issue: int,
        source_url: str,
        status: str = "disabled",
        actor: str = "",
        submitted_at: Optional[datetime] = None,
        findings: Optional[list[dict]] = None,
    ) -> int:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE career_sources
                SET active = false, updated_at = now()
                WHERE lower(career_page) = lower(%s)
                """,
                (suggestion.get("career_page", ""),),
            )
            cursor.execute(
                """
                UPDATE companies
                SET active = false, updated_at = now()
                WHERE lower(name) = lower(%s)
                """,
                (suggestion.get("name", ""),),
            )
        return self.record_company_suggestion(
            suggestion,
            source_issue=source_issue,
            source_url=source_url,
            status=status,
            actor=actor,
            submitted_at=submitted_at,
            findings=findings,
        )

    def upsert_jobs(self, dataframe: pd.DataFrame) -> UpsertStats:
        rows = dataframe.fillna("").to_dict(orient="records")
        stats = UpsertStats(discovered=len(rows))
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        run_id = uuid.uuid4()

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO crawl_runs(id, discovered_count) VALUES (%s, %s)", (run_id, len(rows)))
            try:
                for row in rows:
                    identity_key, url_key, canonical_url = job_keys(row)
                    cursor.execute(
                        """
                        SELECT f.identity_key, f.first_seen_at
                        FROM job_fingerprints f
                        LEFT JOIN job_url_aliases a ON a.identity_key = f.identity_key
                        WHERE f.identity_key = %s OR a.url_key = %s
                        ORDER BY (a.url_key = %s) DESC LIMIT 1
                        """,
                        (identity_key, url_key, url_key),
                    )
                    existing_fingerprint = cursor.fetchone()
                    stable_key = existing_fingerprint[0] if existing_fingerprint else identity_key
                    first_seen = existing_fingerprint[1] if existing_fingerprint else datetime.now(timezone.utc)
                    cursor.execute(
                        """
                        INSERT INTO job_fingerprints(identity_key, first_seen_at, last_seen_at)
                        VALUES (%s, %s, now())
                        ON CONFLICT (identity_key) DO UPDATE SET
                            last_seen_at = now()
                        """,
                        (stable_key, first_seen),
                    )
                    if url_key:
                        cursor.execute(
                            """
                            INSERT INTO job_url_aliases(url_key, identity_key, last_seen_at)
                            VALUES (%s, %s, now())
                            ON CONFLICT (url_key) DO UPDATE SET last_seen_at = now()
                            """,
                            (url_key, stable_key),
                        )

                    posted_at = _posted_date(row.get("Posted Date"))
                    retention_anchor = datetime.combine(posted_at, datetime.min.time(), timezone.utc) if posted_at else first_seen
                    if retention_anchor < cutoff:
                        stats.skipped += 1
                        continue

                    cursor.execute("SELECT 1 FROM jobs WHERE identity_key = %s", (stable_key,))
                    existed = cursor.fetchone() is not None
                    cursor.execute(
                        """
                        INSERT INTO jobs(
                            identity_key, url_key, company_name, title, location, canonical_url,
                            description, employment_type, department, role, level, work_mode,
                            tech_stack, keywords, classification_version, posted_at,
                            company_description, remote, ats_label, source, first_seen_at, last_seen_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''),
                            NULLIF(%s, ''), %s, NULLIF(%s, ''), NULLIF(%s, ''), %s, %s, %s, %s,
                            NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), %s, now()
                        )
                        ON CONFLICT (identity_key) DO UPDATE SET
                            url_key = COALESCE(EXCLUDED.url_key, jobs.url_key),
                            company_name = EXCLUDED.company_name,
                            title = EXCLUDED.title,
                            location = EXCLUDED.location,
                            canonical_url = COALESCE(EXCLUDED.canonical_url, jobs.canonical_url),
                            description = COALESCE(EXCLUDED.description, jobs.description),
                            employment_type = COALESCE(EXCLUDED.employment_type, jobs.employment_type),
                            department = COALESCE(EXCLUDED.department, jobs.department),
                            role = EXCLUDED.role, level = EXCLUDED.level, work_mode = EXCLUDED.work_mode,
                            tech_stack = EXCLUDED.tech_stack, keywords = EXCLUDED.keywords,
                            classification_version = EXCLUDED.classification_version,
                            posted_at = COALESCE(EXCLUDED.posted_at, jobs.posted_at),
                            company_description = COALESCE(EXCLUDED.company_description, jobs.company_description),
                            remote = COALESCE(EXCLUDED.remote, jobs.remote), ats_label = COALESCE(EXCLUDED.ats_label, jobs.ats_label),
                            source = COALESCE(EXCLUDED.source, jobs.source), last_seen_at = now(), updated_at = now()
                        """,
                        (
                            stable_key, url_key, row.get("Company Name") or row.get("Company"),
                            row.get("Job Title"), row.get("Location"), canonical_url,
                            row.get("Job Description"), row.get("Employment Type"), row.get("Department"),
                            row.get("Role"), row.get("Level"), row.get("Work Mode"),
                            _split_list(row.get("Tech Stack")), _split_list(row.get("Keywords")),
                            row.get("Classification Version"), posted_at, row.get("Company Description"),
                            row.get("Remote"), row.get("Label") or row.get("ATS"), row.get("ATS") or row.get("Label"),
                            first_seen,
                        ),
                    )
                    stats.updated += int(existed)
                    stats.inserted += int(not existed)

                cursor.execute(
                    "DELETE FROM jobs WHERE COALESCE(posted_at, (first_seen_at AT TIME ZONE 'Europe/Berlin')::date) "
                    "< (now() AT TIME ZONE 'Europe/Berlin')::date - %s RETURNING id",
                    (self.retention_days,),
                )
                stats.deleted = len(cursor.fetchall())
                cursor.execute(
                    """
                    UPDATE crawl_runs SET finished_at = now(), status = 'succeeded', inserted_count = %s,
                        updated_count = %s, skipped_count = %s, deleted_count = %s WHERE id = %s
                    """,
                    (stats.inserted, stats.updated, stats.skipped, stats.deleted, run_id),
                )
            except Exception as exc:
                connection.rollback()
                with self.connect() as error_connection, error_connection.cursor() as error_cursor:
                    error_cursor.execute(
                        "INSERT INTO crawl_runs(id, finished_at, status, discovered_count, error) "
                        "VALUES (%s, now(), 'failed', %s, %s)",
                        (run_id, len(rows), str(exc)[:2000]),
                    )
                raise
        return stats

    def record_source_health(self, results: list[dict]) -> int:
        records = [
            result for result in results
            if result.get("source_id") is not None and not pd.isna(result.get("source_id"))
        ]
        if not records:
            return 0

        columns = (
            "last_run_at",
            "last_status",
            "last_success_at",
            "last_job_count",
            "last_berlin_engineering_count",
            "consecutive_errors",
            "consecutive_empty",
            "last_error",
            "last_status_code",
            "disabled_at",
            "disabled_reason",
        )
        now = datetime.now(timezone.utc)
        with self.connect() as connection, connection.cursor() as cursor:
            for result in records:
                source_id = int(result["source_id"])
                cursor.execute(
                    f"SELECT {', '.join(columns)} FROM source_health "
                    "WHERE career_source_id = %s FOR UPDATE",
                    (source_id,),
                )
                previous_row = cursor.fetchone()
                previous = dict(zip(columns, previous_row)) if previous_row else None
                state, disable_reason = next_source_health(previous, result, now)
                cursor.execute(
                    """
                    INSERT INTO source_health(
                        career_source_id, last_run_at, last_status, last_success_at,
                        last_job_count, last_berlin_engineering_count, consecutive_errors,
                        consecutive_empty, last_error, last_status_code, disabled_at, disabled_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (career_source_id) DO UPDATE SET
                        last_run_at = EXCLUDED.last_run_at,
                        last_status = EXCLUDED.last_status,
                        last_success_at = EXCLUDED.last_success_at,
                        last_job_count = EXCLUDED.last_job_count,
                        last_berlin_engineering_count = EXCLUDED.last_berlin_engineering_count,
                        consecutive_errors = EXCLUDED.consecutive_errors,
                        consecutive_empty = EXCLUDED.consecutive_empty,
                        last_error = EXCLUDED.last_error,
                        last_status_code = EXCLUDED.last_status_code,
                        disabled_at = EXCLUDED.disabled_at,
                        disabled_reason = EXCLUDED.disabled_reason
                    """,
                    (
                        source_id,
                        state["last_run_at"],
                        state["last_status"],
                        state["last_success_at"],
                        state["last_job_count"],
                        state["last_berlin_engineering_count"],
                        state["consecutive_errors"],
                        state["consecutive_empty"],
                        state["last_error"],
                        state["last_status_code"],
                        state["disabled_at"],
                        state["disabled_reason"],
                    ),
                )
                if disable_reason:
                    cursor.execute(
                        "UPDATE career_sources SET active = false WHERE id = %s",
                        (source_id,),
                    )
        return len(records)

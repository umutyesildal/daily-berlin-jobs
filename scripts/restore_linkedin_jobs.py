"""Restore LinkedIn jobs removed by the 2026-10-23 company-level ATS dedupe.

Reads the `public.jobs` COPY block from a pg_dump backup, loads it into a temp
table and re-inserts LinkedIn rows that are missing from `jobs`, still inside
the 30-day retention window, still fingerprinted, and that have no published
ATS job with the same normalized company and title. Dry run unless --apply.
"""
import argparse
import collections
import gzip
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daily_jobs.discovery.text import norm_name, norm_title  # noqa: E402
from daily_jobs.postgres_storage import PostgresJobStorage  # noqa: E402


def copy_block(dump_path: Path) -> tuple[list[str], str]:
    opener = gzip.open if dump_path.suffix == ".gz" else open
    with opener(dump_path, "rt", encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(r"^COPY public\.jobs \((.*?)\) FROM stdin;\n(.*?\n)\\\.\n", text, re.S | re.M)
    if not match:
        raise SystemExit("No COPY public.jobs block in dump")
    return [column.strip() for column in match.group(1).split(",")], match.group(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    columns, data = copy_block(args.dump)
    column_list = ", ".join(columns)
    storage = PostgresJobStorage()
    with storage.connect() as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TEMP TABLE restore_jobs (LIKE jobs INCLUDING DEFAULTS) ON COMMIT DROP")
        with cursor.copy(f"COPY restore_jobs ({column_list}) FROM STDIN") as copy:
            copy.write(data)
        cursor.execute(
            """
            SELECT r.id, r.company_name, r.title
            FROM restore_jobs r
            WHERE lower(coalesce(r.source, '')) = 'linkedin'
              AND btrim(r.role) <> ''
              AND COALESCE(r.posted_at, (r.first_seen_at AT TIME ZONE 'Europe/Berlin')::date)
                  >= (now() AT TIME ZONE 'Europe/Berlin')::date - 30
              AND EXISTS (SELECT 1 FROM job_fingerprints f WHERE f.identity_key = r.identity_key)
              AND NOT EXISTS (
                  SELECT 1 FROM jobs j
                  WHERE j.id = r.id OR j.identity_key = r.identity_key
                     OR (r.url_key IS NOT NULL AND j.url_key = r.url_key)
              )
            """
        )
        candidates = cursor.fetchall()
        cursor.execute("SELECT company_name, title FROM jobs WHERE lower(coalesce(source, '')) <> 'linkedin'")
        ats_keys = {(norm_name(company), norm_title(title)) for company, title in cursor.fetchall()}
        restore = [(job_id, company) for job_id, company, title in candidates
                   if (norm_name(company), norm_title(title)) not in ats_keys]
        twins = len(candidates) - len(restore)
        print(f"Backup LinkedIn rows missing and in window: {len(candidates)}; "
              f"ATS twin present (kept deleted): {twins}; to restore: {len(restore)}")
        print("Top companies:", collections.Counter(company for _, company in restore).most_common(15))
        if not args.apply:
            connection.rollback()
            print("Dry run: nothing written")
            return 0
        cursor.execute(
            f"INSERT INTO jobs ({column_list}) SELECT {column_list} FROM restore_jobs "
            "WHERE id = ANY(%s) ON CONFLICT DO NOTHING",
            ([job_id for job_id, _ in restore],),
        )
        print(f"Restored rows: {cursor.rowcount}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

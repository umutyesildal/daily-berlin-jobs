#!/usr/bin/env python3
"""Small database CLI for migrations, checks, and one-time company imports."""

import argparse

import pandas as pd

from daily_jobs.data_controller import DataController
from daily_jobs.post_process_jobs import classify_jobs
from daily_jobs.postgres_storage import PostgresJobStorage


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate")
    subparsers.add_parser("doctor")
    importer = subparsers.add_parser("import-companies")
    importer.add_argument("source", help="CSV path or Google Sheet URL/ID")
    importer.add_argument("--input-type", choices=["csv", "yaml", "sheets"], default="csv")
    importer.add_argument("--worksheet", default="OneSingle")
    importer.add_argument("--skip-existing-boards", action="store_true")
    job_importer = subparsers.add_parser("import-jobs")
    job_importer.add_argument("source", help="Canonical published jobs CSV")
    job_importer.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()

    storage = PostgresJobStorage()
    if args.command == "migrate":
        applied = storage.migrate()
        print("Applied migrations:", ", ".join(applied) if applied else "none")
    elif args.command == "doctor":
        with storage.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), version()")
            database, version = cursor.fetchone()
            cursor.execute("SELECT count(*) FROM jobs")
            jobs = cursor.fetchone()[0]
            cursor.execute("SELECT pg_database_size(current_database())")
            size_bytes = cursor.fetchone()[0]
        size_mb = size_bytes / 1024 / 1024
        quota_status = "critical" if size_mb >= 425 else "warning" if size_mb >= 350 else "healthy"
        print(f"Database: {database}")
        print(f"PostgreSQL: {version.split(',')[0]}")
        print(f"Jobs: {jobs}")
        print(f"Size: {size_mb:.1f} MB ({quota_status})")
    elif args.command == "import-companies":
        controller = DataController()
        if args.input_type == "sheets":
            dataframe = controller.load_data_from_google_sheet(args.source, args.worksheet)
        elif args.input_type == "yaml":
            dataframe = controller.load_data_from_yaml(args.source)
        else:
            dataframe = controller.load_data_from_csv(args.source)
        stats = storage.upsert_companies(
            dataframe,
            skip_existing_boards=args.skip_existing_boards,
        )
        print(f"Imported company sources: {stats.inserted} inserted, {stats.skipped} skipped")
    else:
        dataframe = classify_jobs(
            DataController().normalize_jobs_dataframe(
                pd.read_csv(args.source, low_memory=False, dtype=str).fillna("")
            )
        )
        dataframe = dataframe[dataframe["Role"].astype(str).str.strip().ne("")].copy()
        stats = PostgresJobStorage(retention_days=args.retention_days).upsert_jobs(dataframe)
        print(
            f"Imported jobs: {stats.inserted} inserted, {stats.updated} updated, "
            f"{stats.skipped} expired skipped, {stats.deleted} old rows deleted"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

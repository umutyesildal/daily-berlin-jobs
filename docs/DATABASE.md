# Supabase PostgreSQL setup

Daily Berlin Jobs uses ordinary PostgreSQL. Supabase is the recommended free
host, while Docker provides the same database locally.

## Local setup

```bash
make setup
make doctor
make dev
```

The default local URL is:

```text
postgresql://daily_jobs:daily_jobs@localhost:5432/daily_berlin_jobs
```

## Supabase project

1. Create a Supabase project in the desired EU region.
2. In **Connect**, copy a session-pooler PostgreSQL URL for GitHub Actions and a
   transaction-pooler URL for Vercel. Replace the password placeholder.
3. Set the session URL locally as `DATABASE_URL` and run:

   ```bash
   .venv/bin/python scripts/db.py migrate
   ```

4. Import the current company catalog once. This command can use the legacy
   Sheet during migration; the crawler no longer needs it afterward:

   ```bash
   .venv/bin/python scripts/db.py import-companies \
     "https://docs.google.com/spreadsheets/d/YOUR_ID/" \
     --input-type sheets --worksheet OneSingle
   ```

   After the initial migration, keep reviewed sources in
   `catalog/companies.yaml` and import them without Google credentials:

   ```bash
   .venv/bin/python scripts/db.py import-companies \
     catalog/companies.yaml --input-type yaml
   ```

5. Optionally backfill the current canonical export. Every imported row is
   reclassified by the same Python taxonomy used by the crawler, and rows
   outside the engineering taxonomy or older than 30 days are skipped
   automatically:

   ```bash
   .venv/bin/python scripts/db.py import-jobs /path/to/published_all_jobs.csv
   ```

6. Add `SUPABASE_DATABASE_URL` to GitHub Actions secrets. Add `DATABASE_URL`
   and `DATABASE_SSL=true` to Vercel. Neither value is public or prefixed with
   `NEXT_PUBLIC_`.

Migration `002_web_reader.sql` creates a `NOLOGIN` role that can select only
`public_jobs`, `daily_jobs`, and `data_status`. In the Supabase SQL editor, give
it a generated password and login capability, then build the corresponding
pooler URL for Vercel:

```sql
ALTER ROLE daily_jobs_web LOGIN PASSWORD 'GENERATE_A_LONG_RANDOM_PASSWORD';
```

Keep the migration/crawler connection in GitHub Actions. Never reuse the
database owner URL in browser-accessible code.

Migration `003_supabase_api_lockdown.sql` revokes public-schema access from
Supabase's `anon` and `authenticated` API roles. The web application uses only
its server-side PostgreSQL connection; no database URL or Data API key reaches
the browser.

Migration `006_enable_row_level_security.sql` also enables RLS on every public
table. No Data API policies are created because browser clients do not query the
database directly. This resolves Supabase's `rls_disabled_in_public` advisory
while preserving owner access for the crawler and the explicitly granted,
read-only SQL views used by the web application.

Migration `004_enforce_engineering_jobs.sql` removes legacy rows with an empty
role and adds a database constraint so non-engineering rows cannot enter the
canonical job table.

## Daily lifecycle

Each run performs migrations, loads active company sources, crawls jobs,
classifies every row, filters to Berlin engineering roles, and transactionally
upserts the canonical result. The publisher then:

- updates existing rows instead of appending duplicates;
- skips already-expired vacancies;
- deletes full job rows older than 30 days;
- records inserted, updated, skipped, and deleted counts in `crawl_runs`.

The 126 MB raw crawl stays on the GitHub Actions runner and disappears with the
runner. Only the much smaller public subset reaches Supabase.

## Backup and quota policy

Supabase Free does not provide automatic backups. The repository workflow
creates a compressed daily `pg_dump` artifact with 14-day retention. Use the
session/direct connection for backups, not the transaction pooler.

Monitor database size before the free-tier limit becomes operationally risky:

- warning at 350 MB;
- critical at 425 MB;
- investigate unexpected growth in descriptions or fingerprints before 500 MB.

`python scripts/db.py doctor` reports the current database size and marks these
thresholds as healthy, warning, or critical.

Restore testing should be performed periodically in a disposable local
PostgreSQL database:

```bash
gunzip -c daily-berlin-jobs.sql.gz | psql "$RESTORE_DATABASE_URL"
```

## Cutover checklist

- Run the migration and one-time company import.
- Backfill the rolling 30-day job set.
- Use `--storage-backend dual` for three successful crawls.
- Compare counts, canonical URLs, duplicate counts, roles, and
  `classification_version`.
- Point Vercel at PostgreSQL and smoke-test the public page.
- Switch the scheduled workflow to `postgres`.
- Keep the Sheet read-only for a short rollback window, then remove Google
  credentials and the legacy runtime code.

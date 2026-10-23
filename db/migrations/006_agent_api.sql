CREATE OR REPLACE VIEW crawl_status AS
SELECT started_at, finished_at, discovered_count, inserted_count, updated_count, deleted_count
FROM crawl_runs
WHERE status = 'succeeded'
ORDER BY finished_at DESC
LIMIT 1;

CREATE OR REPLACE VIEW api_jobs AS
SELECT
    id,
    company_name,
    title,
    location,
    canonical_url,
    role,
    level,
    work_mode,
    remote,
    employment_type,
    department,
    tech_stack,
    keywords,
    posted_at,
    first_seen_at,
    last_seen_at,
    CASE
        WHEN lower(COALESCE(source, '')) = 'linkedin'
          OR lower(COALESCE(ats_label, '')) = 'linkedin'
          OR canonical_url ILIKE '%linkedin.com/%'
        THEN 'linkedin'
        ELSE 'ats'
    END AS source_type,
    CASE
        WHEN lower(COALESCE(source, '')) = 'linkedin'
          OR lower(COALESCE(ats_label, '')) = 'linkedin'
          OR canonical_url ILIKE '%linkedin.com/%'
        THEN NULL
        ELSE description
    END AS description
FROM public_jobs;

GRANT SELECT ON crawl_status, api_jobs TO daily_jobs_web;

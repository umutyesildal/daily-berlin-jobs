CREATE OR REPLACE VIEW api_companies AS
SELECT
    c.id AS company_id,
    c.name,
    c.website,
    s.ats_label AS ats,
    s.career_page,
    h.last_status AS health,
    h.last_run_at AS last_checked_at,
    COALESCE(job_counts.open_jobs, 0)::integer AS open_jobs
FROM companies c
JOIN career_sources s ON s.company_id = c.id
LEFT JOIN source_health h ON h.career_source_id = s.id
LEFT JOIN (
    SELECT lower(company_name) AS company_name, count(*)::integer AS open_jobs
    FROM api_jobs
    GROUP BY lower(company_name)
) job_counts ON job_counts.company_name = lower(c.name)
WHERE c.active AND s.active;

GRANT SELECT ON api_companies TO daily_jobs_web;

DO $$
DECLARE
    api_role text;
    object_name text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            FOREACH object_name IN ARRAY ARRAY['api_companies']
            LOOP
                IF to_regclass('public.' || object_name) IS NOT NULL THEN
                    EXECUTE format(
                        'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I',
                        object_name,
                        api_role
                    );
                END IF;
            END LOOP;
        END IF;
    END LOOP;
END
$$;

CREATE TABLE IF NOT EXISTS source_health (
    career_source_id bigint PRIMARY KEY REFERENCES career_sources(id) ON DELETE CASCADE,
    last_run_at timestamptz NOT NULL,
    last_status text NOT NULL CHECK (last_status IN ('ok', 'empty', 'error')),
    last_success_at timestamptz,
    last_job_count integer NOT NULL DEFAULT 0,
    last_berlin_engineering_count integer NOT NULL DEFAULT 0,
    consecutive_errors integer NOT NULL DEFAULT 0,
    consecutive_empty integer NOT NULL DEFAULT 0,
    last_error text,
    last_status_code integer,
    disabled_at timestamptz,
    disabled_reason text
);

CREATE OR REPLACE VIEW source_health_summary AS
SELECT
    count(*) FILTER (WHERE s.active)::integer AS active_sources,
    count(*) FILTER (WHERE s.active AND h.last_status = 'ok')::integer AS healthy,
    count(*) FILTER (WHERE s.active AND h.last_status = 'empty')::integer AS empty,
    count(*) FILTER (WHERE s.active AND h.last_status = 'error')::integer AS failing,
    count(*) FILTER (WHERE s.active AND h.career_source_id IS NULL)::integer AS unchecked,
    count(*) FILTER (WHERE h.disabled_at > now() - interval '7 days')::integer AS disabled_last_7_days,
    max(h.last_run_at) AS last_checked_at
FROM career_sources s
LEFT JOIN source_health h ON h.career_source_id = s.id;

CREATE OR REPLACE VIEW source_health_admin AS
SELECT
    c.name AS company_name,
    s.career_page,
    s.ats_label,
    s.active,
    h.career_source_id,
    h.last_run_at,
    h.last_status,
    h.last_success_at,
    h.last_job_count,
    h.last_berlin_engineering_count,
    h.consecutive_errors,
    h.consecutive_empty,
    h.last_error,
    h.last_status_code,
    h.disabled_at,
    h.disabled_reason
FROM career_sources s
JOIN companies c ON c.id = s.company_id
LEFT JOIN source_health h ON h.career_source_id = s.id;

GRANT SELECT ON source_health_summary, source_health_admin TO daily_jobs_web;

DO $$
DECLARE
    api_role text;
    object_name text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            FOREACH object_name IN ARRAY ARRAY[
                'source_health', 'source_health_summary', 'source_health_admin'
            ]
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

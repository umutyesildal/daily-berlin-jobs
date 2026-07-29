-- Supabase exposes the public schema through its Data API by default. The app
-- does not use that API, so public tables intentionally have no RLS policies:
-- API callers receive no rows and cannot insert, update, or delete anything.
-- Database owners used by migrations and the crawler retain their normal
-- PostgreSQL access; the web reader continues to use the explicitly granted
-- read-only views from 002_web_reader.sql.
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.career_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crawl_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_fingerprints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_url_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.company_suggestion_events ENABLE ROW LEVEL SECURITY;

-- Repeat the Data API lockdown after all current tables have been created.
-- Migration 003 predates the suggestion tables, so this also closes the gap
-- for objects added by migration 005.
DO $$
DECLARE
    api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', api_role);
        END IF;
    END LOOP;
END
$$;

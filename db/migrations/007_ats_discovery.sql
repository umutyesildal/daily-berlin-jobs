CREATE TABLE IF NOT EXISTS discovery_search_cache (
    query_key text PRIMARY KEY,
    query jsonb NOT NULL,
    results jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS discovered_boards (
    ats text NOT NULL,
    slug_key text NOT NULL,
    slug text NOT NULL,
    region text NOT NULL DEFAULT '',
    career_page text NOT NULL,
    status text NOT NULL CHECK (status IN ('accepted', 'rejected')),
    reason text,
    company_name text,
    website text,
    api_berlin_eng integer NOT NULL DEFAULT 0,
    scraper_berlin_eng integer NOT NULL DEFAULT 0,
    llm jsonb,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ats, slug_key)
);

DO $$
DECLARE
    api_role text;
    object_name text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            FOREACH object_name IN ARRAY ARRAY[
                'discovery_search_cache', 'discovered_boards', 'crawl_status', 'api_jobs'
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

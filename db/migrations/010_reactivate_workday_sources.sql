-- Workday sources were kept inactive because no working scraper existed.
-- Re-enable them now that the generic Workday scraper is available; sources
-- disabled by source health stay disabled.
WITH reactivated AS (
    UPDATE career_sources s
    SET active = true, ats_label = 'workday', updated_at = now()
    WHERE lower(s.ats_label) IN ('myworkdayjobs', 'workday')
      AND NOT s.active
      AND NOT EXISTS (
          SELECT 1 FROM source_health h
          WHERE h.career_source_id = s.id AND h.disabled_reason IS NOT NULL
      )
    RETURNING s.company_id
)
UPDATE companies c
SET active = true, updated_at = now()
WHERE c.id IN (SELECT company_id FROM reactivated) AND NOT c.active;

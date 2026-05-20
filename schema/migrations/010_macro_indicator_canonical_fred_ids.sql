-- Macro Indicator Canonical FRED IDs
--
-- FRED series IDs are the canonical identifiers for macro indicators. Older
-- deployments used integer surrogate IDs in sec_database or short VARCHAR IDs
-- in stock. Normalize the PostgreSQL shape so macro_indicators.id and all
-- referencing values/watermarks store the FRED series ID directly.

ALTER TABLE IF EXISTS macro_indicator_values
    DROP CONSTRAINT IF EXISTS macro_indicator_values_indicator_id_fkey;

ALTER TABLE IF EXISTS macro_indicator_watermarks
    DROP CONSTRAINT IF EXISTS macro_indicator_watermarks_indicator_id_fkey;

ALTER TABLE IF EXISTS macro_indicator_values
    ADD COLUMN IF NOT EXISTS indicator_series_id VARCHAR(50);

UPDATE macro_indicator_values mv
SET indicator_series_id = COALESCE(mi.series_id, mi.id::text)
FROM macro_indicators mi
WHERE mv.indicator_series_id IS NULL
  AND mv.indicator_id::text = mi.id::text;

ALTER TABLE IF EXISTS macro_indicator_watermarks
    ADD COLUMN IF NOT EXISTS indicator_series_id VARCHAR(50);

UPDATE macro_indicator_watermarks mw
SET indicator_series_id = COALESCE(mi.series_id, mi.id::text)
FROM macro_indicators mi
WHERE mw.indicator_series_id IS NULL
  AND mw.indicator_id::text = mi.id::text;

ALTER TABLE IF EXISTS macro_indicator_values
    DROP COLUMN IF EXISTS indicator_id;

ALTER TABLE IF EXISTS macro_indicator_values
    RENAME COLUMN indicator_series_id TO indicator_id;

ALTER TABLE IF EXISTS macro_indicator_watermarks
    DROP COLUMN IF EXISTS indicator_id;

ALTER TABLE IF EXISTS macro_indicator_watermarks
    RENAME COLUMN indicator_series_id TO indicator_id;

ALTER TABLE IF EXISTS macro_indicators
    DROP CONSTRAINT IF EXISTS macro_indicators_pkey;

ALTER TABLE IF EXISTS macro_indicators
    ALTER COLUMN id TYPE VARCHAR(50) USING id::text;

UPDATE macro_indicators
SET id = series_id
WHERE series_id IS NOT NULL
  AND id IS DISTINCT FROM series_id;

ALTER TABLE IF EXISTS macro_indicators
    ADD CONSTRAINT macro_indicators_pkey PRIMARY KEY (id);

ALTER TABLE IF EXISTS macro_indicator_values
    ALTER COLUMN indicator_id TYPE VARCHAR(50),
    ALTER COLUMN indicator_id SET NOT NULL;

ALTER TABLE IF EXISTS macro_indicator_watermarks
    ALTER COLUMN indicator_id TYPE VARCHAR(50),
    ALTER COLUMN indicator_id SET NOT NULL;

ALTER TABLE IF EXISTS macro_indicator_values
    ADD CONSTRAINT macro_indicator_values_indicator_id_fkey
    FOREIGN KEY (indicator_id) REFERENCES macro_indicators(id);

ALTER TABLE IF EXISTS macro_indicator_watermarks
    ADD CONSTRAINT macro_indicator_watermarks_indicator_id_fkey
    FOREIGN KEY (indicator_id) REFERENCES macro_indicators(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_macro_indicators_series
    ON macro_indicators(series_id);

WITH ranked_values AS (
    SELECT
        ctid,
        ROW_NUMBER() OVER (
            PARTITION BY indicator_id, date
            ORDER BY
                source_fetch_timestamp DESC NULLS LAST,
                updated_at DESC NULLS LAST,
                created_at DESC NULLS LAST,
                ctid DESC
        ) AS rn
    FROM macro_indicator_values
)
DELETE FROM macro_indicator_values mv
USING ranked_values rv
WHERE mv.ctid = rv.ctid
  AND rv.rn > 1;

WITH ranked_watermarks AS (
    SELECT
        ctid,
        ROW_NUMBER() OVER (
            PARTITION BY indicator_id
            ORDER BY
                last_observation_date DESC NULLS LAST,
                last_fetch_timestamp DESC NULLS LAST,
                ctid DESC
        ) AS rn
    FROM macro_indicator_watermarks
)
DELETE FROM macro_indicator_watermarks mw
USING ranked_watermarks rw
WHERE mw.ctid = rw.ctid
  AND rw.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_macro_indicator_values_indicator_date_unique
    ON macro_indicator_values(indicator_id, date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_macro_indicator_watermarks_indicator_unique
    ON macro_indicator_watermarks(indicator_id);

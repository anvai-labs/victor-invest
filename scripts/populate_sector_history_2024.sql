-- Calculate and populate sector multiples for FY 2024
-- This script computes median P/E, P/S, P/B multiples by sector
-- and stores them in the sector_multiples_history table

-- First, create the sector_multiples_history table if it doesn't exist
-- (run the migration first)

-- Step 1: Calculate P/E multiples by sector
-- P/E = Market Cap / Net Income

-- Step 2: Calculate P/S multiples by sector
-- P/S = Market Cap / Total Revenue

-- Step 3: Calculate P/B multiples by sector
-- P/B = Market Cap / Stockholders Equity

INSERT INTO sector_multiples_history (
    group_name,
    group_type,
    fiscal_year,
    snapshot_date,
    pe_multiple,
    ps_multiple,
    pb_multiple,
    sample_size,
    percentile_low,
    percentile_high,
    created_at,
    updated_at
)
WITH
-- Get symbol-level data with sector classification
symbol_data AS (
    SELECT
        p.symbol,
        COALESCE(s."Sector", 'Unknown') as sector,
        p.market_cap,
        p.total_revenue,
        p.net_income,
        p.stockholders_equity,
        p.shares_outstanding,
        p.earnings_per_share
    FROM sec_companyfacts_processed p
    LEFT JOIN symbol s ON UPPER(p.symbol) = UPPER(s.ticker)
    WHERE p.fiscal_year = 2024
      AND p.fiscal_period = 'FY'
      AND p.market_cap IS NOT NULL
      AND p.market_cap > 0
),
-- Calculate individual multiples
symbol_multiples AS (
    SELECT
        sector,
        symbol,
        market_cap,
        -- P/E = Market Cap / Net Income
        CASE WHEN net_income IS NOT NULL AND net_income > 0
            THEN market_cap / net_income
            ELSE NULL
        END as pe_ratio,
        -- P/S = Market Cap / Total Revenue
        CASE WHEN total_revenue IS NOT NULL AND total_revenue > 0
            THEN market_cap / total_revenue
            ELSE NULL
        END as ps_ratio,
        -- P/B = Market Cap / Stockholders Equity
        CASE WHEN stockholders_equity IS NOT NULL AND stockholders_equity > 0
            THEN market_cap / stockholders_equity
            ELSE NULL
        END as pb_ratio
    FROM symbol_data
    WHERE sector != 'Unknown'
),
-- Filter out extreme outliers (5th and 95th percentile)
filtered_pe AS (
    SELECT
        sector,
        pe_ratio,
        PERCENT_RANK() OVER (PARTITION BY sector ORDER BY pe_ratio) as pct_rank
    FROM symbol_multiples
    WHERE pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 1000
),
filtered_ps AS (
    SELECT
        sector,
        ps_ratio,
        PERCENT_RANK() OVER (PARTITION BY sector ORDER BY ps_ratio) as pct_rank
    FROM symbol_multiples
    WHERE ps_ratio IS NOT NULL AND ps_ratio > 0 AND ps_ratio < 100
),
filtered_pb AS (
    SELECT
        sector,
        pb_ratio,
        PERCENT_RANK() OVER (PARTITION BY sector ORDER BY pb_ratio) as pct_rank
    FROM symbol_multiples
    WHERE pb_ratio IS NOT NULL AND pb_ratio > 0 AND pb_ratio < 50
),
-- Calculate medians for each sector
sector_medians AS (
    SELECT
        s.sector,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY f.pe_ratio) as median_pe,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY f2.ps_ratio) as median_ps,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY f3.pb_ratio) as median_pb,
        COUNT(DISTINCT s.symbol) as sample_size
    FROM (SELECT DISTINCT sector FROM symbol_data WHERE sector != 'Unknown') s
    LEFT JOIN filtered_pe f ON s.sector = f.sector AND f.pct_rank BETWEEN 0.05 AND 0.95
    LEFT JOIN filtered_ps f2 ON s.sector = f2.sector AND f2.pct_rank BETWEEN 0.05 AND 0.95
    LEFT JOIN filtered_pb f3 ON s.sector = f3.sector AND f3.pct_rank BETWEEN 0.05 AND 0.95
    GROUP BY s.sector
    HAVING COUNT(DISTINCT s.symbol) >= 5
)
SELECT
    sector,
    'sector' as group_type,
    2024 as fiscal_year,
    '2025-01-31'::date as snapshot_date,
    median_pe,
    median_ps,
    median_pb,
    sample_size,
    0.05 as percentile_low,
    0.95 as percentile_high,
    NOW() as created_at,
    NOW() as updated_at
FROM sector_medians
ON CONFLICT (group_name, group_type, fiscal_year)
DO UPDATE SET
    pe_multiple = EXCLUDED.median_pe,
    ps_multiple = EXCLUDED.median_ps,
    pb_multiple = EXCLUDED.median_pb,
    sample_size = EXCLUDED.sample_size,
    updated_at = NOW();

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT
    group_name,
    ROUND(pe_multiple::numeric, 2) as pe,
    ROUND(ps_multiple::numeric, 2) as ps,
    ROUND(pb_multiple::numeric, 2) as pb,
    sample_size
FROM sector_multiples_history
WHERE group_type = 'sector' AND fiscal_year = 2024
ORDER BY group_name;

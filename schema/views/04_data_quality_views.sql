-- Data Quality Views for Investment Opportunities
--
-- Views to identify data quality issues that need manual review or fixing.
--
-- Author: InvestiGator Team
-- Date: 2026-02-28

-- ==============================================================================
-- EXTREME VALUATION OUTLIERS (Need Manual Review)
-- ==============================================================================
DROP VIEW IF EXISTS valuation_outliers CASCADE;
CREATE VIEW valuation_outliers AS
SELECT
    s.ticker AS symbol,
    description,
    ROUND(td.close::numeric, 2) AS current_price,
    ROUND(s.fair_value_blended::numeric, 2) AS fair_value,
    ROUND(s.fair_value_dcf::numeric, 2) AS fair_value_dcf,
    ROUND(s.fair_value_pe::numeric, 2) AS fair_value_pe,
    ROUND(s.fair_value_ps::numeric, 2) AS fair_value_ps,
    ROUND(pe_ratio::numeric, 2) AS pe_ratio,
    ROUND(pb_ratio::numeric, 2) AS pb_ratio,
    ROUND(ps_ratio::numeric, 2) AS ps_ratio,
    model_agreement_score,
    applicable_models,
    CASE
        WHEN fair_value_blended > 10000 THEN 'EXTREME_FV'
        WHEN fair_value_blended < 0.1 THEN 'NEGATIVE_FV'
        WHEN ps_ratio > 1000 THEN 'EXTREME_PS'
        WHEN ps_ratio < 0 THEN 'NEGATIVE_PS'
        WHEN pe_ratio > 500 THEN 'EXTREME_PE'
        WHEN pe_ratio < 0 THEN 'NEGATIVE_PE'
        WHEN pb_ratio > 50 THEN 'EXTREME_PB'
        WHEN model_agreement_score < 0.3 THEN 'LOW_AGREEMENT'
        ELSE 'OTHER'
    END AS outlier_type
FROM symbol s
INNER JOIN LATERAL (
    SELECT DISTINCT ON (ticker) ticker, date, close
    FROM tickerdata
    WHERE tickerdata.ticker = s.ticker
    ORDER BY tickerdata.ticker, tickerdata.date DESC
) td ON td.ticker = s.ticker
WHERE s.islisted = true
  AND s.isstock = true
  AND (s.isetf IS NULL OR s.isetf = false)
  AND (
    -- Extreme fair values
    s.fair_value_blended > 10000
    OR s.fair_value_blended < 0.1
    -- Extreme multiples
    OR s.pe_ratio > 500 OR s.pe_ratio < 0
    OR s.pb_ratio > 50 OR s.pb_ratio < 0
    OR s.ps_ratio > 1000 OR s.ps_ratio < 0
    -- Low model agreement
    OR s.model_agreement_score < 0.3
  )
ORDER BY
    CASE
        WHEN s.fair_value_blended > 10000 THEN 1
        WHEN s.ps_ratio > 1000 THEN 2
        WHEN s.model_agreement_score < 0.3 THEN 3
        ELSE 4
    END,
    s.fair_value_blended DESC NULLS LAST;

COMMENT ON VIEW valuation_outliers IS '
Symbols with extreme valuations that likely have data quality issues.
These should be manually reviewed and either:
1. Fixed (correct model inputs)
2. Excluded from analysis (set divergence_flag = true)
3. Flagged for special handling (REITs, banks, etc.)
';

-- ==============================================================================
-- POTENTIAL STOCK SPLITS (Price vs Fair Value Mismatch)
-- ==============================================================================
DROP VIEW IF EXISTS potential_stock_splits CASCADE;
CREATE VIEW potential_stock_splits AS
SELECT
    s.ticker AS symbol,
    s.description,
    ROUND(td.close::numeric, 2) AS current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    model_agreement_score,
    s.valuation_updated_at::date AS valuation_date,
    ROUND((fair_value_blended / td.close)::numeric, 2) AS target_multiple,
    CASE
        WHEN fair_value_blended > td.close THEN 'fair_value_above_price'
        WHEN fair_value_blended < td.close THEN 'fair_value_below_price'
        ELSE 'in_line'
    END AS mismatch_direction,
    -- Calculate expected split ratio based on price mismatch in either direction
    CASE
        WHEN td.close > 0 AND fair_value_blended > 0
        THEN ROUND(GREATEST(fair_value_blended / td.close::numeric, td.close::numeric / fair_value_blended))
        ELSE NULL
    END AS implied_split_ratio,
    -- Common split ratios
    CASE
        WHEN td.close > 0 AND fair_value_blended > 0
             AND ROUND(GREATEST(fair_value_blended / td.close::numeric, td.close::numeric / fair_value_blended)) BETWEEN 2 AND 3 THEN '2:1 or 3:1 split/reverse split likely'
        WHEN td.close > 0 AND fair_value_blended > 0
             AND ROUND(GREATEST(fair_value_blended / td.close::numeric, td.close::numeric / fair_value_blended)) BETWEEN 4 AND 6 THEN '5:1 split/reverse split likely'
        WHEN td.close > 0 AND fair_value_blended > 0
             AND ROUND(GREATEST(fair_value_blended / td.close::numeric, td.close::numeric / fair_value_blended)) BETWEEN 9 AND 11 THEN '10:1 split/reverse split likely'
        WHEN td.close > 0 AND fair_value_blended > 0
             AND ROUND(GREATEST(fair_value_blended / td.close::numeric, td.close::numeric / fair_value_blended)) >= 15 THEN '15:1+ split/reverse split likely'
        ELSE 'Unknown or no split'
    END AS likely_split
FROM symbol s
INNER JOIN LATERAL (
    SELECT DISTINCT ON (ticker) ticker, date, close
    FROM tickerdata
    WHERE tickerdata.ticker = s.ticker
    ORDER BY tickerdata.ticker, tickerdata.date DESC
) td ON td.ticker = s.ticker
WHERE s.islisted = true
  AND s.isstock = true
  AND (s.isetf IS NULL OR s.isetf = false)
  AND s.fair_value_blended IS NOT NULL
  AND s.model_agreement_score >= 0.7  -- High agreement, so price mismatch = split
  AND (
      s.fair_value_blended / td.close >= 4.0
      OR s.fair_value_blended / td.close <= 0.25
  )
ORDER BY implied_split_ratio DESC;

COMMENT ON VIEW potential_stock_splits IS '
Symbols that may have undergone stock splits but fair values werent adjusted.
High model agreement (70%+) suggests models agree with each other, but fair value and current
price are far enough apart to require split/stale-data review. Includes fair-value-above-price
and fair-value-below-price cases.

Example: NFLX trading at $96 with $509 fair value = likely 5:1 split (was ~$480)
';

-- ==============================================================================
-- LOW MODEL COVERAGE (Need More Analysis)
-- ==============================================================================
DROP VIEW IF EXISTS low_model_coverage CASCADE;
CREATE VIEW low_model_coverage AS
SELECT
    s.ticker AS symbol,
    description,
    sector,
    industry,
    ROUND(td.close::numeric, 2) AS current_price,
    ROUND(mktcap::numeric, 2) AS mktcap,
    applicable_models,
    model_agreement_score,
    divergence_flag,
    valuation_updated_at::date AS last_analyzed
FROM symbol s
INNER JOIN LATERAL (
    SELECT DISTINCT ON (ticker) ticker, date, close
    FROM tickerdata
    WHERE tickerdata.ticker = s.ticker
    ORDER BY tickerdata.ticker, tickerdata.date DESC
) td ON td.ticker = s.ticker
WHERE s.islisted = true
  AND s.isstock = true
  AND (s.isetf IS NULL OR s.isetf = false)
  AND s.mktcap > 100000000  -- At least $100M market cap
  AND (
    s.applicable_models < 3  -- Less than 3 models apply
    OR s.model_agreement_score < 0.4  -- Models disagree
  )
ORDER BY applicable_models ASC, mktcap DESC;

COMMENT ON VIEW low_model_coverage IS '
Symbols with insufficient model coverage or high model disagreement.
These need:
1. More valuation models to be applicable
2. Manual review to resolve divergences
3. Potential tier classification updates
';

-- ==============================================================================
-- STALE ANALYSIS (Need Refresh)
-- ==============================================================================
DROP VIEW IF EXISTS stale_analysis CASCADE;
CREATE VIEW stale_analysis AS
SELECT
    s.ticker AS symbol,
    description,
    sector,
    ROUND(td.close::numeric, 2) AS current_price,
    mktcap,
    valuation_updated_at::date AS last_analyzed,
    CURRENT_DATE - valuation_updated_at::date AS days_since_analysis,
    CASE
        WHEN CURRENT_DATE - valuation_updated_at::date > 90 THEN 'CRITICAL'
        WHEN CURRENT_DATE - valuation_updated_at::date > 60 THEN 'STALE'
        WHEN CURRENT_DATE - valuation_updated_at::date > 30 THEN 'FADING'
        ELSE 'FRESH'
    END AS freshness_status,
    last_data_refresh
FROM symbol s
INNER JOIN LATERAL (
    SELECT DISTINCT ON (ticker) ticker, date, close
    FROM tickerdata
    WHERE tickerdata.ticker = s.ticker
    ORDER BY tickerdata.ticker, tickerdata.date DESC
) td ON td.ticker = s.ticker
WHERE s.islisted = true
  AND s.isstock = true
  AND (s.isetf IS NULL OR s.isetf = false)
  AND s.valuation_updated_at IS NOT NULL
  AND s.fair_value_blended IS NOT NULL
ORDER BY valuation_updated_at ASC;

COMMENT ON VIEW stale_analysis IS '
Symbols with stale analysis that need refreshing.
Prioritize:
- CRITICAL: 90+ days old
- STALE: 60-90 days old
- FADING: 30-60 days old
';

-- ==============================================================================
-- DATA QUALITY SUMMARY
-- ==============================================================================
DROP VIEW IF EXISTS data_quality_summary CASCADE;
CREATE VIEW data_quality_summary AS
SELECT
    (SELECT COUNT(*) FROM symbol WHERE islisted = true AND isstock = true) AS total_symbols,
    (SELECT COUNT(*) FROM symbol WHERE fair_value_blended IS NOT NULL AND islisted = true AND isstock = true) AS with_fair_value,
    (SELECT COUNT(*) FROM symbol WHERE model_agreement_score >= 0.7 AND islisted = true AND isstock = true) AS high_agreement,
    (SELECT COUNT(*) FROM symbol WHERE model_agreement_score < 0.3 AND islisted = true AND isstock = true) AS low_agreement,
    (SELECT COUNT(*) FROM valuation_outliers) AS total_outliers,
    (SELECT COUNT(*) FROM potential_stock_splits) AS potential_splits,
    (SELECT COUNT(DISTINCT sector) FROM symbol WHERE sector IS NOT NULL AND islisted = true AND isstock = true) AS sectors_covered;

COMMENT ON VIEW data_quality_summary IS '
Overall data quality metrics for the investment opportunities.
Run periodically to track data quality improvements.
';

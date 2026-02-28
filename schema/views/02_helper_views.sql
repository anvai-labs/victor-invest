-- Helper Views for Investment Opportunities
--
-- These views provide pre-filtered access to common investment scenarios.
--
-- Author: InvestiGator Team
-- Date: 2026-02-28

-- ==============================================================================
-- TOP UNDervalued Opportunities (Highest Upside)
-- ==============================================================================
DROP VIEW IF EXISTS top_undervalued_opportunities CASCADE;
CREATE VIEW top_undervalued_opportunities AS
SELECT *
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
  AND valuation_signal = 'UNDERVERUED'
  AND upside_pct >= 10  -- At least 10% upside
ORDER BY upside_pct DESC;

COMMENT ON VIEW top_undervalued_opportunities IS '
Top undervalued opportunities with minimum 10% upside.
Sorted by highest potential return.';

-- ==============================================================================
-- HIGH CONVICTION IDEAS (Agreement + Upside)
-- ==============================================================================
DROP VIEW IF EXISTS high_conviction_opportunities CASCADE;
CREATE VIEW high_conviction_opportunities AS
SELECT *
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
  AND model_agreement_score >= 0.7  -- 70%+ model agreement
  AND upside_pct >= 15
  AND NOT divergence_flag
  AND applicable_models >= 3
ORDER BY
    model_agreement_score DESC,
    upside_pct DESC;

COMMENT ON VIEW high_conviction_opportunities IS '
High conviction ideas where multiple valuation models agree (70%+ consensus)
AND there is significant upside (15%+). Best risk/reward opportunities.';

-- ==============================================================================
-- DEEP VALUE OPPORTUNITIES (Deeply Undervalued)
-- ==============================================================================
DROP VIEW IF EXISTS deep_value_opportunities CASCADE;
CREATE VIEW deep_value_opportunities AS
SELECT *
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
  AND valuation_signal = 'UNDERVERUED'
  AND upside_pct >= 30  -- Deep value territory
ORDER BY upside_pct DESC;

COMMENT ON VIEW deep_value_opportunities IS '
Deep value opportunities with 30%+ upside to fair value.
Higher risk but higher potential returns.';

-- ==============================================================================
-- QUALITY AT REASONABLE PRICE (QARP)
-- ==============================================================================
DROP VIEW IF EXISTS quality_at_reasonable_price CASCADE;
CREATE VIEW quality_at_reasonable_price AS
SELECT *
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
  AND model_agreement_score >= 0.8
  AND upside_pct BETWEEN 5 AND 25  -- Reasonable valuation
  AND fcf_margin >= 10  -- Decent profitability
  AND debt_to_equity < 100  -- Conservative leverage
ORDER BY
    model_agreement_score DESC,
    fcf_margin DESC,
    upside_pct DESC;

COMMENT ON VIEW quality_at_reasonable_price IS '
Quality companies at reasonable prices (QARP).
High model agreement (80%+) with moderate upside (5-25%)
and strong fundamentals (FCF margin 10%+, D/E < 100).';

-- ==============================================================================
-- SAAS / TECH OPPORTUNITIES (Rule of 40)
-- ==============================================================================
DROP VIEW IF EXISTS rule_of_40_opportunities CASCADE;
CREATE VIEW rule_of_40_opportunities AS
SELECT *
FROM investment_opportunities
WHERE rule_of_40_score IS NOT NULL
  AND rule_of_40_score >= 40  -- Healthy growth + margin
  AND fair_value_blended IS NOT NULL
ORDER BY
    rule_of_40_score DESC,
    upside_pct DESC;

COMMENT ON VIEW rule_of_40_opportunities IS '
SaaS/Tech opportunities using Rule of 40 framework.
Combines revenue growth rate and FCF margin to identify quality growth companies.';

-- ==============================================================================
-- SECTOR OPPORTUNITIES (Per Sector Breakdown)
-- ==============================================================================
DROP VIEW IF EXISTS sector_opportunities CASCADE;
CREATE VIEW sector_opportunities AS
SELECT
    sector,
    COUNT(*) AS total_symbols,
    COUNT(*) FILTER (WHERE fair_value_blended IS NOT NULL) AS analyzed_symbols,
    COUNT(*) FILTER (WHERE valuation_signal = 'UNDERVERUED') AS undervalued_count,
    AVG(upside_pct) FILTER (WHERE valuation_signal = 'UNDERVERUED') AS avg_upside_pct,
    AVG(model_agreement_score) FILTER (
        WHERE model_agreement_score IS NOT NULL
    ) AS avg_model_agreement,
    SUM(mktcap) FILTER (WHERE mktcap IS NOT NULL) AS total_market_cap
FROM investment_opportunities
WHERE sector IS NOT NULL
GROUP BY sector
ORDER BY avg_upside_pct DESC NULLS LAST;

COMMENT ON VIEW sector_opportunities IS '
Sector-level opportunity analysis.
Shows which sectors have the most undervalued opportunities and average upside.';

-- ==============================================================================
-- MARKET CAP TIER OPPORTUNITIES
-- ==============================================================================
DROP VIEW IF EXISTS market_cap_opportunities CASCADE;
CREATE VIEW market_cap_opportunities AS
SELECT
    COALESCE(market_cap_tier, 'Unknown') AS cap_tier,
    COUNT(*) AS total_symbols,
    COUNT(*) FILTER (WHERE fair_value_blended IS NOT NULL) AS analyzed_symbols,
    COUNT(*) FILTER (
        WHERE valuation_signal = 'UNDERVERUED' AND upside_pct >= 20
    ) AS deep_undervalued_count,
    AVG(upside_pct) FILTER (WHERE valuation_signal = 'UNDERVERUED') AS avg_upside_pct,
    AVG(model_agreement_score) FILTER (
        WHERE model_agreement_score IS NOT NULL
    ) AS avg_model_agreement
FROM investment_opportunities
GROUP BY COALESCE(market_cap_tier, 'Unknown')
ORDER BY
    CASE
        WHEN COALESCE(market_cap_tier, 'Unknown') = 'Mega Cap' THEN 1
        WHEN COALESCE(market_cap_tier, 'Unknown') = 'Large Cap' THEN 2
        WHEN COALESCE(market_cap_tier, 'Unknown') = 'Mid Cap' THEN 3
        WHEN COALESCE(market_cap_tier, 'Unknown') = 'Small Cap' THEN 4
        WHEN COALESCE(market_cap_tier, 'Unknown') = 'Micro Cap' THEN 5
        ELSE 6
    END;

COMMENT ON VIEW market_cap_opportunities IS '
Market cap tier breakdown of opportunities.
Shows opportunity density by company size.';

-- ==============================================================================
-- RECENTLY ANALYZED (Fresh Analysis)
-- ==============================================================================
DROP VIEW IF EXISTS recently_analyzed_opportunities CASCADE;
CREATE VIEW recently_analyzed_opportunities AS
SELECT *
FROM investment_opportunities
WHERE valuation_updated_at >= CURRENT_DATE - INTERVAL '7 days'
  AND fair_value_blended IS NOT NULL
ORDER BY valuation_updated_at DESC;

COMMENT ON VIEW recently_analyzed_opportunities IS '
Symbols with fresh analysis (updated within last 7 days).
Good for catching newly analyzed opportunities.';

-- ==============================================================================
-- WATCHLIST (Divergence Flags + Recent Updates)
-- ==============================================================================
DROP VIEW IF EXISTS divergence_watchlist CASCADE;
CREATE VIEW divergence_watchlist AS
SELECT *
FROM investment_opportunities
WHERE divergence_flag = true
   OR (
       applicable_models IS NOT NULL
       AND applicable_models < 3
       AND valuation_updated_at >= CURRENT_DATE - INTERVAL '14 days'
   )
ORDER BY
    divergence_flag DESC,
    valuation_updated_at DESC;

COMMENT ON VIEW divergence_watchlist IS '
Symbols requiring manual review due to model divergence
or low model coverage. Investigate these before investing.';

-- ==============================================================================
-- COMPREHENSIVE SCREENING VIEW
-- ==============================================================================
DROP VIEW IF EXISTS investment_screening CASCADE;
CREATE VIEW investment_screening AS
SELECT
    stockid,
    symbol,
    description,
    sector,
    industry,
    current_price,
    fair_value_blended,
    upside_pct,
    valuation_signal,
    model_agreement_score,
    rule_of_40_score,
    fcf_margin,
    pe_ratio,
    pb_ratio,
    mktcap,
    market_cap_tier,
    -- Screening flags (booleans for easy filtering)
    CASE
        WHEN upside_pct >= 30 THEN true
        ELSE false
    END AS is_deep_value,
    CASE
        WHEN model_agreement_score >= 0.8 AND upside_pct >= 15 THEN true
        ELSE false
    END AS is_high_conviction,
    CASE
        WHEN rule_of_40_score >= 40 THEN true
        ELSE false
    END AS is_rule_of_40_quality,
    CASE
        WHEN upside_pct <= -10 THEN true
        ELSE false
    END AS is_overvalued,
    CASE
        WHEN pct_below_52w_high >= 20 THEN true
        ELSE false
    END AS is_near_52w_low,
    valuation_updated_at,
    last_data_refresh
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL;

COMMENT ON VIEW investment_screening IS '
Flat screening view with boolean flags for common filters.
Easy to query: SELECT * FROM investment_screening WHERE is_high_conviction AND is_deep_value;';

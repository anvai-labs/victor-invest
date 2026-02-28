-- Investment Opportunities: Practical Queries
--
-- Common queries for finding investment opportunities using the views.
--
-- Author: InvestiGator Team
-- Date: 2026-02-28

-- ==============================================================================
-- TOP 20 UNDERVERUED OPPORTUNITIES
-- ==============================================================================
-- Find the top 20 undervalued stocks by upside percentage
SELECT
    symbol,
    description,
    sector,
    industry,
    current_price,
    fair_value_blended,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(mktcap::numeric, 2) AS mktcap,
    model_agreement_score,
    valuation_updated_at
FROM top_undervalued_opportunities
LIMIT 20;

-- ==============================================================================
-- HIGH CONVICTION IDEAS
-- ==============================================================================
-- Quality undervalued stocks where models agree (best risk/reward)
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(model_agreement_score::numeric, 3) AS agreement,
    applicable_models,
    ROUND(mktcap::numeric, 2) AS mktcap
FROM high_conviction_opportunities
LIMIT 20;

-- ==============================================================================
-- SECTOR-SPECIFIC OPPORTUNITIES
-- ==============================================================================
-- Find opportunities in specific sectors
-- Example: Technology
SELECT
    symbol,
    description,
    industry,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(pe_ratio::numeric, 2) AS pe_ratio,
    ROUND(fcf_margin::numeric, 2) AS fcf_margin
FROM investment_opportunities
WHERE sector = 'Technology'
  AND fair_value_blended IS NOT NULL
  AND valuation_signal = 'UNDERVERUED'
ORDER BY upside_pct DESC
LIMIT 20;

-- Example: Financials
SELECT
    symbol,
    description,
    industry,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(pb_ratio::numeric, 2) AS pb_ratio,
    ROUND(pe_ratio::numeric, 2) AS pe_ratio
FROM investment_opportunities
WHERE sector = 'Financials'
  AND fair_value_blended IS NOT NULL
  AND valuation_signal = 'UNDERVERUED'
ORDER BY upside_pct DESC
LIMIT 20;

-- ==============================================================================
-- MARKET CAP SPECIFIC
-- ==============================================================================
-- Small Cap opportunities (higher growth potential, higher risk)
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(mktcap::numeric, 2) AS mktcap,
    model_agreement_score
FROM investment_opportunities
WHERE mktcap BETWEEN 500000000 AND 2000000000  -- $500M - $2B
  AND fair_value_blended IS NOT NULL
  AND valuation_signal = 'UNDERVERUED'
ORDER BY upside_pct DESC
LIMIT 20;

-- ==============================================================================
-- NEAR 52-WEEK LOWS (BUYING OPPORTUNITIES)
-- ==============================================================================
-- Quality stocks near 52-week lows with significant upside
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(pct_below_52w_high::numeric, 2) AS pct_below_high,
    ROUND(low_52week::numeric, 2) AS low_52w,
    model_agreement_score
FROM investment_opportunities
WHERE pct_below_52w_high >= 20  -- At least 20% below 52-week high
  AND fair_value_blended IS NOT NULL
  AND model_agreement_score >= 0.6
ORDER BY pct_below_52w_high DESC
LIMIT 20;

-- ==============================================================================
-- SAAS / TECH BY RULE OF 40
-- ==============================================================================
-- Best SaaS/Tech companies by Rule of 40 score
SELECT
    symbol,
    description,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(rule_of_40_score::numeric, 2) AS rule_of_40,
    rule_of_40_classification,
    ROUND(fcf_margin::numeric, 2) AS fcf_margin,
    ROUND(revenue_growth_rate::numeric, 2) AS revenue_growth
FROM rule_of_40_opportunities
WHERE valuation_signal = 'UNDERVERUED'
ORDER BY rule_of_40_score DESC
LIMIT 20;

-- ==============================================================================
-- RECENT ANALYSIS UPDATES
-- ==============================================================================
-- Fresh analysis from last 3 days (new opportunities)
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    valuation_updated_at::date AS analyzed_date
FROM recently_analyzed_opportunities
WHERE valuation_signal = 'UNDERVERUED'
ORDER BY valuation_updated_at DESC
LIMIT 20;

-- ==============================================================================
-- DIVERGENCE WATCHLIST (MANUAL REVIEW NEEDED)
-- ==============================================================================
-- Symbols where models disagree - investigate before investing
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    applicable_models,
    model_agreement_score,
    divergence_flag,
    valuation_updated_at::date AS analyzed_date
FROM divergence_watchlist
ORDER BY
    applicable_models ASC,
    valuation_updated_at DESC
LIMIT 20;

-- ==============================================================================
-- SECTOR HEAT MAP
-- ==============================================================================
-- Which sectors have the most opportunity?
SELECT
    sector,
    analyzed_symbols,
    undervalued_count,
    ROUND(100.0 * undervalued_count / NULLIF(analyzed_symbols, 0)::numeric, 2) AS pct_undervalued,
    ROUND(avg_upside_pct::numeric, 2) AS avg_upside_pct,
    ROUND(avg_model_agreement::numeric, 3) AS avg_agreement
FROM sector_opportunities
ORDER BY avg_upside_pct DESC NULLS LAST;

-- ==============================================================================
-- SCREENING BY MULTIPLE CRITERIA
-- ==============================================================================
-- Example: Find high-quality undervalued SaaS companies
SELECT
    symbol,
    description,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(rule_of_40_score::numeric, 2) AS rule_of_40,
    model_agreement_score
FROM investment_screening
WHERE is_deep_value
  AND is_rule_of_40_quality
ORDER BY upside_pct DESC;

-- Example: Find large cap high conviction ideas
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct,
    ROUND(mktcap::numeric, 2) AS mktcap,
    model_agreement_score
FROM investment_screening
WHERE is_high_conviction
  AND mktcap > 10000000000  -- $10B+ market cap
ORDER BY upside_pct DESC;

-- ==============================================================================
-- COMPARISON: PRICE VS FAIR VALUE BANDS
-- ==============================================================================
-- Group symbols by valuation level
SELECT
    CASE
        WHEN upside_pct >= 50 THEN 'Deep Value (50%+)'
        WHEN upside_pct >= 30 THEN 'Undervalued (30-50%)'
        WHEN upside_pct >= 15 THEN 'Moderately Undervalued (15-30%)'
        WHEN upside_pct >= 0 THEN 'Fair Value (0-15%)'
        WHEN upside_pct >= -15 THEN 'Moderately Overvalued (-15 to 0%)'
        ELSE 'Overvalued (>15% downside)'
    END AS valuation_band,
    COUNT(*) AS symbol_count,
    ROUND(AVG(mktcap)::numeric, 2) AS avg_mktcap
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
GROUP BY valuation_band
ORDER BY
    CASE
        WHEN upside_pct >= 50 THEN 1
        WHEN upside_pct >= 30 THEN 2
        WHEN upside_pct >= 15 THEN 3
        WHEN upside_pct >= 0 THEN 4
        WHEN upside_pct >= -15 THEN 5
        ELSE 6
    END;

-- ==============================================================================
-- TOP PICKS BY COMPOSITE SCORE
-- ==============================================================================
-- Composite score: (upside * 0.4) + (model_agreement * 100 * 0.4) + (rule_of_40 * 0.2)
SELECT
    symbol,
    description,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside,
    ROUND(model_agreement_score::numeric, 3) AS agreement,
    ROUND(pe_ratio::numeric, 2) AS pe,
    ROUND(mktcap::numeric, 2) AS mktcap,
    ROUND(
        (upside_pct * 0.4) +
        (model_agreement_score * 100 * 0.4) +
        (COALESCE(rule_of_40_score, 0) * 0.2)
    , 2) AS composite_score
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
  AND mktcap > 500000000  -- Min $500M market cap
ORDER BY composite_score DESC
LIMIT 20;

-- ==============================================================================
-- MONITORING & ALERTS
-- ==============================================================================
-- Find symbols that might need re-analysis (old data, high volatility)
SELECT
    symbol,
    sector,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    valuation_updated_at::date,
    CURRENT_DATE - valuation_updated_at::date AS days_since_analysis,
    CASE
        WHEN CURRENT_DATE - valuation_updated_at::date > 90 THEN 'NEEDS_REFRESH'
        WHEN CURRENT_DATE - valuation_updated_at::date > 60 THEN 'SOON_NEEDED'
        ELSE 'FRESH'
    END AS refresh_status
FROM investment_opportunities
WHERE fair_value_blended IS NOT NULL
ORDER BY valuation_updated_at ASC;

-- Symbols with high recent upside (might be overbought)
SELECT
    symbol,
    description,
    sector,
    pct_above_52w_low,
    current_price,
    ROUND(fair_value_blended::numeric, 2) AS fair_value,
    ROUND(upside_pct::numeric, 2) AS upside_pct
FROM investment_opportunities
WHERE pct_above_52w_low >= 30  -- 30% above 52-week low
  AND pct_below_52w_high < 10  -- But not near 52-week high
ORDER BY pct_above_52w_low DESC;

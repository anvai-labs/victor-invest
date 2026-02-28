-- Investment Opportunities View
--
-- Joins symbol table with latest tickerdata to identify top investment opportunities.
-- This view provides real-time comparison of current price vs fair value analysis.
--
-- Usage:
--   SELECT * FROM investment_opportunities
--     WHERE fair_value_blended IS NOT NULL
--     ORDER BY upside_pct DESC;
--
-- Author: InvestiGator Team
-- Date: 2026-02-28

-- Drop existing view if it exists
DROP VIEW IF EXISTS investment_opportunities CASCADE;

-- Main investment opportunities view
CREATE VIEW investment_opportunities AS
SELECT
    -- Core Identification
    s.stockid,
    s.ticker AS symbol,

    -- Company Information
    s.description,
    s."Sector" AS sector,
    s."Industry" AS industry,
    s.exchange,
    s."Country",

    -- Pricing (Latest from tickerdata)
    td.close AS current_price,
    s.high_52week,
    s.low_52week,
    td.date AS price_date,

    -- Valuation Metrics (from analysis)
    s.fair_value_blended,
    s.fair_value_dcf,
    s.fair_value_ggm,
    s.fair_value_pe,
    s.fair_value_ps,
    s.fair_value_pb,
    s.fair_value_ev_ebitda,

    -- Opportunity Metrics (calculated)
    CASE
        WHEN s.fair_value_blended IS NOT NULL AND s.fair_value_blended > 0
        THEN s.fair_value_blended - td.close
        ELSE NULL
    END AS upside_amount,

    CASE
        WHEN s.fair_value_blended IS NOT NULL
             AND s.fair_value_blended > 0
             AND td.close > 0
        THEN ((s.fair_value_blended / td.close) - 1) * 100
        ELSE NULL
    END AS upside_pct,

    CASE
        WHEN s.fair_value_blended IS NOT NULL AND td.close > 0
        THEN CASE
            WHEN s.fair_value_blended > td.close THEN 'UNDERVERUED'
            WHEN s.fair_value_blended < td.close THEN 'OVERVALUED'
            ELSE 'FAIR_VALUE'
        END
        ELSE NULL
    END AS valuation_signal,

    -- Distance from 52-week high/low
    CASE
        WHEN s.high_52week IS NOT NULL AND s.high_52week > 0
        THEN ((s.high_52week / td.close) - 1) * 100
        ELSE NULL
    END AS pct_below_52w_high,

    CASE
        WHEN s.low_52week IS NOT NULL AND td.close > 0
        THEN ((td.close / s.low_52week) - 1) * 100
        ELSE NULL
    END AS pct_above_52w_low,

    -- Valuation Multiples
    s.pe_ratio,
    s.pb_ratio,
    s.ps_ratio,
    s.ev_ebitda_ratio,
    s.peg_ratio,

    -- Quality Metrics
    s.model_agreement_score,
    s.model_confidence,
    s.applicable_models,
    s.divergence_flag,
    s.data_quality_score,
    s.data_completeness_pct,

    -- Rule of 40 (for SaaS/Tech)
    s.rule_of_40_score,
    s.rule_of_40_classification,

    -- Financial Health
    s.revenue,
    s.net_income,
    s.ebitda,
    s.fcf_margin,
    s.debt_to_equity,
    s.revenue_growth_rate,

    -- Market Cap & Classification
    s.mktcap,
    s.market_cap_tier,
    s.sp500,
    s.nasdaq100,
    s.dow30,

    -- Index Memberships
    s.russell1000,
    s.russell2000,
    s.russell3000,
    s.sp400,
    s.sp600,

    -- Metadata
    s.fiscal_period,
    s.valuation_updated_at,
    s.last_data_refresh,
    s.metrics_updated_at,
    s.tier_classification,
    s.fallback_weights_used

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
  -- Filter out extreme outliers (data quality issues)
  AND (s.fair_value_blended IS NULL OR s.fair_value_blended BETWEEN 0.1 AND 10000)  -- Exclude extreme FVs
  AND (s.pe_ratio IS NULL OR s.pe_ratio BETWEEN -500 AND 500)  -- Exclude extreme P/E
  AND (s.pb_ratio IS NULL OR s.pb_ratio BETWEEN 0 AND 100)  -- Exclude extreme P/B
  AND (s.ps_ratio IS NULL OR s.ps_ratio BETWEEN 0 AND 5000)  -- Exclude extreme P/S
;

COMMENT ON VIEW investment_opportunities IS '
Investment opportunities view combining latest prices with fair value analysis.
Key fields:
- upside_pct: Percentage upside to fair value (primary sorting metric)
- valuation_signal: UNDERVERUED/OVERVALUED/FAIR_VALUE
- model_agreement_score: Higher = more model consensus (0-1)
- rule_of_40_score: Growth + margin score for SaaS companies
';

-- Note: Indexes cannot be created on views directly.
-- Consider adding these indexes to the underlying symbol table for better performance:
-- CREATE INDEX IF NOT EXISTS idx_symbol_fair_value_opportunities
--     ON symbol (fair_value_blended, mktcap, model_agreement_score)
--     WHERE fair_value_blended IS NOT NULL;

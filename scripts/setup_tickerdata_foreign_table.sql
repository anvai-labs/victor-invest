-- Populate shares_outstanding and market_cap columns in sec_companyfacts_processed
--
-- Uses existing foreign tables: public.tickerdata and public.symbol
-- (already set up via stock_server FDW)
--
-- Prerequisites:
--   1. Source credentials: source ~/.investigator/env
--   2. Connect to sec_database: PGPASSWORD=investigator psql -h dataserver1.singh.local -U investigator -d sec_database
--   3. Run: \i populate_shares_market_cap.sql
--
-- Foreign tables already exist:
--   public.tickerdata -> stock.tickerdata (via stock_server)
--   public.symbol -> stock.symbol (via stock_server)

-- ============================================================================
-- STEP 1: Populate shares_outstanding (exact date match)
-- ============================================================================
UPDATE sec_companyfacts_processed p
SET shares_outstanding = t.shares::BIGINT
FROM tickerdata t
WHERE UPPER(p.symbol) = UPPER(t.symbol)
  AND p.shares_outstanding IS NULL
  AND t.date = DATE(p.period_end_date)
  AND t.shares IS NOT NULL;

-- ============================================================================
-- STEP 2: Populate shares_outstanding (nearest ±7 days)
-- ============================================================================
UPDATE sec_companyfacts_processed p
SET shares_outstanding = subq.shares::BIGINT
FROM (
    SELECT p_inner.symbol, p_inner.period_end_date,
           (SELECT t.shares
            FROM tickerdata t
            WHERE UPPER(t.symbol) = UPPER(p_inner.symbol)
              AND t.date >= DATE(p_inner.period_end_date) - INTERVAL '7 days'
              AND t.date <= DATE(p_inner.period_end_date) + INTERVAL '7 days'
              AND t.shares IS NOT NULL
            ORDER BY ABS(t.date - DATE(p_inner.period_end_date))
            LIMIT 1) as shares
    FROM sec_companyfacts_processed p_inner
    WHERE p_inner.shares_outstanding IS NULL
) subq
WHERE UPPER(sec_companyfacts_processed.symbol) = UPPER(subq.symbol)
  AND sec_companyfacts_processed.period_end_date = subq.period_end_date
  AND sec_companyfacts_processed.shares_outstanding IS NULL
  AND subq.shares IS NOT NULL;

-- ============================================================================
-- STEP 3: Populate market_cap (price ~45 days after period end)
-- ============================================================================
UPDATE sec_companyfacts_processed p
SET market_cap = ROUND(subq.close * p.shares_outstanding)::BIGINT
FROM (
    SELECT p_inner.symbol, p_inner.period_end_date, p_inner.shares_outstanding,
           (SELECT t.close
            FROM tickerdata t
            WHERE UPPER(t.symbol) = UPPER(p_inner.symbol)
              AND t.date >= DATE(p_inner.period_end_date)
              AND t.date <= DATE(p_inner.period_end_date) + INTERVAL '90 days'
              AND t.close IS NOT NULL
            ORDER BY ABS(t.date - DATE(p_inner.period_end_date) - INTERVAL '45 days')
            LIMIT 1) as close
    FROM sec_companyfacts_processed p_inner
    WHERE p_inner.market_cap IS NULL
      AND p_inner.shares_outstanding IS NOT NULL
) subq
WHERE UPPER(sec_companyfacts_processed.symbol) = UPPER(subq.symbol)
  AND sec_companyfacts_processed.period_end_date = subq.period_end_date
  AND sec_companyfacts_processed.market_cap IS NULL
  AND subq.close IS NOT NULL;

-- ============================================================================
-- STEP 4: Calculate EPS (basic)
-- ============================================================================
UPDATE sec_companyfacts_processed
SET earnings_per_share = ROUND(net_income / shares_outstanding::NUMERIC, 6)
WHERE earnings_per_share IS NULL
  AND shares_outstanding IS NOT NULL
  AND shares_outstanding > 0
  AND net_income IS NOT NULL;

-- ============================================================================
-- STEP 5: Set diluted EPS = basic EPS (simplification)
-- ============================================================================
UPDATE sec_companyfacts_processed
SET earnings_per_share_diluted = earnings_per_share
WHERE earnings_per_share_diluted IS NULL
  AND earnings_per_share IS NOT NULL;

-- ============================================================================
-- STEP 6: Set weighted_average_diluted_shares_outstanding
-- ============================================================================
UPDATE sec_companyfacts_processed
SET weighted_average_diluted_shares_outstanding = shares_outstanding
WHERE weighted_average_diluted_shares_outstanding IS NULL
  AND shares_outstanding IS NOT NULL;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT
    COUNT(*) as total_rows,
    COUNT(shares_outstanding) as with_shares,
    COUNT(market_cap) as with_market_cap,
    COUNT(earnings_per_share) as with_eps,
    ROUND(100.0 * COUNT(shares_outstanding) / COUNT(*), 1) as shares_pct,
    ROUND(100.0 * COUNT(market_cap) / COUNT(*), 1) as market_cap_pct,
    ROUND(100.0 * COUNT(earnings_per_share) / COUNT(*), 1) as eps_pct
FROM sec_companyfacts_processed;

-- Sample verification
SELECT symbol, fiscal_year, fiscal_period,
       shares_outstanding, market_cap, earnings_per_share
FROM sec_companyfacts_processed
WHERE shares_outstanding IS NOT NULL
ORDER BY fiscal_year DESC, symbol
LIMIT 10;

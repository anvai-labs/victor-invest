-- Stock Splits Table Migration
-- Version: 1.0.0
-- Copyright (c) 2025 Vijaykumar Singh
-- Licensed under Apache License 2.0
--
-- This table tracks stock splits for accurate EPS comparisons across time
--
-- Key Concepts:
-- - Stock splits change shares outstanding proportionally
-- - EPS = Net Income / Shares Outstanding (actual shares, not split-adjusted)
-- - Pre-split and post-split EPS are NOT directly comparable
-- - This table enables split-adjusted EPS calculations
--
-- Usage:
--   PostgreSQL: psql -h HOST -U USER -d DATABASE -f schema/migrations/008_add_stock_splits_table.sql

-- ============================================================================
-- STOCK SPLITS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_splits (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    split_date DATE NOT NULL,
    split_ratio NUMERIC(10, 4) NOT NULL,  -- e.g., 20.0 for 20:1 split, 0.5 for 1:2 reverse split
    description TEXT,
    source VARCHAR(50) DEFAULT 'manual',  -- 'manual', 'sec_filing', 'api'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_symbol_split UNIQUE (symbol, split_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_stock_splits_symbol ON stock_splits(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_splits_date ON stock_splits(split_date);
CREATE INDEX IF NOT EXISTS idx_stock_splits_symbol_date ON stock_splits(symbol, split_date);

-- Comment for documentation
COMMENT ON TABLE stock_splits IS 'Tracks stock splits for split-adjusted EPS calculations';
COMMENT ON COLUMN stock_splits.split_ratio IS 'Split ratio (e.g., 20.0 = 20:1 split, 0.5 = 1:2 reverse split)';
COMMENT ON COLUMN stock_splits.description IS 'Optional description of the split event';

-- ============================================================================
-- INITIAL DATA: Known Major Stock Splits (2016-2025)
-- ============================================================================

-- Technology stocks
INSERT INTO stock_splits (symbol, split_date, split_ratio, description) VALUES
    ('AAPL', '2020-08-31', 4.0, '4-for-1 stock split'),
    ('AAPL', '2014-06-09', 7.0, '7-for-1 stock split'),
    ('GOOGL', '2022-07-18', 20.0, '20-for-1 stock split'),
    ('AMZN', '2022-06-06', 20.0, '20-for-1 stock split'),
    ('AMZN', '1999-09-02', 2.0, '2-for-1 stock split'),
    ('AMZN', '1998-06-01', 3.0, '3-for-1 stock split'),
    ('TSLA', '2020-08-31', 5.0, '5-for-1 stock split'),
    ('TSLA', '2022-08-25', 3.0, '3-for-1 stock split'),
    ('NVDA', '2021-07-20', 4.0, '4-for-1 stock split'),
    ('NVDA', '2006-09-10', 2.0, '2-for-1 stock split'),
    ('NVDA', '2001-04-24', 2.0, '2-for-1 stock split'),
    ('MSFT', '2003-02-18', 2.0, '2-for-1 stock split'),
    ('META', NULL, NULL, 'No splits as of 2025')
ON CONFLICT (symbol, split_date) DO NOTHING;

-- Other notable splits
INSERT INTO stock_splits (symbol, split_date, split_ratio, description) VALUES
    ('SHOP', '2022-06-29', 10.0, '10-for-1 stock split'),
    ('GAMESTOP', '2023-07-21', 4.0, '4-for-1 stock split via dividend'),
    ('DKNG', '2022-07-18', 10.0, '10-for-1 stock split')
ON CONFLICT (symbol, split_date) DO NOTHING;

-- ============================================================================
-- HELPER VIEW: Cumulative Split Ratios by Symbol
-- ============================================================================

CREATE OR REPLACE VIEW cumulative_split_ratios AS
SELECT
    symbol,
    split_date,
    split_ratio,
    -- Cumulative product of split ratios from this date forward
    EXP(SUM(LN(split_ratio)) OVER (PARTITION BY symbol ORDER BY split_date DESC)) AS cumulative_ratio_forward,
    -- Cumulative product of split ratios up to this date
    EXP(SUM(LN(split_ratio)) OVER (PARTITION BY symbol ORDER BY split_date ASC)) AS cumulative_ratio_backward,
    created_at
FROM stock_splits
WHERE split_date IS NOT NULL
ORDER BY symbol, split_date;

COMMENT ON VIEW cumulative_split_ratios IS 'Helper view for calculating cumulative split ratios for EPS adjustment';

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'stock_splits table created successfully';
    RAISE NOTICE 'Inserted known splits for: AAPL, GOOGL, AMZN, TSLA, NVDA, MSFT, SHOP, GAMESTOP, DKNG';
    RAISE NOTICE 'View cumulative_split_ratios created for split-adjusted calculations';
END $$;

-- Stock Splits Table Migration
-- This table tracks stock split events for split-adjusted valuation calculations
-- Created: 2026-02-21
-- Purpose: Enable accurate split adjustment in sector multiples historical calculations

-- Create stock_splits table in stock database
CREATE TABLE IF NOT EXISTS stock_splits (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    split_date DATE NOT NULL,
    split_ratio NUMERIC(10, 4) NOT NULL,
    -- split_ratio > 1.0 for forward splits (e.g., 4-for-1 = 4.0)
    -- split_ratio < 1.0 for reverse splits (e.g., 1-for-10 = 0.1)

    -- Metadata
    split_type VARCHAR(20) CHECK (split_type IN ('forward', 'reverse', 'stock_dividend')),
    description TEXT,

    -- Audit fields
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    source VARCHAR(100) DEFAULT 'manual',

    -- Constraints
    CONSTRAINT unique_split UNIQUE (symbol, split_date, split_ratio)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_stock_splits_symbol ON stock_splits(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_splits_date ON stock_splits(split_date);
CREATE INDEX IF NOT EXISTS idx_stock_splits_symbol_date ON stock_splits(symbol, split_date);

-- Add comments
COMMENT ON TABLE stock_splits IS 'Tracks stock split events for split-adjusted valuation calculations';
COMMENT ON COLUMN stock_splits.split_ratio IS 'Ratio > 1 for forward splits (e.g., 4-for-1 = 4.0), < 1 for reverse (e.g., 1-for-10 = 0.1)';

-- Insert known major splits (examples to be expanded)
-- NOTE: These are for illustration. Populate from reliable data source.
-- AAPL 4-for-1 split on Aug 31, 2020
INSERT INTO stock_splits (symbol, split_date, split_ratio, split_type, description, source)
VALUES
    ('AAPL', '2020-08-31', 4.0, 'forward', '4-for-1 stock split', 'SEC 10-K')
ON CONFLICT (symbol, split_date, split_ratio) DO NOTHING;

-- NVDA 4-for-1 split on Jul 20, 2021
INSERT INTO stock_splits (symbol, split_date, split_ratio, split_type, description, source)
VALUES
    ('NVDA', '2021-07-20', 4.0, 'forward', '4-for-1 stock split', 'SEC 10-K')
ON CONFLICT (symbol, split_date, split_ratio) DO NOTHING;

-- TSLA 5-for-1 split on Aug 31, 2020
INSERT INTO stock_splits (symbol, split_date, split_ratio, split_type, description, source)
VALUES
    ('TSLA', '2020-08-31', 5.0, 'forward', '5-for-1 stock split', 'SEC 10-K')
ON CONFLICT (symbol, split_date, split_ratio) DO NOTHING;

-- AMZN 20-for-1 split on Jun 6, 2022
INSERT INTO stock_splits (symbol, split_date, split_ratio, split_type, description, source)
VALUES
    ('AMZN', '2022-06-06', 20.0, 'forward', '20-for-1 stock split', 'SEC 10-K')
ON CONFLICT (symbol, split_date, split_ratio) DO NOTHING;

-- GOOGL 20-for-1 split on Jul 18, 2022
INSERT INTO stock_splits (symbol, split_date, split_ratio, split_type, description, source)
VALUES
    ('GOOGL', '2022-07-18', 20.0, 'forward', '20-for-1 stock split', 'SEC 10-K')
ON CONFLICT (symbol, split_date, split_ratio) DO NOTHING;

-- SHOP 10-for-1 split on Jun 28, 2022
INSERT INTO stock_splits (symbol, split_date, split_ratio, split_type, description, source)
VALUES
    ('SHOP', '2022-06-28', 10.0, 'forward', '10-for-1 stock split', 'SEC 10-K')
ON CONFLICT (symbol, split_date, split_ratio) DO NOTHING;

-- Create a view for easy querying
CREATE OR REPLACE VIEW v_recent_splits AS
SELECT
    symbol,
    split_date,
    split_ratio,
    split_type,
    description,
    CASE
        WHEN split_ratio > 1 THEN CONCAT(ROUND(split_ratio::numeric, 1), '-for-1')
        WHEN split_ratio < 1 THEN CONCAT('1-for-', ROUND(1/split_ratio::numeric, 0))
        ELSE '1:1'
    END as split_readable,
    EXTRACT(DAYS FROM NOW() - split_date) as days_ago
FROM stock_splits
WHERE split_date >= CURRENT_DATE - INTERVAL '2 years'
ORDER BY split_date DESC;

COMMENT ON VIEW v_recent_splits IS 'Recent stock splits in the last 2 years with readable format';

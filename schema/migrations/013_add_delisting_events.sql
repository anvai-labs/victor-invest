-- Migration 013: Add delisting_events table
-- Created: 2026-06-14
-- Description: Records terminal (delisting) events so the RL backtest can model a
--              delisting as a realized loss-bearing exit instead of silently
--              dropping the observation when tickerdata rows stop. This removes the
--              delisting half of survivorship bias (finding C).
--
-- Modeled on stock_splits (migration 008): event-dated rows, source provenance,
-- idempotent guards.

CREATE TABLE IF NOT EXISTS delisting_events (
    id                  SERIAL PRIMARY KEY,
    symbol              VARCHAR(20) NOT NULL,
    delist_date         DATE NOT NULL,
    reason              VARCHAR(64),            -- bankruptcy|acquired|compliance|voluntary|unknown
    last_price          NUMERIC(12, 2),         -- last traded price before delisting
    recovery_assumption NUMERIC(5, 4) DEFAULT 0.0,  -- fraction of last_price realized at exit
    acquirer_symbol     VARCHAR(20),            -- for mergers (reserved for future use)
    source              VARCHAR(64) NOT NULL DEFAULT 'unknown',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, delist_date)
);

CREATE INDEX IF NOT EXISTS idx_delisting_symbol ON delisting_events (symbol);
CREATE INDEX IF NOT EXISTS idx_delisting_date ON delisting_events (delist_date);

COMMENT ON TABLE delisting_events IS 'Terminal delisting events used to model loss-bearing exits in backtests (survivorship-bias fix, finding C)';
COMMENT ON COLUMN delisting_events.delist_date IS 'Effective/notification delisting date (e.g. SEC Form 25 filing date)';
COMMENT ON COLUMN delisting_events.last_price IS 'Last traded close before delist_date';
COMMENT ON COLUMN delisting_events.recovery_assumption IS 'Fraction of last_price realized at terminal exit (0 = total loss, 1 = acquired at last price)';
COMMENT ON COLUMN delisting_events.reason IS 'bankruptcy | acquired | compliance | voluntary | unknown';

INSERT INTO schema_version (version, description)
VALUES ('7.0.8', 'Migration 013: Add delisting_events table for survivorship-free backtests')
ON CONFLICT (version) DO NOTHING;

DO $$
BEGIN
    RAISE NOTICE '✅ Migration 013 complete: delisting_events table created';
END $$;

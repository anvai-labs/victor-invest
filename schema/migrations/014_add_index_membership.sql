-- Migration 014: Add index_membership table
-- Created: 2026-06-14
-- Description: Point-in-time index constituent membership with effective/removal
--              dates, so a backtest can select the names that were ACTUALLY members
--              as of a past date — including names later delisted. Removes the
--              selection half of survivorship bias (finding C).
--
-- Source-agnostic: populate from any feed (Sharadar/Norgate/CRSP) or a free
-- reconstruction (e.g. historical S&P change lists) via the CSV loader. The
-- `source` column records provenance so mixed-fidelity data stays auditable.
--
-- Modeled on stock_splits / delisting_events: event-dated rows, source provenance,
-- idempotent guards.

CREATE TABLE IF NOT EXISTS index_membership (
    id             SERIAL PRIMARY KEY,
    symbol         VARCHAR(20) NOT NULL,
    index_name     VARCHAR(32) NOT NULL,       -- sp500 | russell1000 | nasdaq100 | ...
    effective_date DATE NOT NULL,              -- date added to the index
    removal_date   DATE,                       -- date removed (NULL = still a member)
    source         VARCHAR(64) NOT NULL DEFAULT 'unknown',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, index_name, effective_date)
);

CREATE INDEX IF NOT EXISTS idx_index_membership_index ON index_membership (index_name);
CREATE INDEX IF NOT EXISTS idx_index_membership_symbol ON index_membership (symbol);
-- Supports "members as of D": effective_date <= D AND (removal_date IS NULL OR removal_date > D)
CREATE INDEX IF NOT EXISTS idx_index_membership_window ON index_membership (index_name, effective_date, removal_date);

COMMENT ON TABLE index_membership IS 'Point-in-time index constituent membership (survivorship-free universe, finding C)';
COMMENT ON COLUMN index_membership.effective_date IS 'Date the symbol was added to the index';
COMMENT ON COLUMN index_membership.removal_date IS 'Date removed from the index; NULL means still a member';
COMMENT ON COLUMN index_membership.source IS 'Provenance of the membership record (feed name or reconstruction method)';

INSERT INTO schema_version (version, description)
VALUES ('7.0.9', 'Migration 014: Add index_membership table for point-in-time universe selection')
ON CONFLICT (version) DO NOTHING;

DO $$
BEGIN
    RAISE NOTICE '✅ Migration 014 complete: index_membership table created';
END $$;

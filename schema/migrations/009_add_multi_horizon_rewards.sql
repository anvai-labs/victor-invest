-- Migration 009: Add multi-horizon reward columns
-- Created: 2026-02-23
-- Description: Adds columns for 180d, 548d, 730d, 1095d rewards and prices
--              to support training horizon-specific RL policies
--
-- This migration enables:
-- 1. Training separate policies for different holding periods (6m, 18m, 24m, 36m)
-- 2. Comparing which valuation models work best at different horizons
-- 3. Hypothesis: DCF/GGM become more predictive at longer horizons (365+ days)

-- ============================================================================
-- VALUATION_OUTCOMES - Add multi-horizon price and reward columns
-- ============================================================================

-- Add 180-day (6-month) price and reward
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'actual_price_180d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN actual_price_180d NUMERIC(12,2);
        RAISE NOTICE '✅ Added actual_price_180d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'reward_180d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN reward_180d NUMERIC(5,3);
        RAISE NOTICE '✅ Added reward_180d column';
    END IF;
END $$;

-- Add 548-day (18-month) price and reward
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'actual_price_548d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN actual_price_548d NUMERIC(12,2);
        RAISE NOTICE '✅ Added actual_price_548d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'reward_548d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN reward_548d NUMERIC(5,3);
        RAISE NOTICE '✅ Added reward_548d column';
    END IF;
END $$;

-- Add 730-day (24-month / 2-year) price and reward
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'actual_price_730d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN actual_price_730d NUMERIC(12,2);
        RAISE NOTICE '✅ Added actual_price_730d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'reward_730d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN reward_730d NUMERIC(5,3);
        RAISE NOTICE '✅ Added reward_730d column';
    END IF;
END $$;

-- Add 1095-day (36-month / 3-year) price and reward
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'actual_price_1095d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN actual_price_1095d NUMERIC(12,2);
        RAISE NOTICE '✅ Added actual_price_1095d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'reward_1095d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN reward_1095d NUMERIC(5,3);
        RAISE NOTICE '✅ Added reward_1095d column';
    END IF;
END $$;

-- Add exit dates for new holding periods
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'exit_date_180d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN exit_date_180d DATE;
        RAISE NOTICE '✅ Added exit_date_180d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'exit_date_548d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN exit_date_548d DATE;
        RAISE NOTICE '✅ Added exit_date_548d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'exit_date_730d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN exit_date_730d DATE;
        RAISE NOTICE '✅ Added exit_date_730d column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'exit_date_1095d'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN exit_date_1095d DATE;
        RAISE NOTICE '✅ Added exit_date_1095d column';
    END IF;
END $$;

-- Add multi_period_rewards JSONB column for consolidated storage
-- This will contain all rewards in one place: {"1m": 0.5, "3m": 0.3, "6m": 0.2, ...}
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'multi_period_rewards'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN multi_period_rewards JSONB;
        RAISE NOTICE '✅ Added multi_period_rewards column';
    END IF;
END $$;

-- ============================================================================
-- INDEXES - Add indexes for multi-horizon queries
-- ============================================================================

-- Index for 180-day reward queries (6-month horizon training)
CREATE INDEX IF NOT EXISTS idx_outcomes_reward_180d
ON valuation_outcomes(reward_180d)
WHERE reward_180d IS NOT NULL;

-- Index for 548-day reward queries (18-month horizon training)
CREATE INDEX IF NOT EXISTS idx_outcomes_reward_548d
ON valuation_outcomes(reward_548d)
WHERE reward_548d IS NOT NULL;

-- Index for 730-day reward queries (2-year horizon training)
CREATE INDEX IF NOT EXISTS idx_outcomes_reward_730d
ON valuation_outcomes(reward_730d)
WHERE reward_730d IS NOT NULL;

-- Index for 1095-day reward queries (3-year horizon training)
CREATE INDEX IF NOT EXISTS idx_outcomes_reward_1095d
ON valuation_outcomes(reward_1095d)
WHERE reward_1095d IS NOT NULL;

-- GIN index for multi_period_rewards JSONB column
CREATE INDEX IF NOT EXISTS idx_outcomes_multi_period_rewards_gin
ON valuation_outcomes USING GIN (multi_period_rewards);

-- ============================================================================
-- CONSTRAINTS - Add comments for documentation
-- ============================================================================

COMMENT ON COLUMN valuation_outcomes.actual_price_180d IS 'Actual stock price 180 days (6 months) after analysis_date';
COMMENT ON COLUMN valuation_outcomes.reward_180d IS 'Risk-adjusted reward for 180-day holding period (-1 to 1)';
COMMENT ON COLUMN valuation_outcomes.exit_date_180d IS 'Exit date for 180-day holding period (analysis_date + 180 days)';

COMMENT ON COLUMN valuation_outcomes.actual_price_548d IS 'Actual stock price 548 days (18 months) after analysis_date';
COMMENT ON COLUMN valuation_outcomes.reward_548d IS 'Risk-adjusted reward for 548-day holding period (-1 to 1)';
COMMENT ON COLUMN valuation_outcomes.exit_date_548d IS 'Exit date for 548-day holding period (analysis_date + 548 days)';

COMMENT ON COLUMN valuation_outcomes.actual_price_730d IS 'Actual stock price 730 days (24 months / 2 years) after analysis_date';
COMMENT ON COLUMN valuation_outcomes.reward_730d IS 'Risk-adjusted reward for 730-day holding period (-1 to 1)';
COMMENT ON COLUMN valuation_outcomes.exit_date_730d IS 'Exit date for 730-day holding period (analysis_date + 730 days)';

COMMENT ON COLUMN valuation_outcomes.actual_price_1095d IS 'Actual stock price 1095 days (36 months / 3 years) after analysis_date';
COMMENT ON COLUMN valuation_outcomes.reward_1095d IS 'Risk-adjusted reward for 1095-day holding period (-1 to 1)';
COMMENT ON COLUMN valuation_outcomes.exit_date_1095d IS 'Exit date for 1095-day holding period (analysis_date + 1095 days)';

COMMENT ON COLUMN valuation_outcomes.multi_period_rewards IS 'Consolidated rewards for all holding periods in JSONB format: {"1m": 0.5, "3m": 0.3, "6m": 0.2, "12m": 0.1, "18m": 0.05, "24m": 0.02, "36m": 0.01}';

-- ============================================================================
-- VERSION UPDATE
-- ============================================================================

INSERT INTO schema_version (version, description)
VALUES ('7.0.6', 'Migration 009: Add multi-horizon reward columns for 180d, 548d, 730d, 1095d')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- SUMMARY
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '✅ Migration 009 complete: Added multi-horizon reward columns';
    RAISE NOTICE '   - Added: actual_price_180d, reward_180d, exit_date_180d';
    RAISE NOTICE '   - Added: actual_price_548d, reward_548d, exit_date_548d';
    RAISE NOTICE '   - Added: actual_price_730d, reward_730d, exit_date_730d';
    RAISE NOTICE '   - Added: actual_price_1095d, reward_1095d, exit_date_1095d';
    RAISE NOTICE '   - Added: multi_period_rewards JSONB column';
    RAISE NOTICE '   - Created indexes for efficient horizon-specific queries';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Re-run RL backtest to populate new columns';
    RAISE NOTICE '  2. Train horizon-specific policies (90d, 180d, 365d, 730d)';
    RAISE NOTICE '  3. Compare learned weights across horizons';
END $$;

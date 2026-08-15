-- Migration 012: Add RL evaluation-integrity columns
-- Created: 2026-06-14
-- Description: Adds columns required to make RL backtest rows valid training labels:
--   - position_predicted_fv : synthetic/predicted fair value that produced this
--                             position's reward (keeps features and label coherent
--                             for the contrastive LONG/SHORT dataset)
--   - conviction_band       : fractional band used to derive the synthetic FV
--   - data_quality_score    : 0-100 data-quality score for training-set filtering
--   - model_agreement_score : 0-100 cross-model agreement score
--   - sources_failed        : count of data sources that failed during enrichment
--   - survivorship_flag     : True if universe selection may carry survivorship bias
--
-- See docs/audits/2026-06-14-rl-backtest-and-convergence-audit.md (findings B, C, D).

-- ============================================================================
-- VALUATION_OUTCOMES - Add evaluation-integrity / provenance columns
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'position_predicted_fv'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN position_predicted_fv NUMERIC(12,2);
        RAISE NOTICE '✅ Added position_predicted_fv column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'conviction_band'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN conviction_band NUMERIC(5,4);
        RAISE NOTICE '✅ Added conviction_band column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'data_quality_score'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN data_quality_score NUMERIC(5,2);
        RAISE NOTICE '✅ Added data_quality_score column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'model_agreement_score'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN model_agreement_score NUMERIC(5,2);
        RAISE NOTICE '✅ Added model_agreement_score column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'sources_failed'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN sources_failed INTEGER;
        RAISE NOTICE '✅ Added sources_failed column';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'valuation_outcomes' AND column_name = 'survivorship_flag'
    ) THEN
        ALTER TABLE valuation_outcomes ADD COLUMN survivorship_flag BOOLEAN DEFAULT FALSE;
        RAISE NOTICE '✅ Added survivorship_flag column';
    END IF;
END $$;

-- ============================================================================
-- INDEXES - Support training-quality filtering
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_outcomes_data_quality
ON valuation_outcomes(data_quality_score)
WHERE data_quality_score IS NOT NULL;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON COLUMN valuation_outcomes.position_predicted_fv IS 'Synthetic/predicted fair value that produced this position''s reward (coherent feature/label for the contrastive LONG/SHORT dataset)';
COMMENT ON COLUMN valuation_outcomes.conviction_band IS 'Fractional band used to derive the synthetic predicted fair value (e.g. 0.10 = +/-10%)';
COMMENT ON COLUMN valuation_outcomes.data_quality_score IS '0-100 data-quality score at recording time; used to filter the training set';
COMMENT ON COLUMN valuation_outcomes.model_agreement_score IS '0-100 cross-model valuation agreement score';
COMMENT ON COLUMN valuation_outcomes.sources_failed IS 'Count of data sources that failed during feature enrichment';
COMMENT ON COLUMN valuation_outcomes.survivorship_flag IS 'True when the universe selection may carry survivorship bias (e.g. currently-listed-only)';

-- ============================================================================
-- VERSION UPDATE
-- ============================================================================

INSERT INTO schema_version (version, description)
VALUES ('7.0.7', 'Migration 012: Add RL evaluation-integrity columns (synthetic FV, data quality, survivorship)')
ON CONFLICT (version) DO NOTHING;

DO $$
BEGIN
    RAISE NOTICE '✅ Migration 012 complete: RL evaluation-integrity columns added';
END $$;

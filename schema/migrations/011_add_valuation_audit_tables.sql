-- Auditable fair-value run history.
--
-- The stock.symbol table remains the current screening snapshot. These tables
-- preserve valuation run inputs, outputs, policy decisions, and per-model rows
-- so fair value screens can be audited historically.

CREATE TABLE IF NOT EXISTS valuation_runs (
    valuation_run_id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    run_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_completed_at TIMESTAMPTZ,
    analysis_mode TEXT NOT NULL,
    valuation_basis TEXT,
    forward_horizon TEXT,
    current_price NUMERIC,
    blended_fair_value NUMERIC,
    expected_return_pct NUMERIC,
    data_quality_score NUMERIC,
    model_agreement_score NUMERIC,
    dispersion_ratio NUMERIC,
    applicable_models INTEGER,
    decision_action TEXT,
    decision_confidence TEXT,
    decision_score NUMERIC,
    guardrails_triggered JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_freshness_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_valuation_runs_symbol_completed
ON valuation_runs (symbol, run_completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_valuation_runs_decision
ON valuation_runs (decision_action, decision_confidence);

CREATE TABLE IF NOT EXISTS valuation_model_outputs (
    valuation_model_output_id BIGSERIAL PRIMARY KEY,
    valuation_run_id BIGINT NOT NULL REFERENCES valuation_runs(valuation_run_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    applicable BOOLEAN NOT NULL DEFAULT false,
    fair_value_per_share NUMERIC,
    weight NUMERIC,
    confidence NUMERIC,
    assumptions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_valuation_model_outputs_run
ON valuation_model_outputs (valuation_run_id);

CREATE INDEX IF NOT EXISTS idx_valuation_model_outputs_model
ON valuation_model_outputs (model_name, applicable);

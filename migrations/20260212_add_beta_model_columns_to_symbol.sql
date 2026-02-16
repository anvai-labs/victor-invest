-- Migration: Add canonical beta-model columns to symbol table
-- Purpose:
-- 1) Keep legacy b_12_month / r2_12_month untouched for backward compatibility
-- 2) Store additional 12M beta model variants for valuation selection
-- 3) Keep detailed point-in-time history in symbol_beta_models table

ALTER TABLE symbol
    ADD COLUMN IF NOT EXISTS beta_fundamental DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS beta_fundamental_12m DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS beta_ff6_12m DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS r2_ff6_12m DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS beta_blended_12m DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS r2_blended_12m DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS beta_model_updated_at TIMESTAMP;

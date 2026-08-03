# Fair Value and Agentic Workflow LLD

**Date:** 2026-05-20

## Purpose

This design turns the platform review findings into a low-level implementation plan. The goal is to make Victor Invest a deterministic fair-value and technical-analysis platform with a controlled agentic layer for synthesis, comparison, and explanation.

The main product invariant is:

> Investment decisions must be derived from deterministic evidence first. LLM output can explain, compare, and challenge the result, but must not silently override fair value, technical setup, data quality, or model disagreement constraints.

## Scope

In scope:

- one shared decision policy for CLI, API, UI rankings, batch screens, and reports
- Victor-first workflow routing and parity with legacy analysis options
- contract-boundary alignment with `../codingagent`
- valuation persistence model for current screening and historical audit
- UI/API contract changes needed to expose fair value quality correctly
- comprehensive TDD plan with narrow, surgical edits

Out of scope for the first implementation slice:

- live brokerage execution
- paid option-chain providers
- full replacement of legacy `src/investigator` internals
- broad UI redesign

## Current-State Problems

### P1: Recommendation and Fair Value Can Disagree

The current analysis can surface contradictory output such as a sell recommendation beside positive fair value upside and constructive technical/fundamental readings. The root cause is split responsibility:

- valuation models compute fair value and expected return
- technical analysis computes trend and momentum
- synthesizer or LLM-derived recommendation selects the headline action
- CLI/API/UI formatters each choose fields from slightly different places

### P1: Victor-First Is Not Fully True

`cli_orchestrator.py` forwards to `victor_invest` only for narrow defaults. Important production options such as force refresh, verbose detail, beta source, and valuation basis still use legacy orchestration.

### P1: Codingagent Boundary Is Mixed

The vertical plugin entry point is present, but standalone app/runtime imports are mixed into the same package surface. `../codingagent` expects external verticals to depend on `victor-contracts` at the plugin boundary, with `victor-ai` used by runtime hosts.

### P1: Generated Runtime State Is Under Source Tree

`victor_invest/workflows/.victor/` contains generated project DB, lock, WAL, SHM, and Lance embedding files. These should not ship as source or affect reproducibility.

### P2: Fair Value Persistence Is Current-State Only

The `symbol` table is efficient for current screens, but it overwrites run history. There is no normalized audit table that records model inputs, model outputs, source freshness, policy decisions, and LLM synthesis for each valuation run.

## Target Architecture

```text
CLI / API / UI / Batch
        |
        v
victor_invest orchestration
        |
        +--> deterministic data fetch
        |       SEC, tickerdata, macro/FRED, metadata
        |
        +--> deterministic analysis
        |       valuation models, TA, data quality, model agreement
        |
        +--> DecisionPolicy
        |       action, confidence, guardrails, explanation inputs
        |
        +--> optional LLM synthesis
        |       narrative only; cannot silently change policy action
        |
        +--> persistence
                symbol current snapshot
                valuation_runs audit trail
                valuation_model_outputs per-model rows
```

## Design Principles

- `symbol` remains the fast current screening surface.
- Historical/auditable valuation data lives in normalized run tables.
- Every user-visible recommendation comes from one policy module.
- LLM synthesis receives the policy result and may attach dissent, not override.
- Victor plugin code remains contract-only where possible.
- Runtime bootstrap remains optional and isolated to CLI/API/standalone paths.
- All migrations and behavioral changes are tested before implementation.

## Component Design

### 1. Decision Policy

Add a shared deterministic module:

```text
src/investigator/domain/services/investment_decision_policy.py
```

Primary types:

```python
@dataclass(frozen=True)
class DecisionInputs:
    symbol: str
    current_price: float | None
    fair_value: float | None
    expected_return_pct: float | None
    technical_score: float | None
    technical_signal: str | None
    model_agreement_score: float | None
    dispersion_ratio: float | None
    data_quality_score: float | None
    applicable_models: int | None
    valuation_age_hours: float | None
    divergence_flag: bool = False
    split_suspect: bool = False
    llm_recommendation: str | None = None

@dataclass(frozen=True)
class DecisionOutput:
    action: str
    confidence: str
    score: float
    expected_return_pct: float | None
    guardrails_triggered: tuple[str, ...]
    evidence: dict[str, Any]
```

Action vocabulary:

- `STRONG_BUY`
- `BUY`
- `HOLD`
- `SELL`
- `STRONG_SELL`
- `REVIEW`

`REVIEW` is a first-class output when data is too contradictory or stale for a clean investment call.

Policy outline:

```text
hard guards:
  missing current price or fair value -> REVIEW
  split suspect or divergence flag -> REVIEW
  data_quality below floor -> REVIEW or downgrade confidence
  model agreement below floor -> downgrade confidence or REVIEW
  valuation stale beyond limit -> REVIEW

valuation score:
  expected return >= 25% -> strong positive
  12% to 25% -> positive
  -10% to 12% -> neutral
  -25% to -10% -> negative
  <= -25% -> strong negative

technical modifier:
  bullish setup confirms positive valuation
  bearish setup reduces confidence or action
  extreme overbought/oversold becomes evidence, not an override by itself

contradiction handling:
  positive FV but bearish TA -> HOLD or REVIEW
  negative FV but bullish TA -> HOLD or REVIEW
  LLM opposite deterministic policy -> keep policy, record dissent
```

Initial thresholds should be constants, then moved to config after tests stabilize:

```python
MIN_DATA_QUALITY = 60.0
MIN_MODEL_AGREEMENT = 0.35
MAX_DISPERSION = 0.75
MAX_VALUATION_AGE_HOURS = 24 * 30
STRONG_BUY_UPSIDE = 25.0
BUY_UPSIDE = 12.0
SELL_DOWNSIDE = -10.0
STRONG_SELL_DOWNSIDE = -25.0
```

### 2. Policy Adapters

Adapters convert existing payload shapes into `DecisionInputs`:

```text
src/investigator/application/decision_input_extractor.py
```

Entry points:

- `from_legacy_analysis_result(results: dict) -> DecisionInputs`
- `from_victor_workflow_state(state: dict) -> DecisionInputs`
- `from_symbol_ranking_row(row: Mapping[str, Any]) -> DecisionInputs`
- `from_ui_cache_summary(summary: dict) -> DecisionInputs`

This keeps the policy pure and avoids spreading JSON-path fallback logic into the policy itself.

### 3. CLI Integration

Current problem: CLI summary prints recommendation and valuation fields assembled from separate formatter outputs.

Change:

- compute `DecisionOutput` after result formatting
- print policy `action` and `confidence`
- print LLM recommendation separately only when it differs
- include guardrails in compact/verbose JSON

Affected areas:

- `cli_orchestrator.py`
- `src/investigator/application/result_formatter.py`
- `victor_invest/cli.py`

The first surgical edit should preserve legacy output shape while adding:

```json
"decision_policy": {
  "action": "BUY",
  "confidence": "MEDIUM",
  "guardrails_triggered": [],
  "score": 68.5
}
```

### 4. Victor Workflow Integration

Current rule-based synthesis in `victor_invest/workflows/graphs.py` computes its own composite score and action.

Change:

- replace local recommendation thresholding with `DecisionPolicy`
- keep local composite score only as supporting evidence
- pass `decision_policy` to LLM synthesis
- LLM synthesis output may include:
  - `narrative_recommendation`
  - `dissent`
  - `risks`
  - `catalysts`
- final top-level recommendation remains policy-derived

Affected areas:

- `victor_invest/workflows/graphs.py`
- `victor_invest/handlers.py`
- `victor_invest/workflows/*.yaml` only if context keys need explicit mapping

### 5. API and UI Ranking Integration

Current ranking payload reads `fair_value_blended` from `symbol`, latest price from `tickerdata`, filters on quality/agreement/dispersion, then ranks by expected return.

Change:

- build `DecisionInputs` for each rankable row
- add `decision_policy` to each entry
- rank long candidates by policy action tier, expected return, model agreement, data quality, and technical score
- keep current expected-return rankings as a secondary field

API additions per ranked item:

```json
{
  "decision_action": "BUY",
  "decision_confidence": "MEDIUM",
  "decision_score": 67.2,
  "guardrails_triggered": [],
  "llm_dissent": null
}
```

Affected areas:

- `victor_invest/api/app.py`
- `frontend/src/lib/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/components/rankings/RankingsTab.tsx`

### 6. Valuation Persistence

Keep current snapshot columns on `symbol`:

- `fair_value_blended`
- model-specific fair values
- `model_agreement_score`
- `model_confidence`
- `applicable_models`
- `valuation_updated_at`
- `valuation_models_json`
- `data_quality_score`

Add audit tables in `sec_database`:

```sql
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

CREATE TABLE IF NOT EXISTS valuation_model_outputs (
    valuation_model_output_id BIGSERIAL PRIMARY KEY,
    valuation_run_id BIGINT NOT NULL REFERENCES valuation_runs(valuation_run_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    applicable BOOLEAN NOT NULL DEFAULT false,
    fair_value_per_share NUMERIC,
    weight NUMERIC,
    confidence NUMERIC,
    assumptions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes_json JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_valuation_model_outputs_run
ON valuation_model_outputs (valuation_run_id);
```

Persistence write path:

- valuation computation produces model summary
- policy evaluates decision
- `symbol` current snapshot updates
- run tables insert audit row and model rows

Failure behavior:

- if audit write fails, analysis should continue but surface warning
- if symbol update fails, analysis should continue but surface warning
- if both fail, CLI/API response must include persistence warning

### 7. Victor/Codingagent Boundary

Package-level target:

```text
victor_invest.vertical.*
  imports victor_contracts only for framework contracts

victor_invest.framework_bootstrap
victor_invest.api
victor_invest.cli
  may import victor.framework / victor-ai runtime
```

Tests:

- plugin can register with `MockPluginContext`
- vertical imports pass `assert_import_boundaries`
- manifest validates
- package declares `victor-contracts` as core dependency
- `victor-ai` remains optional runtime dependency

Implementation approach:

- do not move the entire package in one shot
- first add tests that define the allowed boundary
- move runtime imports behind functions and optional extras where tests require it
- keep CLI/API install docs clear that runtime mode needs `[runtime]`

### 8. Generated State Cleanup

Policy:

- no `.victor/`, `.db`, `.db-wal`, `.db-shm`, Lance embedding data, or lock files under importable package directories
- local generated state should live under:
  - `artifacts/victor/`
  - `.cache/victor-invest/`
  - configurable `VICTOR_INVEST_STATE_DIR`

Edits:

- add ignore patterns
- remove generated files from working tree or tracking
- ensure workflow loading reads only YAML/Python files

## TDD Plan

### Slice 1: Decision Policy Unit Tests

Add tests first:

```text
tests/unit/domain/services/test_investment_decision_policy.py
```

Cases:

- positive FV upside plus bullish TA -> `BUY`
- high FV upside plus high quality/agreement -> `STRONG_BUY`
- negative FV downside -> `SELL`
- severe downside -> `STRONG_SELL`
- missing fair value -> `REVIEW`
- low data quality downgrades confidence
- low model agreement triggers guardrail
- split suspect triggers `REVIEW`
- LLM contradiction is recorded but does not override
- positive FV plus bearish TA becomes lower confidence or `HOLD`

Implementation after tests:

- add policy dataclasses and evaluator
- keep no DB/API imports in policy module

### Slice 2: Payload Extractors

Tests:

```text
tests/unit/application/test_decision_input_extractor.py
```

Cases:

- extracts from legacy analysis output
- extracts from Victor workflow state
- extracts from `symbol` ranking row
- handles missing/null fields without exceptions
- normalizes model agreement in 0-1 and data quality in 0-100 ranges

Implementation:

- add extractor module
- use existing summary extractor helpers where useful

### Slice 3: CLI Summary Consistency

Tests:

```text
tests/unit/application/test_result_formatter_decision_policy.py
tests/unit/test_cli_orchestrator_summary_policy.py
```

Cases:

- CLI summary recommendation matches policy action
- price target and expected return remain visible
- divergent LLM recommendation appears as dissent/secondary field
- compact and verbose output contain `decision_policy`

Implementation:

- integrate policy after formatting
- avoid large formatter rewrites

### Slice 4: Victor Workflow Policy Integration

Tests:

```text
tests/unit/victor_invest/test_workflow_decision_policy.py
```

Cases:

- `run_synthesis` uses policy action
- old composite score is retained as evidence
- LLM synthesis cannot override final action
- failed/partial data returns `REVIEW` with guardrails

Implementation:

- replace local action threshold block with policy call
- pass policy output into synthesis payload

### Slice 5: API Rankings Contract

Tests:

```text
tests/unit/victor_invest/test_api_rankings_decision_policy.py
frontend/src/components/rankings/RankingsTab.test.tsx
frontend/src/lib/api.test.ts
```

Cases:

- ranking item includes decision fields
- low agreement row is filtered or marked according to query params
- split suspect is excluded by default
- CSV export includes decision columns
- frontend renders action/confidence without breaking old fixtures

Implementation:

- enrich ranking payload using extractor + policy
- update TypeScript types and fixtures

### Slice 6: Valuation Audit Tables

Tests:

```text
tests/unit/infrastructure/database/test_valuation_run_repository.py
tests/unit/domain/agents/test_symbol_update_agent.py
```

Cases:

- repository inserts valuation run and model outputs
- repository serializes guardrails/source freshness/input/output snapshots
- symbol update still updates current snapshot
- persistence warning is returned on audit write failure

Implementation:

- migration SQL under `schema/migrations/`
- repository module under infrastructure database
- call repository from symbol update or valuation completion point

### Slice 7: Victor Boundary Tests

Tests:

```text
tests/unit/victor_invest/test_contract_boundary.py
```

Cases:

- plugin registers with `MockPluginContext`
- vertical manifest validates
- vertical package does not import `victor.framework`
- runtime bootstrap is the only allowed runtime import surface
- `victor-ai` is optional, not required for plugin-only import

Implementation:

- move imports lazily if tests fail
- adjust dependency classification if needed

### Slice 8: Generated State Hygiene

Tests:

```text
tests/unit/victor_invest/test_repository_hygiene.py
```

Cases:

- no `.victor` under `victor_invest`
- no DB/WAL/SHM/lock files under importable packages
- workflow provider ignores generated folders

Implementation:

- update `.gitignore`
- remove generated files from repo

## Implementation Sequence

1. Add decision policy tests and implementation.
2. Add extractor tests and implementation.
3. Wire policy into legacy CLI output.
4. Wire policy into Victor workflow synthesis.
5. Enrich API rankings and frontend types.
6. Add valuation audit migrations and repository.
7. Add contract-boundary tests and isolate runtime imports.
8. Remove generated `.victor` state and add hygiene tests.
9. Refresh architecture docs to point at this LLD.

## Acceptance Criteria

- No CLI/API/UI path can show a headline recommendation that contradicts deterministic policy without marking it as dissent.
- `/ui/api/rankings` includes policy action, confidence, score, and guardrails.
- Current fair value screens still read efficiently from `symbol`.
- Historical valuation runs are queryable from normalized audit tables.
- Victor plugin import works without importing `victor.framework`.
- Force-refresh and verbose analysis are available through the Victor-first path or have explicit tracked exceptions.
- Generated runtime state is absent from package directories.
- Tests cover policy decisions, extractor mappings, API contract, frontend rendering, persistence, and Victor boundary.

## Open Decisions

- Whether `REVIEW` should appear in UI as its own action or map to `HOLD` with a guardrail badge.
- Whether initial policy thresholds should be config-file driven immediately or constants until behavior stabilizes.
- Whether valuation audit writes should happen in `SymbolUpdateAgent` or a separate `ValuationPersistenceService`.
- Whether `victor-ai` should remain an optional dependency in this package or be moved to a separate app/runtime package later.

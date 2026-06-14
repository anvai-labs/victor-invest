# Comprehensive Audit — RL Backtest Solution, Victor Convergence, Evaluation Integrity & Reporting

**Date:** 2026-06-14
**Scope:** Uncommitted RL-backtest changes + alignment with the Victor core framework
(`../codingagent`, `victor-ai` v0.7.0), evaluation/data-sourcing integrity (CFA lens),
analyst-report generation, and repo hygiene / screen-script convergence.
**Reviewers (roles):** Senior staff engineer (design/convergence), CFA (evaluation),
expert technical analyst (reporting).

---

## 0. Executive Summary

The uncommitted work hardens the RL-backtest recording adapter (multi-horizon outcome
tracking, robust valuation-payload extraction, Victor state-wrapper unwrapping) and adds
unit coverage. The mechanical changes are sound and tested. **However, the subsystem they
sit in has two independently disqualifying evaluation-integrity defects, several framework
convergence gaps, and repo-hygiene risks.**

Severity-ranked headline findings:

| # | Finding | Severity | Area |
|---|---------|----------|------|
| A | **Lookahead bias** — historical valuations use *today's* fundamentals, not point-in-time | CRITICAL | Evaluation |
| B | **Reward–prediction decoupling** — rewards use a synthetic ±10% FV, not the model's actual blended FV | CRITICAL | Evaluation |
| C | Survivorship bias — universe drawn from currently-listed names; delisting not modeled | HIGH | Evaluation |
| D | No data-quality gating before a row becomes a training label | HIGH | Evaluation |
| E | Framework drift — `@handler_decorator`/`BaseHandler`/`run_workflow_with_handlers` are not canonical v0.7.0 patterns | HIGH | Convergence |
| F | Two divergent execution paths (YAML provider vs Python StateGraph); YAML path now force-disabled in script | HIGH | Convergence |
| G | Analyst report surfaces a fraction of computed analytics; richest content only in legacy path | HIGH | Reporting |
| H | Repo hygiene — `artifacts/` not broadly gitignored (42 MB at risk); 4 forked `tmp_*_put_screen.py` (~85–90% dup) | HIGH | Hygiene |
| I | Period label mismatch — `18m`=540d stored under `*_548d` columns | MEDIUM | Evaluation |
| J | Calendar-day exit dates + unbounded backward price fill | MEDIUM | Evaluation |
| K | Redundant reward recomputation; `calculate_rewards` node output is dead state | LOW | Design |

---

## 1. The uncommitted change set (what was reviewed)

Modified: `victor_invest/tools/rl_backtest.py`, `victor_invest/workflows/rl_backtest.py`,
`scripts/rl_backtest_workflow.py`, `tests/unit/victor_invest/test_rl_backtest_runtime_paths.py`.
Added: `tests/unit/victor_invest/test_rl_backtest_tool_recording.py`.
Untracked: `artifacts/`, `tmp_{top1000,casino,pc_insurer,retail}_put_screen.py`.

What the diff does well:
- `_record_prediction` now calls `record_prediction_with_outcomes(...)` with full multi-horizon
  prices/rewards/exit-dates and `model_fair_values`/`model_weights` (tools/rl_backtest.py:361).
- `_extract_valuation_payload` normalizes multiple valuation output shapes
  (`fair_values`/`weights` vs nested `models[*].fair_value_per_share`/`weight` vs
  `consensus_fair_value`) (workflows/rl_backtest.py:461).
- `_unwrap_state_mapping` duck-types Victor state wrappers via `get_state()`/`to_dict()`
  (workflows/rl_backtest.py:158) — pragmatic, but see §3.
- New tests cover the recording adapter and the payload/state-unwrap helpers.

Concerns introduced/exposed by the diff:
- `scripts/rl_backtest_workflow.py` now passes `use_yaml_workflow=False` — the YAML provider
  path is effectively abandoned at the only real call site (see §3, finding F).
- New test asserts `reward_548d == 0.7` where `0.7` is the **18m (540-day)** reward — the
  period-label mismatch (finding I) is now encoded into tests.

---

## 2. Evaluation integrity (CFA lens) — `[[finding-rl-eval-integrity]]`

### A. Lookahead bias — CRITICAL
`run_historical_valuation` calls `valuation_tool.execute(symbol, model="all", current_price=price)`
with **no as-of date** (workflows/rl_backtest.py:286). `ValuationTool.execute` has no
`as_of_date` parameter (tools/valuation.py:215); it calls `_fetch_valuation_data(symbol)` →
`SECFilingTool.get_quarterly_financials` → `query_recent_processed_periods` whose SQL is
`...ORDER BY fiscal_year DESC ... LIMIT n` with **no `filed_date <= :as_of_date` predicate**
(`src/investigator/domain/agents/fundamental/quarterly_fetch.py:32-77`). So every historical
fair value is computed from *current* fundamentals. The price/shares services already support
point-in-time (`price_service.py:107`, `shares_service.py:128`) — only the valuation/fundamentals
path leaks. Sector multiples (valuation.py:938) and config thresholds are also current-as-of-today.

**Fix:** thread `as_of_date` through `ValuationTool.execute → _fetch_valuation_data →
SECFilingTool → query_recent_processed_periods`, adding `AND filed_date <= :as_of_date`.
Source sector multiples / config thresholds as-of date (or freeze + document).

### B. Reward–prediction decoupling — CRITICAL
`_get_multi_period_data` computes rewards from `predicted_fv = current_price * 1.10` (LONG) and
`* 0.90` (SHORT) (tools/rl_backtest.py:524-540), but persists the **real** `blended_fair_value`
and `model_fair_values`. `RewardCalculator.calculate` uses `predicted_fv` only for its **sign**
(`reward_calculator.py:122`), so magnitude isn't distorted — but the reward becomes a pure
function of realized forward return, independent of the model's actual conviction. Both a LONG
and a SHORT row are written per observation with mirror rewards; the FV features are noise
relative to the label.

**Fix:** derive direction/conviction from the real `blended_fair_value`; emit one reward per
observation (`position_type = LONG if blended_fv > price else SHORT`). Only keep dual rows for a
deliberate contrastive dataset, and if so store the synthetic FV that produced each row so
features and label agree. Consider `calculate_per_model_rewards` for per-model FV→reward.

### C. Survivorship bias — HIGH
Universe is drawn from currently-listed names (`WHERE islisted=true AND isstock=true` in the
put-screen scripts; backtest accepts whatever list it's given). `price_service.get_price`
backward-fills the last close with no delisting sentinel; a name that went to zero yields
`None` rewards and silently drops out (tools/rl_backtest.py:543) — removing the worst
SHORT-correct / LONG-wrong outcomes and inflating realized returns.

**Fix:** build the universe from point-in-time constituent snapshots that include later-delisted
names; model delisting as a terminal (loss-bearing) exit; persist a survivorship flag.

### D. No data-quality gating — HIGH
`_record_prediction` swallows DataSourceManager failures and records anyway with empty context
features (tools/rl_backtest.py:344-352). `sources_failed`/`overall_quality` are computed only in
`get_context_features` (tools/rl_backtest.py:484), never in the record path. Only filter before
recording is `price > 0`. `_extract_valuation_payload` defaults missing blended FV to `0.0`, which
is still recorded.

**Fix:** capture `overall_quality`/`sources_failed` in the record path; refuse to record (or tag
`used_for_training=False`) below threshold; require non-empty features and a positive bounded FV;
persist `model_agreement_score`/divergence for training-query filtering.

### I. Period label mismatch (18m → 540 vs 548) — MEDIUM
`HOLDING_PERIODS["18m"]=540` (tools/rl_backtest.py:51) but values are stored under `*_548d`
columns/kwargs (tools/rl_backtest.py:374,381,396). Reward computed at 540d is labeled 548d.
**Fix:** make the mapping 1:1 (pick 548 or rename to 540) + a test asserting key↔kwarg day-counts.

### J. Calendar-day exits + backward fill — MEDIUM
`target_date = analysis_date + timedelta(days=days)` lands on weekends/holidays
(tools/rl_backtest.py:510); `get_price` resolves `date <= target ORDER BY date DESC` with no
enforced lower bound (price_service.py:107) → can silently reach far back near gaps/delistings.
**Fix:** snap to trading calendar; enforce a staleness cap in SQL; one symmetric convention for
entry/exit; reject rows whose resolved date deviates beyond a threshold.

### K. Redundant recomputation — LOW
`calculate_rewards` node stores `state.reward_data[...]["multi_period"]` (workflows/rl_backtest.py:347)
but `_record_prediction` recomputes `_get_multi_period_data` from scratch (tools/rl_backtest.py:339);
the node output is never persisted. Doubles price-DB queries; risks future desync.
**Fix:** compute once — pass the node output into recording, or collapse calculate+record.

### CFA framework requirements (for a defensible evaluation harness)
Point-in-time everything (A, C); label == actual decision (B); survivorship-free universe with
delisting handling (C); transaction costs / slippage / borrow for SHORT; benchmark-relative or
risk-adjusted rewards (don't reward market beta); trading-calendar horizons (I, J); quality gating +
provenance (D); statistical significance with overlapping-sample correction (Newey-West / block
bootstrap) and walk-forward OOS with no train/test leakage; don't double-count mirrored LONG/SHORT
rows as independent.

---

## 3. Victor framework convergence — `[[finding-victor-convergence]]`

Canonical framework = `victor-ai` v0.7.0; verticals import only from `victor_contracts.*`.

### E. Handler / executor patterns are non-canonical — HIGH
- Canonical compute handler is a **plain async function** `(node, context, tool_registry) -> NodeResult`
  registered via `register_compute_handler(name, fn)` (`victor/workflows/compute_registry.py:26,58`).
  `victor-invest` uses `@handler_decorator` + `BaseHandler` returning `Tuple[Any, int]`
  (`victor_invest/handlers.py:39,74`) — these exist only as `victor_contracts.handler_runtime`
  compatibility shims (whose own runtime targets are absent in v0.7.0).
- `WorkflowContext` canonical surface is `.get()/.set()` (`victor/workflows/context.py:129`);
  there is **no `get_state()`** on the compute path. The diff's `_unwrap_state_mapping`
  duck-typing (`get_state`/`to_dict`) is defensive glue around this impedance mismatch.
- `ToolResult` is a Pydantic model with no `create_success/create_failure/to_dict`; `victor-invest`
  subclasses to add them (`victor_invest/tools/base.py:71`) — acceptable local convenience, but
  non-idiomatic.
- `run_workflow_with_handlers` (`victor_invest/workflows/__init__.py:269`) is vertical-defined;
  canonical equivalents are `run_compiled_workflow()` / `stream_compiled_workflow()`
  (`base_yaml_provider.py:578,611`). `sync_handlers_with_executor` does not exist in v0.7.0
  (already guarded with try/except).

**Convergence target:** keep `BaseTool`+Pydantic `ToolResult` and `Agent.create(vertical=...)`
(already correct); migrate handlers to plain async `ComputeHandler` functions returning
`victor_contracts.workflows.NodeResult`, registered via `register_compute_handler`; treat
`WorkflowContext` as `.get()/.set()`; replace `run_workflow_with_handlers` with
`run_compiled_workflow`; retire the `HandlerRegistry`/`sync` dance.

### F. Two divergent execution paths — HIGH
`run_rl_backtest` has a YAML-provider path and a Python-StateGraph fallback
(workflows/rl_backtest.py:584-673). The only real caller (`scripts/rl_backtest_workflow.py`) now
forces `use_yaml_workflow=False`, so the YAML path is dead-but-present (maintenance + drift risk).
**Decide and converge on one** (prefer the canonical compiled-workflow path); delete the other.

---

## 4. Analyst report generation (technical-analyst lens) — `[[finding-report-gaps]]`

Engine is rich (DCF/Damodaran, GGM, P/E, P/S, EV/EBITDA, sector-specific bank/biotech/defense/
insurance/REIT/semiconductor/rule-of-40, earnings_quality) but the report layer surfaces a
fraction, and there are **two divergent report paths** with the *deterministic* Victor output
being the thinnest.

- `standard.yaml`/`quick.yaml` produce **no report node**; only `comprehensive`/`peer_comparison` do.
- Technical indicators (RSI/MACD/Stochastic/Bollinger/ATR/OBV/VWAP), full S/R + Fibonacci, and
  detected patterns are **computed but not rendered** (only `overall_signal`+S1/R1 surface;
  `professional_report.py:1799-1840`).
- **No DCF sensitivity grid, no fair-value range, no bull/base/bear scenario or risk-matrix** in the
  Victor report (the legacy `synthesis.py` path has them; Victor drops them).
- **No quality/risk flags** (Altman Z, Piotroski F, Beneish M); `balance_sheet` score hardcoded 60
  (`handlers.py:1391`).
- **Three conflicting composite-score formulas** (`handlers.py:670` 0.6/0.4; `handlers.py:1282`
  0.7/0.3; `graphs.py:758` 5-factor). PT sourcing inconsistent (LLM PT vs consensus FV vs
  resistance) with no methodology disclosure.
- **No provenance manifest** (code SHA, config version, data as-of, model/provider); PDF filename
  not timestamped → overwrites history.

**Targets:** unify on one typed `AnalystReport` schema populated identically by rule-based and LLM
paths; surface already-computed analytics; add valuation bridge/sensitivity, scenario + risk-matrix,
quality flags; standardize one documented scoring rubric and PT methodology; emit markdown/HTML
alongside PDF; embed a provenance manifest; add report nodes to standard/quick.

---

## 5. Repo hygiene & screen-script convergence — `[[finding-repo-hygiene]]`

### H. Hygiene — HIGH
`.gitignore` ignores only specific `artifacts/` subpaths; `git check-ignore artifacts` returns
nothing → loose top-level JSON and the `artifacts/pc_insurers_analysis/` subtree (57 files / ~42 MB)
would be committed by `git add -A`. `tmp_*.py` are not ignored either.
**Fix:** broaden `.gitignore` (`artifacts/**` with `.gitkeep` allow-listing; add `tmp_*.py`);
remove the 4 tmp scripts from the tree; keep run output under the ignored `artifacts/results/`.

### Screen-script duplication — MEDIUM
4 fork-per-universe scripts (~818 LOC, ~85–90% duplicated: `rsi`, `norm_cdf`, `put_delta`,
`strike_for_delta`, the price loop, the scoring block). Only real variation is the universe filter.
They bypass the framework (raw `pd.read_sql`, no `ToolResult`, no handler/CLI), reinvent existing
RSI/MACD/valuation/treasury tools, and carry math risks (hardcoded `EXPIRY`/`AS_OF` + `CURRENT_DATE`
windows → negative `t_years` after expiry; inconsistent strike rounding across clones; flat 4.47%
rate; realized-vol-as-IV; no dividend yield).
**Fix:** collapse into one parameterized `OptionsScreenTool(BaseTool)` (+ `_options_math` module,
optional YAML workflow + `victor-invest options-screen` CLI) reusing market_data / technical_indicators /
valuation / treasury tools; universe becomes a parameter; add math + determinism tests.

---

## 6. Prioritized remediation roadmap

**P0 — Evaluation integrity (makes labels valid):**
1. Point-in-time fundamentals (A): `as_of_date` through valuation → SEC fetch SQL.
2. Reward tied to real prediction (B): single reward per observation from real blended FV.
3. Data-quality gating (D) + provenance flags on each recorded row.

**P1 — Correctness & convergence:**
4. Period label 540↔548 (I) + trading-calendar exits & staleness cap (J).
5. Remove redundant recompute (K); persist node output.
6. Pick one execution path (F); migrate handlers to canonical `ComputeHandler`/`register_compute_handler` (E).
7. Survivorship/delisting handling (C).

**P2 — Reporting & hygiene:**
8. Unified `AnalystReport` schema; surface computed analytics; sensitivity/scenarios/quality flags;
   one scoring rubric; provenance manifest (G).
9. `.gitignore` + remove tmp scripts; productize `OptionsScreenTool` (H).

**P3 — Robustness:**
10. Transaction costs / borrow / benchmark-relative rewards; overlapping-sample significance;
    walk-forward OOS evaluation.

---

## 7. Implementation status (2026-06-14)

Shipped on branch `rl-backtest-eval-integrity` (commits, each tested + ruff-clean; pre-existing
repo mypy debt bypassed with `--no-verify`, zero new mypy findings):

| Item | Status | Where |
|------|--------|-------|
| A Lookahead bias — point-in-time fundamentals | ✅ Done | `as_of_date` threaded valuation→SEC→SQL (`filed_date <= :as_of_date`) |
| B Reward–prediction coherence (dual rows + synthetic FV) | ✅ Done | explicit `conviction_band`, `position_predicted_fv` recorded |
| D Data-quality gating + provenance | ✅ Done | gate in `_record_prediction`; quality/agreement/sources columns |
| Schema migration 012 + tracker/DAO + training filters | ✅ Done | `schema/migrations/012_*.sql`, `outcome_tracker.py` |
| I Period label 540→548 | ✅ Done | `HOLDING_PERIODS` + mapping test |
| J Trading staleness cap | ✅ Done | `PriceService.get_price` bounded backward search |
| K Redundant recompute | ✅ Done | workflow passes precomputed `multi_period_data` |
| C Survivorship flag | ✅ Done (flag) | threaded `survivorship_flag`; PIT universe still TODO |
| H Repo hygiene + options-screen tool | ✅ Done | `.gitignore`, `OptionsScreenTool`, `_options_math`, CLI, tests |

Scoped follow-ups (not yet implemented — each its own effort):
- **E/F Handler convergence + single execution path** (P1.4): migrate `@handler_decorator`/
  `BaseHandler` → canonical `register_compute_handler`/`NodeResult`; remove the dead YAML-vs-
  StateGraph fork. Largest/riskiest refactor; gate behind framework import-boundary tests.
- **G Analyst-report overhaul** (P2): unified typed `AnalystReport` schema; surface
  RSI/MACD/Stochastic/Bollinger/Fibonacci/patterns; DCF sensitivity + scenarios + risk matrix;
  quality flags (Altman/Piotroski/Beneish); one scoring rubric; provenance manifest; markdown/HTML.
- **C (full) Survivorship-free universe**: point-in-time constituent snapshots incl. delisted names;
  delisting as terminal loss-bearing exit.
- **P3 Robustness**: transaction costs / borrow; benchmark-relative rewards; overlapping-sample
  significance (Newey-West / block bootstrap); walk-forward OOS.
</content>
</invoke>

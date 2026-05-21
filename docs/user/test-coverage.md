# Test Coverage

Victor Invest tracks Python coverage across both importable source roots:

- `investigator` from `src/investigator`
- `victor_invest` from `victor_invest`

Coverage is reported per module so it is clear which areas are well tested and which still need work.
Use the [Module Guide](module-guide.md) to map each covered file back to its package responsibility and preferred test style.

## Commands

Generate the full repo/module coverage report without failing the run:

```bash
make coverage-report
```

Generate the same reports and print a grouped package/module summary:

```bash
make coverage-modules
```

Run the critical-module coverage gate:

```bash
make coverage-critical
```

Run the deterministic RL core/training coverage gate:

```bash
make coverage-rl
```

`make` prefers `../.venv/bin/python` when that workspace virtualenv exists. Override the interpreter explicitly if needed:

```bash
make coverage-report PYTHON=/path/to/python
```

This writes:

- terminal module summary with missing lines
- grouped package/module summary through `scripts/report_module_coverage.py`
- critical valuation/FRED module gate through `scripts/assert_critical_coverage.py`
- RL core/training module gate through `scripts/assert_rl_coverage.py`
- `htmlcov/index.html`
- `coverage.xml`
- `coverage.json`
- `rl-coverage.json` when running `make coverage-rl`

Run the enforced repo-wide coverage gate:

```bash
make coverage-gate
```

The default gate is:

```bash
COVERAGE_MIN=66.67
```

Override it for local experiments:

```bash
make coverage-gate COVERAGE_MIN=30
```

## Current Baseline

Measured on 2026-05-20 with:

```bash
pytest tests/unit -q --cov=src/investigator --cov=victor_invest --cov-report=term --cov-fail-under=66.67
```

Result:

- tests: `1683 passed`, `19 skipped`
- repo-wide coverage: `30.11%`
- 66.67% gate status: failing

The repo-wide 66.67% gate is intentionally available through `make coverage-gate`, but it is not yet suitable as a required commit hook because large legacy surfaces remain lightly tested. The highest-priority low-coverage areas are older CLI orchestration, LLM adapters, report generation, broad tool wrappers, and large multi-responsibility API/workflow modules that should be split before file-level gates are practical.

## How To Read Module Coverage

Use the terminal report for quick triage:

```bash
make coverage-report
```

Then open:

```bash
open htmlcov/index.html
```

Focus first on modules changed by a feature branch. For each changed module:

- add direct unit tests for pure functions and dataclasses
- mock DB/network/LLM boundaries
- add API or workflow contract tests for public payloads
- keep integration tests marked when they need external services

## Coverage Policy

- New deterministic domain/application modules should target at least 66.67% coverage before merge.
- Critical valuation/FRED persistence modules are enforced at 67% or higher by `make coverage-critical`.
- Deterministic RL core/training modules are enforced at 67% or higher by `make coverage-rl`.
- Repo-wide coverage is tracked every run and should move upward over time.
- The repo-wide 66.67% gate becomes enforceable once legacy low-coverage modules are either tested, retired, or explicitly excluded by architectural decision.

## Critical Modules

The critical-module gate focuses on the production path that extracts fair-value inputs, makes deterministic recommendations, persists valuation/macro data, and formats that output for the UI:

| Module | Responsibility |
| --- | --- |
| `decision_input_extractor.py` | Normalizes valuation, TA, and quality inputs for deterministic policy decisions. |
| `result_formatter.py` | Produces compact/minimal output consumed by CLI/API/UI paths. |
| `symbol_update.py` | Persists fair-value, ratio, and SEC-derived metrics into `symbol`. |
| `investment_decision_policy.py` | Converts FV cushion, TA, and quality signals into deterministic action/confidence. |
| `robust_valuation_service.py` | Runs robust multi-method valuation logic and guards. |
| `unified_valuation_executor.py` | Shared multi-model valuation execution and blending. |
| `valuation_run_repository.py` | Stores valuation run/model audit trails. |
| `macro_indicators.py` | Reads canonical FRED macro values and derived Buffett Indicator inputs. |

## RL Core Modules

The RL gate focuses on deterministic learning contracts and intentionally excludes DB-heavy outcome tracking adapters from the file-level gate:

| Module | Responsibility |
| --- | --- |
| `reward_calculator.py` | Converts predicted fair value and realized prices into a consistent reward signal. |
| `feature_extractor.py` | Builds RL state/context features from financial, technical, data-quality, and insider inputs. |
| `feature_normalizer.py` | Fits, transforms, persists, and reports feature normalization statistics. |
| `models.py` | Defines RL contexts, rewards, experiences, metrics, holding periods, and A/B test results. |
| `monitoring/ab_testing.py` | Routes deterministic A/B assignments and recommends rollout changes from test results. |
| `monitoring/metrics.py` | Maps persisted RL outcomes into sector, tier, model, trend, and summary metrics. |
| `policy/base.py` | Defines shared policy contracts and applicability/weight helper behavior. |
| `policy/dual_policy.py` | Composes technical timing and fundamental weighting/holding-period policies. |
| `training/experience_collector.py` | Collects, filters, splits, balances, and summarizes training experiences. |

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

`make` prefers `../.venv/bin/python` when that workspace virtualenv exists. Override the interpreter explicitly if needed:

```bash
make coverage-report PYTHON=/path/to/python
```

This writes:

- terminal module summary with missing lines
- grouped package/module summary through `scripts/report_module_coverage.py`
- `htmlcov/index.html`
- `coverage.xml`
- `coverage.json`

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

- tests: `1618 passed`, `19 skipped`
- repo-wide coverage: `28.67%`
- 66.67% gate status: failing

The repo-wide 66.67% gate is intentionally available through `make coverage-gate`, but it is not yet suitable as a required commit hook because large legacy surfaces remain lightly tested. The highest-priority low-coverage areas are older CLI orchestration, LLM adapters, report generation, and broad tool wrappers.

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
- Repo-wide coverage is tracked every run and should move upward over time.
- The repo-wide 66.67% gate becomes enforceable once legacy low-coverage modules are either tested, retired, or explicitly excluded by architectural decision.

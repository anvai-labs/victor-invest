#!/usr/bin/env python3
"""Enforce coverage for critical valuation/FRED persistence modules."""

from __future__ import annotations

import json
import sys
from pathlib import Path


THRESHOLD = 67.0

CRITICAL_MODULES = [
    "src/investigator/application/decision_input_extractor.py",
    "src/investigator/application/result_formatter.py",
    "src/investigator/domain/agents/symbol_update.py",
    "src/investigator/domain/services/investment_decision_policy.py",
    "src/investigator/domain/services/robust_valuation_service.py",
    "src/investigator/domain/services/unified_valuation_executor.py",
    "src/investigator/infrastructure/database/valuation_run_repository.py",
    "src/investigator/infrastructure/external/fred/macro_indicators.py",
]


def load_coverage(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def module_percent(coverage: dict, module_path: str) -> float:
    try:
        return float(coverage["files"][module_path]["summary"]["percent_covered"])
    except KeyError as exc:
        raise KeyError(f"Critical module missing from coverage report: {module_path}") from exc


def main(argv: list[str]) -> int:
    coverage_path = Path(argv[1]) if len(argv) > 1 else Path("coverage.json")
    if not coverage_path.exists():
        print(f"Coverage JSON not found: {coverage_path}", file=sys.stderr)
        print("Run `make coverage-report` first.", file=sys.stderr)
        return 2

    coverage = load_coverage(coverage_path)
    failures = []

    print(f"Critical module coverage threshold: {THRESHOLD:.2f}%")
    for module_path in CRITICAL_MODULES:
        percent = module_percent(coverage, module_path)
        status = "PASS" if percent >= THRESHOLD else "FAIL"
        print(f"{status} {percent:6.2f}% {module_path}")
        if percent < THRESHOLD:
            failures.append((module_path, percent))

    if failures:
        print("\nCritical coverage failures:", file=sys.stderr)
        for module_path, percent in failures:
            print(f"- {module_path}: {percent:.2f}% < {THRESHOLD:.2f}%", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

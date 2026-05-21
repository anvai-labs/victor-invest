#!/usr/bin/env python3
"""Enforce coverage for deterministic RL core and training modules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLD = 67.0

RL_MODULES = [
    "src/investigator/domain/services/rl/reward_calculator.py",
    "src/investigator/domain/services/rl/feature_extractor.py",
    "src/investigator/domain/services/rl/feature_normalizer.py",
    "src/investigator/domain/services/rl/models.py",
    "src/investigator/domain/services/rl/monitoring/ab_testing.py",
    "src/investigator/domain/services/rl/monitoring/metrics.py",
    "src/investigator/domain/services/rl/policy/base.py",
    "src/investigator/domain/services/rl/policy/dual_policy.py",
    "src/investigator/domain/services/rl/training/experience_collector.py",
]


def load_coverage(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def module_percent(coverage: dict, module_path: str) -> float:
    try:
        return float(coverage["files"][module_path]["summary"]["percent_covered"])
    except KeyError as exc:
        raise KeyError(f"RL module missing from coverage report: {module_path}") from exc


def main(argv: list[str]) -> int:
    coverage_path = Path(argv[1]) if len(argv) > 1 else Path("rl-coverage.json")
    if not coverage_path.exists():
        print(f"Coverage JSON not found: {coverage_path}", file=sys.stderr)
        print("Run `make coverage-rl` first.", file=sys.stderr)
        return 2

    coverage = load_coverage(coverage_path)
    failures = []

    print(f"RL module coverage threshold: {THRESHOLD:.2f}%")
    for module_path in RL_MODULES:
        percent = module_percent(coverage, module_path)
        status = "PASS" if percent >= THRESHOLD else "FAIL"
        print(f"{status} {percent:6.2f}% {module_path}")
        if percent < THRESHOLD:
            failures.append((module_path, percent))

    if failures:
        print("\nRL coverage failures:", file=sys.stderr)
        for module_path, percent in failures:
            print(f"- {module_path}: {percent:.2f}% < {THRESHOLD:.2f}%", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

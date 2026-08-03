#!/usr/bin/env python3
"""Print grouped coverage from coverage.py JSON output."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CoverageBucket:
    covered: int = 0
    statements: int = 0

    @property
    def missing(self) -> int:
        return max(self.statements - self.covered, 0)

    @property
    def percent(self) -> float:
        if self.statements == 0:
            return 100.0
        return (self.covered / self.statements) * 100


def module_name_for_path(path: str) -> str:
    parts = Path(path).parts
    if len(parts) >= 3 and parts[0] == "src" and parts[1] == "investigator":
        if parts[2] == "__init__.py":
            return "investigator"
        if parts[2].endswith(".py"):
            return f"investigator.{Path(parts[2]).stem}"
        return f"investigator.{parts[2]}"
    if parts and parts[0] == "victor_invest":
        if len(parts) == 1 or parts[1] == "__init__.py":
            return "victor_invest"
        if parts[1].endswith(".py"):
            return f"victor_invest.{Path(parts[1]).stem}"
        return f"victor_invest.{parts[1]}"
    return ".".join(Path(path).with_suffix("").parts)


def load_buckets(coverage_json: Path) -> dict[str, CoverageBucket]:
    data = json.loads(coverage_json.read_text(encoding="utf-8"))
    buckets: dict[str, CoverageBucket] = {}

    for file_path, file_data in data.get("files", {}).items():
        summary = file_data.get("summary", {})
        module_name = module_name_for_path(file_path)
        bucket = buckets.setdefault(module_name, CoverageBucket())
        bucket.covered += int(summary.get("covered_lines", 0))
        bucket.statements += int(summary.get("num_statements", 0))

    return buckets


def format_rows(buckets: dict[str, CoverageBucket]) -> list[str]:
    rows = ["Module                                      Stmts   Miss   Cover", "-" * 68]
    for module_name, bucket in sorted(buckets.items()):
        rows.append(f"{module_name:<42} {bucket.statements:>6} {bucket.missing:>6} {bucket.percent:>6.2f}%")
    return rows


def main(argv: list[str]) -> int:
    coverage_json = Path(argv[1]) if len(argv) > 1 else Path("coverage.json")
    if not coverage_json.exists():
        print(f"Coverage JSON not found: {coverage_json}", file=sys.stderr)
        print("Run `make coverage-report` first.", file=sys.stderr)
        return 2

    print("\n".join(format_rows(load_buckets(coverage_json))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

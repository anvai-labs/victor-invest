"""Measure how often TTM metrics are computed over incomplete quarterly data.

``calculate_ttm_metrics`` sums the four most recent quarters. A quarter that omits
a metric contributes 0.0, which understates the total with nothing in the result to
show it. Since #71 the result also carries ``<metric>_quarters_present``, so the
shortfall is measurable rather than merely suspected.

This script reports that incidence across a symbol universe. It answers two
questions that decide what to do next:

  1. How often is a TTM total built from fewer than four quarters of a metric?
     Rare  -> suppressing incomplete metrics is cheap and clearly correct.
     Common -> suppression would blank out much of the universe, and the real
               fix belongs upstream in extraction.

  2. Which symbols and periods are affected? A large-cap issuer missing revenue
     for a quarter is far more likely an extraction gap than a real SEC omission,
     which points at the CompanyFacts extractor rather than this aggregation.

Usage:
    source ~/.investigator/env
    python3 utils/measure_ttm_coverage.py --limit 200
    python3 utils/measure_ttm_coverage.py --symbols AAPL MSFT GOOGL --verbose
    python3 utils/measure_ttm_coverage.py --limit 500 --json artifacts/ttm_coverage.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from investigator.domain.agents.fundamental.financial_ratios import (  # noqa: E402
    _TTM_METRIC_NAMES,
    calculate_ttm_metrics,
)

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("ttm_coverage")

# Every operating issuer reports these every quarter, so a gap here is a data problem
# and it distorts the multiples built on top of it.
CORE_METRICS = ("revenues", "net_income")

# These are legitimately absent for whole classes of issuer -- a company that pays no
# dividend has no dividends_paid, and EBITDA is only derived when operating income is
# reported. Counting their absence as a gap would swamp the signal, so they are
# reported separately and never drive the exit code.
OPTIONAL_METRICS = tuple(m for m in _TTM_METRIC_NAMES if m not in CORE_METRICS)


class _QuietLogger:
    """Swallow the per-symbol warnings so the summary is readable."""

    def warning(self, *_args: Any, **_kwargs: Any) -> None: ...

    def info(self, *_args: Any, **_kwargs: Any) -> None: ...


def load_symbols(limit: int | None) -> list[str]:
    """Read the analysable universe from the SEC database."""
    from sqlalchemy import text

    from investigator.infrastructure.database.db import get_db_manager

    query = "SELECT DISTINCT symbol FROM sec_companyfacts_processed ORDER BY symbol"
    if limit:
        query += f" LIMIT {int(limit)}"
    with get_db_manager().engine.connect() as conn:
        return [row[0] for row in conn.execute(text(query))]


def quarterly_data_for(symbol: str) -> list[Any]:
    """Fetch quarterly data through the same path the fundamental agent uses."""
    from investigator.infrastructure.sec.quarterly_processor import SECQuarterlyProcessor

    return SECQuarterlyProcessor().get_recent_quarterly_data(symbol) or []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="*", help="Symbols to check (default: read universe from the database)")
    parser.add_argument("--limit", type=int, default=None, help="Cap the universe read from the database")
    parser.add_argument("--verbose", action="store_true", help="List every symbol with incomplete coverage")
    parser.add_argument("--json", dest="json_out", help="Write the full per-symbol result to this path")
    args = parser.parse_args()

    symbols = args.symbols or load_symbols(args.limit)
    if not symbols:
        logger.error("No symbols to measure.")
        return 1

    quiet = _QuietLogger()
    incomplete_by_metric: Counter[str] = Counter()
    affected: dict[str, dict[str, float]] = defaultdict(dict)
    computed = skipped = 0

    for symbol in symbols:
        try:
            quarters = quarterly_data_for(symbol)
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the sweep
            logger.warning("%s: could not load quarterly data (%s)", symbol, exc)
            skipped += 1
            continue

        ttm = calculate_ttm_metrics(quarterly_data=quarters, symbol=symbol, logger=quiet)
        if not ttm:
            # Fewer than four actual quarters: already refused, not the case we measure.
            skipped += 1
            continue

        computed += 1
        used = ttm.get("quarters_used", 0.0)
        for metric in _TTM_METRIC_NAMES:
            present = ttm.get(f"{metric}_quarters_present", 0.0)
            if present < used:
                incomplete_by_metric[metric] += 1
                affected[symbol][metric] = present

    core_affected = {s: g for s, g in affected.items() if any(m in CORE_METRICS for m in g)}
    pct = (lambda n: f"{n / computed:.1%}") if computed else (lambda _n: "n/a")

    print(f"\nSymbols with a computable TTM   : {computed}")
    print(f"Symbols skipped (<4 quarters)   : {skipped}")
    print(f"Symbols with a CORE metric gap  : {len(core_affected)}  ({pct(len(core_affected))})")
    print("\nCore metrics -- a gap here is a data problem and distorts multiples:")
    for metric in CORE_METRICS:
        print(f"  {metric:<18} {incomplete_by_metric[metric]:>6}  ({pct(incomplete_by_metric[metric])})")
    print("\nOptional metrics -- absence is often legitimate (no dividend, EBITDA not derivable):")
    for metric in OPTIONAL_METRICS:
        print(f"  {metric:<18} {incomplete_by_metric[metric]:>6}  ({pct(incomplete_by_metric[metric])})")

    if args.verbose and core_affected:
        print("\nSymbols with a core gap (metric: quarters present of 4):")
        for symbol in sorted(core_affected):
            detail = ", ".join(f"{m}: {int(p)}" for m, p in sorted(core_affected[symbol].items()) if m in CORE_METRICS)
            print(f"  {symbol:<8} {detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "symbols_computed": computed,
                    "symbols_skipped": skipped,
                    "core_metrics": list(CORE_METRICS),
                    "incomplete_by_metric": dict(incomplete_by_metric),
                    "symbols_with_core_gap": sorted(core_affected),
                    "affected": affected,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(f"\nWrote {out}")

    # Only a core-metric gap is actionable; optional metrics are legitimately sparse.
    return 2 if core_affected else 0


if __name__ == "__main__":
    raise SystemExit(main())

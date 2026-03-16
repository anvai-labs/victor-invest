#!/usr/bin/env python3
"""Refresh stale investment analysis.

This script identifies symbols with stale analysis or data quality issues
and triggers victor-invest analyze to refresh them.

Usage:
    python scripts/refresh_stale_analysis.py --mode comprehensive --parallel 4
    python scripts/refresh_stale_analysis.py --symbols NFLX CPT --mode standard
"""

import argparse
import asyncio
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import List, Optional, Set  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402
from victor_invest.workflows.graphs import run_analysis  # noqa: E402


logger = logging.getLogger(__name__)


@dataclass
class SymbolIssue:
    """Represents a symbol with analysis issues."""

    symbol: str
    issue_type: str  # STALE, EXTREME_VALUATION, SPLIT_FLAG, DIVERGENCE
    severity: str  # CRITICAL, HIGH, MEDIUM
    description: str
    days_since_analysis: Optional[int] = None
    upside_pct: Optional[float] = None


class StaleAnalysisDetector:
    """Detect symbols needing analysis refresh."""

    def __init__(self, db_url: str):
        """Initialize detector.

        Args:
            db_url: PostgreSQL connection URL
        """
        self.engine = create_engine(db_url)

    def detect_stale_analysis(
        self,
        stale_days: int = 60,
        max_symbols: int = 100,
    ) -> List[SymbolIssue]:
        """Find symbols with stale analysis.

        Args:
            stale_days: Days threshold for staleness
            max_symbols: Maximum symbols to return

        Returns:
            List of SymbolIssue objects
        """
        issues = []

        with self.engine.connect() as conn:
            # Query stale analysis from view
            query = text("""
                SELECT
                    symbol,
                    description,
                    valuation_updated_at::date AS last_analyzed,
                    CURRENT_DATE - valuation_updated_at::date AS days_since_analysis,
                    upside_pct,
                    model_agreement_score,
                    divergence_flag,
                    fair_value_blended,
                    current_price
                FROM investment_opportunities
                WHERE valuation_updated_at IS NOT NULL
                  AND fair_value_blended IS NOT NULL
                  AND valuation_updated_at < CURRENT_DATE - INTERVAL ':stale_days days'
                ORDER BY valuation_updated_at ASC
                LIMIT :max_symbols
            """)

            result = conn.execute(query, {"stale_days": stale_days, "max_symbols": max_symbols})

            for row in result:
                severity = "HIGH" if row.days_since_analysis > 90 else "MEDIUM"

                issues.append(
                    SymbolIssue(
                        symbol=row.symbol,
                        issue_type="STALE",
                        severity=severity,
                        description=f"Analysis {row.days_since_analysis} days old (last: {row.last_analyzed})",
                        days_since_analysis=row.days_since_analysis,
                        upside_pct=row.upside_pct,
                    )
                )

        logger.info(f"Found {len(issues)} symbols with stale analysis (>{stale_days} days)")
        return issues

    def detect_extreme_valuations(self, max_symbols: int = 50) -> List[SymbolIssue]:
        """Find symbols with extreme valuations (potential data issues).

        Args:
            max_symbols: Maximum symbols to return

        Returns:
            List of SymbolIssue objects
        """
        issues = []

        with self.engine.connect() as conn:
            # Query extreme valuations
            query = text("""
                SELECT
                    symbol,
                    description,
                    upside_pct,
                    model_agreement_score,
                    fair_value_blended,
                    current_price,
                    pe_ratio,
                    ps_ratio,
                    pb_ratio
                FROM investment_opportunities
                WHERE upside_pct IS NOT NULL
                  AND (
                      -- Extreme upside
                      upside_pct > 200
                      OR upside_pct < -90
                      -- Extreme ratios
                      OR pe_ratio > 100 OR pe_ratio < -50
                      OR ps_ratio > 500
                      OR pb_ratio > 20
                  )
                ORDER BY ABS(upside_pct) DESC
                LIMIT :max_symbols
            """)

            result = conn.execute(query, {"max_symbols": max_symbols})

            for row in result:
                issues.append(
                    SymbolIssue(
                        symbol=row.symbol,
                        issue_type="EXTREME_VALUATION",
                        severity="CRITICAL",
                        description=f"Extreme valuation: {row.upside_pct:.1f}% upside",
                        upside_pct=row.upside_pct,
                    )
                )

        logger.info(f"Found {len(issues)} symbols with extreme valuations")
        return issues

    def detect_divergence_flags(self, max_symbols: int = 50) -> List[SymbolIssue]:
        """Find symbols with divergence flags (model disagreement).

        Args:
            max_symbols: Maximum symbols to return

        Returns:
            List of SymbolIssue objects
        """
        issues = []

        with self.engine.connect() as conn:
            # Query divergent models
            query = text("""
                SELECT
                    symbol,
                    description,
                    model_agreement_score,
                    applicable_models,
                    valuation_updated_at::date AS last_analyzed,
                    upside_pct
                FROM investment_opportunities
                WHERE divergence_flag = true
                   OR model_agreement_score < 0.3
                ORDER BY model_agreement_score ASC
                LIMIT :max_symbols
            """)

            result = conn.execute(query, {"max_symbols": max_symbols})

            for row in result:
                issues.append(
                    SymbolIssue(
                        symbol=row.symbol,
                        issue_type="DIVERGENCE",
                        severity="MEDIUM",
                        description=f"Model divergence (agreement: {row.model_agreement_score:.2f})",
                        upside_pct=row.upside_pct,
                    )
                )

        logger.info(f"Found {len(issues)} symbols with model divergence")
        return issues

    def detect_stock_splits(self, max_symbols: int = 20) -> List[SymbolIssue]:
        """Find potential stock splits from view.

        Args:
            max_symbols: Maximum symbols to return

        Returns:
            List of SymbolIssue objects
        """
        issues = []

        with self.engine.connect() as conn:
            # Query potential stock splits
            query = text("""
                SELECT
                    symbol,
                    description,
                    current_price,
                    fair_value,
                    implied_split_ratio,
                    likely_split
                FROM potential_stock_splits
                ORDER BY implied_split_ratio DESC
                LIMIT :max_symbols
            """)

            result = conn.execute(query, {"max_symbols": max_symbols})

            for row in result:
                issues.append(
                    SymbolIssue(
                        symbol=row.symbol,
                        issue_type="SPLIT_FLAG",
                        severity="HIGH",
                        description=(
                            f"Potential stock split: {row.likely_split} (ratio: {row.implied_split_ratio:.1f}x)"
                        ),
                    )
                )

        logger.info(f"Found {len(issues)} symbols with potential stock splits")
        return issues

    def get_all_issues(
        self,
        stale_days: int = 60,
        max_per_category: int = 50,
    ) -> List[SymbolIssue]:
        """Get all symbols needing refresh.

        Args:
            stale_days: Days threshold for stale analysis
            max_per_category: Max symbols per category

        Returns:
            List of unique SymbolIssue objects
        """
        all_issues = []

        # Detect all issue types
        all_issues.extend(self.detect_stale_analysis(stale_days, max_per_category))
        all_issues.extend(self.detect_extreme_valuations(max_per_category))
        all_issues.extend(self.detect_divergence_flags(max_per_category))
        all_issues.extend(self.detect_stock_splits(max_per_category // 2))

        # Deduplicate by symbol (keep highest severity)
        seen: Set[str] = set()
        unique_issues = []
        severity_rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}

        for issue in all_issues:
            if issue.symbol not in seen:
                seen.add(issue.symbol)
                unique_issues.append(issue)
            else:
                # Replace with higher severity if found
                for i, existing in enumerate(unique_issues):
                    if existing.symbol == issue.symbol:
                        if severity_rank[issue.severity] > severity_rank[existing.severity]:
                            unique_issues[i] = issue
                        break

        # Sort by severity and days since analysis
        unique_issues.sort(
            key=lambda x: (
                -severity_rank[x.severity],
                -(x.days_since_analysis or 0),
            )
        )

        logger.info(f"Total unique symbols needing refresh: {len(unique_issues)}")
        return unique_issues


async def refresh_symbol(
    symbol: str,
    mode: str = "comprehensive",
) -> dict:
    """Run analysis for a single symbol.

    Args:
        symbol: Stock symbol
        mode: Analysis mode (quick, standard, comprehensive)

    Returns:
        Result dict
    """
    logger.info(f"Refreshing {symbol} with mode={mode}...")

    try:
        # Convert mode string to AnalysisMode enum
        from victor_invest.workflows.state import AnalysisMode

        mode_map = {
            "quick": AnalysisMode.QUICK,
            "standard": AnalysisMode.STANDARD,
            "comprehensive": AnalysisMode.COMPREHENSIVE,
        }
        analysis_mode = mode_map.get(mode, AnalysisMode.STANDARD)

        result = await run_analysis(symbol=symbol, mode=analysis_mode)

        # Check if analysis was successful (has fundamental analysis or recommendation)
        is_success = (
            result is not None
            and (result.fundamental_analysis is not None or result.recommendation is not None)
            and not result.errors
        )

        if is_success:
            logger.info(f"✓ {symbol} refreshed successfully")
            return {
                "symbol": symbol,
                "status": "success",
                "errors": result.errors,
                "completed_steps": result.completed_steps,
            }
        else:
            logger.error(f"✗ {symbol} failed: errors={result.errors}")
            return {
                "symbol": symbol,
                "status": "failed",
                "error": f"errors={result.errors}",
                "completed_steps": result.completed_steps,
            }

    except Exception as e:
        logger.exception(f"✗ {symbol} crashed: {e}")
        return {"symbol": symbol, "status": "error", "error": str(e)}


async def refresh_symbols_batch(
    symbols: List[str],
    mode: str = "comprehensive",
    parallel: int = 4,
) -> List[dict]:
    """Refresh multiple symbols in parallel.

    Args:
        symbols: List of symbols to refresh
        mode: Analysis mode
        parallel: Number of parallel workers

    Returns:
        List of result dicts
    """
    semaphore = asyncio.Semaphore(parallel)

    async def refresh_with_limit(symbol: str) -> dict:
        async with semaphore:
            return await refresh_symbol(symbol, mode)

    tasks = [refresh_with_limit(s) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions
    processed_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.exception(f"Symbol {symbols[i]} raised exception: {r}")
            processed_results.append({"symbol": symbols[i], "status": "error", "error": str(r)})
        else:
            processed_results.append(r)

    return processed_results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Refresh stale investment analysis",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=60,
        help="Days threshold for stale analysis (default: 60)",
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "comprehensive"],
        default="standard",
        help="Analysis mode (default: standard)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=100,
        help="Maximum symbols to refresh (default: 100)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to refresh (skips detection)",
    )
    parser.add_argument(
        "--category",
        choices=["all", "stale", "extreme", "divergence", "splits"],
        default="all",
        help="Category to refresh (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only detect issues, don't refresh",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get database URL
    db_url = os.environ.get(
        "DATABASE_URL",
        f"postgresql://{os.environ.get('STOCK_DB_USER', 'stockuser')}:"
        f"{os.environ.get('STOCK_DB_PASSWORD')}@"
        f"{os.environ.get('STOCK_DB_HOST', 'localhost')}:"
        f"{os.environ.get('STOCK_DB_PORT', '5432')}/"
        f"{os.environ.get('STOCK_DB_NAME', 'stock')}",
    )

    # Detect issues
    detector = StaleAnalysisDetector(db_url)

    if args.symbols:
        # User specified symbols directly
        symbols_to_refresh = args.symbols
        logger.info(f"Refreshing {len(symbols_to_refresh)} user-specified symbols")
    else:
        # Detect symbols needing refresh
        if args.category == "all":
            issues = detector.get_all_issues(
                stale_days=args.stale_days,
                max_per_category=args.max_symbols,
            )
        elif args.category == "stale":
            issues = detector.detect_stale_analysis(args.stale_days, args.max_symbols)
        elif args.category == "extreme":
            issues = detector.detect_extreme_valuations(args.max_symbols)
        elif args.category == "divergence":
            issues = detector.detect_divergence_flags(args.max_symbols)
        elif args.category == "splits":
            issues = detector.detect_stock_splits(args.max_symbols)

        symbols_to_refresh = [i.symbol for i in issues]

        # Print summary
        print("\n" + "=" * 60)
        print("SYMBOLS NEEDING REFRESH")
        print("=" * 60)
        for issue in issues:
            print(f"  [{issue.severity}] {issue.symbol:6s} - {issue.description}")
        print("=" * 60 + "\n")

        if not symbols_to_refresh:
            logger.info("No symbols need refreshing")
            return 0

    if args.dry_run:
        logger.info("Dry run - skipping refresh")
        return 0

    # Refresh symbols
    logger.info(f"Refreshing {len(symbols_to_refresh)} symbols (mode={args.mode}, parallel={args.parallel})...")

    start_time = datetime.now()
    results = asyncio.run(refresh_symbols_batch(symbols_to_refresh, args.mode, args.parallel))
    elapsed = (datetime.now() - start_time).total_seconds()

    # Print summary
    success_count = sum(1 for r in results if r.get("status") == "success")
    failed_count = len(results) - success_count

    print("\n" + "=" * 60)
    print("REFRESH SUMMARY")
    print("=" * 60)
    print(f"  Total:     {len(results)}")
    print(f"  Success:   {success_count}")
    print(f"  Failed:    {failed_count}")
    print(f"  Elapsed:   {elapsed:.1f}s ({elapsed / len(results):.1f}s per symbol)")
    print("=" * 60 + "\n")

    if failed_count > 0:
        print("Failed symbols:")
        for r in results:
            if r.get("status") != "success":
                print(f"  - {r['symbol']}: {r.get('error', 'Unknown error')}")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

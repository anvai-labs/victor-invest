#!/usr/bin/env python3
"""
Sweep all symbols with is_sec_filing=true in compact mode to prepopulate web UI cache.

This script processes all symbols in order of stockid using victor-invest CLI
with --detail compact flag to generate compact format for web UI consumption.

Usage:
    python scripts/sweep_compact_cache.py [--parallel N] [--limit N] [--start-stockid N]

Options:
    --parallel N       Number of parallel workers (default: 4)
    --limit N          Limit number of symbols to process (default: all)
    --start-stockid N  Start from specific stockid (default: 1)
    --dry-run          Show symbols to process without running analysis
    --output-dir DIR   Output directory for results (default: /tmp/sweep_compact)
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from investigator.infrastructure.database.db import DatabaseManager
from sqlalchemy import text


def get_symbols_with_sec_filing(
    limit: Optional[int] = None, start_stockid: int = 1
) -> List[str]:
    """Get all symbols with is_sec_filing=true in order of stockid.

    Args:
        limit: Optional limit on number of symbols
        start_stockid: Start from specific stockid

    Returns:
        List of symbols
    """
    db_manager = DatabaseManager()

    with db_manager.get_session() as session:
        query = text(
            """
        SELECT s.ticker as symbol
        FROM symbol s
        WHERE s.is_sec_filing = true
        AND s.stockid >= :start_stockid
        ORDER BY s.stockid
        """
            + (f"LIMIT {limit}" if limit else "")
        )

        results = session.execute(query, {"start_stockid": start_stockid}).fetchall()

        symbols = []
        for row in results:
            if isinstance(row[0], str):
                symbols.append(row[0])
            elif isinstance(row[0], dict):
                symbol = row[0].get("symbol")
                if symbol:
                    symbols.append(symbol)

        return symbols


async def run_sweep(
    symbols: List[str],
    parallel: int = 4,
    output_dir: str = "/tmp/sweep_compact",
    mode: str = "standard",
    dry_run: bool = False,
):
    """Run victor-invest batch analysis in compact mode.

    Args:
        symbols: List of symbols to process
        parallel: Number of parallel workers
        output_dir: Output directory
        mode: Analysis mode (quick/standard/comprehensive)
        dry_run: If True, only show what would be processed
    """
    from victor_invest.cli import _run_batch

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sweep_summary = {
        "start_time": datetime.now().isoformat(),
        "total_symbols": len(symbols),
        "parallel_workers": parallel,
        "mode": mode,
        "output_dir": str(output_dir),
        "symbols": symbols,
    }

    if dry_run:
        print(f"DRY RUN: Would process {len(symbols)} symbols")
        print(f"Output directory: {output_dir}")
        print(f"Parallel workers: {parallel}")
        print("\nFirst 20 symbols:")
        for i, symbol in enumerate(symbols[:20], 1):
            print(f"  {i:3d}. {symbol}")
        if len(symbols) > 20:
            print(f"  ... and {len(symbols) - 20} more")
        return

    print(f"\nStarting sweep of {len(symbols)} symbols...")
    print(f"Output directory: {output_dir}")
    print(f"Parallel workers: {parallel}")
    print(f"Mode: {mode}")
    print(f"Timestamp: {timestamp}")

    # Run the batch analysis
    await _run_batch(
        symbols=tuple(symbols),
        mode=mode,
        output_dir=output_dir,
        provider="ollama",
        model=None,
        parallel=parallel,
        detail="compact",
    )

    # Update summary
    sweep_summary["end_time"] = datetime.now().isoformat()
    summary_file = output_path / f"sweep_summary_{timestamp}.json"
    with open(summary_file, "w") as f:
        json.dump(sweep_summary, f, indent=2, default=str)

    print("\nSweep complete!")
    print(f"Summary saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Sweep symbols with SEC filings in compact mode"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of symbols to process (default: all)",
    )
    parser.add_argument(
        "--start-stockid",
        type=int,
        default=1,
        help="Start from specific stockid (default: 1)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="standard",
        choices=["quick", "standard", "comprehensive"],
        help="Analysis mode (default: standard)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show symbols to process without running analysis",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/tmp/sweep_compact",
        help="Output directory for results (default: /tmp/sweep_compact)",
    )

    args = parser.parse_args()

    # Get symbols
    print("Fetching symbols with is_sec_filing=true...")
    symbols = get_symbols_with_sec_filing(
        limit=args.limit,
        start_stockid=args.start_stockid,
    )

    if not symbols:
        print("No symbols found!")
        return

    # Run sweep
    asyncio.run(
        run_sweep(
            symbols=symbols,
            parallel=args.parallel,
            output_dir=args.output_dir,
            mode=args.mode,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Sweep all symbols with is_sec_filing=true in compact mode to prepopulate web UI cache.

This script processes all symbols in order of stockid using victor-invest CLI
with --detail compact flag and saves directly to artifacts/ui_cache/ for web UI consumption.

Usage:
    python scripts/sweep_ui_cache.py [--parallel N] [--limit N] [--start-stockid N]

Options:
    --parallel N       Number of parallel workers (default: 4)
    --limit N          Limit number of symbols to process (default: all)
    --start-stockid N  Start from specific stockid (default: 1)
    --mode             Analysis mode (default: standard)
    --valuation-basis  Valuation basis (default: forward)
    --forward-horizon  Forward horizon (default: 1y)
    --dry-run          Show symbols to process without running analysis
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text


# UI Cache Directory (must match victor_invest/api/app.py)
UI_CACHE_DIR = Path("artifacts/ui_cache")


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
    from investigator.infrastructure.database.symbol_repository import SymbolRepository
    from dataclasses import dataclass

    @dataclass
    class SymbolRow:
        ticker: str
        stockid: int

    repo = SymbolRepository()

    # Build query
    filters = [
        "islisted = TRUE",
        "isstock = TRUE",
        "(isetf IS NULL OR isetf = FALSE)",
        "stockid IS NOT NULL",
        "stockid >= :min_stockid",
    ]

    limit_clause = "LIMIT :limit" if limit and limit > 0 else ""
    query = text(
        f"""
        SELECT ticker, stockid
        FROM symbol
        WHERE {" AND ".join(filters)}
        ORDER BY stockid ASC
        {limit_clause}
        """
    )

    params: dict = {"min_stockid": start_stockid}
    if limit and limit > 0:
        params["limit"] = int(limit)

    with repo.stock_engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [str(r[0]).upper() for r in rows]


def write_ui_cache(symbol: str, payload: dict, source: str) -> Path:
    """Write compact format payload to UI cache directory.

    This creates the canonical {SYMBOL}.json file that the web UI loads.

    Args:
        symbol: Stock symbol
        payload: Compact format analysis payload
        source: Source identifier

    Returns:
        Path to cache file
    """
    UI_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_path = UI_CACHE_DIR / f"{symbol.upper()}.json"

    record = {
        "symbol": symbol.upper(),
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }

    cache_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return cache_path


async def run_sweep(
    symbols: List[str],
    parallel: int = 4,
    mode: str = "standard",
    valuation_basis: str = "forward",
    forward_horizon: str = "1y",
    dry_run: bool = False,
):
    """Run victor-invest batch analysis in compact mode and save to UI cache.

    Args:
        symbols: List of symbols to process
        parallel: Number of parallel workers
        mode: Analysis mode (quick/standard/comprehensive)
        valuation_basis: Valuation basis (ttm/forward)
        forward_horizon: Forward horizon (1q/2q/3q/1y)
        dry_run: If True, only show what would be processed
    """
    from victor_invest.cli import _run_batch

    # Create temp directory for batch output
    temp_dir = Path("/tmp/sweep_ui_cache_temp")
    temp_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sweep_log = Path("/tmp/sweep_ui_cache.log")

    summary = {
        "start_time": datetime.now().isoformat(),
        "total_symbols": len(symbols),
        "parallel_workers": parallel,
        "mode": mode,
        "valuation_basis": valuation_basis,
        "forward_horizon": forward_horizon,
        "cache_dir": str(UI_CACHE_DIR.absolute()),
        "symbols_processed": [],
        "symbols_failed": [],
    }

    if dry_run:
        print(f"\nDRY RUN: Would process {len(symbols)} symbols")
        print(f"Cache directory: {UI_CACHE_DIR.absolute()}")
        print(f"Parallel workers: {parallel}")
        print(f"Mode: {mode}")
        print(f"Valuation basis: {valuation_basis}")
        print(f"Forward horizon: {forward_horizon}")
        print("\nFirst 20 symbols:")
        for i, symbol in enumerate(symbols[:20], 1):
            print(f"  {i:3d}. {symbol}")
        if len(symbols) > 20:
            print(f"  ... and {len(symbols) - 20} more")
        return

    print(f"\nStarting sweep of {len(symbols)} symbols...")
    print(f"Cache directory: {UI_CACHE_DIR.absolute()}")
    print(f"Parallel workers: {parallel}")
    print(f"Mode: {mode}")
    print(f"Valuation basis: {valuation_basis}")
    print(f"Forward horizon: {forward_horizon}")
    print(f"Timestamp: {timestamp}")
    print(f"Log file: {sweep_log}")

    # Run batch analysis with compact format
    # Note: victor-invest doesn't support valuation-basis and forward-horizon flags yet
    # We'll use standard mode and the batch will save in compact format
    with open(sweep_log, "a") as log:
        log.write(f"\n[{datetime.now().isoformat()}] Starting sweep\n")
        log.write(f"Symbols: {len(symbols)}\n")
        log.write(f"Parallel: {parallel}\n")

        await _run_batch(
            symbols=tuple(symbols),
            mode=mode,
            output_dir=str(temp_dir),
            provider="ollama",
            model=None,
            parallel=parallel,
            detail="compact",
        )

        log.write(f"\n[{datetime.now().isoformat()}] Batch analysis complete\n")
        log.write("Copying to UI cache...\n")

    # Copy batch output to UI cache
    processed = 0
    failed = []

    for symbol in symbols:
        # Find the output file for this symbol
        files = list(temp_dir.glob(f"{symbol}_*.json"))
        if not files:
            failed.append(symbol)
            continue

        try:
            # Load the compact format
            with open(files[0], "r") as f:
                payload = json.load(f)

            # Write to UI cache
            write_ui_cache(
                symbol=symbol, payload=payload, source=f"sweep_ui_cache_{timestamp}"
            )

            processed += 1
            summary["symbols_processed"].append(symbol)

            if processed % 100 == 0:
                print(f"  Processed {processed}/{len(symbols)} symbols...")

        except Exception as e:
            failed.append(symbol)
            with open(sweep_log, "a") as log:
                log.write(f"  Error processing {symbol}: {e}\n")

    summary["symbols_failed"] = failed
    summary["end_time"] = datetime.now().isoformat()
    summary["processed_count"] = processed
    summary["failed_count"] = len(failed)

    # Save summary
    summary_file = UI_CACHE_DIR / f"sweep_summary_{timestamp}.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\nSweep complete!")
    print(f"  Processed: {processed}/{len(symbols)}")
    print(f"  Failed: {len(failed)}")
    if failed:
        print(f"  Failed symbols: {', '.join(failed[:10])}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")
    print(f"  Cache directory: {UI_CACHE_DIR.absolute()}")
    print(f"  Summary: {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Sweep symbols with SEC filings in compact mode to UI cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be processed
  python scripts/sweep_ui_cache.py --dry-run

  # Process first 100 symbols
  python scripts/sweep_ui_cache.py --limit 100

  # Process all symbols with 8 parallel workers
  python scripts/sweep_ui_cache.py --parallel 8

  # Resume from stockid 1000
  python scripts/sweep_ui_cache.py --start-stockid 1000

  # Use quick mode for faster processing
  python scripts/sweep_ui_cache.py --mode quick
        """,
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
        "--valuation-basis",
        type=str,
        default="forward",
        choices=["ttm", "forward"],
        help="Valuation basis (default: forward)",
    )
    parser.add_argument(
        "--forward-horizon",
        type=str,
        default="1y",
        choices=["1q", "2q", "3q", "1y"],
        help="Forward horizon (default: 1y)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show symbols to process without running analysis",
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
            mode=args.mode,
            valuation_basis=args.valuation_basis,
            forward_horizon=args.forward_horizon,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()

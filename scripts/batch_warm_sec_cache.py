#!/usr/bin/env python3
"""
Batch SEC Cache Warming Script

Processes top 2000 stock symbols from stock.symbol table (isstock=true),
ordered by stockid (1-2674), excluding recently processed entries.

Note: Top 2000 stocks by stockid are established, real companies.
Stocks beyond stockid > 2674 include penny stocks, microcaps, and
companies with limited or no market cap data.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text

# Top 2000 stocks by stockid threshold (determined from stock.symbol)
MAX_STOCKID_FOR_TOP_2000 = 2674

# Database URLs
STOCK_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/stock"
SEC_DB_URL = (
    "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
)


def get_top_stocks_from_stock_db(max_stockid: int = MAX_STOCKID_FOR_TOP_2000) -> dict:
    """
    Get top 2000 stocks (ticker -> cik mapping) from stock.symbol table.
    Returns dict of ticker -> cik.
    """
    from sqlalchemy import create_engine

    stock_engine = create_engine(STOCK_URL)

    with stock_engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT ticker, cik
            FROM symbol
            WHERE isstock = true
              AND stockid <= :max_stockid
            ORDER BY stockid
        """),
            {"max_stockid": max_stockid},
        )
        return {row[0]: row[1] for row in result}


def get_recently_processed_symbols(exclude_days: int = 30) -> set:
    """Get set of symbols processed in the last N days from sec_database."""
    from sqlalchemy import create_engine

    sec_engine = create_engine(SEC_DB_URL)

    cutoff_date = datetime.now() - timedelta(days=exclude_days)

    with sec_engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT DISTINCT UPPER(symbol) as symbol
            FROM sec_companyfacts_processed
            WHERE fiscal_period = 'FY'
              AND filed_date > :cutoff_date
        """),
            {"cutoff_date": cutoff_date},
        )
        return {row[0] for row in result}


def get_symbols_to_process(
    batch_size: int = 100, offset: int = 0, exclude_recent_days: int = 30
):
    """
    Get stock symbols that need SEC cache warming, ordered by stockid.
    Limited to top 2000 stocks (stockid <= 2674).
    """
    # Get all top stocks and recently processed
    all_stocks = get_top_stocks_from_stock_db()
    recently_processed = get_recently_processed_symbols(exclude_recent_days)

    # Filter out recently processed
    pending_stocks = [
        (ticker, cik)
        for ticker, cik in all_stocks.items()
        if ticker.upper() not in recently_processed
    ]

    # Apply offset and limit
    end_idx = offset + batch_size
    batch = pending_stocks[offset:end_idx]

    return batch


def get_total_symbols_to_process(exclude_recent_days: int = 30) -> int:
    """Get total count of stock symbols needing processing (top 2000 only)."""
    all_stocks = get_top_stocks_from_stock_db()
    recently_processed = get_recently_processed_symbols(exclude_recent_days)

    pending_count = sum(
        1 for ticker in all_stocks.keys() if ticker.upper() not in recently_processed
    )

    return pending_count


def process_batch(symbols: list, batch_num: int, dry_run: bool = False):
    """Process a batch of symbols through SEC cache warming."""
    tickers = [s[0] for s in symbols]

    print(f"\n{'=' * 60}")
    print(f"Batch {batch_num}: {len(tickers)} stock symbols")
    print(f"{'=' * 60}")
    print(f"Symbols: {', '.join(tickers[:10])}")
    if len(tickers) > 10:
        print(f"         ... and {len(tickers) - 10} more")

    if dry_run:
        print("[DRY RUN] Would process these symbols")
        return

    # Run investigator cache warm
    import subprocess

    # Process in smaller sub-batches for stability
    sub_batch_size = 50
    for i in range(0, len(tickers), sub_batch_size):
        sub_batch = tickers[i : i + sub_batch_size]
        print(
            f"\n  Processing sub-batch {i // sub_batch_size + 1}: {', '.join(sub_batch[:5])}..."
        )

        cmd = [
            "investigator",
            "cache",
            "warm",
            "--symbols",
            ",".join(sub_batch),
            "--process-raw",
            "--force-refresh",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes per sub-batch
            )

            if result.returncode == 0:
                print("    ✓ Success")
            else:
                print(f"    ✗ Failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("    ✗ Timeout after 10 minutes")
        except Exception as e:
            print(f"    ✗ Error: {e}")

        # Small delay between sub-batches
        time.sleep(2)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch SEC cache warming for top 2000 stock symbols by stockid (isstock=true, stockid <= 2674)"
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Symbols per batch")
    parser.add_argument("--max-batches", type=int, default=None, help="Max batches")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    parser.add_argument(
        "--exclude-days", type=int, default=30, help="Exclude recent days"
    )
    parser.add_argument("--start-batch", type=int, default=0, help="Start from batch N")

    args = parser.parse_args()

    # Get total count
    print("Counting stock symbols to process...")
    total = get_total_symbols_to_process(args.exclude_days)

    print(f"\nTotal stock symbols needing refresh: {total}")
    print(f"Batch size: {args.batch_size}")
    print(f"Estimated batches: {(total + args.batch_size - 1) // args.batch_size}")
    print(f"Starting from batch: {args.start_batch + 1}")
    print(f"Scope: Top 2000 stocks by stockid (stockid <= {MAX_STOCKID_FOR_TOP_2000})")
    print(
        f"Note: Excludes penny stocks and microcaps (stockid > {MAX_STOCKID_FOR_TOP_2000})"
    )

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        # Show first batch in dry run
        symbols = get_symbols_to_process(
            args.batch_size, args.start_batch * args.batch_size
        )
        if symbols:
            process_batch(symbols, 1, dry_run=True)
        return

    # Process batches
    batch_num = args.start_batch
    offset = args.start_batch * args.batch_size

    while True:
        if args.max_batches and batch_num >= args.max_batches:
            print(f"\nReached maximum batch limit ({args.max_batches})")
            break

        symbols = get_symbols_to_process(
            batch_size=args.batch_size,
            offset=offset,
            exclude_recent_days=args.exclude_days,
        )

        if not symbols:
            print("\nNo more symbols to process!")
            break

        batch_num += 1
        process_batch(symbols, batch_num)

        processed = min(offset + args.batch_size, total)
        print(
            f"\nProgress: {processed}/{total} symbols ({processed / total * 100:.1f}%)"
        )

        offset += args.batch_size
        time.sleep(5)

    print(f"\n{'=' * 60}")
    print(f"Complete! Processed {batch_num - args.start_batch} batches")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

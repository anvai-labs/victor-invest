#!/usr/bin/env python3
"""
Batch SEC Cache Warming Script

Processes all stock symbols from ticker_cik_mapping,
excluding recently processed entries.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from investigator.infrastructure.database.db import get_db_manager
from sqlalchemy import text


def get_symbols_to_process(batch_size: int = 100, offset: int = 0, exclude_recent_days: int = 30):
    """
    Get symbols that need SEC cache warming.
    """
    db_manager = get_db_manager()
    engine = db_manager.engine

    with engine.connect() as conn:
        # Get all ticker_cik_mapping symbols, excluding those recently processed
        interval_str = f"INTERVAL '{exclude_recent_days} days'"
        query = text(f"""
            SELECT t.ticker, t.cik
            FROM ticker_cik_mapping t
            LEFT JOIN sec_companyfacts_processed p
                ON t.ticker = p.symbol
                AND p.fiscal_period = 'FY'
                AND p.filed_date > NOW() - {interval_str}
            WHERE p.symbol IS NULL  -- Exclude recently processed
            ORDER BY t.ticker
            LIMIT :batch_size OFFSET :offset
        """)

        result = conn.execute(query, {"batch_size": batch_size, "offset": offset})
        return [(row[0], row[1]) for row in result]


def get_total_symbols_to_process(exclude_recent_days: int = 30) -> int:
    """Get total count of symbols needing processing."""
    db_manager = get_db_manager()
    engine = db_manager.engine

    with engine.connect() as conn:
        interval_str = f"INTERVAL '{exclude_recent_days} days'"
        result = conn.execute(text(f"""
            SELECT COUNT(DISTINCT t.ticker)
            FROM ticker_cik_mapping t
            LEFT JOIN sec_companyfacts_processed p
                ON t.ticker = p.symbol
                AND p.fiscal_period = 'FY'
                AND p.filed_date > NOW() - {interval_str}
            WHERE p.symbol IS NULL
        """))

        return result.fetchone()[0]


def process_batch(symbols: list, batch_num: int, dry_run: bool = False):
    """Process a batch of symbols through SEC cache warming."""
    tickers = [s[0] for s in symbols]

    print(f"\n{'='*60}")
    print(f"Batch {batch_num}: {len(tickers)} symbols")
    print(f"{'='*60}")
    print(f"Symbols: {', '.join(tickers[:10])}")
    if len(tickers) > 10:
        print(f"         ... and {len(tickers) - 10} more")

    if dry_run:
        print("[DRY RUN] Would process these symbols")
        return

    # Run investigator cache warm
    import subprocess

    # Process in smaller sub-batches to avoid overwhelming the system
    sub_batch_size = 50
    for i in range(0, len(tickers), sub_batch_size):
        sub_batch = tickers[i:i + sub_batch_size]
        print(f"\n  Processing sub-batch {i//sub_batch_size + 1}: {', '.join(sub_batch[:5])}...")

        cmd = [
            "investigator", "cache", "warm",
            "--symbols", ",".join(sub_batch),
            "--process-raw",
            "--force-refresh"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes per sub-batch
            )

            if result.returncode == 0:
                print(f"    ✓ Success")
            else:
                print(f"    ✗ Failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"    ✗ Timeout after 10 minutes")
        except Exception as e:
            print(f"    ✗ Error: {e}")

        # Small delay between sub-batches
        time.sleep(2)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch SEC cache warming"
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Symbols per batch")
    parser.add_argument("--max-batches", type=int, default=None, help="Max batches")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    parser.add_argument("--exclude-days", type=int, default=30, help="Exclude recent days")
    parser.add_argument("--start-batch", type=int, default=0, help="Start from batch N")

    args = parser.parse_args()

    # Get total count
    print("Counting symbols to process...")
    total = get_total_symbols_to_process(args.exclude_days)

    print(f"\nTotal symbols needing refresh: {total}")
    print(f"Batch size: {args.batch_size}")
    print(f"Estimated batches: {(total + args.batch_size - 1) // args.batch_size}")
    print(f"Starting from batch: {args.start_batch + 1}")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        # Show first batch in dry run
        symbols = get_symbols_to_process(args.batch_size, args.start_batch * args.batch_size)
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
            exclude_recent_days=args.exclude_days
        )

        if not symbols:
            print("\nNo more symbols to process!")
            break

        batch_num += 1
        process_batch(symbols, batch_num)

        processed = min(offset + args.batch_size, total)
        print(f"\nProgress: {processed}/{total} symbols")

        offset += args.batch_size
        time.sleep(5)

    print(f"\n{'='*60}")
    print(f"Complete! Processed {batch_num - args.start_batch} batches")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

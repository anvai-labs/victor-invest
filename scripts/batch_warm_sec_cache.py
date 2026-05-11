#!/usr/bin/env python3
"""
Batch SEC Cache Warming Script

Intelligently processes stock symbols from stock.symbol table (isstock=true),
ordered by stockid, excluding recently processed entries.

Cutoff Selection:
- stockid <= 1000: Large/mega caps (avg MC $20-127B) - HIGH VALUE
- stockid 1001-2000: Mid caps (avg MC $4.6B) - GOOD VALUE
- stockid 2001-3000: Mid/small caps (avg MC $6.2B) - GOOD VALUE
- stockid 3001-5000: Small caps (avg MC $1.2B) - MARGINAL VALUE
- stockid > 5000: Micro/penny caps - LOW VALUE

Default: stockid <= 3000 (covers ~1,500 stocks with good market cap coverage)

Uses foreign tables (symbol, tickerdata) in sec_database for efficient joins.
"""

import sys
import time
from pathlib import Path
from typing import Callable

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError


def retry_on_connection_error(func: Callable, max_retries: int = 3, base_delay: float = 2.0):
    """
    Retry function on database connection errors with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except (OperationalError, DBAPIError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2**attempt)
            print(f"    Connection error (attempt {attempt + 1}/{max_retries}): {e}")
            print(f"    Retrying in {delay:.1f} seconds...")
            time.sleep(delay)
    return None


# Default cutoff: stockid <= 3000 (covers ~1,500 stocks)
DEFAULT_MAX_STOCKID = 3000

# Tier definitions based on market cap analysis
TIERS = {
    "large_cap": {"max_stockid": 1000, "avg_mc_b": "$20-127B", "symbols": ~825},
    "mid_cap": {"max_stockid": 2000, "avg_mc_b": "$4.6B", "symbols": ~721},
    "small_cap": {"max_stockid": 3000, "avg_mc_b": "$6.2B", "symbols": ~740},
    "micro_cap": {"max_stockid": 5000, "avg_mc_b": "$1.2B", "symbols": ~1760},
    "nano_cap": {"max_stockid": None, "avg_mc_b": "<$1B", "symbols": ~13000},
}

# SEC database has foreign tables to stock.symbol and stock.tickerdata
SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"


def get_symbols_to_process(
    batch_size: int = 100,
    offset: int = 0,
    exclude_recent_days: int = 30,
    max_stockid: int = DEFAULT_MAX_STOCKID,
) -> list[tuple[str, str | None]]:
    """
    Get stock symbols that need SEC cache warming, ordered by stockid.

    Returns list of (ticker, cik) tuples.
    """

    def _query():
        engine = create_engine(
            SEC_DB_URL,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
            connect_args={"connect_timeout": 10},
        )

        with engine.connect() as conn:
            interval_str = f"INTERVAL '{exclude_recent_days} days'"
            query = text(f"""
                SELECT s.ticker, s.cik
                FROM symbol s
                LEFT JOIN sec_companyfacts_processed p
                    ON UPPER(s.ticker) = p.symbol
                    AND p.fiscal_period = 'FY'
                    AND p.extracted_at > NOW() - {interval_str}
                WHERE s.isstock = true
                  AND (
                    (s.is_sec_filing = true AND s.stockid <= :max_stockid)
                    OR (s.stockid > :max_stockid)
                  )
                  AND p.symbol IS NULL
                ORDER BY s.stockid
                LIMIT :batch_size OFFSET :offset
            """)

            result = conn.execute(
                query,
                {
                    "batch_size": batch_size,
                    "offset": offset,
                    "max_stockid": max_stockid,
                },
            )
            return [(row[0], row[1]) for row in result]

    return retry_on_connection_error(_query)


def get_total_symbols_to_process(exclude_recent_days: int = 30, max_stockid: int = DEFAULT_MAX_STOCKID) -> int:
    """Get total count of stock symbols needing processing."""

    def _query():
        engine = create_engine(
            SEC_DB_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={"connect_timeout": 10},
        )

        with engine.connect() as conn:
            interval_str = f"INTERVAL '{exclude_recent_days} days'"
            result = conn.execute(
                text(f"""
                    SELECT COUNT(DISTINCT s.ticker)
                    FROM symbol s
                    LEFT JOIN sec_companyfacts_processed p
                        ON UPPER(s.ticker) = p.symbol
                        AND p.fiscal_period = 'FY'
                        AND p.extracted_at > NOW() - {interval_str}
                    WHERE s.isstock = true
                      AND (
                        (s.is_sec_filing = true AND s.stockid <= :max_stockid)
                        OR (s.stockid > :max_stockid)
                      )
                      AND p.symbol IS NULL
                """),
                {"max_stockid": max_stockid},
            )
            return result.fetchone()[0]

    return retry_on_connection_error(_query)


def get_tier_name(max_stockid: int) -> str:
    """Get tier name based on max_stockid."""
    if max_stockid <= 1000:
        return "large_cap"
    elif max_stockid <= 2000:
        return "mid_cap"
    elif max_stockid <= 3000:
        return "small_cap"
    elif max_stockid <= 5000:
        return "micro_cap"
    else:
        return "nano_cap"


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
        print(f"\n  Processing sub-batch {i // sub_batch_size + 1}: {', '.join(sub_batch[:5])}...")

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
        description="Batch SEC cache warming for stock symbols (isstock=true)",
        epilog="""
Tier Selection Guide:
  --max-stockid 1000  : Large/mega caps (avg MC $20-127B) - ~825 symbols
  --max-stockid 2000  : + Mid caps (avg MC $4.6B) - ~1,546 symbols total
  --max-stockid 3000  : + Small caps (avg MC $6.2B) - ~2,286 symbols total [DEFAULT]
  --max-stockid 5000  : + Micro caps (avg MC $1.2B) - ~4,046 symbols total
  --max-stockid 10000 : + Nano caps (avg MC <$1B) - ~5,260 symbols total

Recommendation: Use stockid <= 3000 for best balance of coverage and quality.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Symbols per batch")
    parser.add_argument("--max-batches", type=int, default=None, help="Max batches")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    parser.add_argument("--exclude-days", type=int, default=30, help="Exclude recent days")
    parser.add_argument("--start-batch", type=int, default=0, help="Start from batch N")
    parser.add_argument(
        "--max-stockid",
        type=int,
        default=DEFAULT_MAX_STOCKID,
        help="Maximum stockid to process (default: 3000)",
    )

    args = parser.parse_args()

    tier_name = get_tier_name(args.max_stockid)
    tier_info = TIERS.get(tier_name, {})

    # Get total count
    print("Counting stock symbols to process...")
    total = get_total_symbols_to_process(args.exclude_days, args.max_stockid)

    print(f"\nTotal stock symbols needing refresh: {total}")
    print(f"Batch size: {args.batch_size}")
    print(f"Estimated batches: {(total + args.batch_size - 1) // args.batch_size}")
    print(f"Starting from batch: {args.start_batch + 1}")
    print(f"Scope: stockid <= {args.max_stockid} ({tier_name} tier)")
    if tier_info:
        print(f"  Avg market cap: {tier_info.get('avg_mc_b', 'N/A')}")
    print(f"Note: Excludes stocks with stockid > {args.max_stockid}")
    print("Using foreign tables: symbol, tickerdata in sec_database")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        # Show first batch in dry run
        symbols = get_symbols_to_process(
            args.batch_size,
            args.start_batch * args.batch_size,
            args.exclude_days,
            args.max_stockid,
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
            max_stockid=args.max_stockid,
        )

        if not symbols:
            print("\nNo more symbols to process!")
            break

        batch_num += 1
        process_batch(symbols, batch_num)

        processed = min(offset + args.batch_size, total)
        print(f"\nProgress: {processed}/{total} symbols ({processed / total * 100:.1f}%)")

        offset += args.batch_size
        time.sleep(5)

    print(f"\n{'=' * 60}")
    print(f"Complete! Processed {batch_num - args.start_batch} batches")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

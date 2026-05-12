#!/usr/bin/env python3
"""
Real-time batch progress monitor for SEC cache warming.

Run this in a separate terminal while batch_warm_sec_cache.py is running.

Usage:
    python3 scripts/monitor_batch_progress.py
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine

SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"


def check_progress():
    """Check current batch progress."""
    engine = create_engine(SEC_DB_URL)

    print("\n" + "=" * 80)
    print(f"🔍 BATCH PROGRESS CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Overall stats
    df = pd.read_sql(
        """
        SELECT
            COUNT(*) as total_rows,
            COUNT(DISTINCT symbol) as unique_symbols,
            MAX(extracted_at) as last_activity
        FROM sec_companyfacts_processed
    """,
        engine,
    )

    print("\n📊 Database Status:")
    print(f"  Total rows: {df['total_rows'].iloc[0]:,}")
    print(f"  Unique symbols: {df['unique_symbols'].iloc[0]:,}")
    print(f"  Last activity: {df['last_activity'].iloc[0]}")

    # Recent activity (last 5 min)
    df_recent = pd.read_sql(
        """
        SELECT COUNT(*) as count
        FROM sec_companyfacts_processed
        WHERE extracted_at > NOW() - INTERVAL '5 minutes'
    """,
        engine,
    )

    recent_count = df_recent["count"].iloc[0]
    print("\n⚡ Recent Activity:")
    print(f"  Filings in last 5 min: {recent_count:,}")

    # FY2024 coverage
    df_fy2024 = pd.read_sql(
        """
        SELECT COUNT(DISTINCT symbol) as symbols
        FROM sec_companyfacts_processed
        WHERE fiscal_year = 2024 AND fiscal_period = 'FY'
    """,
        engine,
    )

    print("\n📅 FY2024 Coverage:")
    print(f"  Symbols with FY2024: {df_fy2024['symbols'].iloc[0]:,}")

    # Processing rate (last 30 min)
    df_rate = pd.read_sql(
        """
        WITH recent AS (
            SELECT COUNT(*) as filings
            FROM sec_companyfacts_processed
            WHERE extracted_at > NOW() - INTERVAL '30 minutes'
        )
        SELECT
            filings::float / 30 as filings_per_min,
            filings::float / 30 / 60 as filings_per_sec
        FROM recent
    """,
        engine,
    )

    rate = df_rate["filings_per_min"].iloc[0]
    print("\n⚙️  Processing Rate (last 30 min):")
    print(f"  {rate:.1f} filings/minute")

    # ETA calculation
    total_target = 16126  # From your batch output
    current_symbols = df["unique_symbols"].iloc[0]
    remaining = total_target - current_symbols

    if rate > 0:
        eta_minutes = remaining / rate
        eta_hours = eta_minutes / 60

        print("\n📈 Progress Estimate:")
        print(f"  Target: {total_target:,} symbols")
        print(f"  Processed: {current_symbols:,} symbols ({current_symbols / total_target * 100:.1f}%)")
        print(f"  Remaining: {remaining:,} symbols")
        print(f"  ETA: {eta_minutes:.0f} minutes ({eta_hours:.1f} hours)")

        # Calculate completion time
        from datetime import timedelta

        completion = datetime.now() + timedelta(minutes=eta_minutes)
        print(f"  Est. completion: {completion.strftime('%Y-%m-%d %H:%M')}")

    print("\n" + "=" * 80)
    print("💡 Press Ctrl+C to exit, or it will refresh every 30 seconds")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        while True:
            check_progress()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped")

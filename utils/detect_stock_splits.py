#!/usr/bin/env python3
"""
Stock Split Detection Tool

This script analyzes SEC company facts data to detect potential stock splits
by identifying significant, sudden increases in shares outstanding.

Usage:
    python utils/detect_stock_splits.py
    python utils/detect_stock_splits.py --symbol AAPL
    python utils/detect_stock_splits.py --threshold 3.0 --min-increase 50

Detection Logic:
- Stock splits cause SUDDEN, LARGE increases in shares outstanding
- Typical indicators: 2:1, 3:1, 4:1, 5:1, 10:1, 20:1 ratios
- We look for:
    1. Large quarter-over-quarter increase (e.g., >100%)
    2. The increase is near a whole number ratio (2x, 3x, 4x, etc.)
    3. No corresponding stock offering/dividend explanation
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
import os


def get_database_url():
    """Get database URL from environment."""
    db_host = os.environ.get("SEC_DB_HOST", os.environ.get("DB_HOST", "localhost"))
    db_port = os.environ.get("SEC_DB_PORT", os.environ.get("DB_PORT", "5432"))
    db_name = os.environ.get(
        "SEC_DB_NAME", os.environ.get("DB_DATABASE", "sec_database")
    )
    db_user = os.environ.get(
        "SEC_DB_USER", os.environ.get("DB_USERNAME", "investigator")
    )
    db_pass = os.environ.get(
        "SEC_DB_PASSWORD", os.environ.get("DB_PASSWORD", "investigator")
    )

    return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def detect_splits_for_symbol(
    engine, symbol: str, min_increase_pct: float = 50.0, max_ratio: float = 25.0
):
    """
    Detect potential stock splits for a single symbol.

    Args:
        engine: SQLAlchemy database engine
        symbol: Stock symbol
        min_increase_pct: Minimum quarter-over-quarter increase % to consider
        max_ratio: Maximum split ratio to consider (avoid false positives)

    Returns:
        List of potential splits: [(date, ratio, confidence), ...]
    """
    with engine.connect() as conn:
        # Get shares outstanding history, ordered by fiscal period
        query = text("""
            SELECT
                symbol,
                fiscal_year,
                fiscal_period,
                period_end_date,
                shares_outstanding
            FROM sec_companyfacts_processed
            WHERE symbol = :symbol
                AND shares_outstanding IS NOT NULL
                AND shares_outstanding > 0
            ORDER BY period_end_date ASC
        """)

        result = conn.execute(query, {"symbol": symbol})
        rows = result.fetchall()

    if len(rows) < 2:
        return []  # Not enough data

    potential_splits = []
    prev_shares = None

    for row in rows:
        symbol, fy, fp, period_end_date, shares = row

        if prev_shares is not None and prev_shares > 0:
            # Calculate quarter-over-quarter change
            change_pct = ((shares - prev_shares) / prev_shares) * 100

            # Look for large increases
            if change_pct >= min_increase_pct:
                ratio = shares / prev_shares

                # Check if ratio is close to a whole number (2x, 3x, 4x, etc.)
                # Allow some tolerance for float rounding
                whole_ratio = round(ratio)
                tolerance = 0.15  # 15% tolerance

                if abs(ratio - whole_ratio) <= tolerance and ratio <= max_ratio:
                    # Found a potential split!
                    confidence = (
                        "HIGH" if abs(ratio - whole_ratio) <= 0.05 else "MEDIUM"
                    )
                    potential_splits.append(
                        (period_end_date, ratio, confidence, prev_shares, shares)
                    )
                    print(f"  🔍 Potential {whole_ratio}:1 split detected:")
                    print(f"     Date: {period_end_date}")
                    print(f"     Ratio: {ratio:.2f}x (target: {whole_ratio}x)")
                    print(f"     Shares: {prev_shares:,.0f} → {shares:,.0f}")
                    print(f"     Change: +{change_pct:.1f}%")
                    print(f"     Confidence: {confidence}")
                else:
                    # Large increase but not a clean split ratio
                    print("  ⚠️  Unusual shares increase (not a clean split ratio):")
                    print(f"     Date: {period_end_date}")
                    print(f"     Ratio: {ratio:.2f}x")
                    print(f"     Shares: {prev_shares:,.0f} → {shares:,.0f}")
                    print(f"     Change: +{change_pct:.1f}%")
                    print("     Note: Could be stock offering, not split")

        prev_shares = shares

    return potential_splits


def get_all_symbols(engine):
    """Get all unique symbols from sec_companyfacts_processed."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT DISTINCT symbol
            FROM sec_companyfacts_processed
            WHERE shares_outstanding IS NOT NULL
            ORDER BY symbol
        """)
        )
        return [row[0] for row in result.fetchall()]


def get_existing_splits(engine):
    """Get all existing splits from stock_splits table."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT symbol, split_date, split_ratio
            FROM stock_splits
            WHERE split_date IS NOT NULL
            ORDER BY symbol, split_date
        """)
        )
        return {(row[0], row[1]): row[2] for row in result.fetchall()}


def main():
    parser = argparse.ArgumentParser(description="Detect stock splits from SEC data")
    parser.add_argument("--symbol", help="Analyze specific symbol only")
    parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="Minimum %% increase to consider as split (default: 50)",
    )
    parser.add_argument(
        "--max-ratio",
        type=float,
        default=25.0,
        help="Maximum split ratio to consider (default: 25)",
    )
    parser.add_argument("--export-sql", help="Export INSERT statements to file")

    args = parser.parse_args()

    # Source environment file
    env_file = Path.home() / ".investigator" / "env"
    if env_file.exists():
        # Read and parse env file manually to avoid shell subprocess
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip().strip("export")
                    value = value.strip().strip('"')
                    os.environ[key] = value

    engine = create_engine(get_database_url())

    # Get existing splits
    existing_splits = get_existing_splits(engine)
    print(f"📊 Found {len(existing_splits)} existing splits in database\n")

    # Get symbols to analyze
    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = get_all_symbols(engine)
        print(f"🔍 Analyzing {len(symbols)} symbols for potential splits...\n")

    all_detected = []
    export_statements = []

    for symbol in symbols:
        print(f"Symbol: {symbol}")

        # Detect potential splits
        detected = detect_splits_for_symbol(
            engine, symbol, args.threshold, args.max_ratio
        )

        for period_end_date, ratio, confidence, prev_shares, new_shares in detected:
            # Check if already recorded
            # (allow some date flexibility - split might be effective before period end)
            split_date = period_end_date  # Assume split at period end

            # Check for existing split within 60 days
            already_recorded = False
            for (
                existing_symbol,
                existing_date,
            ), existing_ratio in existing_splits.items():
                if existing_symbol == symbol:
                    # Check if dates are close (within 60 days)

                    if abs((period_end_date - existing_date).days) <= 60:
                        # Also check if ratios match (convert both to float to handle Decimal)
                        ratio_float = float(ratio)
                        existing_ratio_float = float(existing_ratio)
                        if abs(ratio_float - existing_ratio_float) <= 0.2:
                            already_recorded = True
                            print(
                                f"     ✓ Already recorded (existing: {existing_ratio}x on {existing_date})"
                            )
                            break

            if not already_recorded:
                all_detected.append(
                    {
                        "symbol": symbol,
                        "split_date": split_date,
                        "ratio": round(ratio, 1),
                        "confidence": confidence,
                        "prev_shares": prev_shares,
                        "new_shares": new_shares,
                    }
                )

                # Generate INSERT statement
                whole_ratio = round(ratio)
                export_statements.append(f"""
INSERT INTO stock_splits (symbol, split_date, split_ratio, description, source)
VALUES (
    '{symbol}',
    '{split_date}',
    {round(ratio, 1)},
    '{whole_ratio}-for-1 stock split (auto-detected from SEC data)',
    'auto_detected'
)
ON CONFLICT (symbol, split_date) DO NOTHING;
""")

        print()

    # Summary
    if all_detected:
        print(f"\n{'=' * 80}")
        print(f"🎯 DETECTED {len(all_detected)} NEW POTENTIAL SPLITS:")
        print(f"{'=' * 80}\n")

        for split in all_detected:
            print(
                f"{split['symbol']}: {split['ratio']}x split on {split['split_date']} (confidence: {split['confidence']})"
            )

        # Export SQL if requested
        if args.export_sql:
            with open(args.export_sql, "w") as f:
                f.write("-- Auto-detected stock splits\n")
                f.write(f"-- Generated: {datetime.now().isoformat()}\n")
                f.write(f"-- Detection threshold: {args.threshold}% increase\n\n")
                f.write(
                    "-- IMPORTANT: Review and verify each split before adding to database!\n\n"
                )
                f.writelines(export_statements)
            print(
                f"\n✅ Exported {len(export_statements)} INSERT statements to {args.export_sql}"
            )
            print(f"   Review the file and run: psql -f {args.export_sql}")
    else:
        print("\n✅ No new splits detected (all existing splits are up to date)")

    print("\n" + "=" * 80)
    print("Next steps:")
    print("1. Review the detected splits above")
    print("2. Verify against historical records (press releases, SEC filings)")
    print("3. Add verified splits using --export-sql or manually")
    print("=" * 80)


if __name__ == "__main__":
    main()

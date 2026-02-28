#!/usr/bin/env python3
"""
SEC Filing Polling Script

Monitors SEC database tables for stale filing data and triggers refresh when needed.

Logic:
1. Check sec_companyfacts_raw or sec_companyfacts_processed for latest filing date
2. Calculate max_filing_date + 90 days
3. If today >= stale_date, data is stale - trigger refresh
4. When fresh submissions are pulled, reset the 90-day timer

Usage:
    python scripts/poll_sec_filings.py --symbol AAPL --interval 3600
    python scripts/poll_sec_filings.py --all-symbols --interval 7200 --verbose

Author: InvestiGator Team
Date: 2026-02-28
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/sec_polling.log"),
    ],
)
logger = logging.getLogger(__name__)


class SECFilingPoller:
    """Polls SEC database for stale filing data and triggers refresh."""

    def __init__(
        self,
        db_url: str,
        stock_db_url: Optional[str] = None,
        stale_days: int = 90,
        check_table: str = "sec_companyfacts_processed",
    ):
        """
        Initialize the SEC filing poller.

        Args:
            db_url: SEC database connection URL
            stock_db_url: Stock database connection URL (for symbol metadata)
            stale_days: Days after which data is considered stale (default: 90)
            check_table: Table to check for latest filing date
                        Options: sec_companyfacts_processed, sec_companyfacts_raw
        """
        self.db_url = db_url
        self.stock_db_url = stock_db_url
        self.stale_days = stale_days
        self.check_table = check_table
        self.engine: Optional[Engine] = None
        self.stock_engine: Optional[Engine] = None

    def connect(self) -> Engine:
        """Establish database connection."""
        try:
            self.engine = create_engine(self.db_url)
            return self.engine
        except Exception as e:
            logger.error(f"Failed to connect to SEC database: {e}")
            raise

    def connect_stock_db(self) -> Engine:
        """Establish connection to stock database for symbol metadata."""
        if not self.stock_db_url:
            raise ValueError("stock_db_url not configured")
        try:
            self.stock_engine = create_engine(self.stock_db_url)
            return self.stock_engine
        except Exception as e:
            logger.error(f"Failed to connect to stock database: {e}")
            raise

    def get_latest_filing_date(self, symbol: Optional[str] = None) -> Optional[datetime]:
        """
        Get the latest filing date from the configured table.

        Args:
            symbol: Filter by specific symbol (None = all symbols)

        Returns:
            Latest filing date as datetime, or None if no data found
        """
        if not self.engine:
            self.connect()

        try:
            with self.engine.connect() as conn:
                if self.check_table == "sec_companyfacts_processed":
                    # Check processed table
                    if symbol:
                        query = text("""
                            SELECT MAX(filed_date) as latest_date
                            FROM sec_companyfacts_processed
                            WHERE symbol = :symbol
                        """)
                        result = conn.execute(query, {"symbol": symbol})
                    else:
                        query = text("""
                            SELECT MAX(filed_date) as latest_date
                            FROM sec_companyfacts_processed
                        """)
                        result = conn.execute(query)
                elif self.check_table == "sec_companyfacts_raw":
                    # Check raw table
                    if symbol:
                        query = text("""
                            SELECT MAX(filed) as latest_date
                            FROM sec_companyfacts_raw
                            WHERE ticker = :symbol
                        """)
                        result = conn.execute(query, {"symbol": symbol})
                    else:
                        query = text("""
                            SELECT MAX(filed) as latest_date
                            FROM sec_companyfacts_raw
                        """)
                        result = conn.execute(query)
                else:
                    raise ValueError(f"Unknown table: {self.check_table}")

                row = result.fetchone()
                if row and row[0]:
                    return row[0]
                return None

        except Exception as e:
            logger.error(f"Error fetching latest filing date: {e}")
            return None

    def check_stale_status(self, symbol: Optional[str] = None) -> Tuple[bool, Optional[datetime], Optional[datetime]]:
        """
        Check if filing data is stale.

        Args:
            symbol: Filter by specific symbol

        Returns:
            (is_stale, latest_date, stale_date)
        """
        latest_date = self.get_latest_filing_date(symbol)

        if not latest_date:
            logger.warning(f"No filing data found for {symbol or 'all symbols'}")
            return True, None, None  # No data = stale

        # Calculate stale threshold
        stale_date = latest_date + timedelta(days=self.stale_days)
        today = datetime.now().date()
        latest_date_only = latest_date.date() if hasattr(latest_date, "date") else latest_date

        is_stale = today >= stale_date

        if is_stale:
            days_stale = (today - stale_date).days
            logger.warning(
                f"{symbol or 'All symbols'}: Data is STALE by {days_stale} days | "
                f"Latest: {latest_date_only} | Stale date: {stale_date}"
            )
        else:
            days_until_stale = (stale_date - today).days
            logger.info(
                f"{symbol or 'All symbols'}: Data is FRESH | "
                f"Latest: {latest_date_only} | Stale in {days_until_stale} days"
            )

        return is_stale, latest_date, stale_date

    def trigger_refresh(self, symbols: List[str]) -> bool:
        """
        Trigger SEC data refresh for specified symbols.

        Args:
            symbols: List of symbols to refresh

        Returns:
            True if refresh triggered successfully
        """
        logger.info(f"Triggering SEC data refresh for {len(symbols)} symbols...")

        # Run the investigator cache warm command
        import subprocess

        cmd = [
            "investigator",
            "cache",
            "warm",
            "--symbols",
            ",".join(symbols),
            "--process-raw",
            "--force-refresh",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            if result.returncode == 0:
                logger.info("SEC data refresh completed successfully")
                return True
            else:
                logger.error(f"SEC data refresh failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("SEC data refresh timed out after 1 hour")
            return False
        except Exception as e:
            logger.error(f"Error triggering SEC data refresh: {e}")
            return False

    def poll_once(self, symbols: List[str]) -> dict:
        """
        Perform a single poll check for stale data.

        Args:
            symbols: List of symbols to check

        Returns:
            Dict with polling results
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "stale_symbols": [],
            "fresh_symbols": [],
            "no_data_symbols": [],
        }

        for symbol in symbols:
            is_stale, latest_date, stale_date = self.check_stale_status(symbol)

            if latest_date is None:
                results["no_data_symbols"].append(symbol)
            elif is_stale:
                results["stale_symbols"].append(
                    {
                        "symbol": symbol,
                        "latest_date": str(latest_date),
                        "stale_date": str(stale_date),
                    }
                )
            else:
                results["fresh_symbols"].append(
                    {
                        "symbol": symbol,
                        "latest_date": str(latest_date),
                        "stale_date": str(stale_date),
                    }
                )

        return results

    def poll_all_symbols(
        self, filter_sec_filing: bool = True, override_symbols: Optional[List[str]] = None
    ) -> List[str]:
        """
        Get all symbols from the stock database that should be monitored.

        Args:
            filter_sec_filing: If True, filter by is_sec_filing=true or is_sec_files=true
            override_symbols: If provided, return these symbols directly (bypasses all filters)

        Returns:
            List of symbols ordered by stock_id
        """
        if override_symbols:
            logger.info(f"Using override symbols: {len(override_symbols)} symbols")
            return override_symbols

        if not self.stock_db_url:
            raise ValueError(
                "stock_db_url must be configured for --all-symbols. "
                "Set STOCK_DB_HOST, STOCK_DB_NAME, STOCK_DB_USER, STOCK_DB_PASSWORD environment variables."
            )

        if not self.stock_engine:
            self.connect_stock_db()

        try:
            with self.stock_engine.connect() as conn:
                # Query from symbol table in stock database
                if filter_sec_filing:
                    query = text("""
                        SELECT ticker
                        FROM symbol
                        WHERE is_sec_filing = true OR is_sec_files = true
                        ORDER BY stockid
                    """)
                else:
                    query = text("""
                        SELECT ticker
                        FROM symbol
                        ORDER BY stockid
                    """)

                result = conn.execute(query)
                symbols = [row[0] for row in result.fetchall()]
                logger.info(f"Found {len(symbols)} symbols in stock.symbol (filter_sec_filing={filter_sec_filing})")
                return symbols

        except Exception as e:
            logger.error(f"Error fetching symbols from stock database: {e}")
            return []

    def run_polling_loop(
        self,
        symbols: Optional[List[str]] = None,
        interval_seconds: int = 3600,
        refresh_on_stale: bool = True,
        filter_sec_filing: bool = True,
    ):
        """
        Run continuous polling loop.

        Args:
            symbols: List of symbols to poll (None = all symbols in table)
            interval_seconds: Seconds between polls (default: 3600 = 1 hour)
            refresh_on_stale: Whether to trigger refresh when stale data detected
            filter_sec_filing: Filter by is_sec_filing=true when symbols=None
        """
        logger.info(f"Starting SEC filing polling loop (interval: {interval_seconds}s)")
        logger.info(f"Checking table: {self.check_table} | Stale threshold: {self.stale_days} days")

        if symbols is None:
            symbols = self.poll_all_symbols(filter_sec_filing=filter_sec_filing)
            logger.info(f"Found {len(symbols)} symbols to monitor")

        while True:
            try:
                # Check all symbols
                stale_symbols = []
                for symbol in symbols:
                    is_stale, _, _ = self.check_stale_status(symbol)
                    if is_stale:
                        stale_symbols.append(symbol)

                # Trigger refresh if any stale data found
                if stale_symbols and refresh_on_stale:
                    logger.info(f"Found {len(stale_symbols)} stale symbols, triggering refresh...")
                    self.trigger_refresh(stale_symbols)

                # Log summary and wait
                logger.info(
                    f"Poll complete. Next check in {interval_seconds} seconds ({interval_seconds // 60} minutes)"
                )

                import time

                time.sleep(interval_seconds)

            except KeyboardInterrupt:
                logger.info("Polling stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                import time

                time.sleep(60)  # Wait 1 minute before retrying


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Poll SEC database for stale filing data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check single symbol
  python %(prog)s --symbol AAPL

  # Check all symbols
  python %(prog)s --all-symbols

  # Continuous polling with custom interval
  python %(prog)s --all-symbols --interval 7200 --continuous

  # Use raw table instead of processed
  python %(prog)s --all-symbols --table sec_companyfacts_raw

  # Custom stale threshold (default: 90 days)
  python %(prog)s --symbol AAPL --stale-days 60
        """,
    )

    parser.add_argument(
        "--symbol",
        help="Check specific symbol (can be used multiple times)",
        action="append",
        dest="symbols",
    )
    parser.add_argument(
        "--all-symbols",
        help="Check all symbols in database table",
        action="store_true",
    )
    parser.add_argument(
        "--table",
        choices=["sec_companyfacts_processed", "sec_companyfacts_raw"],
        default="sec_companyfacts_processed",
        help="Table to check for latest filing (default: sec_companyfacts_processed)",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=90,
        help="Days after which data is considered stale (default: 90)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Polling interval in seconds (default: 3600 = 1 hour)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous polling loop",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Don't trigger refresh on stale data (check only)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Don't filter by is_sec_filing=true when using --all-symbols",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get database URL from environment
    import os

    # Support both SEC_DB_* and DB_* prefixes
    db_host = os.getenv("SEC_DB_HOST") or os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("SEC_DB_PORT") or os.getenv("DB_PORT", "5432")
    db_name = os.getenv("SEC_DB_NAME") or os.getenv("DB_NAME", "sec_database")
    db_user = os.getenv("SEC_DB_USER") or os.getenv("DB_USER", db_name)  # Fallback to db name
    db_password = os.getenv("SEC_DB_PASSWORD") or os.getenv("DB_PASSWORD", "")

    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    # Stock database for symbol metadata
    stock_db_host = os.getenv("STOCK_DB_HOST") or os.getenv("DB_HOST", "localhost")
    stock_db_port = os.getenv("STOCK_DB_PORT") or os.getenv("DB_PORT", "5432")
    stock_db_name = os.getenv("STOCK_DB_NAME") or os.getenv("DB_NAME", "stock")
    stock_db_user = os.getenv("STOCK_DB_USER") or os.getenv("DB_USER", stock_db_name)
    stock_db_password = os.getenv("STOCK_DB_PASSWORD") or os.getenv("DB_PASSWORD", "")

    stock_db_url = f"postgresql://{stock_db_user}:{stock_db_password}@{stock_db_host}:{stock_db_port}/{stock_db_name}"

    # Determine which symbols to check and filter settings
    filter_sec_filing = not args.no_filter
    symbols = args.symbols  # Directly specified symbols (overrides all filters)
    use_all_symbols = args.all_symbols

    if not symbols and not use_all_symbols:
        parser.error("Must specify --symbol or --all-symbols")

    # Create poller and run
    poller = SECFilingPoller(
        db_url=db_url,
        stock_db_url=stock_db_url,
        stale_days=args.stale_days,
        check_table=args.table,
    )

    if args.continuous:
        poller.run_polling_loop(
            symbols=symbols,  # None means fetch from DB with filters
            interval_seconds=args.interval,
            refresh_on_stale=not args.no_refresh,
            filter_sec_filing=filter_sec_filing,
        )
    else:
        # Single poll check
        if symbols is None:
            # Fetch all symbols from DB with filters
            symbols = poller.poll_all_symbols(filter_sec_filing=filter_sec_filing)

        results = poller.poll_once(symbols)

        print("\n" + "=" * 60)
        print("SEC Filing Poll Results")
        print("=" * 60)
        print(f"Total symbols checked: {len(symbols)}")
        print(f"Fresh symbols: {len(results['fresh_symbols'])}")
        print(f"Stale symbols: {len(results['stale_symbols'])}")
        print(f"No data symbols: {len(results['no_data_symbols'])}")

        if results["stale_symbols"]:
            print("\nStale symbols:")
            for item in results["stale_symbols"]:
                print(f"  - {item['symbol']}: Latest {item['latest_date']}, Stale date {item['stale_date']}")

            if not args.no_refresh:
                stale_symbols = [s["symbol"] for s in results["stale_symbols"]]
                print(f"\nTriggering refresh for {len(stale_symbols)} stale symbols...")
                poller.trigger_refresh(stale_symbols)

        sys.exit(0 if not results["stale_symbols"] else 1)


if __name__ == "__main__":
    main()

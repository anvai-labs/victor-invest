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
    python scripts/poll_sec_filings.py --all-symbols --continuous --include-submissions

Author: InvestiGator Team
Date: 2026-02-28
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

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
    ):
        """
        Initialize the SEC filing poller.

        Args:
            db_url: SEC database connection URL
            stock_db_url: Stock database connection URL (for symbol metadata)
            stale_days: Days after which data is considered stale (default: 90)
        """
        self.db_url = db_url
        self.stock_db_url = stock_db_url
        self.stale_days = stale_days
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
            Get the latest filing date from sec_companyfacts_processed.

            This checks the actual SEC filing date (filed_date), not when we fetched it.

        Args:
                symbol: Filter by specific symbol (None = all symbols)

            Returns:
                Latest filing date as datetime, or None if no data found
        """
        if not self.engine:
            self.connect()

        try:
            with self.engine.connect() as conn:
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

                row = result.fetchone()
                if row and row[0]:
                    return row[0]
                return None

        except Exception as e:
            logger.error(f"Error fetching latest filing date: {e}")
            return None

    def get_last_fetch_date(self, symbol: str) -> Optional[datetime]:
        """
        Get when we last fetched data from SEC for this symbol.

        This prevents excessive SEC API calls - don't refetch if we just checked.

        Args:
            symbol: Stock symbol to check

        Returns:
            Last fetch datetime, or None if never fetched
        """
        if not self.engine:
            self.connect()

        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT MAX(fetched_at) as latest_fetch
                    FROM sec_companyfacts_raw
                    WHERE symbol = :symbol
                """)
                result = conn.execute(query, {"symbol": symbol})
                row = result.fetchone()
                if row and row[0]:
                    return row[0]
                return None

        except Exception as e:
            logger.error(f"Error fetching last fetch date: {e}")
            return None

    def check_stale_status(self, symbol: Optional[str] = None) -> Tuple[bool, Optional[datetime], Optional[datetime]]:
        """
        Check if filing data is stale using TWO checks:

        1. filed_date check: Is the latest filing older than stale_days (default 90)?
           - If company filed 90+ days ago, data is stale and needs refresh

        2. fetched_at check: Did we recently try to refresh with no new data?
           - Skip if we just checked today (SEC API rate limiting)
           - Skip if we checked in last 7 days and filing is < 120 days old

        Args:
            symbol: Filter by specific symbol

        Returns:
            (is_stale, latest_filed_date, stale_date)
        """
        latest_filed_date = self.get_latest_filing_date(symbol)

        if not latest_filed_date:
            logger.warning(f"No filing data found for {symbol or 'all symbols'}")
            return True, None, None  # No data = stale

        # Check 1: Is the filing date old enough to be stale?
        stale_date = latest_filed_date + timedelta(days=self.stale_days)
        today = datetime.now().date()
        latest_date_only = latest_filed_date.date() if hasattr(latest_filed_date, "date") else latest_filed_date

        is_filing_stale = today >= stale_date

        # Check 2: Did we recently fetch? (prevent excessive SEC API calls)
        skip_refresh = False
        if symbol and is_filing_stale:
            last_fetch = self.get_last_fetch_date(symbol)
            if last_fetch:
                fetch_date = last_fetch.date() if hasattr(last_fetch, "date") else last_fetch
                days_since_fetch = (today - fetch_date).days
                days_since_filing = (today - latest_date_only).days

                # Don't refetch if we just checked today
                if days_since_fetch == 0:
                    logger.info(
                        f"{symbol}: Filing is {days_since_filing} days old, "
                        f"but we just checked today ({days_since_fetch} days ago). Skipping to avoid excessive SEC API calls."
                    )
                    skip_refresh = True
                # Don't refetch if we checked recently (7 days) and filing isn't super old (120+ days)
                elif days_since_fetch <= 7 and days_since_filing < 120:
                    logger.info(
                        f"{symbol}: Filing is {days_since_filing} days old, "
                        f"but we recently checked ({days_since_fetch} days ago). Skipping to avoid excessive SEC API calls."
                    )
                    skip_refresh = True

        is_stale = is_filing_stale and not skip_refresh

        if skip_refresh:
            # Not refreshing, but technically still "stale" by date definition
            pass
        elif is_filing_stale:
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

        return is_stale, latest_filed_date, stale_date

    def trigger_refresh(
        self,
        symbols: List[str],
        include_submissions: bool = False,
        analyze: bool = False,
        analysis_mode: str = "standard",
    ) -> bool:
        """
        Trigger SEC data refresh for specified symbols.

        Args:
            symbols: List of symbols to refresh
            include_submissions: Also fetch submissions along with CompanyFacts
            analyze: Run victor-invest analysis after refresh
            analysis_mode: Analysis mode (quick, standard, comprehensive)

        Returns:
            True if refresh triggered successfully
        """
        logger.info(
            f"Triggering SEC data refresh for {len(symbols)} symbols"
            + (" (with submissions)" if include_submissions else "")
            + (f" + analysis ({analysis_mode})" if analyze else "")
        )

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

        if include_submissions:
            cmd.append("--include-submissions")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            if result.returncode == 0:
                logger.info("SEC data refresh completed successfully")

                # Run analysis if requested
                if analyze:
                    for symbol in symbols:
                        logger.info(f"Running {analysis_mode} analysis for {symbol}...")
                        analyze_cmd = ["victor-invest", "analyze", symbol, "--mode", analysis_mode]
                        analyze_result = subprocess.run(analyze_cmd, capture_output=True, text=True, timeout=1800)
                        if analyze_result.returncode == 0:
                            logger.info(f"Analysis completed for {symbol}")
                        else:
                            logger.warning(f"Analysis failed for {symbol}: {analyze_result.stderr}")

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

    def poll_and_refresh(
        self,
        symbols: List[str],
        refresh_on_stale: bool = True,
        include_submissions: bool = False,
        analyze: bool = False,
        analysis_mode: str = "standard",
        on_progress=None,
    ) -> dict:
        """
        Poll symbols one-by-one and trigger refresh immediately when stale.

        This provides natural spacing between SEC API calls and better observability.

        Args:
            symbols: List of symbols to check and potentially refresh
            refresh_on_stale: Whether to trigger refresh when stale data detected
            include_submissions: Also fetch submissions along with CompanyFacts
            analyze: Run victor-invest analysis after refresh
            analysis_mode: Analysis mode (quick, standard, comprehensive)
            on_progress: Optional callback function(symbol, status) for progress updates

        Returns:
            Dict with polling results
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "checked": 0,
            "fresh": 0,
            "stale": 0,
            "no_data": 0,
            "refreshed": [],
            "failed": [],
        }

        for symbol in symbols:
            results["checked"] += 1

            # Check staleness
            is_stale, latest_date, stale_date = self.check_stale_status(symbol)

            if latest_date is None:
                results["no_data"] += 1
                status = "NO_DATA"
            elif is_stale:
                results["stale"] += 1
                status = "STALE"

                # Trigger refresh immediately
                if refresh_on_stale:
                    try:
                        success = self.trigger_refresh(
                            [symbol],
                            include_submissions=include_submissions,
                            analyze=analyze,
                            analysis_mode=analysis_mode,
                        )
                        if success:
                            results["refreshed"].append(symbol)
                            status = "REFRESHED"
                        else:
                            results["failed"].append(symbol)
                            status = "REFRESH_FAILED"
                    except Exception as e:
                        logger.error(f"Error refreshing {symbol}: {e}")
                        results["failed"].append(symbol)
                        status = "REFRESH_ERROR"
            else:
                results["fresh"] += 1
                status = "FRESH"

            # Progress callback
            if on_progress:
                on_progress(symbol, status)

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
                # Use same filters as get_sec_filing_symbols() in symbol_repository.py
                if filter_sec_filing:
                    query = text("""
                        SELECT ticker
                        FROM symbol
                        WHERE is_sec_filing = TRUE
                          AND islisted = TRUE
                          AND isstock = TRUE
                          AND (isetf IS NULL OR isetf = FALSE)
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
        include_submissions: bool = False,
        analyze: bool = False,
        analysis_mode: str = "standard",
    ):
        """
        Run continuous polling loop.

        Args:
            symbols: List of symbols to poll (None = all symbols in table)
            interval_seconds: Seconds between polls (default: 3600 = 1 hour)
            refresh_on_stale: Whether to trigger refresh when stale data detected
            filter_sec_filing: Filter by is_sec_filing=true when symbols=None
            include_submissions: Also fetch submissions along with CompanyFacts
            analyze: Run victor-invest analysis after refresh
            analysis_mode: Analysis mode (quick, standard, comprehensive)
        """
        logger.info(f"Starting SEC filing polling loop (interval: {interval_seconds}s)")
        logger.info(f"Stale threshold: {self.stale_days} days (based on SEC filing date)")
        if include_submissions:
            logger.info("Submissions will be fetched along with CompanyFacts")
        if analyze:
            logger.info(f"Analysis ({analysis_mode}) will run after each successful refresh")

        if symbols is None:
            symbols = self.poll_all_symbols(filter_sec_filing=filter_sec_filing)
            logger.info(f"Found {len(symbols)} symbols to monitor")

        while True:
            try:
                # Progress callback for logging
                def log_progress(symbol: str, status: str):
                    logger.info(f"[{symbol}] {status}")

                # Process all symbols sequentially with immediate refresh
                results = self.poll_and_refresh(
                    symbols=symbols,
                    refresh_on_stale=refresh_on_stale,
                    include_submissions=include_submissions,
                    analyze=analyze,
                    analysis_mode=analysis_mode,
                    on_progress=log_progress,
                )

                # Log summary
                logger.info(
                    f"Poll cycle complete: "
                    f"Checked={results['checked']}, "
                    f"Fresh={results['fresh']}, "
                    f"Stale={results['stale']}, "
                    f"No Data={results['no_data']}, "
                    f"Refreshed={len(results['refreshed'])}, "
                    f"Failed={len(results['failed'])}"
                )

                # Wait for next poll cycle
                logger.info(f"Next check in {interval_seconds} seconds ({interval_seconds // 60} minutes)")

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
        description="Poll SEC database for stale filing data and refresh+analyze when needed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check all symbols (default behavior - refreshes stale, runs analysis)
  python %(prog)s

  # Check specific symbol
  python %(prog)s --symbol AAPL

  # Check multiple symbols (use --symbol multiple times)
  python %(prog)s --symbol AAPL --symbol TRV --symbol HIG

  # Check only, don't analyze
  python %(prog)s --no-analyze

  # Quick analysis instead of standard
  python %(prog)s --mode quick

  # Don't include submissions
  python %(prog)s --no-include-submissions

  # Continuous polling with custom interval
  python %(prog)s --interval 7200 --continuous

  # Custom stale threshold (default: 90 days)
  python %(prog)s --stale-days 60
        """,
    )

    parser.add_argument(
        "--symbol",
        "-s",
        help="Check specific symbol (can be specified multiple times: --symbol AAPL --symbol TRV). If not specified, checks all SEC filing symbols.",
        action="append",
        dest="symbols",
        default=None,
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
        help="Don't filter by is_sec_filing=true (default: filters for SEC filing symbols)",
    )
    parser.add_argument(
        "--no-include-submissions",
        action="store_true",
        help="Don't fetch submissions along with CompanyFacts during refresh (default: includes submissions)",
    )
    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Don't run victor-invest analysis after refresh (default: runs analysis)",
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "comprehensive"],
        default="standard",
        help="Analysis mode (default: standard)",
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
    include_submissions = not args.no_include_submissions  # Default: True
    analyze = not args.no_analyze  # Default: True
    analysis_mode = args.mode
    symbols = args.symbols  # Directly specified symbols, None means use all SEC filing symbols

    # Create poller and run
    poller = SECFilingPoller(
        db_url=db_url,
        stock_db_url=stock_db_url,
        stale_days=args.stale_days,
    )

    if args.continuous:
        poller.run_polling_loop(
            symbols=symbols,  # None means fetch from DB with filters
            interval_seconds=args.interval,
            refresh_on_stale=not args.no_refresh,
            filter_sec_filing=filter_sec_filing,
            include_submissions=include_submissions,
            analyze=analyze,
            analysis_mode=analysis_mode,
        )
    else:
        # Single run - process symbols sequentially with immediate refresh
        if symbols is None:
            # Fetch all symbols from DB with filters
            symbols = poller.poll_all_symbols(filter_sec_filing=filter_sec_filing)

        print(f"\nProcessing {len(symbols)} symbols sequentially...")
        if include_submissions:
            print("Include submissions: enabled")
        if analyze:
            print(f"Analysis mode: {analysis_mode}")
        print("=" * 60)

        # Progress callback for terminal output
        def log_progress(symbol: str, status: str):
            status_emoji = {
                "FRESH": "✅",
                "STALE": "🔄",
                "REFRESHED": "🆕",
                "REFRESH_FAILED": "❌",
                "NO_DATA": "⚠️",
                "REFRESH_ERROR": "💥",
            }.get(status, "❓")
            print(f"  {status_emoji} {symbol}: {status}")

        results = poller.poll_and_refresh(
            symbols=symbols,
            refresh_on_stale=not args.no_refresh,
            include_submissions=include_submissions,
            analyze=analyze,
            analysis_mode=analysis_mode,
            on_progress=log_progress,
        )

        # Print summary
        print()
        print("=" * 60)
        print("SEC Filing Poll Results")
        print("=" * 60)
        print(f"Total symbols checked: {results['checked']}")
        print(f"Fresh: {results['fresh']} | Stale: {results['stale']} | No Data: {results['no_data']}")
        print(f"Refreshed: {len(results['refreshed'])} | Failed: {len(results['failed'])}")

        if results["refreshed"]:
            print("\nRefreshed symbols:")
            for symbol in results["refreshed"][:10]:  # Show first 10
                print(f"  ✅ {symbol}")
            if len(results["refreshed"]) > 10:
                print(f"  ... and {len(results['refreshed']) - 10} more")

        if results["failed"]:
            print("\nFailed symbols:")
            for symbol in results["failed"][:10]:  # Show first 10
                print(f"  ❌ {symbol}")
            if len(results["failed"]) > 10:
                print(f"  ... and {len(results['failed']) - 10} more")

        sys.exit(0 if not results["failed"] else 1)


if __name__ == "__main__":
    main()

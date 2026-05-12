# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Backfill company sector premium history.

Populates company_sector_premium_history table with historical data
from sec_companyfacts_processed and sector_multiples_history.
"""

import argparse
import logging
import sys
from typing import List

# Add src to path for imports
sys.path.insert(0, "/Users/vijaysingh/code/victor-invest")

from investigator.domain.services.company_premium_history import (
    CompanyPremiumHistory,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_symbols_to_backfill(sectors: List[str] = None, limit: int = None) -> List[str]:
    """Get list of symbols to backfill.

    Args:
        sectors: List of sectors to filter (None = all)
        limit: Maximum number of symbols to process (None = all)

    Returns:
        List of symbols
    """
    from sqlalchemy import create_engine, text

    from investigator.config import get_config

    config = get_config()
    stock_db_url = config.database.url.replace("/sec_database", "/stock")
    engine = create_engine(stock_db_url)

    with engine.connect() as conn:
        query = """
            SELECT DISTINCT ticker
            FROM symbol
            WHERE islisted = true
        """

        params = {}

        if sectors:
            sector_list = ", ".join([f"'{s.title()}'" for s in sectors])
            query += f' AND "Sector" IN ({sector_list})'

        query += " ORDER BY ticker"

        if limit:
            query += f" LIMIT {limit}"

        result = conn.execute(text(query), params)

        symbols = [row[0] for row in result]

    logger.info(f"Found {len(symbols)} symbols to backfill")
    return symbols


def backfill_symbol(symbol: str, service: CompanyPremiumHistory, years: List[int]) -> dict:
    """Backfill premium data for a single symbol.

    Args:
        symbol: Stock symbol
        service: CompanyPremiumHistory service instance
        years: List of fiscal years to backfill

    Returns:
        Dict with results
    """
    logger.info(f"Backfilling {symbol}...")

    results = {
        "symbol": symbol,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "years_processed": [],
    }

    for year in years:
        try:
            # Calculate premium for FY
            premium_data = service.calculate_premium_for_period(symbol=symbol, fiscal_year=year, fiscal_period="FY")

            if premium_data:
                # Store in database
                if service.store_premium_record(premium_data):
                    results["success"] += 1
                    results["years_processed"].append(year)
                    logger.debug(f"  {symbol} FY{year}: Success")
                else:
                    results["failed"] += 1
                    logger.warning(f"  {symbol} FY{year}: Failed to store")
            else:
                results["skipped"] += 1
                logger.debug(f"  {symbol} FY{year}: Skipped (no data)")

        except Exception as e:
            results["failed"] += 1
            logger.error(f"  {symbol} FY{year}: Error - {e}")

    return results


def backfill_company_premium_history(
    sectors: List[str] = None,
    symbols: List[str] = None,
    start_year: int = 2020,
    end_year: int = 2025,
    limit: int = None,
    dry_run: bool = False,
):
    """Backfill company sector premium history.

    Args:
        sectors: List of sectors to backfill (None = all)
        symbols: List of specific symbols to backfill (overrides sectors)
        start_year: Start fiscal year
        end_year: End fiscal year
        limit: Maximum number of symbols to process
        dry_run: Calculate without storing
    """
    logger.info("=" * 80)
    logger.info("Company Sector Premium History Backfill")
    logger.info("=" * 80)
    logger.info(f"Sectors: {sectors or 'All'}")
    logger.info(f"Symbols: {symbols or 'Auto-detect'}")
    logger.info(f"Years: {start_year} - {end_year}")
    logger.info(f"Limit: {limit or 'No limit'}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 80)

    # Initialize service
    service = CompanyPremiumHistory()

    # Determine symbols to process
    if symbols:
        symbols_to_process = symbols
    else:
        symbols_to_process = get_symbols_to_backfill(sectors=sectors, limit=limit)

    if not symbols_to_process:
        logger.error("No symbols to process")
        return

    # Years to backfill
    years = list(range(start_year, end_year + 1))

    # Backfill each symbol
    total_success = 0
    total_skipped = 0
    total_failed = 0

    for i, symbol in enumerate(symbols_to_process, 1):
        logger.info(f"[{i}/{len(symbols_to_process)}] Processing {symbol}...")

        if dry_run:
            # Just calculate, don't store
            for year in years:
                premium_data = service.calculate_premium_for_period(symbol=symbol, fiscal_year=year, fiscal_period="FY")
                if premium_data:
                    total_success += 1
                    logger.info(f"  {symbol} FY{year}: P/E premium = {premium_data.get('pe_premium_pct', 'N/A')}%")
                else:
                    total_skipped += 1
        else:
            # Calculate and store
            results = backfill_symbol(symbol, service, years)
            total_success += results["success"]
            total_skipped += results["skipped"]
            total_failed += results["failed"]

    # Summary
    logger.info("=" * 80)
    logger.info("Backfill Summary")
    logger.info("=" * 80)
    logger.info(f"Symbols processed: {len(symbols_to_process)}")
    logger.info(f"Years per symbol: {len(years)}")
    logger.info(f"Successful: {total_success}")
    logger.info(f"Skipped: {total_skipped}")
    logger.info(f"Failed: {total_failed}")
    logger.info("=" * 80)


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(description="Backfill company sector premium history")

    parser.add_argument(
        "--sectors",
        nargs="+",
        help="Sectors to backfill (e.g., Technology Healthcare)",
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to backfill (e.g., AAPL MSFT GOOGL)",
    )

    parser.add_argument(
        "--start-year",
        type=int,
        default=2020,
        help="Start fiscal year (default: 2020)",
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=2025,
        help="End fiscal year (default: 2025)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of symbols to process",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate without storing in database",
    )

    args = parser.parse_args()

    backfill_company_premium_history(
        sectors=args.sectors,
        symbols=args.symbols,
        start_year=args.start_year,
        end_year=args.end_year,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

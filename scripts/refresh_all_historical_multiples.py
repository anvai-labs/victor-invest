#!/usr/bin/env python3
"""
Refresh all historical sector and industry multiples.

Calculates and stores historical multiples for all fiscal years (2020-2024)
for all sectors and industries in the database.

Usage:
    python scripts/refresh_all_historical_multiples.py
"""

import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_for_year(year: int) -> bool:
    """Run historical calculation for a specific fiscal year.

    Args:
        year: Fiscal year

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"{'=' * 80}")
    logger.info(f"Processing FY{year}")
    logger.info(f"{'=' * 80}")

    cmd = [
        "investigator",
        "sector-multiples",
        "historical",
        "--fiscal-year",
        str(year),
        "--min-samples",
        "1",  # Allow small samples for better coverage
        "--store",
        "--no-exclude-outliers",  # Don't exclude outliers to capture full range
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes per year
        )

        if result.returncode == 0:
            logger.info(f"✅ FY{year} completed successfully")
            return True
        else:
            logger.error(f"❌ FY{year} failed with return code {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"❌ FY{year} timed out after 10 minutes")
        return False
    except Exception as e:
        logger.error(f"❌ FY{year} failed with exception: {e}")
        return False


def main():
    """Run historical calculation for all fiscal years."""
    years = [2020, 2021, 2022, 2023, 2024]

    logger.info(f"Starting historical multiples refresh for years: {years}")
    logger.info("This will calculate sector AND industry multiples for each year")

    results = {}
    for year in years:
        results[year] = run_for_year(year)

    # Summary
    logger.info(f"{'=' * 80}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 80}")

    successful = sum(1 for success in results.values() if success)
    total = len(results)

    for year, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"  FY{year}: {status}")

    logger.info(f"\nTotal: {successful}/{total} years completed successfully")

    if successful == total:
        logger.info("🎉 All years processed successfully!")
        return 0
    else:
        logger.warning(f"⚠️  {total - successful} year(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

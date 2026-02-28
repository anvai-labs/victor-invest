#!/usr/bin/env python3
"""Add missing columns to sec_companyfacts_processed table.

These columns are needed for sector multiples historical calculation:
- shares_outstanding: Number of shares outstanding
- weighted_average_diluted_shares_outstanding: Diluted shares
- market_cap: Market capitalization
- earnings_per_share: Basic EPS
- earnings_per_share_diluted: Diluted EPS
"""

import logging

from sqlalchemy import text

from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


def upgrade():
    """Add missing columns to sec_companyfacts_processed table."""

    db = get_db_manager()

    # Columns to add with their types
    columns = [
        ("shares_outstanding", "BIGINT"),
        ("weighted_average_diluted_shares_outstanding", "BIGINT"),
        ("market_cap", "BIGINT"),
        ("earnings_per_share", "NUMERIC(20, 6)"),
        ("earnings_per_share_diluted", "NUMERIC(20, 6)"),
    ]

    with db.get_session() as session:
        for col_name, col_type in columns:
            # Check if column exists
            check_query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'sec_companyfacts_processed'
                  AND column_name = :col_name
            """)

            result = session.execute(check_query, {"col_name": col_name})
            exists = result.fetchone() is not None

            if not exists:
                add_query = text(f"""
                    ALTER TABLE sec_companyfacts_processed
                    ADD COLUMN {col_name} {col_type}
                """)
                logger.info(f"Adding column: {col_name} ({col_type})")
                session.execute(add_query)
            else:
                logger.info(f"Column {col_name} already exists, skipping")

        session.commit()

    logger.info("sec_companyfacts_processed table upgrade completed successfully")


def populate_shares_and_market_cap():
    """Populate shares_outstanding and market_cap from SEC data.

    Since sec_companyfacts_raw only has metadata and the actual XBRL data
    is in companyfacts.companyfacts as JSONB, we need to extract from there.

    For shares outstanding, we calculate from market_cap / price when available,
    or use tickerdata.shares with the date matching period_end_date.
    """

    db = get_db_manager()

    with db.get_session() as session:
        logger.info("Populating shares_outstanding and market_cap...")

        # First, try to get shares from tickerdata matching period_end_date
        # This gives us shares outstanding as of the fiscal period end
        update_shares_from_tickerdata = text("""
            UPDATE sec_companyfacts_processed p
            SET shares_outstanding = t.shares::BIGINT
            FROM tickerdata t
            WHERE UPPER(p.symbol) = UPPER(t.symbol)
              AND p.shares_outstanding IS NULL
              AND t.date = DATE(p.period_end_date)
              AND t.shares IS NOT NULL
        """)
        result = session.execute(update_shares_from_tickerdata)
        logger.info(f"Updated {result.rowcount} rows with shares_outstanding (exact date match)")

        # For remaining rows, get shares from nearest date within 7 days
        update_shares_nearest = text("""
            UPDATE sec_companyfacts_processed p
            SET shares_outstanding = t.shares::BIGINT
            FROM tickerdata t
            WHERE UPPER(p.symbol) = UPPER(t.symbol)
              AND p.shares_outstanding IS NULL
              AND t.date >= DATE(p.period_end_date) - INTERVAL '7 days'
              AND t.date <= DATE(p.period_end_date) + INTERVAL '7 days'
              AND t.shares IS NOT NULL
              AND t.date = (
                  SELECT date
                  FROM tickerdata
                  WHERE UPPER(symbol) = UPPER(p.symbol)
                    AND date >= DATE(p.period_end_date) - INTERVAL '7 days'
                    AND date <= DATE(p.period_end_date) + INTERVAL '7 days'
                    AND shares IS NOT NULL
                  ORDER BY ABS(date - DATE(p.period_end_date))
                  LIMIT 1
              )
        """)
        result = session.execute(update_shares_nearest)
        logger.info(f"Updated {result.rowcount} rows with shares_outstanding (nearest date)")

        # Calculate market_cap from price * shares
        # Use price from period_end_date + 90 days (quarter end + filing window)
        update_mc = text("""
            UPDATE sec_companyfacts_processed p
            SET market_cap = ROUND(t.close * p.shares_outstanding)::BIGINT
            FROM tickerdata t
            WHERE UPPER(p.symbol) = UPPER(t.symbol)
              AND p.market_cap IS NULL
              AND p.shares_outstanding IS NOT NULL
              AND t.date = (
                  SELECT date
                  FROM tickerdata
                  WHERE UPPER(symbol) = UPPER(p.symbol)
                    AND date >= DATE(p.period_end_date)
                    AND date <= DATE(p.period_end_date) + INTERVAL '90 days'
                  ORDER BY ABS(date - DATE(p.period_end_date) - INTERVAL '45 days')
                  LIMIT 1
              )
              AND t.close IS NOT NULL
        """)
        result = session.execute(update_mc)
        logger.info(f"Updated {result.rowcount} rows with market_cap (price at ~45 days after period end)")

        # Calculate EPS (basic) = net_income / shares_outstanding
        update_eps_basic = text("""
            UPDATE sec_companyfacts_processed
            SET earnings_per_share = CASE
                WHEN shares_outstanding > 0 AND net_income IS NOT NULL
                THEN ROUND(net_income / shares_outstanding::NUMERIC, 6)
                ELSE NULL
            END
            WHERE earnings_per_share IS NULL
              AND shares_outstanding IS NOT NULL
              AND net_income IS NOT NULL
        """)
        result = session.execute(update_eps_basic)
        logger.info(f"Updated {result.rowcount} rows with earnings_per_share (calculated)")

        # Calculate diluted EPS (assume basic = diluted for simplicity, can be refined)
        update_eps_diluted = text("""
            UPDATE sec_companyfacts_processed
            SET earnings_per_share_diluted = earnings_per_share
            WHERE earnings_per_share_diluted IS NULL
              AND earnings_per_share IS NOT NULL
        """)
        result = session.execute(update_eps_diluted)
        logger.info(f"Updated {result.rowcount} rows with earnings_per_share_diluted (same as basic)")

        # Set weighted_average_diluted_shares_outstanding = shares_outstanding
        update_diluted_shares = text("""
            UPDATE sec_companyfacts_processed
            SET weighted_average_diluted_shares_outstanding = shares_outstanding
            WHERE weighted_average_diluted_shares_outstanding IS NULL
              AND shares_outstanding IS NOT NULL
        """)
        result = session.execute(update_diluted_shares)
        logger.info(f"Updated {result.rowcount} rows with weighted_average_diluted_shares_outstanding")

        session.commit()

    logger.info("Data population completed successfully")


def verify_data():
    """Verify that the data was populated correctly."""

    db = get_db_manager()

    with db.get_session() as session:
        logger.info("Verifying data...")

        # Check column counts
        check_query = text("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(shares_outstanding) as with_shares,
                COUNT(market_cap) as with_market_cap,
                COUNT(earnings_per_share) as with_eps
            FROM sec_companyfacts_processed
        """)

        result = session.execute(check_query)
        row = result.fetchone()

        logger.info(f"Total rows: {row[0]}")
        logger.info(f"Rows with shares_outstanding: {row[1]} ({row[1] / row[0] * 100:.1f}%)")
        logger.info(f"Rows with market_cap: {row[2]} ({row[2] / row[0] * 100:.1f}%)")
        logger.info(f"Rows with earnings_per_share: {row[3]} ({row[3] / row[0] * 100:.1f}%)")

        # Sample a few rows
        sample_query = text("""
            SELECT symbol, fiscal_year, shares_outstanding, market_cap,
                   earnings_per_share, total_revenue, net_income
            FROM sec_companyfacts_processed
            WHERE shares_outstanding IS NOT NULL
            ORDER BY fiscal_year DESC, symbol
            LIMIT 5
        """)

        result = session.execute(sample_query)
        logger.info("\nSample data:")
        for row in result:
            logger.info(
                f"  {row[0]} FY{row[1]}: shares={row[2]}, mc=${row[3] / 1e9:.2f}B, "
                f"eps={row[4]}, revenue=${row[5] / 1e9:.2f}B, net_income=${row[6] / 1e6:.2f}M"
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("Step 1: Adding columns...")
    upgrade()

    print("\nStep 2: Populating data from tickerdata...")
    populate_shares_and_market_cap()

    print("\nStep 3: Verifying data...")
    verify_data()

    print("\n✓ Migration complete!")

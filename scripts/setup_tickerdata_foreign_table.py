#!/usr/bin/env python3
"""Setup tickerdata foreign table in sec_database.

This script creates a foreign table wrapper to the stock database's tickerdata table,
allowing sec_database to query market data directly.
"""

import logging
from sqlalchemy import create_engine, text
from investigator.config import get_config

logger = logging.getLogger(__name__)


def setup_tickerdata_foreign_table():
    """Setup tickerdata as a foreign table in sec_database."""

    config = get_config()

    # SEC database connection
    sec_db_url = config.database.url

    # Note: Foreign tables already exist as public.tickerdata and public.symbol
    # via stock_server FDW (no need to recreate)

    print("Step 1: Creating postgres_fdw extension...")
    sec_engine = create_engine(sec_db_url)

    with sec_engine.begin() as conn:
        # Create extension if not exists
        conn.execute(
            text("""
            CREATE EXTENSION IF NOT EXISTS postgres_fdw
        """)
        )
        print("  ✓ postgres_fdw extension created")

        # Create foreign server to stock database
        conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_foreign_server
                    WHERE srvname = 'stock_db_server'
                ) THEN
                    PERFORM create_foreign_server(
                        'stock_db_server',
                        'postgres_fdw',
                        'dataserver1.singh.local',
                        5432,
                        'stock'
                    );

                    -- Set server options
                    ALTER SERVER stock_db_server OPTIONS (
                        SET host 'dataserver1.singh.local',
                        SET port '5432',
                        SET dbname 'stock'
                    );
                END IF;
            END $$;
        """)
        )
        print("  ✓ Foreign server 'stock_db_server' created/verified")

        # Create user mapping for current user
        conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_user_mapping
                    WHERE srvname = 'stock_db_server'
                      AND usename = current_user
                ) THEN
                    CREATE USER MAPPING FOR current_user
                    SERVER stock_db_server
                    OPTIONS (
                        user 'investigator',
                        password 'investigator'
                    );
                END IF;
            END $$;
        """)
        )
        print("  ✓ User mapping created")

        # Import foreign schema - tickerdata table
        conn.execute(
            text("""
            DO $$
            BEGIN
                -- Create schema for foreign tables if not exists
                CREATE SCHEMA IF NOT EXISTS stock;

                -- Import tickerdata table
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'stock'
                    AND table_name = 'tickerdata'
                ) THEN
                    IMPORT FOREIGN SCHEMA public
                    LIMIT TO (tickerdata, symbol)
                    FROM SERVER stock_db_server
                    INTO stock;
                END IF;
            END $$;
        """)
        )
        print("  ✓ Foreign tables imported: stock.tickerdata, stock.symbol")

    print("\nStep 2: Verifying foreign tables...")
    with sec_engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT schemaname, tablename
            FROM pg_tables
            WHERE schemaname = 'stock'
        """)
        )
        tables = result.fetchall()
        if tables:
            print("  Available foreign tables:")
            for schema, table in tables:
                print(f"    stock.{table}")
        else:
            print("  WARNING: No foreign tables found in stock schema")

    print("\nStep 3: Testing tickerdata access...")
    with sec_engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT COUNT(*) as row_count
            FROM stock.tickerdata
            LIMIT 1
        """)
        )
        row = result.fetchone()
        if row:
            print(f"  ✓ stock.tickerdata accessible ({row[0]} rows)")
        else:
            print("  ✗ Failed to access stock.tickerdata")
            return False

    print("\n✓ Foreign table setup complete!")
    print("\nYou can now query tickerdata in sec_database:")
    print("  SELECT * FROM stock.tickerdata LIMIT 10")
    print("  SELECT * FROM stock.symbol WHERE isstock = true LIMIT 10")

    return True


def populate_new_columns_from_tickerdata():
    """Populate new columns using tickerdata foreign table."""

    print("\nStep 4: Populating shares_outstanding and market_cap...")

    config = get_config()
    sec_engine = create_engine(config.database.url)

    with sec_engine.begin() as conn:
        # Update shares_outstanding from tickerdata matching period_end_date
        update_shares = text("""
            UPDATE sec_companyfacts_processed p
            SET shares_outstanding = t.shares::BIGINT
            FROM stock.tickerdata t
            WHERE UPPER(p.symbol) = UPPER(t.symbol)
              AND p.shares_outstanding IS NULL
              AND t.date = DATE(p.period_end_date)
              AND t.shares IS NOT NULL
        """)
        result = conn.execute(update_shares)
        print(f"  Updated {result.rowcount} rows with shares_outstanding (exact match)")

        # For remaining rows, get shares from nearest date within ±7 days
        update_shares_nearest = text("""
            UPDATE sec_companyfacts_processed p
            SET shares_outstanding = subq.shares::BIGINT
            FROM (
                SELECT p.symbol, p.period_end_date,
                       (SELECT t.shares
                        FROM stock.tickerdata t
                        WHERE UPPER(t.symbol) = UPPER(p.symbol)
                          AND t.date >= DATE(p.period_end_date) - INTERVAL '7 days'
                          AND t.date <= DATE(p.period_end_date) + INTERVAL '7 days'
                          AND t.shares IS NOT NULL
                        ORDER BY ABS(t.date - DATE(p.period_end_date))
                        LIMIT 1) as shares
                FROM sec_companyfacts_processed p
                WHERE p.shares_outstanding IS NULL
            ) subq
            WHERE UPPER(sec_companyfacts_processed.symbol) = UPPER(subq.symbol)
              AND sec_companyfacts_processed.period_end_date = subq.period_end_date
              AND sec_companyfacts_processed.shares_outstanding IS NULL
              AND subq.shares IS NOT NULL
        """)
        result = conn.execute(update_shares_nearest)
        print(
            f"  Updated {result.rowcount} rows with shares_outstanding (nearest ±7 days)"
        )

        # Calculate market_cap using price ~45 days after period end
        update_mc = text("""
            UPDATE sec_companyfacts_processed p
            SET market_cap = ROUND(subq.close * p.shares_outstanding)::BIGINT
            FROM (
                SELECT p.symbol, p.period_end_date, p.shares_outstanding,
                       (SELECT t.close
                        FROM stock.tickerdata t
                        WHERE UPPER(t.symbol) = UPPER(p.symbol)
                          AND t.date >= DATE(p.period_end_date)
                          AND t.date <= DATE(p.period_end_date) + INTERVAL '90 days'
                          AND t.close IS NOT NULL
                        ORDER BY ABS(t.date - DATE(p.period_end_date) - INTERVAL '45 days')
                        LIMIT 1) as close
                FROM sec_companyfacts_processed p
                WHERE p.market_cap IS NULL
                  AND p.shares_outstanding IS NOT NULL
            ) subq
            WHERE UPPER(sec_companyfacts_processed.symbol) = UPPER(subq.symbol)
              AND sec_companyfacts_processed.period_end_date = subq.period_end_date
              AND sec_companyfacts_processed.market_cap IS NULL
              AND subq.close IS NOT NULL
        """)
        result = conn.execute(update_mc)
        print(f"  Updated {result.rowcount} rows with market_cap")

        # Calculate EPS = net_income / shares_outstanding
        update_eps = text("""
            UPDATE sec_companyfacts_processed
            SET earnings_per_share = ROUND(net_income / shares_outstanding::NUMERIC, 6)
            WHERE earnings_per_share IS NULL
              AND shares_outstanding IS NOT NULL
              AND shares_outstanding > 0
              AND net_income IS NOT NULL
        """)
        result = conn.execute(update_eps)
        print(f"  Updated {result.rowcount} rows with earnings_per_share")

        # Set diluted EPS = basic EPS
        update_eps_diluted = text("""
            UPDATE sec_companyfacts_processed
            SET earnings_per_share_diluted = earnings_per_share
            WHERE earnings_per_share_diluted IS NULL
              AND earnings_per_share IS NOT NULL
        """)
        result = conn.execute(update_eps_diluted)
        print(f"  Updated {result.rowcount} rows with earnings_per_share_diluted")

        # Set weighted_average_diluted_shares_outstanding
        update_diluted_shares = text("""
            UPDATE sec_companyfacts_processed
            SET weighted_average_diluted_shares_outstanding = shares_outstanding
            WHERE weighted_average_diluted_shares_outstanding IS NULL
              AND shares_outstanding IS NOT NULL
        """)
        result = conn.execute(update_diluted_shares)
        print(
            f"  Updated {result.rowcount} rows with weighted_average_diluted_shares_outstanding"
        )

    print("\nStep 5: Verification...")
    with sec_engine.connect() as conn:
        check_query = text("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(shares_outstanding) as with_shares,
                COUNT(market_cap) as with_market_cap,
                COUNT(earnings_per_share) as with_eps
            FROM sec_companyfacts_processed
        """)
        result = conn.execute(check_query)
        row = result.fetchone()
        print(f"  Total rows: {row[0]}")
        print(f"  With shares_outstanding: {row[1]} ({row[1] / row[0] * 100:.1f}%)")
        print(f"  With market_cap: {row[2]} ({row[2] / row[0] * 100:.1f}%)")
        print(f"  With earnings_per_share: {row[3]} ({row[3] / row[0] * 100:.1f}%)")

    print("\n✓ Column population complete!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 70)
    print("Setting up tickerdata foreign table and populating new columns")
    print("=" * 70)

    if setup_tickerdata_foreign_table():
        populate_new_columns_from_tickerdata()
        print("\n" + "=" * 70)
        print("Setup complete! You can now:")
        print("  1. Run: investor cache warm --force-refresh")
        print("  2. Run: investor sector-multiples historical --year 2024 --store")
        print("=" * 70)
    else:
        print("\n✗ Setup failed. Please check database connections and permissions.")

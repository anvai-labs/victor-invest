#!/usr/bin/env python3
"""Populate shares_outstanding and market_cap in sec_companyfacts_processed.

Uses existing database managers to connect to both stock and sec databases.
Joins via symbol/cik to get tickerdata shares and price data.
"""

import logging
from sqlalchemy import text
from investigator.infrastructure.database.db import get_db_manager
from investigator.infrastructure.database.symbol_repository import SymbolRepository

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Get SEC database manager (for sec_companyfacts_processed)
    sec_db = get_db_manager()

    # Get stock database connection via SymbolRepository (for tickerdata)
    symbol_repo = SymbolRepository()

    print("Step 1: Populating shares_outstanding from tickerdata...")

    # We need to use stock_db connection for tickerdata
    # Update via cross-database query using dblink or fetch data first
    # Simpler: fetch tickerdata shares for matching dates, then update

    with symbol_repo.stock_engine.connect() as stock_conn:
        # Fetch shares data for symbols and dates
        shares_query = text("""
            SELECT symbol, date, shares
            FROM tickerdata
            WHERE shares IS NOT NULL
        """)
        shares_data = stock_conn.execute(shares_query).fetchall()
        print(f"  Fetched {len(shares_data)} rows from tickerdata")

    # Now update sec_companyfacts_processed in batches
    with sec_db.get_session() as sec_session:
        update_count = 0
        for symbol, date, shares in shares_data:
            update = text("""
                UPDATE sec_companyfacts_processed
                SET shares_outstanding = :shares
                WHERE UPPER(symbol) = UPPER(:symbol)
                  AND shares_outstanding IS NULL
                  AND DATE(period_end_date) = :date
            """)
            result = sec_session.execute(
                update, {"symbol": symbol, "date": date, "shares": shares}
            )
            update_count += result.rowcount

        sec_session.commit()
        print(
            f"  Updated {update_count} rows with shares_outstanding (exact date match)"
        )

    print("\nStep 2: Populating remaining shares from nearby dates...")

    with symbol_repo.stock_engine.connect() as stock_conn:
        # Get unique symbols from sec_companyfacts_processed that need shares
        with sec_db.get_session() as sec_session:
            missing_shares = sec_session.execute(
                text("""
                SELECT DISTINCT UPPER(symbol) as symbol, period_end_date
                FROM sec_companyfacts_processed
                WHERE shares_outstanding IS NULL
                ORDER BY symbol, period_end_date
                LIMIT 10000
            """)
            ).fetchall()

        print(f"  Processing {len(missing_shares)} symbol-period combinations")

        batch_updates = []
        for symbol, period_end in missing_shares:
            # Find nearest tickerdata date within ±7 days
            nearest_query = text("""
                SELECT shares
                FROM tickerdata
                WHERE UPPER(symbol) = UPPER(:symbol)
                  AND date >= :start_date
                  AND date <= :end_date
                  AND shares IS NOT NULL
                ORDER BY ABS(date - :target_date)
                LIMIT 1
            """)
            result = stock_conn.execute(
                nearest_query,
                {
                    "symbol": symbol,
                    "start_date": str(period_end)[:-3] + "01",  # 7 days before (approx)
                    "end_date": str(period_end)[:-3] + "15",  # 7 days after (approx)
                    "target_date": str(period_end),
                },
            ).fetchone()

            if result and result[0]:
                batch_updates.append(
                    {"symbol": symbol, "period_end": period_end, "shares": result[0]}
                )

        # Batch update
        with sec_db.get_session() as sec_session:
            for update_data in batch_updates[:5000]:  # Limit for speed
                update = text("""
                    UPDATE sec_companyfacts_processed
                    SET shares_outstanding = :shares
                    WHERE UPPER(symbol) = UPPER(:symbol)
                      AND shares_outstanding IS NULL
                      AND period_end_date = :period_end
                """)
                sec_session.execute(update, update_data)

            sec_session.commit()
            print(f"  Updated {len(batch_updates[:5000])} rows with nearby shares")

    print("\nStep 3: Calculating market_cap and EPS...")

    with sec_db.get_session() as sec_session:
        # Calculate market_cap using tickerdata price ~45 days after period end
        update_mc = text("""
            UPDATE sec_companyfacts_processed p
            SET market_cap = ROUND(t.close * p.shares_outstanding)::BIGINT
            FROM (SELECT symbol, date, close
                  FROM tickerdata
                  WHERE close IS NOT NULL) t
            WHERE UPPER(p.symbol) = UPPER(t.symbol)
              AND p.market_cap IS NULL
              AND p.shares_outstanding IS NOT NULL
              AND t.date >= DATE(p.period_end_date)
              AND t.date <= DATE(p.period_end_date) + INTERVAL '90 days'
              AND t.date = (
                  SELECT date
                  FROM tickerdata t2
                  WHERE UPPER(t2.symbol) = UPPER(t.symbol)
                    AND t2.date >= DATE(p.period_end_date)
                    AND t2.date <= DATE(p.period_end_date) + INTERVAL '90 days'
                    AND t2.close IS NOT NULL
                  ORDER BY ABS(t2.date - DATE(p.period_end_date) - INTERVAL '45 days')
                  LIMIT 1
              )
        """)
        result = sec_session.execute(update_mc)
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
        result = sec_session.execute(update_eps)
        print(f"  Updated {result.rowcount} rows with earnings_per_share")

        # Set diluted EPS = basic EPS (simplification)
        update_eps_diluted = text("""
            UPDATE sec_companyfacts_processed
            SET earnings_per_share_diluted = earnings_per_share
            WHERE earnings_per_share_diluted IS NULL
              AND earnings_per_share IS NOT NULL
        """)
        result = sec_session.execute(update_eps_diluted)
        print(f"  Updated {result.rowcount} rows with earnings_per_share_diluted")

        # Set weighted_average_diluted_shares_outstanding
        update_diluted_shares = text("""
            UPDATE sec_companyfacts_processed
            SET weighted_average_diluted_shares_outstanding = shares_outstanding
            WHERE weighted_average_diluted_shares_outstanding IS NULL
              AND shares_outstanding IS NOT NULL
        """)
        result = sec_session.execute(update_diluted_shares)
        print(
            f"  Updated {result.rowcount} rows with weighted_average_diluted_shares_outstanding"
        )

        sec_session.commit()

    print("\nStep 4: Verification...")

    with sec_db.get_session() as sec_session:
        check_query = text("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(shares_outstanding) as with_shares,
                COUNT(market_cap) as with_market_cap,
                COUNT(earnings_per_share) as with_eps
            FROM sec_companyfacts_processed
        """)
        result = sec_session.execute(check_query)
        row = result.fetchone()
        print(f"  Total rows: {row[0]}")
        print(f"  With shares_outstanding: {row[1]} ({row[1] / row[0] * 100:.1f}%)")
        print(f"  With market_cap: {row[2]} ({row[2] / row[0] * 100:.1f}%)")
        print(f"  With earnings_per_share: {row[3]} ({row[3] / row[0] * 100:.1f}%)")

    print("\n✓ Complete!")


if __name__ == "__main__":
    main()

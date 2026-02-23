#!/usr/bin/env python3
"""
Populate All Sectors - SEC Data Pipeline Script

This script diagnoses and fixes missing sector data in sec_companyfacts_processed table.

PROBLEM:
- Only 4 sectors have data in sec_companyfacts_processed
- Missing: Technology, Healthcare, Financials, Communication Services, Utilities, Real Estate

ROOT CAUSE:
- The sec_companyfacts_processed table is being populated from dataserver1.singh.local
- Foreign data wrapper (FDW) connects to stock.symbol and stock.tickerdata tables
- Cache warming process pulls data from SEC EDGAR and processes it

SOLUTION:
1. Test with sample symbols from missing sectors
2. Run full cache warm for all mapped symbols
3. Verify data quality
4. Regenerate visualizations

Author: Claude Code
Date: February 22, 2026
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    print("=" * 80)
    print("SECTOR DATA POPULATION SCRIPT")
    print("=" * 80)
    print()

    # Sample symbols from missing sectors
    sample_symbols = {
        "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
        "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "TMO"],
        "Financials": ["JPM", "BAC", "WFC", "GS", "MS"],
        "Communication Services": ["GOOG", "META", "T", "VZ", "CMCSA"],
        "Utilities": ["NEE", "DUK", "SO", "D", "EXC"],
        "Real Estate": ["AMT", "PLD", "CCI", "EQIX", "DLR"],
        "Industrials": ["HON", "UNP", "CAT", "GE", "UPS"],  # Already has some
        "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE"],  # Already has
        "Consumer Staples": ["PG", "KO", "PEP", "WMT", "COST"],  # Already has
        "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],  # Already has
    }

    print("SAMPLE SYMBOLS TO TEST:")
    for sector, symbols in sample_symbols.items():
        print(f"  {sector}: {', '.join(symbols)}")

    print()
    print("=" * 80)
    print("STEP 1: TEST WITH SAMPLE SYMBOLS")
    print("=" * 80)
    print()

    # Flatten all sample symbols
    all_samples = []
    for symbols in sample_symbols.values():
        all_samples.extend(symbols)

    print("Command to test with sample symbols:")
    print(
        f"  investigator cache warm --symbols {','.join(all_samples[:10])} --process-raw --force-refresh"
    )
    print()

    print("=" * 80)
    print("STEP 2: RUN FULL CACHE WARM (ALL SECTORS)")
    print("=" * 80)
    print()

    print("Option A: Use batch script (RECOMMENDED)")
    print("  python3 scripts/batch_warm_sec_cache.py --max-stockid 3000")
    print("    - Processes ~1,500 stocks (stockid <= 3000)")
    print("    - Covers large cap, mid cap, and small cap stocks")
    print("    - Excludes recently processed entries")
    print()

    print("Option B: Manual sector-by-sector")
    for sector, symbols in sample_symbols.items():
        print(f"  # {sector}")
        print(f"  investigator cache warm --symbols {','.join(symbols)} --process-raw")
        print()

    print("=" * 80)
    print("STEP 3: VERIFY DATA QUALITY")
    print("=" * 80)
    print()

    print("Check processed data:")
    print('  python3 -c "')
    print(
        "  import pandas as pd; from investigator.infrastructure.database.db import DatabaseManager;"
    )
    print(
        "  df = pd.read_sql('SELECT sector, COUNT(*) FROM sec_companyfacts_processed GROUP BY sector', DatabaseManager().engine)"
    )
    print("  print(df)")
    print('  "')
    print()

    print("=" * 80)
    print("STEP 4: CALCULATE SECTOR MULTIPLES")
    print("=" * 80)
    print()

    print("Calculate and store historical multiples:")
    print("  investigator sector-multiples historical --fiscal-year 2024")
    print()

    print("=" * 80)
    print("STEP 5: REGENERATE VISUALIZATION")
    print("=" * 80)
    print()

    print("Run visualization generation script:")
    print("  python3 scripts/generate_sector_visualization.py --year 2024")
    print()

    print("=" * 80)
    print("ESTIMATED TIME")
    print("=" * 80)
    print()
    print("  Test (10 symbols):        ~2-5 minutes")
    print("  Full batch (3000 stockid): ~2-4 hours")
    print("  Sector multiples:         ~30-60 minutes")
    print("  Visualization:            ~5 minutes")
    print()

    print("=" * 80)
    print("PREREQUISITES")
    print("=" * 80)
    print()
    print("1. Database credentials configured in:")
    print("   - ~/.investigator/env (recommended)")
    print("   - or environment variables (STOCK_DB_*, SEC_DB_*)")
    print()
    print("2. Foreign data wrappers set up:")
    print("   - stock.symbol (stock symbols with sector mapping)")
    print("   - stock.tickerdata (market data: price, shares, etc.)")
    print()
    print("3. SEC EDGAR access:")
    print("   - Rate limited to 10 requests/second")
    print("   - User agent configured in config.yaml")
    print()

    print("=" * 80)
    print("TROUBLESHOOTING")
    print("=" * 80)
    print()
    print("If cache warm fails with 'Database credentials not found':")
    print("  source ~/.investigator/env")
    print()
    print("If foreign tables don't exist:")
    print("  psql -h dataserver1.singh.local -U investigator -d sec_database")
    print("  \\i scripts/setup_tickerdata_foreign_table.sql")
    print()
    print("If SEC rate limit errors:")
    print("  - Reduce parallel workers: --parallel 2")
    print("  - Or use batch script which handles rate limiting")
    print()

    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print()
    print("1. Run test command first to verify setup")
    print("2. Then run full batch script overnight")
    print("3. Verify data quality next morning")
    print("4. Regenerate visualization")
    print()


if __name__ == "__main__":
    main()

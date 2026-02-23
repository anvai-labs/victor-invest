# Sector Data Pipeline - Complete Fix Guide

**Problem Identified:** Only 4 sectors (Consumer Discretionary, Industrials, Energy, Consumer Staples) were represented in the visualization, missing 7 major sectors (Technology, Healthcare, Financials, etc.).

**Root Cause:** The database already has **161,232 rows** and **3,724 symbols** processed, but the sector multiples calculation was only finding data in the local database connection, not the remote dataserver1.singh.local.

**Solution:** The data pipeline is working correctly. Need to ensure sector multiples calculation connects to dataserver1 and processes all symbols.

---

## Quick Start (Test First)

```bash
# 1. Source environment variables
source ~/.investigator/env

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Test with 5 symbols from missing sectors
investigator cache warm --symbols AAPL,MSFT,GOOGL,JNJ,JPM --process-raw --force-refresh

# Expected: ~2 minutes, processes 5 symbols
# Result: ✅ Working - 161,232 rows, 3,724 symbols in database
```

---

## Full Population Commands

### Option A: Batch Script (Recommended)

```bash
# Processes ~1,500 stocks (stockid <= 3000)
# Covers large cap, mid cap, small cap
# Excludes recently processed entries
# Estimated time: 2-4 hours

python3 scripts/batch_warm_sec_cache.py --max-stockid 3000
```

### Option B: Sector-by-Sector

```bash
# Technology (157 symbols in sector_mapping.json)
investigator cache warm --symbols AAPL,MSFT,GOOGL,META,NVDA,ADBE,CRM,CSCO,AVGO,AMD --process-raw

# Healthcare (100 symbols)
investigator cache warm --symbols JNJ,UNH,PFE,ABBV,TMO,MRK,ABT,DHR,LLY,BMY --process-raw

# Financials (141 symbols)
investigator cache warm --symbols JPM,BAC,WFC,GS,MS,C,BLK,SPGI,SCHW,ICE --process-raw

# Communication Services (24 symbols)
investigator cache warm --symbols GOOG,META,T,VZ,CMCSA,DIS,FOX,NFLX,EA,ATVI --process-raw

# Utilities (53 symbols)
investigator cache warm --symbols NEE,DUK,SO,D,EXC,AWK,ETR,AEP,SRE,CMS --process-raw

# Real Estate (41 symbols)
investigator cache warm --symbols AMT,PLD,CCI,EQIX,DLR,PRO,O,VERR,WELL,EXR --process-raw

# Industrials (113 symbols) - Already has some
investigator cache warm --symbols HON,UNP,CAT,GE,UPS,RTN,LMT,BA,MMM,DE --process-raw

# Consumer Discretionary (177 symbols) - Already has some
investigator cache warm --symbols AMZN,TSLA,HD,MCD,NKE,TJX,SBUX,F,GM,MAR --process-raw

# Consumer Staples (35 symbols) - Already has some
investigator cache warm --symbols PG,KO,PEP,WMT,COST,MDLZ,K,MO,CL,EL --process-raw

# Energy (43 symbols) - Already has some
investigator cache warm --symbols XOM,CVX,COP,SLB,EOG,MPC,PSX,VLO,EC,BKR --process-raw
```

### Option C: All Symbols from sector_mapping.json

```bash
# Extract all symbols and process in batches
# Total: 906 symbols across 11 sectors

# Create symbol list
python3 << 'EOF'
import json
with open('data/sector_mapping.json') as f:
    mapping = json.load(f)

symbols_by_sector = {}
for symbol, sector in mapping.items():
    if sector not in symbols_by_sector:
        symbols_by_sector[sector] = []
    symbols_by_sector[sector].append(symbol)

for sector, symbols in sorted(symbols_by_sector.items()):
    print(f"{sector}: {len(symbols)} symbols")
    print(f"  investigator cache warm --symbols {','.join(symbols[:50])} --process-raw")
    if len(symbols) > 50:
        print(f"  investigator cache warm --symbols {','.join(symbols[50:])} --process-raw")
EOF
```

---

## Calculate Sector Multiples

After populating data, calculate sector multiples:

```bash
# Calculate for FY2024 (all sectors)
investigator sector-multiples historical --fiscal-year 2024 --store

# Verify results
investigator sector-multiples timeline --years 2024

# View specific sector
investigator sector-multiples historical --fiscal-year 2024 --sectors Technology
```

---

## Regenerate Visualization

```bash
# After sector multiples are calculated
python3 scripts/generate_sector_visualization.py --year 2024
```

---

## Database Status

### Current State (as of Feb 22, 2026)

```
sec_companyfacts_processed:
  - Total rows: 161,232
  - Unique symbols: 3,724
  - Database: dataserver1.singh.local:5432/sec_database
  - Connection: postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database
```

### Sector Coverage (from sector_mapping.json)

```
Technology:              157 symbols
Consumer Discretionary:  177 symbols
Financials:              141 symbols
Industrials:             113 symbols
Healthcare:              100 symbols
Utilities:                53 symbols
Energy:                   43 symbols
Real Estate:              41 symbols
Consumer Staples:         35 symbols
Communication Services:   24 symbols
Materials:                22 symbols
---
Total:                   906 symbols
```

---

## Troubleshooting

### Error: "Database credentials not found"

```bash
# Source environment file
source ~/.investigator/env

# Verify variables are set
echo $STOCK_DB_HOST
echo $STOCK_DB_PASSWORD
```

### Error: "relation does not exist"

```bash
# Connect to remote database and check tables
psql -h dataserver1.singh.local -U investigator -d sec_database

\dt sec_companyfacts_*

# Should show:
# sec_companyfacts_raw
# sec_companyfacts_processed
# sec_companyfacts_metadata
```

### Error: "No such command 'get'"

```bash
# Use correct command syntax
investigator sector-multiples historical --fiscal-year 2024
investigator sector-multiples timeline --years 2024
```

### SEC Rate Limit Errors

```bash
# Reduce parallel workers
investigator cache warm --symbols AAPL,MSFT,GOOGL --process-raw --parallel 2

# Or use batch script which handles rate limiting
python3 scripts/batch_warm_sec_cache.py --max-stockid 1000 --parallel 2
```

---

## Estimated Times

| Task | Symbols | Time |
|------|---------|------|
| Test run | 5 | ~2 minutes |
| Technology sector | 157 | ~15 minutes |
| Healthcare sector | 100 | ~10 minutes |
| Financials sector | 141 | ~15 minutes |
| All sectors (batch 3000) | ~1,500 | ~2-4 hours |
| Sector multiples calculation | - | ~30-60 minutes |
| Visualization generation | - | ~5 minutes |

---

## Verification

### Check Processed Data Count

```bash
python3 << 'EOF'
import pandas as pd
from sqlalchemy import create_engine

SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
engine = create_engine(SEC_DB_URL)

df = pd.read_sql("""
    SELECT COUNT(*) as total_rows,
           COUNT(DISTINCT symbol) as unique_symbols
    FROM sec_companyfacts_processed
""", engine)

print(f"Total rows: {df['total_rows'].iloc[0]:,}")
print(f"Unique symbols: {df['unique_symbols'].iloc[0]:,}")
EOF
```

### Check Sector Representation

```bash
python3 << 'EOF'
import pandas as pd
from sqlalchemy import create_engine

SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
engine = create_engine(SEC_DB_URL)

df = pd.read_sql("""
    SELECT s.sector, COUNT(DISTINCT scp.symbol) as symbol_count
    FROM sec_companyfacts_processed scp
    JOIN stock.symbol s ON scp.symbol = UPPER(s.ticker)
    WHERE scp.fiscal_year = 2024 AND scp.fiscal_period = 'FY'
    GROUP BY s.sector
    ORDER BY symbol_count DESC
""", engine)

print("Sector representation in FY2024:")
print(df.to_string(index=False))
EOF
```

---

## Next Steps

1. ✅ **Test with sample symbols** - Verify pipeline works
2. ⏳ **Run batch script overnight** - Process all 1,500 stocks
3. ⏳ **Verify data quality** - Check sector coverage next morning
4. ⏳ **Calculate sector multiples** - Run historical calculation
5. ⏳ **Regenerate visualization** - Create complete visualization with all 10 sectors

---

## Related Files

- Population script: `scripts/populate_all_sectors.py`
- Batch warm script: `scripts/batch_warm_sec_cache.py`
- Sector mapping: `data/sector_mapping.json`
- Visualization: `docs/assets/visualizations/sector_timeline_2024.html`
- Status tracker: `docs/assets/visualizations/SECTOR_DATA_STATUS.md`

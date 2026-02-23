# Sector Data Status (FY2024)

## Current Status

**Last Updated:** February 22, 2026

### Available Sectors in Database

The `sec_companyfacts_processed` table currently contains data for **4 out of 11 sectors**:

| Sector | Symbols Available | Status |
|--------|------------------|--------|
| Consumer Discretionary | 261 | ✅ Complete |
| Industrials | 157 | ✅ Complete |
| Energy | 44 | ✅ Complete |
| Consumer Staples | 38 | ✅ Complete |
| Technology | 0 | ❌ Missing |
| Healthcare | 0 | ❌ Missing |
| Financials | 0 | ❌ Missing |
| Communication Services | 0 | ❌ Missing |
| Utilities | 0 | ❌ Missing |
| Real Estate | 0 | ❌ Missing |
| Materials | 0 | ❌ Missing |

### Root Cause

The `sec_companyfacts_processed` table is missing data for 7 major sectors. This appears to be a data pipeline issue where:

1. **Initial data load** may have been limited to specific sectors
2. **SEC data ingestion** process may have filtering logic excluding certain symbols
3. **Market data joins** may be failing for symbols in missing sectors

### Sector Mapping Coverage

The `data/sector_mapping.json` file contains mappings for all 11 sectors:

```
Technology: 157 symbols
Consumer Discretionary: 177 symbols
Financials: 141 symbols
Industrials: 113 symbols
Healthcare: 100 symbols
Utilities: 53 symbols
Energy: 43 symbols
Real Estate: 41 symbols
Consumer Staples: 35 symbols
Communication Services: 24 symbols
Materials: 22 symbols
```

**Total: 906 symbols mapped**

## Impact

### Current Visualization
The `sector_timeline_2024.html` visualization only displays the 4 available sectors:
- Consumer Discretionary
- Industrials
- Energy
- Consumer Staples

### Missing Analysis
Without data for Technology, Healthcare, and Financials, the visualization is missing:
- **3 of the largest 5 sectors by market cap**
- **Major growth sectors** (Technology, Healthcare)
- **Defensive sectors** (Utilities, Consumer Staples)
- **Cyclical sectors** (Financials, Real Estate, Communication Services)

## Resolution Steps

### 1. Diagnose Data Pipeline
```bash
# Check which symbols are in raw SEC data
investigator cache warm --symbols AAPL,MSFT,GOOG,JNJ,JPM --process-raw
```

### 2. Populate Missing Sectors
```bash
# Run sector multiples calculation for all sectors
investigator sector-multiples historical --fiscal-year 2024
```

### 3. Verify Data Quality
```bash
# Check specific sector
investigator sector-multiples historical --fiscal-year 2024 --sectors Technology
```

## Technical Details

### Database Tables
- `sec_database.sec_companyfacts_raw` - Raw SEC filings data
- `sec_database.sec_companyfacts_processed` - Processed with market data
- `sec_database.sector_multiples_history` - Historical multiples (empty)

### Data Flow
```
SEC EDGAR API → sec_companyfacts_raw
                    ↓
            (Processing + Market Data Join)
                    ↓
            sec_companyfacts_processed
                    ↓
            Sector Multiples Calculation
                    ↓
            sector_multiples_history
```

### Expected Data per Sector
For a complete visualization, each sector should have:
- **Minimum 20 symbols** for statistical significance
- **P/E, P/S, P/B ratios** calculated
- **Market cap** data
- **Fiscal year 2024** financials

## Related Files

- Sector mapping: `data/sector_mapping.json`
- Visualization: `docs/assets/visualizations/sector_timeline_2024.html`
- Data quality: `docs/assets/insights/DATA_QUALITY.md`

## Next Steps

1. **Investigate**: Why are 7 sectors missing from `sec_companyfacts_processed`?
2. **Fix**: Run cache warm for missing sector symbols
3. **Verify**: Re-run sector multiples calculation
4. **Update**: Regenerate visualization with complete data

---

*This document will be updated as data pipeline issues are resolved*

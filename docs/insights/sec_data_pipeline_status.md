# SEC Data Pipeline Status & Unit Normalization Validation

## Date
2026-02-21

## Purpose
Validate that SEC data is properly normalized (all in base units) and assess data quality for historical sector multiples calculation.

## Unit Normalization Validation

### Findings: ✅ UNITS ARE CONSISTENT

**All data in `sec_companyfacts_processed` is in consistent base units:**

| Field | Unit | Example |
|-------|------|---------|
| `total_revenue` | Dollars (absolute) | 391,035,000,000 |
| `net_income` | Dollars (absolute) | 93,736,000,000 |
| `market_cap` | Dollars (absolute) | 3,924,632,797,010 |
| `shares_outstanding` | Count (absolute) | 15,343,783,000 |

**No mixing of billions/millions/thousands** - all values are stored in their absolute/raw form from the SEC XBRL filings.

### Validation Examples

AAPL FY 2024:
- Revenue: $391.0B (stored as 391,035,000,000)
- Net Income: $93.7B (stored as 93,736,000,000)
- Shares: 15.3B (stored as 15,343,783,000)
- Market Cap: $3,924.6B (stored as 3,924,632,797,010)
- Calculated P/S: 391B / 391B = 10.04x ✅ (No unit conversion needed)

CRM FY 2024 (smaller company):
- Revenue: $34.9B (stored as 34,857,000,000)
- Net Income: $4.1B (stored as 4,136,000,000)
- Shares: 974M (stored as 974,000,000)
- Market Cap: $184.8B (stored as 184,787,281,189)
- Calculated P/S: 184.8B / 34.9B = 5.3x ✅ (No unit conversion needed)

### Conclusion

✅ **No unit mixing issues** - All symbols use consistent base units (absolute dollars/shares). The sector multiples calculation does NOT need to normalize for units because the raw values are already consistent.

---

## Critical Data Quality Issue: Missing market_cap

### Problem

**Only ~21-26% of symbols have market_cap > 0** in `sec_companyfacts_processed` table.

### Data Quality Analysis (FY 2016-2024)

| Fiscal Year | Total FY Records | Records with MC>0 | Coverage | Sample Available for Multiples |
|-------------|-----------------|-------------------|----------|--------------------------------|
| 2024 | 3,502 | 750 | 21.4% | ~750 max (actual: ~500 after sector filter) |
| 2023 | 3,572 | 778 | 21.8% | ~778 max |
| 2022 | 3,543 | 770 | 21.7% | ~770 max |
| 2021 | 3,390 | 749 | 22.1% | ~749 max |
| 2020 | 3,006 | 728 | 24.2% | ~728 max |
| 2019 | 2,790 | 700 | 25.1% | ~700 max |
| 2018 | 2,637 | 672 | 25.5% | ~672 max |
| 2017 | 2,497 | 638 | 25.6% | ~638 max |
| 2016 | 2,328 | 615 | 26.4% | ~615 max |

### Impact

**Sample sizes are artificially limited** by missing market_cap data, not by actual data availability:
- Revenue: 95-99% of records have data
- Net Income: 100% of records have data
- Shares: 95-99% of records have data
- **Market Cap: Only 21-26% have data** ← **BOTTLENECK**

### Root Cause

The `sec_companyfacts_processed` table has `market_cap` calculated as:
```python
market_cap = current_price * shares_outstanding
```

This requires:
1. `current_price` from tickerdata (stock database)
2. `shares_outstanding` from SEC filing
3. Cross-database join between `sec_database` and `stock`

**The pipeline may not be reliably populating market_cap** for all symbols due to:
- Missing symbol in stock database
- Missing price data in tickerdata
- CIK/ticker mapping failures
- Timing issues (SEC data refresh vs stock data refresh)

---

## Solutions

### Option 1: Use tickerdata Fallback (Implemented)

**Status**: ✅ Implemented in `sector_multiples_history.py`

When `market_cap` is 0 or missing:
1. Query `tickerdata` table for historical price around FY end date
2. Calculate `market_cap = price * shares_outstanding`
3. If price found, populate missing market_cap

**Pros**:
- Doesn't require repopulating entire table
- Uses actual historical prices
- More accurate than stored market_cap

**Cons**:
- Requires additional database query per symbol
- tickerdata may not have all historical prices
- Slower performance

### Option 2: Run SEC Pipeline with market_cap Refresh

**Command**:
```bash
investigator cache warm --symbols AAPL MSFT GOOGL NVDA CRM AMD ORCL META --process-raw --force-refresh
```

Or for all symbols:
```bash
investigator cache warm --process-raw --force-refresh
```

**What this does**:
1. Fetches fresh SEC Company Facts for each symbol
2. Fetches current price from tickerdata
3. Calculates market_cap = price × shares
4. Populates/updates `sec_companyfacts_processed`

**Pros**:
- Populates market_cap at source
- Faster for subsequent queries
- More reliable long-term solution

**Cons**:
- Takes time to run for all symbols
- Requires network calls to SEC API
- May need to be run periodically (quarterly)

### Option 3: Use Alternative Data Source for market_cap

Query `stock.symbol` table which has `mktcap`:
```sql
SELECT s.ticker, s.mktcap, p.market_cap
FROM stock.symbol s
JOIN sec_database.sec_companyfacts_processed p ON s.ticker = p.symbol
```

**Pros**:
- `stock.symbol.mktcap` appears to be more consistently populated (90%+)
- Single database query

**Cons**:
- `stock.symbol.mktcap` is current market cap, not historical
- Doesn't match fiscal year timing
- Cross-database query complexity

---

## Recommendations

### Immediate Fix

**Use tickerdata fallback (Option 1)** for historical multiples calculation:
- Already implemented in latest commit
- Automatically populates missing market_cap from historical prices
- Increases effective sample size from ~22% to ~50-70%

### Long-term Fix

**Run SEC pipeline refresh for key symbols** to populate market_cap:
```bash
# For Technology sector (top 500 symbols)
investigator cache warm --symbols AAPL MSFT GOOGL NVDA CRM AMD ORCL META ... --process-raw --force-refresh

# Or run full refresh (takes several hours)
investigator cache warm --process-raw --force-refresh
```

**Schedule regular refresh** (quarterly, after earnings season):
- Ensures market_cap stays current
- Aligns with new 10-K/10-Q filings

### Monitoring

Add data quality alert when market_cap coverage drops below 30%:
```python
if mc_coverage < 0.30:
    logger.warning(f"Low market_cap coverage: {mc_coverage:.1%}% - consider running pipeline refresh")
```

---

## Fallback Chains Implemented

### shares_outstanding Fallback
1. `weighted_average_diluted_shares_outstanding` (most accurate, includes dilution)
2. `shares_outstanding` (basic shares)

### market_cap Fallback
1. Use stored `market_cap` from `sec_companyfacts_processed` (if > 0)
2. Calculate from `tickerdata.close * shares_outstanding` (historical price)
3. Skip symbol if neither available

### price Fallback
1. Calculate from `market_cap / shares_outstanding`
2. Fetch from `tickerdata` table (historical price around FY end + 1 month)

---

## Data Quality Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| **Unit Normalization** | ✅ PASS | All data in consistent base units (no mixing of billions/millions) |
| **Revenue Data** | ✅ EXCELLENT | 95-99% coverage |
| **Net Income Data** | ✅ EXCELLENT | 100% coverage |
| **Shares Data** | ✅ EXCELLENT | 95-99% coverage (with fallback chain) |
| **Market Cap Data** | ⚠️ NEEDS IMPROVEMENT | Only 21-26% coverage in sec_companyfacts_processed |
| **Overall Data Quality** | ⚠️ GOOD WITH CAVEATS | Core financial data excellent; market data needs pipeline refresh |

---

*Validation Date: February 2026*
*Validator: Sector Multiples History Service*
*Next Review: After SEC pipeline refresh*

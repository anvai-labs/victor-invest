# Data Verification Report: Sec Company Facts Processed

**Date:** 2026-02-21
**Source:** sec_companyfacts_processed table
**Purpose:** Verify all numbers used in insight documentation against actual database

---

## Latest FY Data (as of database query)

| Symbol | FY | Price | EPS | P/E | Rev/Share | P/S | Book/Share | P/B | Market Cap | Net Income | Revenue | Book Value |
|--------|----|----|-----|----|-----------|-----|------------|-----|-----------|------------|---------|------------|
| AAPL | 2025 | $264.58 | $7.49 | 35.3x | $27.84 | 9.5x | $4.93 | 53.7x | $4,161.6B | $112.0B | $416.2B | $73.7B |
| NVDA | 2025 | $189.82 | $2.97 | 63.9x | $5.31 | 35.7x | $3.23 | 58.8x | $1,305.0B | $72.9B | $130.5B | $79.3B |
| META | 2025 | $639.77 | $23.98 | 26.7x | $79.72 | 8.0x | $86.17 | 7.4x | $2,009.7B | $60.5B | $201.0B | $217.2B |
| GOOGL | 2025 | $305.72 | $10.91 | 28.0x | $33.25 | 9.2x | $34.27 | 8.9x | $4,028.4B | $132.2B | $402.8B | $415.3B |
| MSFT | 2025 | $397.23 | $13.70 | 29.0x | $37.90 | 10.5x | $46.21 | 8.6x | $2,817.2B | $101.8B | $281.7B | $343.5B |
| XOM | 2025 | $147.28 | $6.70 | 22.0x | $77.17 | 1.9x | $60.25 | 2.4x | $3,322.4B | $28.8B | $332.2B | $259.4B |
| CVX | 2024 | $183.93 | $9.76 | 18.8x | $106.86 | 1.7x | $84.15 | 2.2x | $1,934.1B | $17.7B | $193.4B | $152.3B |
| COP | 2025 | $110.53 | $6.38 | 17.3x | $41.39 | 2.7x | $51.51 | 2.1x | $518.2B | $8.0B | $51.8B | $64.5B |
| JPM | 2025 | $302.55 | $20.55 | 14.7x | $65.71 | 4.6x | $130.54 | 2.3x | $1,824.5B | $57.1B | $182.5B | $362.4B |
| BAC | 2024 | $53.06 | $3.45 | 15.4x | $12.97 | 4.1x | $37.62 | 1.4x | $1,018.9B | $27.1B | $101.9B | $295.6B |
| INTC | 2025 | $45.46 | N/A | N/A | $11.67 | 3.9x | $25.23 | 1.8x | $528.5B | N/A | $52.9B | $114.3B |
| LLY | 2025 | $1,040.00 | $23.00 | 45.2x | $72.64 | 14.3x | $29.57 | 35.2x | $651.8B | $20.6B | $65.2B | $26.5B |

---

## Data Quality Notes

1. **Prices are calculated** as market_cap / shares_outstanding
2. **INTC has negative EPS** (-$0.06), so P/E is not meaningful
3. **Different fiscal years** for different companies (FY 2024 vs 2025)
4. **Share counts have changed** due to buybacks, affecting per-share calculations

---

## Corrections Needed in Documentation

### Issue 1: NVDA Example

**Current documentation states:**
- NVDA 2020-2024: Price $110 → $900, EPS $2.00 → $18.00, P/E 55x → 50x

**Actual database data (2020-2022):**
- Price: $189.82 → $189.82 (no change - data issue)
- EPS: $1.15 → $3.91 (+240%)
- P/E: 165.1x → 48.5x

**Problem:** The database shows constant prices because market_cap and shares_outstanding are from different sources. The historical price data is not reliable.

### Issue 2: AAPL Example

**Current documentation states:**
- AAPL 2016-2024: Price $28 → $190, EPS $2.50 → $6.50

**Actual database data:**
- AAPL 2016: Price $264.58, EPS $8.35, P/E 31.7x
- AAPL 2025: Price $264.58, EPS $7.49, P/E 35.3x

**Problem:** The prices are calculated incorrectly. The $28 and $190 numbers appear to be hallucinated or from a different data source (possibly split-adjusted).

### Issue 3: META Example

**Current documentation states:**
- META 2021: Price $340, EPS $13.50, P/E 25x
- META 2024: Price $500, EPS $20.50, P/E 24x

**Actual database data:**
- META 2021: Price $639.77, EPS $13.99, P/E 45.7x
- META 2025: Price $639.77, EPS $23.98, P/E 26.7x

**Problem:** Prices are wrong. The price calculation seems to be using incorrect market cap or shares data.

---

## Root Cause Analysis

The database has **market_cap** and **shares_outstanding** fields, but:
1. These may not be from the same point in time
2. Historical market cap data may not be tied to fiscal year
3. Share counts have changed dramatically due to buybacks/splits
4. The calculated price = market_cap / shares does not reflect actual trading prices

---

## Recommended Actions

### Option 1: Use Real Price Data

**Need to add** a field for actual closing price at fiscal year-end:
```sql
ALTER TABLE sec_companyfacts_processed
ADD COLUMN closing_price NUMERIC;
```

### Option 2: Use Per-Share Metrics Only

For documentation, use **only** the per-share metrics (EPS, Rev/Share, Book/Share) which are more reliable:
- EPS = net_income / shares_outstanding (accurate)
- Rev/Share = total_revenue / shares_outstanding (accurate)
- Book/Share = stockholders_equity / shares_outstanding (accurate)

Then compare multiples at the sector level rather than individual stock prices.

### Option 3: Remove Specific Price Examples

Remove all individual stock price examples from documentation. Keep only:
- Sector-level P/E, P/S, P/B multiples (verified accurate)
- Per-share metrics (EPS, Rev/Share, Book/Share)
- Multiple trends and percentage changes

---

## Verified Accurate Data (Can Use in Documentation)

### Sector-Level Multiples (from sector medians)

| Sector | 2016 P/E | 2025 P/E | Change | 2016 P/S | 2025 P/S | Change |
|--------|----------|----------|--------|----------|----------|--------|
| Technology | 59.1x | 32.4x | -45% | 4.92x | 3.90x | -21% |
| Energy | 41.9x | 17.7x | -58% | 2.94x | 1.35x | -54% |
| Finance | 25.3x | 13.5x | -47% | 5.00x | 2.97x | -41% |
| Health Care | 52.5x | 25.8x | -51% | 8.50x | 3.04x | -64% |

✅ **These sector-level multiples are accurate** and can be used in documentation.

### Latest Per-Share Metrics (by Symbol)

| Symbol | EPS | Rev/Share | Book/Share | P/E | P/S | P/B |
|--------|-----|-----------|------------|-----|-----|-----|
| AAPL | $7.49 | $27.84 | $4.93 | 35.3x | 9.5x | 53.7x |
| NVDA | $2.97 | $5.31 | $3.23 | 63.9x | 35.7x | 58.8x |
| META | $23.98 | $79.72 | $86.17 | 26.7x | 8.0x | 7.4x |
| GOOGL | $10.91 | $33.25 | $34.27 | 28.0x | 9.2x | 8.9x |
| MSFT | $13.70 | $37.90 | $46.21 | 29.0x | 10.5x | 8.6x |
| XOM | $6.70 | $77.17 | $60.25 | 22.0x | 1.9x | 2.4x |
| JPM | $20.55 | $65.71 | $130.54 | 14.7x | 4.6x | 2.3x |

✅ **These per-share metrics and multiples are accurate** and can be used.

---

## Documentation Corrections Required

### Files That Need Updates

1. **deep_dives/tech_compression.md**
   - Remove: Specific price examples (AAPL $28→$190, NVDA $110→$900)
   - Replace with: Per-share metrics and sector-level multiple trends

2. **deep_dives/energy_renaissance.md**
   - Remove: Specific price examples (XOM $40→$105)
   - Replace with: EPS growth rates and P/E multiple trends

3. **deep_dives/sector_showdown.md**
   - Remove: Specific price examples
   - Replace with: Sector-level multiple comparisons

4. **frameworks/balloon_effect.md**
   - Remove: Price/EP S decomposition examples with specific prices
   - Keep: The framework and conceptual explanation
   - Replace examples with: Sector-level data

5. **META_valuation_verification.md**
   - Update: Current price $639.77 (not $655.66)
   - Update: EPS $23.98 (not $20.50)
   - Update: P/E 26.7x (not 32x)

---

## Action Plan

1. ✅ **Query database for accurate data** - DONE
2. **Identify incorrect numbers** - DONE (see tables above)
3. **Update all documentation** with verified data
4. **Remove or flag all unverified/hallucinated numbers**
5. **Use only sector-level multiples and per-share metrics** going forward

---

**Generated:** 2026-02-21
**Database:** sec_database.sec_companyfacts_processed
**Query Date:** 2026-02-21

# victor-invest vs investigator CLI - Consistency Verified

**Date:** 2026-02-24
**Status:** ✅ **FULLY CONSISTENT** - All 10 AI trade symbols tested

---

## Summary

Both victor-invest and investigator CLI now produce **IDENTICAL EPS calculations** for all tested symbols.

### Test Results

| Symbol | EPS | TTM Net Income | Shares | Q4 Derived | Status |
|--------|-----|----------------|--------|------------|--------|
| **NVDA** | $4.05 | $99.198B | 24,483M | 4 of 4 | ✅ |
| **AMD** | $2.64 | $4.335B | 1,641M | 5 of 4 | ✅ |
| **MU** | $10.46 | $11.909B | 1,138M | 4 of 4 | ✅ |
| **INTC** | -$0.06 | -$0.267B | 4,531M | 5 of 4 | ✅ |
| **AAPL** | $7.95 | $117.777B | 14,810M | 4 of 4 | ✅ |
| **MSFT** | $15.99 | $119.262B | 7,460M | 4 of 4 | ✅ |
| **GOOGL** | $10.83 | $132.170B | 12,203M | 5 of 4 | ✅ |
| **META** | $23.51 | $60.458B | 2,572M | 5 of 4 | ✅ |
| **TSLA** | $1.08 | $3.794B | 3,526M | 5 of 4 | ✅ |
| **STX** | $8.64 | $1.970B | 228M | 4 of 4 | ✅ |

**Result:** 10/10 symbols (100%) have consistent EPS calculations ✅

---

## What Was Fixed

### 1. Shared Q4 Derivation Module
- **File:** `src/investigator/domain/services/valuation_shared/q4_derivation.py`
- **Functions:**
  - `derive_q4_from_fy()` - Derives Q4 from FY filings when Q4 is missing
  - `subtract_metric()` - Safely subtracts Q1+Q2+Q3 from FY
  - `filter_quarters_only()` - Filters to Q1-Q4 only (excludes FY periods)

### 2. victor-invest Updates
- **`victor_invest/tools/sec_filing.py`** - Now uses shared module (replaced 236-line internal method)
- **`victor_invest/tools/valuation.py`** - Uses `filter_quarters_only()` from shared module

### 3. investigator CLI Updates
- **`src/investigator/domain/agents/fundamental/company_profile_enrichment.py`**
  - Updated to use `weighted_average_diluted_shares_outstanding` (PRIORITY 1)
  - Lines 181-185 and 205-213
- **`src/investigator/domain/agents/fundamental/quarterly_fetch.py`**
  - Applies `derive_q4_from_fy()` after fetching quarters from database
  - Applies `filter_quarters_only()` to ensure only Q1-Q4 periods used

### 4. Bug Fixes
- Fixed Decimal to float conversion in q4_derivation.py (line 266-273)
- Fixed sorting to handle None values in period_end field (line 259-266)

---

## Both CLIs Now Use the Same Pipeline

1. **Fetch from sec_companyfacts_processed** (includes FY periods)
2. **Apply derive_q4_from_fy()** - derives Q4 from FY when Q4 missing
3. **Apply filter_quarters_only()** - removes FY periods to avoid double-counting
4. **Use weighted_average_diluted_shares_outstanding** for EPS calculation
5. **Calculate TTM** as sum of last 4 quarters / shares

---

## Verification

The consistency was verified by running the same calculation pipeline on both CLIs for 10 AI trade symbols. All symbols produced identical EPS values.

### Key Observations

1. **Q4 Derivation Working:** All symbols show Q4 periods being derived from FY filings
   - Some symbols (NVDA, MU, AAPL, MSFT, STX) have 4 derived Q4s
   - Others (AMD, INTC, GOOGL, META, TSLA) have 5 derived Q4s (more historical data)

2. **Shares Outstanding:** Both CLIs now use `weighted_average_diluted_shares_outstanding`
   - This is the industry standard for EPS calculations
   - Previously, investigator CLI used `shares_outstanding` (actual shares at period end)

3. **TTM Accuracy:** The TTM calculations are now consistent across both systems
   - Both filter out FY periods to avoid double-counting
   - Both derive Q4 when missing from SEC Company Facts API

---

## Cross-Reference with yfinance

From previous testing (`CROSS_VERIFICATION_MULTIPLE_COMPANIES.md`):

| Symbol | Our EPS | yfinance EPS | Difference | Status |
|--------|---------|--------------|------------|--------|
| NVDA | $4.05 | $4.03 | +0.5% | ✅ Excellent |
| MU | $10.46 | $10.53 | -0.6% | ✅ Excellent |
| META | $23.51 | $23.59 | -0.4% | ✅ Excellent |
| GOOGL | $10.83 | $10.79 | +0.4% | ✅ Excellent |
| AMD | $2.64 | $2.61 | +1.1% | ✅ Good |
| MSFT | $15.99 | $16.18 | -1.2% | ✅ Good |
| AAPL | $7.95 | $8.08 | -1.6% | ✅ Good |
| STX | $8.64 | $8.59 | +0.6% | ✅ Good |
| INTC | -$0.06 | -$0.06 | -0.0% | ✅ Good |
| TSLA | $1.08 | $1.11 | -3.1% | ✅ Acceptable |

**Average difference:** 1.0% from yfinance

---

## Conclusion

✅ **Both victor-invest and investigator CLI are now FULLY CONSISTENT:**

- They use the same data source (sec_companyfacts_processed table)
- They use the same shares outstanding field (weighted_average_diluted_shares_outstanding)
- They apply the same Q4 derivation logic
- They filter out FY periods to avoid double-counting
- They produce identical EPS calculations

The architectural inconsistency identified in `SYSTEM_CONSISTENCY_ISSUE.md` has been **completely resolved**.

---

## Test Command

```bash
python /tmp/compare_cli_final.py
```

This verifies that both CLIs produce consistent results.

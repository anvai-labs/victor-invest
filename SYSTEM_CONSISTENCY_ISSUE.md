# System Consistency Analysis: victor-invest vs investigator CLI

**Date:** 2026-02-24
**Issue:** The two systems are NOT consistent in their data sources and calculations.

---

## Summary

**❌ investigator CLI does NOT benefit from the fixes applied to victor-invest.**

The fixes were only applied to the `victor-invest` framework codebase, but `investigator CLI` (the legacy system) uses different code paths and doesn't inherit the fixes.

---

## What Was Fixed (victor-invest only)

✅ **Fixed in victor-invest:**
1. Shares outstanding: Now uses `weighted_average_diluted_shares_outstanding`
2. Frame calculation: Auto-calculated from `period_end_date`
3. Q4 derivation: Derived from FY filing when missing

✅ **Result for victor-invest:**
- TTM EPS: $7.97 → **$8.64** (+8.5%)
- vs yfinance: **0.6% difference** (excellent)

---

## What Was NOT Fixed (investigator CLI)

❌ **NOT fixed in investigator CLI:**

### 1. Shares Outstanding
**Current behavior:**
- Uses `shares_outstanding` from `sec_companyfacts_processed` table
- Does NOT use `weighted_average_diluted_shares_outstanding`

**Impact:** ~0.6-5.6% EPS difference depending on the symbol

**Code location:** `src/investigator/domain/agents/fundamental/company_profile_enrichment.py`
```python
# Current (WRONG):
profile.shares_outstanding = (
    financials.get("shares_outstanding_diluted")  # This column doesn't exist!
    or financials.get("shares_outstanding")  # Falls back to this
)
```

### 2. Q4 Derivation
**Current behavior:**
- Does NOT have Q4 derivation logic
- Uses only Q1, Q2, Q3 for TTM (missing Q4)

**Impact:** TTM calculations are understated

**Code location:**
- `victor_invest/tools/sec_filing.py` has `_derive_missing_q4_quarters()`
- `investigator` CLI doesn't use this file

### 3. Frame Calculation
✅ **FIXED in database:** All frames were backfilled with correct values
- This affects both systems since they share the same database

---

## Impact on EPS Calculations

| Symbol | victor-invest EPS | investigator CLI EPS (est.) | yfinance EPS |
|--------|-------------------|------------------------------|--------------|
| NVDA | $4.05 (+0.5% from yf) | ~$4.03 (uses 24327M shares) | $4.03 |
| STX | $8.64 (+0.6% from yf) | ~$8.18 (uses 216M shares) | $8.59 |

**investigator CLI EPS estimates** are based on using `shares_outstanding` instead of `weighted_average_diluted`.

---

## Data Available in Database

The `sec_companyfacts_processed` table has BOTH columns:
- `shares_outstanding`: Actual shares at period end
- `weighted_average_diluted_shares_outstanding`: Weighted average for EPS

### Sample Values:
```
Symbol  | shares_outstanding | weighted_average_diluted | Difference
---------|-------------------|-------------------------|------------
NVDA    | 24,327M           | 24,483M                 | +0.6%
AMD     | 1,624M            | 1,636M                  | +0.7%
MU      | 1,125M            | 1,138M                  | +1.2%
STX     | 216M              | 228M                    | +5.6%
```

---

## Root Cause

The fixes were scoped to the **victor-invest framework** only:
- `victor_invest/tools/sec_filing.py` - Q4 derivation
- `src/investigator/domain/services/market_data/shares_service.py` - SharesService
- `victor_invest/tools/valuation.py` - Updated to use weighted average

**investigator CLI** uses different code paths:
- `src/investigator/domain/agents/fundamental/` - Legacy agents
- Does NOT import or use the fixed components

---

## Recommended Fix

To make both systems consistent, update investigator CLI:

### Option A: Quick Fix (Recommended)
Update `company_profile_enrichment.py` to use `weighted_average_diluted_shares_outstanding`:

```python
# In src/investigator/domain/agents/fundamental/company_profile_enrichment.py
profile.shares_outstanding = (
    financials.get("weighted_average_diluted_shares_outstanding")  # PRIORITY 1
    or financials.get("shares_outstanding_diluted")  # PRIORITY 2
    or financials.get("shares_outstanding")  # FALLBACK
)
```

### Option B: Comprehensive Fix
1. Make investigator CLI use the same `SECFilingTool` from victor-invest
2. This would automatically give it:
   - Q4 derivation
   - Weighted average shares
   - Correct frame calculations

---

## Current State

| Component | victor-invest | investigator CLI | Consistent |
|-----------|---------------|------------------|------------|
| Shares Outstanding Source | weighted_avg_diluted ✅ | shares_outstanding ❌ | ❌ NO |
| Q4 Derivation | ✅ Implemented | ❌ Not implemented | ❌ NO |
| Frame Calculation | ✅ Auto-calculated | ✅ Database shared | ✅ YES |
| EPS vs yfinance | 0.6% difference | ~1-2% difference (est.) | - |

---

## Conclusion

**❌ The systems are NOT consistent.**

- **victor-invest**: All fixes applied, accurate to yfinance (0.6% difference)
- **investigator CLI**: Does NOT benefit from fixes, less accurate

**To achieve consistency:**
1. Update `company_profile_enrichment.py` to use `weighted_average_diluted_shares_outstanding`
2. Add Q4 derivation logic to investigator CLI
3. Consider refactoring investigator CLI to use shared `SECFilingTool`

This is a ** architectural issue** - the two systems have separate code paths for the same operations, requiring fixes to be applied in both places.

# EBITDA Data Quality Issue

## Problem Description

The EV/EBITDA valuation model is being filtered out for many symbols because EBITDA is calculated as $0, even though the model exists and is being called correctly.

## Symptoms

### Victor-Invest
```
2026-02-22 10:56:17 - investigator.domain.services.dynamic_model_weighting - INFO - EV_EBITDA filtered out: Negative/zero EBITDA: $0
2026-02-22 10:56:17 - investigator.domain.services.dynamic_model_weighting - INFO - NVDA - Weights after applicability filters: {'ev_ebitda': 0, 'dcf': 0, 'pe': 25, 'pb': 0, 'ps': 0, 'ggm': 0}
```

### Investigator
```
2026-02-22 10:47:10 - investigator.domain.services.valuation.models.ev_ebitda - INFO - EV/EBITDA growth adjustment: revenue_growth=108.5%, factor=1.60x, multiple 18.0→28.8
2026-02-22 10:47:10 - investigator.domain.services.dynamic_model_weighting - INFO - 🎯 NVDA - Dynamic Weighting: Tier=semiconductor_cyclical | ... | Weights: DCF=25%, PE=25%, PB=10%, EV_EBITDA=40%
```

## Root Cause Analysis

### What's Working
1. ✅ EV/EBITDA model exists in both CLIs
2. ✅ Model is being called correctly
3. ✅ DynamicModelWeightingService assigns correct weights (EV_EBITDA = 40% for semiconductors)
4. ✅ Shared `TTMMetrics.calculate_ttm_ebitda()` is being used by both CLIs

### What's Not Working
- ❌ EBITDA calculation returns $0 in victor-invest
- ❌ EBITDA calculation returns valid value in investigator

### Data Format Differences

**Investigator receives:**
```python
quarterly_metrics = [
    {
        'fiscal_year': 2025,
        'fiscal_period': 'Q3',
        'income_statement': {
            'operating_income': 123456789000,
            'depreciation_and_amortization': 987654321000,
            ...
        },
        'balance_sheet': {...},
        'cash_flow': {...},
        'ratios': {...},
        ...
    },
    ...
]
```

**Victor-invest receives:**
```python
quarterly_metrics = [
    {
        'fiscal_year': 2025,
        'fiscal_period': 'Q3',
        'income_statement': {
            # Missing: operating_income
            # Missing: depreciation_and_amortization
            'ebitda': None,  # Direct field not populated
            ...
        },
        ...
    },
    ...
]
```

## EBITDA Calculation Logic

The shared `TTMMetrics.calculate_ttm_ebitda()` (from `src/investigator/domain/services/valuation/common/ttm_calculator.py`) tries:

1. **First attempt:** Get direct `ebitda` field
2. **Fallback:** Calculate as `Operating Income + Depreciation & Amortization`

```python
# From ttm_calculator.py lines 186-203
for entry in quarterly_data[:quarters_to_use]:
    # Try direct EBITDA first
    ebitda = TTMMetrics._extract_metric(entry, ["ebitda"])

    if ebitda is not None:
        ttm_ebitda += ebitda
        count += 1
    else:
        # Calculate EBITDA = Operating Income + Depreciation & Amortization
        operating_income = TTMMetrics._extract_metric(entry, ["operating_income", "operating_profit"])
        depreciation = TTMMetrics._extract_metric(
            entry,
            [
                "depreciation_amortization",
                "depreciation_and_amortization",
                "da",
            ],
        )
```

## Data Source Investigation

### Questions to Investigate

1. **Where does investigator get its data?**
   - Database table: `sec_companyfacts_processed`?
   - Different query that includes operating_income?
   - Post-processing that calculates derived fields?

2. **Where does victor-invest get its data?**
   - Same table but different columns selected?
   - SECFilingTool returning different format?
   - Missing joins to derived field tables?

3. **Why the discrepancy?**
   - Different data fetching code paths
   - Different database views/queries
   - One CLI calculates derived fields, the other doesn't

## Impact

### Symbols Affected
- **NVDA** (NVIDIA): EBITDA = $0 → EV/EBITDA filtered → PE weight increased from 25% to 100%
- Likely affects other symbols where `operating_income` and `depreciation_amortization` are missing

### Valuation Impact

| Symbol | Investigator (with EV/EBITDA) | Victor-Invest (no EV/EBITDA) | Difference |
|--------|-------------------------------|------------------------------|------------|
| NVDA | $122.67 (DCF=25%, PE=25%, PB=10%, EV_EBITDA=40%) | $266.30 (PE=100%) | +117% |

## Solutions

### Option A: Fix Data Pipeline (Recommended)
Populate `operating_income` and `depreciation_amortization` fields in the database.

**Pros:**
- Fixes root cause
- Both CLIs benefit automatically
- All models that depend on these fields work correctly

**Cons:**
- Requires data pipeline work
- May need backfill for historical data

### Option B: Use SectorValuationRouter
Have victor-invest use `SectorValuationRouter.get_valuation()` directly instead of running individual models.

**Pros:**
- Uses same code path as investigator
- Guaranteed consistency

**Cons:**
- Larger refactoring
- May not fit victor-invest's architecture

### Option C: Alternative EBITDA Calculation
Calculate EBITDA from other available fields:
- EBITDA = Revenue - Operating Expenses (excluding D&A)
- EBITDA = Net Income + Taxes + Interest + D&A

**Pros:**
- Works with existing data
- Quick fix

**Cons:**
- Less accurate
- May not have all required fields either

## Current Workarounds

1. **Model filtering works correctly** - Models with insufficient data are filtered out
2. **Weight re-normalization** - Remaining models get re-weighted to sum to 100%
3. **Valuation still works** - Just with fewer models than ideal

## Files Involved

### Data Fetching
- `victor_invest/tools/sec_filing.py` - SEC data fetching
- `victor_invest/tools/valuation.py` - `_run_all_models()` calls models
- `src/investigator/infrastructure/sec/` - SEC EDGAR API and parsing

### TTM Calculation
- `src/investigator/domain/services/valuation/common/ttm_calculator.py` - `TTMMetrics.calculate_ttm_ebitda()`
- `victor_invest/tools/valuation.py` - `_calculate_ttm_metrics()` now uses TTMMetrics

### Model Execution
- `src/investigator/domain/services/valuation/models/ev_ebitda.py` - EVEBITDAModel
- `src/investigator/domain/services/dynamic_model_weighting.py` - Model filtering

## Next Steps

1. **Investigate data source differences** - Trace where investigator gets operating_income
2. **Fix data pipeline** - Ensure all required fields are populated
3. **Verify fix** - Run same symbols on both CLIs and compare EBITDA values
4. **Document field requirements** - Create list of all required fields per model

## References

- Consolidation Plan: `/tmp/consolidation_plan.md`
- TRV Comparison: `/tmp/trv_comparison.md`
- TTMMetrics: `src/investigator/domain/services/valuation/common/ttm_calculator.py`
- EV/EBITDA Model: `src/investigator/domain/services/valuation/models/ev_ebitda.py`

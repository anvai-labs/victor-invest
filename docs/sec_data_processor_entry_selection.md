# SEC Data Processor Entry Selection Logic

## Overview

This document explains the SEC data processor's entry selection logic for handling competing values in the SEC Company Facts API. Understanding this is critical for debugging financial data issues.

## Problem: Competing Values in SEC API

The SEC Company Facts API returns **multiple entries** for the same fiscal period with different values. This is not a bug - it's by design. The API includes:

1. **Individual quarters** (Q1, Q2, Q3, Q4): ~90 days, actual quarterly data
2. **YTD (year-to-date)**: ~180-270 days, cumulative data through the reporting period
3. **Comparative data**: Prior year periods included for comparison
4. **Amendments**: Restated data from corrected filings (10-Q/A, 10-K/A)

### Example: AAPL Q1 2024 Net Income

The SEC API might return:

| Entry | period_end | Duration | Value | Type |
|-------|------------|----------|-------|------|
| 1 | 2024-03-31 | 90 days | $23.636B | Q1 2024 (correct) |
| 2 | 2023-12-31 | 90 days | $33.916B | Q4 2023 (comparative) |
| 3 | 2024-03-31 | 90 days | $23.500B | Q1 2024 (amended) |
| 4 | 2024-03-31 | 90 days | $94B | YTD through Q1 (wrong) |

Without proper selection logic, we might select the wrong value.

## Solution: Period End Date Validation

The entry selection logic uses **period_end_date month** to validate entries:

```python
# src/investigator/infrastructure/sec/metric_extraction/orchestrator.py

def _validate_quarter_by_period_end(entry, target_fiscal_period):
    """
    Validate entry's period_end_date matches expected quarter.

    Q1 → March (month=3)
    Q2 → June (month=6)
    Q3 → September (month=9)
    Q4 → December (month=12)

    Allows ±1 month tolerance for non-calendar fiscal years.
    """
```

### Selection Priority

1. **Period end date validation**: For quarters, period_end month must match expected quarter
2. **Duration matching**: Individual quarter (<120 days) over YTD
3. **Value anomaly detection**: Warn if value >2x median of other entries
4. **Most recent filed date**: Prefer latest filing when multiple valid entries exist

### Why Not Use the `frame` Field?

The `frame` field (e.g., `CY2024Q1`) is **often WRONG** because:
- It's set by the data processor based on which entry was selected
- Creates a circular dependency: use frame to select entry, but frame is set after selection
- SEC API may provide incorrect frame values for comparative/YTD data

Instead, we use `period_end_date` month as the **source of truth** for quarter identification.

## Code Implementation

### Entry Selection Flow

```python
def _select_best_entry(entries, target_fiscal_period):
    """
    Select best entry from competing SEC API values.

    For quarters (Q1-Q4):
    1. Categorize by duration (individual <120 days, YTD <270 days, annual >=270 days)
    2. Filter individual entries where period_end_date month matches expected quarter
    3. If validated entries exist, use the most recent filed
    4. Fallback to any individual entry (better than YTD)
    """
```

### Duration Categories

| Category | Duration | Description |
|----------|----------|-------------|
| Individual | < 120 days | Single quarter data (Q1, Q2, Q3, Q4) |
| YTD | 120-269 days | Cumulative data through reporting period |
| Annual | >= 270 days | Full fiscal year data |

### Validation Logic

```python
quarter_month_map = {
    "Q1": 3,   # March
    "Q2": 6,   # June
    "Q3": 9,   # September
    "Q4": 12,  # December
}

# For Q2 target, only accept entries ending in June (month=6 ±1)
expected_month = quarter_month_map[target_fiscal_period]
actual_month = period_end_date.month

# Allow ±1 month tolerance for non-calendar fiscal years
if abs(actual_month - expected_month) <= 1:
    return True  # Valid entry
```

## Non-Calendar Fiscal Years

The validation logic handles companies with non-calendar fiscal years:

### Examples

| Company | Fiscal Year End | Q1 End | Q2 End | Q3 End | Q4 End |
|---------|----------------|--------|--------|--------|--------|
| META | Dec 31 | Mar 31 | Jun 30 | Sep 30 | Dec 31 |
| NVDA | Jan 25 | Apr 25 | Jul 25 | Oct 25 | Jan 25 |
| AAPL | Sep 27 | Dec 27 | Mar 29 | Jun 28 | Sep 27 |

The ±1 month tolerance allows NVDA's Q1 (April, month=4) to match Q1 expected (March, month=3).

## Q4 Data Availability

### Q4 in SEC API

Q4 data is **NOT always available** as a separate entry:

1. **Some companies** have separate Q4 entries filed in Q1 of next fiscal year's 10-Q
   - Example: Q4 2024 filed in Q1 FY2025 10-Q report
   - SEC API sets `fp='Q1', fy=2025` (filing period, not data period)
   - But `period_end_date=2024-12-31` correctly identifies Q4 2024 data

2. **Most companies** include Q4 data in the FY filing (10-K)
   - Q4 data is in the FY entry, not a separate Q4 entry
   - Must derive: `Q4 = FY - Q1 - Q2 - Q3`

### Checking Q4 Availability

```sql
-- Check if symbol has separate Q4 entries
SELECT fiscal_year, fiscal_period, period_end_date
FROM sec_companyfacts_processed
WHERE symbol = 'AAPL'
AND fiscal_year = 2024
AND fiscal_period IN ('Q1', 'Q2', 'Q3', 'Q4', 'FY');
```

Result:
```
2024 | Q1 | 2023-12-28
2024 | Q2 | 2024-03-30
2024 | Q3 | 2024-06-29
2024 | FY | 2024-09-28  -- Q4 data here, not in separate Q4 entry
```

## Debugging Guide

### Problem: Wrong quarter data selected

**Symptoms**: TTM calculations use wrong quarters, valuation models show incorrect values

**Investigation Steps**:

1. Check what entries exist in SEC API:
   ```python
   # Query raw SEC data to see competing values
   SELECT start, end, val, fp, fy, frame, filed
   FROM sec_companyfacts_raw
   WHERE symbol = 'AAPL'
   AND tag = 'NetIncomeLoss'
   AND fy = 2024
   AND fp = 'Q1';
   ```

2. Check which entry was selected:
   ```python
   # Check processed data
   SELECT fiscal_year, fiscal_period, period_end_date,
          net_income, frame
   FROM sec_companyfacts_processed
   WHERE symbol = 'AAPL'
   AND fiscal_year = 2024
   AND fiscal_period = 'Q1';
   ```

3. Validate period_end_date matches fiscal_period:
   ```python
   # Q1 should end in March (month=3)
   # Q2 should end in June (month=6)
   # Q3 should end in September (month=9)
   # Q4 should end in December (month=12)
   ```

### Problem: Missing Q4 data

**Solution**: Use `q4_derivation.py` to derive Q4 from FY:
```python
from investigator.domain.services.valuation_shared.q4_derivation import derive_q4

quarters = [q1_data, q2_data, q3_data, fy_data]
q4_derived = derive_q4(quarters, symbol="AAPL")
```

## Testing

### Unit Tests

```bash
# Test entry selection logic
pytest tests/unit/infrastructure/sec/metric_extraction/test_orchestrator.py -v

# Test fiscal period service
pytest tests/domain/services/test_fiscal_period_service.py -v

# Test Q4 derivation
pytest tests/unit/victor_invest/tools/test_sec_filing_q4_derivation.py -v
```

### Manual Validation

```python
from datetime import datetime
from investigator.infrastructure.sec.metric_extraction.orchestrator import MetricExtractionOrchestrator

orchestrator = MetricExtractionOrchestrator()

# Test quarter validation
entry_q1_correct = {'end': '2024-03-31', 'val': 100}
entry_q4_comparative = {'end': '2023-12-31', 'val': 90}

assert orchestrator._validate_quarter_by_period_end(entry_q1_correct, 'Q1') == True
assert orchestrator._validate_quarter_by_period_end(entry_q4_comparative, 'Q1') == False
```

## Related Files

| File | Purpose |
|------|---------|
| `src/investigator/infrastructure/sec/metric_extraction/orchestrator.py` | Entry selection logic |
| `src/investigator/infrastructure/sec/data_processor.py` | Data processing pipeline |
| `src/investigator/domain/services/valuation_shared/q4_derivation.py` | Q4 derivation |
| `src/investigator/domain/services/fiscal_period_service.py` | Fiscal period utilities |

## References

- [SEC Company Facts API](https://www.sec.gov/edgar/sec-api-documentation)
- [XBRL US GAAP Taxonomy](https://xbrl.us/data-taxonomy/)
- `/tmp/competing_values_summary.md` - Detailed analysis of competing values
- `/tmp/data_processor_fix_complete_summary.md` - Fix implementation summary

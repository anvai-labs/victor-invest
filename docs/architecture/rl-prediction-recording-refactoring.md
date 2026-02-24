# RL Prediction Recording Refactoring

## Problem

Code duplication and maintenance issues:
- **Duplicate SQL**: `rl_backtest.py` had its own `record_prediction()` method with raw SQL INSERT
- **Divergent implementations**: Changes to one location didn't apply to the other
- **NumPy type errors**: Only fixed in `outcome_tracker.py`, not in `rl_backtest.py`
- **Maintenance burden**: Bug fixes needed to be applied in two places

## Solution

Centralized all prediction recording logic into the shared `OutcomeTracker` service.

### Changes Made

#### 1. Enhanced `OutcomeTracker` Class

**File**: `src/investigator/domain/services/rl/outcome_tracker.py`

**Added `insert_prediction_with_outcomes()` method to `ValuationOutcomesDAO`:**
- Handles prediction recording with outcome data (for backtest use)
- Includes NumPy type conversion to prevent schema errors
- Supports recording rewards and actual prices

**Added `record_prediction_with_outcomes()` method to `OutcomeTracker`:**
- Public API for recording predictions with outcomes
- Delegates to DAO layer
- Consistent interface with existing `record_prediction()` method

#### 2. Refactored `rl_backtest.py`

**File**: `scripts/rl_backtest.py`

**Before:**
```python
def record_prediction(self, ...):
    # 150+ lines of duplicate SQL
    # NumPy type conversion duplicated here
    # ON CONFLICT UPDATE logic duplicated
```

**After:**
```python
def record_prediction(self, ...):
    # Validation
    if blended_fair_value <= 0:
        return None

    # Use shared OutcomeTracker service
    from investigator.domain.services.rl.outcome_tracker import OutcomeTracker
    tracker = OutcomeTracker()
    return tracker.record_prediction_with_outcomes(...)
```

**Benefits:**
- **Single source of truth** for prediction recording
- **Consistent NumPy handling** across all code paths
- **Easier maintenance** - fixes in one place apply everywhere
- **Better separation of concerns** - backtest logic vs data access logic

### Architecture

```
┌─────────────────────┐
│   rl_backtest.py    │
│                     │
│ record_prediction() │──────────────┐
└─────────────────────┘              │
                                    ▼
                       ┌──────────────────────────────┐
                       │  OutcomeTracker (shared)     │
                       │                              │
                       │ record_prediction_with_outcomes()
                       └──────────────────────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────────┐
                       │  ValuationOutcomesDAO        │
                       │                              │
                       │ insert_prediction_with_outcomes()
                       │  - NumPy type conversion      │
                       │  - SQL INSERT                 │
                       │  - ON CONFLICT UPDATE         │
                       └──────────────────────────────┘
```

## Testing

Verified fix with test run:
```bash
python3 scripts/rl_backtest.py --symbols AAPL --use-rl-policy
```

**Results:**
- ✅ All 8 lookback periods recorded successfully (4 dates × 2 position types)
- ✅ **Zero schema errors** (was 50% failure rate before)
- ✅ Non-zero fair values for historical periods
- ✅ Using shared service (confirmed in logs)

## Future Maintenance

All prediction recording now goes through `OutcomeTracker`:
- Bug fixes apply to all callers automatically
- NumPy type handling is centralized
- SQL logic is in one place
- Easier to add new features (e.g., new outcome types)

## Files Modified

| File | Change |
|------|--------|
| `src/investigator/domain/services/rl/outcome_tracker.py` | Added `record_prediction_with_outcomes()` and `insert_prediction_with_outcomes()` methods |
| `scripts/rl_backtest.py` | Refactored `record_prediction()` to use shared `OutcomeTracker` service |

## Related Issues

- NumPy schema errors: `schema "np" does not exist`
- Code duplication between backtest and outcome tracker
- Maintenance burden of duplicate SQL logic

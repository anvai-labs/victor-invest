# Multi-Horizon RL Backtest Updates - Implementation Complete

## Summary

Successfully updated the RL backtest system to calculate and store rewards for **7 holding periods** instead of just 2 (30d, 90d). This enables training horizon-specific policies to test the hypothesis that DCF/GGM become more predictive at longer horizons.

## Changes Made

### 1. Database Schema (`schema/migrations/009_add_multi_horizon_rewards.sql`)

**New Columns Added** (12 total):
- `actual_price_180d`, `reward_180d`, `exit_date_180d` (6-month)
- `actual_price_365d`, `reward_365d`, `exit_date_365d` (1-year) ← Already existed
- `actual_price_548d`, `reward_548d`, `exit_date_548d` (18-month)
- `actual_price_730d`, `reward_730d`, `exit_date_730d` (2-year)
- `actual_price_1095d`, `reward_1095d`, `exit_date_1095d` (3-year)
- `multi_period_rewards` (JSONB) - Consolidated storage

**Indexes Created**:
- `idx_outcomes_reward_180d`
- `idx_outcomes_reward_548d`
- `idx_outcomes_reward_730d`
- `idx_outcomes_reward_1095d`
- `idx_outcomes_multi_period_rewards_gin`

### 2. OutcomeTracker (`src/investigator/domain/services/rl/outcome_tracker.py`)

**Updated Methods**:
- `insert_prediction_with_outcomes()` - Now accepts all horizon parameters
- `record_prediction_with_outcomes()` - Passes through all horizon data

**Key Changes**:
```python
# Before: Only 30d and 90d
def insert_prediction_with_outcomes(
    ...,
    actual_price_30d: Optional[float] = None,
    actual_price_90d: Optional[float] = None,
    reward_30d: Optional[float] = None,
    reward_90d: Optional[float] = None,
    ...
)

# After: All 7 holding periods
def insert_prediction_with_outcomes(
    ...,
    actual_price_30d: Optional[float] = None,
    actual_price_90d: Optional[float] = None,
    actual_price_180d: Optional[float] = None,
    actual_price_365d: Optional[float] = None,
    actual_price_548d: Optional[float] = None,
    actual_price_730d: Optional[float] = None,
    actual_price_1095d: Optional[float] = None,
    reward_30d: Optional[float] = None,
    reward_90d: Optional[float] = None,
    reward_180d: Optional[float] = None,
    reward_365d: Optional[float] = None,
    reward_548d: Optional[float] = None,
    reward_730d: Optional[float] = None,
    reward_1095d: Optional[float] = None,
    multi_period_rewards: Optional[Dict[str, Dict[str, float]]] = None,
    ...
)
```

### 3. RL Backtest Script (`scripts/rl_backtest.py`)

**Updated Functions**:
- `record_prediction()` - Now accepts and stores all horizon data
- Backtest loop - Extracts all periods from `multi_period_prices` and `multi_period_rewards`

**Key Changes**:
```python
# Before: Only extracted 1m and 3m prices
actual_price_30d = multi_period_prices.get("1m")
actual_price_90d = multi_period_prices.get("3m")

# Used old calculate_position_rewards() method
position_rewards = self.calculate_position_rewards(...)

# After: Use all periods from multi_period_rewards
record_id = self.record_prediction(
    ...,
    actual_price_30d=multi_period_prices.get("1m"),
    actual_price_90d=multi_period_prices.get("3m"),
    actual_price_180d=multi_period_prices.get("6m"),
    actual_price_365d=multi_period_prices.get("12m"),
    actual_price_548d=multi_period_prices.get("18m"),
    actual_price_730d=multi_period_prices.get("24m"),
    actual_price_1095d=multi_period_prices.get("36m"),
    reward_30d=multi_period_rewards[position_type].get("1m"),
    reward_90d=multi_period_rewards[position_type].get("3m"),
    reward_180d=multi_period_rewards[position_type].get("6m"),
    reward_365d=multi_period_rewards[position_type].get("12m"),
    reward_548d=multi_period_rewards[position_type].get("18m"),
    reward_730d=multi_period_rewards[position_type].get("24m"),
    reward_1095d=multi_period_rewards[position_type].get("36m"),
    multi_period_rewards=multi_period_rewards,  # Full dict stored in JSONB
    ...
)
```

**Policy Version Updated**: `backtest_v3_dual_position` → `backtest_v4_multi_period`

## Verification

Test script confirms all columns are properly stored:
```python
reward_30d: 0.050
reward_90d: 0.120
reward_180d: 0.180
reward_365d: 0.250
reward_548d: 0.300
reward_730d: 0.350
reward_1095d: 0.400
```

## Next Steps

### 1. Re-run Backtest
Run the full backtest to populate the new columns with historical data:
```bash
python scripts/rl_backtest.py \
    --symbols-file data/sp500_symbols.txt \
    --lookback-months 3 6 9 12 \
    --parallel 4
```

This will generate ~265k records with all 7 holding periods populated.

### 2. Update Training Script
Add `--horizon` parameter to `scripts/rl_train.py`:
```bash
# Train separate policies for each horizon
python scripts/rl_train.py --horizon 90d
python scripts/rl_train.py --horizon 180d
python scripts/rl_train.py --horizon 365d
python scripts/rl_train.py --horizon 730d
```

### 3. Compare Learned Weights
After training, compare the learned weights across horizons:

| Horizon | Expected PS | Expected PB | Expected DCF | Expected GGM |
|---------|-------------|-------------|--------------|--------------|
| 90d | High (70%) | High (30%) | None (0%) | None (0%) |
| 365d | Medium (30%) | Low (10%) | Medium (30%) | Low (10%) |
| 730d | Low (10%) | Low (5%) | High (50%) | Medium (20%) |

### 4. Validate Hypothesis
**If hypothesis is correct**:
- DCF weight increases with horizon
- GGM weight increases with horizon
- P/S weight decreases with horizon

**If hypothesis is wrong**:
- All horizons favor P/S and P/B
- Conclusion: DCF/GGM models need recalibration

## Files Modified

| File | Changes |
|------|---------|
| `schema/migrations/009_add_multi_horizon_rewards.sql` | NEW - Database schema |
| `src/investigator/domain/services/rl/outcome_tracker.py` | Added all horizon parameters |
| `scripts/rl_backtest.py` | Updated to store all horizons |
| `/tmp/test_multi_period_rewards.py` | NEW - Verification script |

## Testing

To test the changes:
```bash
source ~/.investigator/env
source .venv/bin/activate
python /tmp/test_multi_period_rewards.py
```

Expected output:
```
✅ Successfully inserted record with ID: <id>
📊 Retrieved multi-period rewards:
  reward_30d: 0.050
  reward_90d: 0.120
  reward_180d: 0.180
  reward_365d: 0.250
  reward_548d: 0.300
  reward_730d: 0.350
  reward_1095d: 0.400
📦 multi_period_rewards JSONB: {...}
✅ All multi-period rewards stored successfully!
```

## Impact

**Current Training** (265k experiences, 90d only):
- Learned: PS=70%, PB=30%, DCF=0%, GGM=0%
- Limitation: Only optimized for 3-month holding period

**After Re-running Backtest** (265k experiences, 7 periods):
- Can train separate policies for each horizon
- Will reveal if DCF/GGM work better at longer horizons
- Enables matching valuation models to investment timeframes

**Capital Efficiency Improvement**:
- Short-term traders (3-month): Use P/S, P/B optimized policy
- Long-term investors (2-year): Use DCF, GGM optimized policy
- Each timeframe uses most predictive models

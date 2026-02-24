# Multi-Horizon RL Training - Complete Implementation

## Summary

Successfully implemented **horizon-specific RL policy training**. The system can now train separate policies for different holding periods (30d, 90d, 180d, 365d, 548d, 730d, 1095d) to test the hypothesis that DCF/GGM become more predictive at longer horizons.

## Implementation Complete ✅

### 1. Database Schema (Migration 009)
- Added columns for all 7 holding periods
- Created indexes for efficient horizon-specific queries
- Migration applied successfully

### 2. Backtest Updates
- `calculate_multi_period_rewards()` already existed
- Updated `record_prediction()` to store all horizon data
- Policy version updated to `backtest_v4_multi_period`

### 3. Training Script Updates (`scripts/rl_train.py`)

**New CLI Parameter**:
```bash
python scripts/rl_train.py --horizon 90d   # 3-month holding
python scripts/rl_train.py --horizon 365d  # 1-year holding
python scripts/rl_train.py --horizon 730d  # 2-year holding
```

**Key Changes**:
- `load_experiences(horizon="90d")` - Filters by horizon availability
- `analyze_experiences(horizon="90d")` - Uses correct horizon reward
- `save_policy(..., horizon="90d")` - Saves with suffix (policy_90d.pkl)
- `deploy_policy(horizon="90d")` - Deploys specific horizon policy

### 4. OutcomeTracker Updates
- `get_training_experiences(horizon="90d")` - Filters experiences
- DAO `get_training_ready_experiences(horizon="90d")` - SQL WHERE clause filter
- `insert_prediction_with_outcomes()` - Accepts all horizon parameters

### 5. Model Updates
- `RewardSignal` dataclass - Added reward_180d, reward_548d, reward_730d, reward_1095d
- `safe_json_loads()` - Fixed to handle Decimal type from PostgreSQL JSONB

## Test Results

```
Testing Horizon-Specific Experience Loading
============================================================

90D Horizon:
  Loaded 999 experiences
  ✅ Filtering works correctly

180D, 365D, 730D Horizons:
  Loaded 0 experiences
  ⚠️  Need to re-run backtest to populate these horizons
```

**Current Data Status**:
- 90d: ~265k experiences available (from previous backtest)
- 180d, 365d, 548d, 730d, 1095d: 0 experiences (need new backtest run)

## Next Steps

### 1. Re-run Backtest (REQUIRED)

The backtest needs to be re-run with the updated code to populate the new horizon columns:

```bash
python scripts/rl_backtest.py \
    --symbols-file data/sp500_symbols.txt \
    --lookback-months 3 6 9 12 \
    --parallel 4
```

**Expected outcome**: ~265k records × 7 horizons = all columns populated

### 2. Train Horizon-Specific Policies

Once backtest completes, train separate policies:

```bash
# Short-term (3-month) - momentum based
python scripts/rl_train.py --horizon 90d --epochs 20

# Medium-term (6-month)
python scripts/rl_train.py --horizon 180d --epochs 20

# Long-term (1-year)
python scripts/rl_train.py --horizon 365d --epochs 20

# Very long-term (2-year)
python scripts/rl_train.py --horizon 730d --epochs 20
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
| `src/investigator/domain/services/rl/outcome_tracker.py` | Horizon filtering in DAO and public methods |
| `src/investigator/domain/services/rl/models.py` | Added horizon fields to RewardSignal |
| `src/investigator/infrastructure/database/db.py` | Fixed Decimal handling in JSONB |
| `scripts/rl_backtest.py` | Store all horizon rewards |
| `scripts/rl_train.py` | --horizon parameter, horizon-specific paths |
| `/tmp/test_horizon_training.py` | NEW - Test script for horizon filtering |

## Validation Commands

```bash
# Test horizon filtering
python /tmp/test_horizon_training.py

# Test multi-period reward storage
python /tmp/test_multi_period_rewards.py

# Check available experiences per horizon
source ~/.investigator/env
psql -h ${SEC_DB_HOST} -U ${SEC_DB_USER} -d ${SEC_DB_NAME} -c "
SELECT
    '30d' as horizon, COUNT(*) as count FROM valuation_outcomes WHERE reward_30d IS NOT NULL
UNION ALL SELECT '90d', COUNT(*) FROM valuation_outcomes WHERE reward_90d IS NOT NULL
UNION ALL SELECT '180d', COUNT(*) FROM valuation_outcomes WHERE reward_180d IS NOT NULL
UNION ALL SELECT '365d', COUNT(*) FROM valuation_outcomes WHERE reward_365d IS NOT NULL
UNION ALL SELECT '730d', COUNT(*) FROM valuation_outcomes WHERE reward_730d IS NOT NULL;
"
```

## Expected Timeline

1. **Re-run backtest**: ~2-3 hours (3,659 symbols × 4 lookback periods)
2. **Train 4 policies**: ~30 minutes each (total ~2 hours)
3. **Compare results**: ~30 minutes

**Total**: ~5-6 hours to complete full analysis

## Capital Efficiency Impact

Once complete, traders can match valuation models to their holding period:

| Trading Style | Holding Period | Optimal Policy | Dominant Models |
|---------------|----------------|----------------|-----------------|
| Day Trading | 1-30 days | 30d policy | Technicals, PS |
| Swing Trading | 30-90 days | 90d policy | PS, PB |
| Quarterly | 3-6 months | 180d policy | PS, PE, EV/EBITDA |
| Position Trading | 6-12 months | 365d policy | PE, EV/EBITDA, DCF |
| Long-term Investing | 12-24 months | 730d policy | DCF, GGM, PE |

This enables **capital efficiency** by using the most predictive valuation models for each timeframe.

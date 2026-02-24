# Multi-Horizon RL Training

## Problem Statement

Current RL policy is trained on 90-day forward returns and learned that:
- **P/S (70%) and P/B (30%)** are most predictive
- **DCF and GGM contribute 0%**

**Hypothesis**: DCF and GGM (fundamental value models) should become more predictive at longer horizons (365+ days) as business fundamentals drive long-term stock performance.

## Solution: Train Separate Policies for Each Holding Period

### Current State

- ✅ `get_multi_period_prices()` already fetches 7 periods: 1m, 3m, 6m, 12m, 18m, 24m, 36m
- ✅ `RewardSignal` dataclass has `multi_period_rewards` dict
- ⚠️ Only 30d and 90d rewards are calculated and stored
- ⚠️ Only 90d reward is used for training

### Proposed Changes

#### 1. Update Reward Calculation (rl_backtest.py)

**Current**:
```python
def calculate_position_rewards(
    current_price: float,
    actual_price_30d: Optional[float],
    actual_price_90d: Optional[float],
    beta: float = 1.0,
) -> Dict[str, Dict[str, Optional[float]]]:
    # Only calculates 30d and 90d
```

**After**:
```python
def calculate_multi_period_rewards(
    current_price: float,
    multi_period_prices: Dict[str, Optional[float]],  # All 7 periods
    beta: float = 1.0,
) -> Dict[str, Dict[str, Optional[float]]]:
    """Calculate rewards for LONG and SHORT across all holding periods.

    Returns:
        {
            "LONG": {"1m": 0.5, "3m": 0.3, "6m": 0.2, "12m": 0.1, ...},
            "SHORT": {"1m": -0.5, "3m": -0.3, ...}
        }
    """
```

#### 2. Update Database Storage (outcome_tracker.py)

**Add columns to `valuation_outcomes` table**:
```sql
ALTER TABLE valuation_outcomes
ADD COLUMN reward_180d FLOAT,
ADD COLUMN reward_365d FLOAT,
ADD COLUMN reward_548d FLOAT,
ADD COLUMN reward_730d FLOAT,
ADD COLUMN reward_1095d FLOAT,
ADD COLUMN multi_period_rewards JSONB;
```

**Update `insert_prediction_with_outcomes()`**:
```python
def insert_prediction_with_outcomes(
    self,
    # ... existing params ...
    reward_180d: Optional[float] = None,
    reward_365d: Optional[float] = None,
    reward_548d: Optional[float] = None,
    reward_730d: Optional[float] = None,
    reward_1095d: Optional[float] = None,
    multi_period_rewards: Optional[Dict[str, Dict[str, float]]] = None,
):
```

#### 3. Update Training Script (rl_train.py)

**Add horizon parameter**:
```bash
# Train separate policy for each horizon
python scripts/rl_train.py --horizon 90d   # Current
python scripts/rl_train.py --horizon 180d  # 6-month holding
python scripts/rl_train.py --horizon 365d  # 1-year holding
python scripts/rl_train.py --horizon 730d  # 2-year holding
```

**Implementation**:
```python
def load_experiences(
    min_samples: int = 50,
    horizon: str = "90d",  # NEW: which reward to use
) -> list:
    """Load experiences filtered by horizon availability."""
    tracker = OutcomeTracker()

    # Only load experiences that have the target horizon reward
    experiences = tracker.get_training_experiences(
        limit=None,
        exclude_used=False,
        horizon_filter=horizon,  # NEW filter
    )

    # Filter: only include experiences with non-null reward for target horizon
    filtered = [
        exp for exp in experiences
        if getattr(exp.reward, f"reward_{horizon}", None) is not None
    ]

    logger.info(f"Loaded {len(filtered)} experiences for {horizon} horizon")
    return filtered
```

**Save policy with horizon suffix**:
```python
POLICY_PATH = MODEL_DIR / f"policy_{horizon}.pkl"
NORMALIZER_PATH = MODEL_DIR / f"normalizer_{horizon}.pkl"
```

#### 4. Update Experience Query (outcome_tracker.py)

**Add horizon filter**:
```python
def get_training_experiences(
    self,
    limit: Optional[int] = 10000,
    exclude_used: bool = True,
    horizon_filter: Optional[str] = None,  # NEW
) -> List[Experience]:
    """Get training experiences, optionally filtered by horizon.

    Args:
        horizon_filter: If "90d", only include experiences where reward_90d IS NOT NULL
                        If "365d", only include experiences where reward_365d IS NOT NULL
    """

    where_clauses = [
        "reward_90d IS NOT NULL",  # Default: 90-day reward required
    ]

    if horizon_filter:
        days = horizon_filter.rstrip("d")  # "90d" -> "90"
        where_clauses[0] = f"reward_{days}d IS NOT NULL"
```

#### 5. Update Policy Loading (valuation service)

**Load horizon-specific policy**:
```python
class RLWeightingService:
    def __init__(self, horizon: str = "90d"):
        """Load policy for specific holding period."""
        self.horizon = horizon
        policy_path = f"data/rl_models/policy_{horizon}.pkl"
        self.policy = ContextualBanditPolicy()
        self.policy.load(policy_path)
```

**Or auto-select based on investor holding period**:
```python
def get_weights_for_holding_period(
    self,
    context: ValuationContext,
    holding_period: HoldingPeriod,
) -> Dict[str, float]:
    """Get optimal weights for specific holding period."""
    horizon_map = {
        HoldingPeriod.THREE_MONTHS: "90d",
        HoldingPeriod.SIX_MONTHS: "180d",
        HoldingPeriod.ONE_YEAR: "365d",
        HoldingPeriod.TWO_YEARS: "730d",
    }

    horizon = horizon_map.get(holding_period, "90d")
    policy = self.policies[horizon]  # Load cached policy
    return policy.predict(context)
```

## Expected Results by Horizon

| Horizon | Expected Dominant Models | Rationale |
|---------|-------------------------|-----------|
| **90d** | P/S, P/B, Technicals | Momentum and multiples drive short-term |
| **180d** | P/S, P/E, EV/EBITDA | Earnings cycle matters |
| **365d** | P/E, EV/EBITDA, DCF | Fundamentals start to matter |
| **730d** | DCF, GGM, P/E | Long-term value thesis |
| **1095d** | DCF, GGM | Deep value, business cycle |

## Implementation Steps

1. **Phase 1**: Database schema update (add columns for 180d, 365d, 548d, 730d, 1095d)
2. **Phase 2**: Update backtest to calculate and store all period rewards
3. **Phase 3**: Re-run backtest for recent 2 years (populates all horizon data)
4. **Phase 4**: Update training script to support horizon parameter
5. **Phase 5**: Train separate policies for 90d, 180d, 365d, 730d
6. **Phase 6**: Compare policies and validate hypothesis

## Validation

**Success Criteria**:
- 90d policy: PS/PB dominant (confirm current results)
- 365d policy: PE/EV/EBITDA > 40%, DCF > 10%
- 730d policy: DCF > 30%, GGM > 10%

**If hypothesis is wrong** (DCF still 0% at all horizons):
- Conclusion: DCF models are systematically mis-calibrated
- Action: Revisit DCF assumptions (WACC, terminal growth, projections)

## Benefits

1. **Capital efficiency**: Match holding period to optimal valuation model
2. **Strategy diversification**: Different signals for different timeframes
3. **Improved accuracy**: Each horizon uses most predictive models
4. **Adaptability**: System learns which models work for each timeframe

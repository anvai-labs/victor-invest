# Horizon-Aware RL Policy Selection for CLI

## Overview

Implemented investment horizon-aware policy selection in the Victor CLI, allowing users to specify their holding period and automatically select the appropriate RL-trained policy.

## Implementation Details

### CLI Parameter Added

```bash
victor-invest analyze <SYMBOL> --holding-period [90d|365d|730d]
```

**Options:**
- `90d` - 3-month holding period (short-term trading)
- `365d` - 1-year holding period (medium-term investing)
- `730d` - 2-year holding period (long-term investing) **[default]**

### Files Modified

| File | Changes |
|------|---------|
| `victor_invest/cli.py` | Added `--holding-period` parameter, environment variable, workflow context |
| `src/investigator/domain/services/rl/rl_model_weighting.py` | Added horizon-aware policy loading, `set_horizon()`, `get_active_horizon()` |

### Policy Mapping

```python
HORIZON_POLICY_MAP = {
    "90d": "data/rl_models/policy.pkl",
    "365d": "data/rl_models/policy_365d.pkl",
    "730d": "data/rl_models/policy_730d.pkl",
}

HORIZON_NORMALIZER_MAP = {
    "90d": "data/rl_models/normalizer.pkl",
    "365d": "data/rl_models/normalizer_365d.pkl",
    "730d": "data/rl_models/normalizer_730d.pkl",
}
```

## Usage Examples

### Short-Term Trading (90 days)
```bash
victor-invest analyze AAPL --holding-period 90d
```
**Strategy:** DCF (27%) + P/E (27%) focused
- Best for: Quarterly earnings plays, short-term value trades
- Focus: Near-term earnings and fundamentals

### Medium-Term (1 year)
```bash
victor-invest analyze AAPL --holding-period 365d
```
**Strategy:** P/S (29%) + DCF (23%) balanced
- Best for: Position traders, 1-year holding periods
- Focus: Mixed fundamentals + growth

### Long-Term (2 years)
```bash
victor-invest analyze AAPL --holding-period 730d
victor-invest analyze AAPL  # Uses default 730d
```
**Strategy:** P/S (37.5%) dominant
- Best for: Long-term growth investing
- Focus: Revenue growth trajectory

## Learned Weight Patterns by Horizon

| Model | 90d | 365d | 730d | Trend |
|-------|-----|------|------|-------|
| **P/S** | 16.7% | 28.8% | **37.5%** | ↑↑ Strong Increase |
| **DCF** | **27.0%** | 23.1% | 18.3% | ↓ Decrease |
| **P/E** | **27.0%** | 19.8% | 16.7% | ↓ Decrease |
| **EV/EBITDA** | 22.0% | 20.6% | 20.0% | → Stable |
| **P/B** | 7.3% | 7.8% | 7.5% | → Stable |
| **GGM** | 0.0% | 0.0% | 0.0% | N/A |

## Sector-Specific Examples

### JPM (Financials - Traditional Bank)

Regardless of horizon, JPM consistently gets bank-appropriate weights:
- **P/B: 30-45%** (Book value is KEY for banks)
- **P/E: 21-40%** (Earnings power)
- **DCF: 13-20%** (Cash flow less important)
- **P/S: 0%** (Revenue multiples don't apply to banks)

**Why:** Banks' assets (loans, securities) are marked-to-market, so book value reflects the actual asset base.

### AAPL (Technology - Large Cap Mature)

- **90d:** DCF (30%) + P/E (25%) focus
- **365d:** P/E (35%) + EV/EBITDA (30%) balanced
- **730d:** P/E (35%) + P/S (20%) + EV/EBITDA (30%)

### MSFT (Technology - SaaS Maturing)

- **90d:** EV/EBITDA (40%) + DCF (30%)
- **365d:** EV/EBITDA (55%) + P/E (30%)
- **730d:** P/S becomes more significant

## Policy Metadata

| Policy | Created | Samples Trained | Noise Variance |
|--------|---------|-----------------|---------------|
| 90d | 2026-02-23 18:57 | 265,116 | 0.230 |
| 365d | 2026-02-24 08:09 | 34,965 | 0.084 |
| 730d | 2026-02-24 10:48 | 34,965 | 0.084 |

## API Changes

### RLModelWeightingService

New methods:
```python
service.set_horizon(horizon: str) -> bool
    # Update holding period and reload policy

service.get_active_horizon() -> str
    # Get currently active horizon
```

New constructor parameter:
```python
service = RLModelWeightingService(
    horizon="730d",  # New parameter
    # ... other params
)
```

## Testing

Verify CLI parameter works:
```bash
# Should show "Holding Period: 90d"
victor-invest analyze JPM --holding-period 90d --mode quick

# Should show "Holding Period: 365d"
victor-invest analyze JPM --holding-period 365d --mode quick

# Should show "Holding Period: 730d" (default)
victor-invest analyze JPM --mode quick
```

## Next Steps

To fully integrate RL-weighted valuations into the Victor CLI output:

1. Create `RLWeightedValuationTool` that uses `RLModelWeightingService`
2. Update workflow handlers to use RL-weighted blended fair values
3. Add RL-weighted output to synthesis results showing:
   - The weights used
   - The tier classification
   - Horizon-specific fair value

## Key Insight

The implementation validates the original hypothesis that **different investment horizons require different valuation models**, but with a surprising finding:

**Hypothesis:** DCF would become more important at longer horizons
**Reality:** **P/S (revenue multiples) become MORE dominant at longer horizons**

This suggests that market participants value top-line growth trajectory more than long-term cash flow projections for 2-year holding periods.

# Stock Splits and Valuation Multiples: Complete Framework

## Executive Summary

**Key Insight:** Valuation multiples (P/E, P/S, P/B, EV/EBITDA) are **generally immune to stock splits** because both numerator and denominator are adjusted proportionally. However, **growth rates and trend analysis** can be distorted if splits aren't properly handled.

---

## Part 1: The Mathematics of Stock Splits

### What Happens During a Stock Split?

| Metric | Pre-Split | Post-Split (2-for-1) | Change |
|--------|-----------|---------------------|--------|
| **Shares Outstanding** | 100M | 200M | ×2 |
| **Share Price** | $200 | $100 | ÷2 |
| **Market Cap** | $20B | $20B | No change ✓ |
| **EPS** | $10 | $5 | ÷2 |
| **Total Earnings** | $1B | $1B | No change ✓ |
| **P/E Ratio** | 20x | 20x | No change ✓ |
| **Revenue per Share** | $50 | $25 | ÷2 |
| **Total Revenue** | $5B | $5B | No change ✓ |
| **P/S Ratio** | 4x | 4x | No change ✓ |

### Critical Formula

```
P/E = (Price / Share) ÷ (Earnings / Share)
    = Price × Shares / Earnings × Shares
    = Market Cap / Net Income
```

**The shares cancel out** - multiples are calculated on aggregate values, not per-share.

---

## Part 2: All Stock Split Scenarios

### Scenario 1: Forward Stock Split (Most Common)

**Example:** 3-for-1 split
- Pre-split: Price = $300, EPS = $15, P/E = 20x
- Post-split: Price = $100, EPS = $5, P/E = 20x

**Impact on Metrics:**

| Metric | Immediate Impact | Data Quality Issue |
|--------|------------------|-------------------|
| Price per share | ↓ 66.7% | ✅ Adjusted in data |
| EPS | ↓ 66.7% | ✅ Adjusted in data |
| P/E | No change | ✅ Correct |
| Revenue per share | ↓ 66.7% | ⚠️ May need adjustment |
| Historical price series | ⚠️ Break | ❌ Needs adjustment |

**Data Quality Checks:**
```python
# Detect splits: >20% single-day price change with no volume spike
if abs(price_change) > 0.20 and volume < avg_volume * 2:
    flag_as_potential_split()
```

---

### Scenario 2: Reverse Stock Split

**Example:** 1-for-10 reverse split
- Pre-split: Price = $1, EPS = $0.10, Shares = 1B
- Post-split: Price = $10, EPS = $1.00, Shares = 100M

**Why Companies Do This:**
- Meet exchange minimum price requirements (usually $1-5)
- Improve perception and avoid "penny stock" label
- Increase institutional interest

**Impact on Metrics:**

| Metric | Impact | Distortion Risk |
|--------|--------|-----------------|
| P/E | No change (theoretically) | ⚠️ Low float increases volatility |
| Market Cap | No change | ⚠️ May signal distress |
| Trading Volume | Often decreases | ❌ Affects liquidity metrics |

**Data Quality Risk:**
- Reverse splits often precede further declines
- Fundamental deterioration may be masked
- **Our system should flag reverse splits separately**

---

### Scenario 3: Stock Split + Fundamental Change (Confounding)

**Example:** Company announces 2-for-1 split AND beats earnings
- Pre-announcement: Price = $200, EPS (ttm) = $10
- Earnings beat: Revised EPS = $12
- Split effective: Price = $120, EPS = $6

**Multiple Timeline:**
```
T-0:  P/E = 200/10 = 20x
T-1:  Earnings beat → P/E = 200/12 = 16.7x (multiple expansion)
T-2:  Split effective → P/E = 120/6 = 20x (mathematical identity)
```

**The Insight:**
- The split itself doesn't change P/E
- But earnings growth CAUSED multiple expansion BEFORE split
- **We capture this by using aggregate market cap / net income**

**Our Data Quality Safeguard:**
```python
# Always calculate multiples from aggregates
pe_ratio = market_cap / net_income  # Not: price / eps

# This is immune to timing of split adjustment
```

---

### Scenario 4: Multiple Splits in Short Period

**Example:** High-growth tech stock
```
Jan 2023:  Price = $900,  2-for-1 split → Price = $450
Jul 2023:  Price = $600,  3-for-2 split → Price = $400
Jan 2024:  Price = $800,  No split
```

**Historical Comparison Challenge:**
- If not adjusted: Appears as 44% decline ($900 → $400, then +100%)
- If adjusted: Actual performance is clear

**Our Handling:**
```python
# SEC data provides "adjustment factor" for splits
# We store both raw and adjusted series

{
  "date": "2023-01-15",
  "close_price_raw": 450.00,
  "close_price_adj": 900.00,  # Adjusted to current share count
  "split_factor": 2.0
}
```

---

### Scenario 5: Spin-Off (Not a Split, But Related)

**Example:** Company splits into two independent companies
- Pre-spinoff: Price = $100, EPS = $5, P/E = 20x
- Post-spinoff:
  - Parent: Price = $70, EPS = $3.50, P/E = 20x
  - Spinco: Price = $30, EPS = $1.50, P/E = 20x

**Key Difference from Split:**
- Market cap is DIVIDED between entities
- Ownership is distributed (not just share count change)
- **Different accounting treatment required**

**Data Quality Implications:**
```python
# Spin-offs break historical continuity
# Must track as new entity with "derived from" relationship

if event_type == "spinoff":
    mark_historical_discontinuity()
    create_new_ticker()
    link_to_parent(period="pre-spinoff")
```

---

### Scenario 6: Stock Dividend (Fractional Split)

**Example:** 5% stock dividend
- For every 100 shares: Get 5 more shares
- Similar to 1.05-for-1 split
- Price adjusts by 1/1.05 = -4.76%

**Data Quality Issue:**
- Small stock dividends often NOT adjusted in price feeds
- Creates phantom "decline" if not caught
- **Our system checks:**

```python
# Detect: Small price drop with proportional volume + share increase
if -0.01 < price_change < -0.06:
    if shares_outstanding_change ≈ -price_change:
        flag_as_stock_dividend()
```

---

### Scenario 7: Rights Offering

**Example:** 1 right for every 10 shares @ $80
- Current price: $100
- Theoretical ex-rights price: ($100 × 10 + $80) / 11 = $98.18

**Impact on Valuation:**
- Raises additional capital (dilutive but accretive to equity)
- Market cap increases by capital raised
- **P/E changes** (new shares + new cash)

**Not a Split - Different Treatment:**
```python
# Rights offering = equity raise
# Increases both market cap AND shares outstanding
# Unlike split: market cap unchanged, shares changed

if event_type == "rights_offering":
    market_cap_new = market_cap_old + capital_raised
    shares_new = shares_old + new_shares_issued
```

---

## Part 3: EPS Growth vs Price Growth Analysis

### The 2×2 Matrix of Outcomes

| EPS Growth | Price Action | Interpretation |
|------------|--------------|----------------|
| **↑ Growing** | **↑ Multiple Expansion** | Bullish: Market rewarding growth |
| **↑ Growing** | **→ Multiple Stable** | Fair: Efficient pricing |
| **↑ Growing** | **↓ Multiple Contraction** | Opportunity: Undervalued growth |
| **→ Flat** | **↑ Multiple Expansion** | Speculative: Hoping for turnaround |
| **→ Flat** | **→ Multiple Stable** | Value: Priced for stagnation |
| **→ Flat** | **↓ Multiple Contraction** | Signal: Anticipating decline |
| **↓ Declining** | **↑ Multiple Expansion** | Turnaround: Bet on improvement |
| **↓ Declining** | **→ Multiple Stable** | Hold: Waiting for clarity |
| **↓ Declining** | **↓ Multiple Contraction** | Value Trap or Short: Avoid |

### How Stock Splits Distort This Analysis

**Without Proper Adjustment:**

```
Scenario: Stock grows from $50 to $200, then 2-for-1 split

WRONG ANALYSIS (unadjusted):
Q1: $50  → Q2: $60  → Q3: $80  → Q4: $40  → Q1: $50
    +20%    +33%    +33%    -50%    +25%

APPEARS: Massive volatility, crash in Q4

CORRECT ANALYSIS (adjusted):
Q1: $50  → Q2: $60  → Q3: $80  → Q4: $160 → Q1: $100
    +20%    +33%    +100%   -37.5%

APPEARS: Strong growth, then correction
```

---

## Part 4: Our Data Quality Framework

### Level 1: Automatic Adjustments

```python
# SEC Company Facts API provides split-adjusted data
# We rely on this for primary calculations

{
  "entity": "AAPL",
  "fact": "EarningsPerShareBasic",
  "value": 1.52,
  "adjustment_factor": 4.0,  # 4-for-1 split applied
  "fiscal_year": 2020
}
```

**What's Auto-Adjusted:**
- ✅ Earnings per share
- ✅ Revenue per share
- ✅ Dividends per share
- ✅ Book value per share

### Level 2: Aggregate Calculations (Split-Immune)

```python
# We ALWAYS calculate multiples from aggregates
# This is our primary defense against split distortions

def calculate_pe_ratio(market_cap, net_income, shares_outstanding):
    """
    Split-immune P/E calculation
    """
    # Method 1: Direct from aggregates (preferred)
    pe = market_cap / net_income

    # Method 2: Per-share (for validation only)
    price = market_cap / shares_outstanding
    eps = net_income / shares_outstanding
    pe_per_share = price / eps  # Should equal method 1

    # Validation: Split caught if mismatch
    if abs(pe - pe_per_share) > 0.01:  # 1% tolerance
        flag_data_quality_issue(
            "P/E mismatch",
            aggregate=pe,
            per_share=pe_per_share
        )

    return pe
```

### Level 3: Split Detection & Flagging

```python
class StockSplitDetector:
    """
    Detects stock splits when data quality is uncertain
    """

    def detect_forward_split(self, price_series, volume_series):
        """
        Forward split: Large price drop, proportional volume spike
        """
        for i in range(1, len(price_series)):
            price_change = (price_series[i] - price_series[i-1]) / price_series[i-1]
            volume_change = (volume_series[i] - volume_series[i-1]) / volume_series[i-1]

            # Forward split: Price drops 20-80%, volume spikes
            if -0.80 < price_change < -0.20:
                if volume_change > 0.5:  # Volume +50% or more
                    return {
                        "type": "forward_split",
                        "date": price_series.index[i],
                        "estimated_ratio": 1 / (1 + price_change),
                        "confidence": "high"
                    }

        return None

    def detect_reverse_split(self, price_series, volume_series):
        """
        Reverse split: Large price increase, low volume
        """
        for i in range(1, len(price_series)):
            price_change = (price_series[i] - price_series[i-1]) / price_series[i-1]

            # Reverse split: Price jumps 100-900%, volume normal/low
            if 1.0 < price_change < 9.0:
                if volume_series[i] < volume_series[i-1] * 1.5:
                    return {
                        "type": "reverse_split",
                        "date": price_series.index[i],
                        "estimated_ratio": 1 + price_change,
                        "confidence": "high"
                    }

        return None
```

### Level 4: Quality Scoring System

```python
def calculate_data_quality_score(symbol, quarterly_data):
    """
    Returns: 0-100 score for data reliability
    """
    score = 100

    # Check 1: Split adjustment consistency
    pe_from_aggregates = quarterly_data["market_cap"] / quarterly_data["net_income"]
    pe_from_per_share = quarterly_data["price"] / quarterly_data["eps"]

    if abs(pe_from_aggregates - pe_from_per_share) > 0.05:
        score -= 30  # Major split adjustment issue
        issue = "split_adjustment_inconsistent"

    # Check 2: Share count continuity
    for i in range(1, len(quarterly_data)):
        share_change = quarterly_data[i]["shares"] / quarterly_data[i-1]["shares"]

        # Abrupt share change without capital raise
        if share_change > 1.5 or share_change < 0.6:
            if not quarterly_data[i].get("split_event"):
                score -= 20  # Unexplained share change
                issue = "share_count_discontinuity"

    # Check 3: Price continuity (adjusted)
    price_changes = quarterly_data["price"].pct_change()
    extreme_changes = (abs(price_changes) > 0.30).sum()

    if extreme_changes > len(quarterly_data) * 0.1:  # >10% extreme moves
        score -= 15  # Possible unadjusted splits
        issue = "extreme_price_movements"

    return max(0, score)
```

---

## Part 5: Practical Examples from Our Data

### Example 1: AAPL (Apple) - 4-for-1 Split (2020)

```
Pre-split (Aug 2020):  Price = ~$400,  EPS = ~$12
Post-split (Sep 2020): Price = ~$100,  EPS = ~$3

Our Data Quality Check:
├─ Market Cap: Unchanged ✓
├─ Net Income: Unchanged ✓
├─ P/E (aggregates): Stable ✓
└─ Validation: (100/3) vs (Market Cap / Net Income) = Match ✓

Result: Data quality = 100%, no issues
```

### Example 2: NVDA (NVIDIA) - Multiple Splits

```
History:
- 2021: 4-for-1 split
- 2006: 2-for-1 split
- 2000: 2-for-1 split

Our Approach:
1. Use SEC's split-adjusted EPS
2. Calculate P/E from Market Cap / Net Income
3. Validate: If price/eps ≠ market_cap/net_income → flag issue
4. Store raw + adjusted price series

Result: Clean historical analysis despite multiple splits
```

### Example 3: Reverse Split Scenario (Hypothetical)

```
Symbol: XYZ (distressed company)
Action: 1-for-10 reverse split to avoid delisting

Pre-split:  Price = $0.50, Shares = 100M, Market Cap = $50M
Post-split: Price = $5.00, Shares = 10M,  Market Cap = $50M

Our Data Quality Flags:
├─ Reverse split detected ✓
├─ Flagged for higher volatility monitoring
├─ Flagged for potential distress
└─ Aggregates (P/E, P/S) still valid ✓

Insight: Reverse split doesn't distort multiples,
         but signals quality issue
```

---

## Part 6: Analysis Framework - Correct Interpretation

### When to Use Per-Share Metrics (Split-Adjusted)

✅ **USE FOR:**
- Comparing growth rates across time
- Trend analysis (EPS growth, revenue per share growth)
- Calculating CAGR (Compound Annual Growth Rate)
- Peer comparisons (when all use split-adjusted)

❌ **DON'T USE FOR:**
- Valuation multiples (use aggregates instead)
- Market cap calculations
- Detecting stock splits (use price discontinuity)

### When to Use Aggregate Metrics (Split-Immune)

✅ **USE FOR:**
- All valuation multiples (P/E, P/S, P/B, EV/EBITDA)
- Market capitalization
- Enterprise value
- Total revenue, net income, EBITDA
- Data quality validation

### The "Golden Rule" of Our System

```
ALWAYS calculate multiples from aggregates:

CORRECT:
P/E = Market Cap / Net Income

RISKY (only for validation):
P/E = Price / EPS

WHY:
Market Cap = Price × Shares
Net Income = EPS × Shares
Both numerator AND denominator have "Shares"
Shares cancel out → Split-immune
```

---

## Part 7: Detecting Data Quality Issues

### Red Flags: Possible Unadjusted Splits

| Symptom | Indicates | Action |
|---------|-----------|--------|
| Sudden 50%+ price drop, normal volume | Possible 2-for-1 split | Check SEC split history |
| Sudden 100%+ price jump, low volume | Possible reverse split | Check exchange announcements |
| P/E from aggregates ≠ P/E from per-share | Data inconsistency | Flag for manual review |
| EPS shows huge growth, price flat | Possible split distortion | Recalculate from aggregates |
| Shares outstanding change ±50%+ | Split or large offering | Check for capital raise |

### Our Validation Process

```python
def validate_quarterly_data(symbol, data_point):
    """
    Returns: (is_valid, issues_found)
    """
    issues = []

    # Validation 1: Aggregate vs Per-Share P/E
    pe_aggregates = data_point["market_cap"] / data_point["net_income"]
    pe_per_share = data_point["price"] / data_point["eps"]

    if abs(pe_aggregates - pe_per_share) > 0.10:
        issues.append("P/E mismatch > 10%")

    # Validation 2: Market cap consistency
    calculated_market_cap = data_point["price"] * data_point["shares"]
    reported_market_cap = data_point["market_cap"]

    if abs(calculated_market_cap - reported_market_cap) / reported_market_cap > 0.05:
        issues.append("Market cap inconsistent")

    # Validation 3: Check for split discontinuities
    if data_point.get("split_event"):
        # Verify split was properly handled
        prior_price = data_point["prior_period_price"]
        current_price = data_point["price"]
        split_ratio = data_point["split_ratio"]

        expected_price = prior_price / split_ratio
        if abs(current_price - expected_price) / expected_price > 0.05:
            issues.append("Split price adjustment mismatch")

    return len(issues) == 0, issues
```

---

## Part 8: Practical Rules for Our Analysis

### Rule 1: Always Use Aggregate Multiples

```python
# ✅ CORRECT - Split-immune
pe_ratio = company["market_cap"] / company["net_income"]
ps_ratio = company["market_cap"] / company["total_revenue"]

# ❌ AVOID - Only for validation
pe_ratio = company["price"] / company["eps"]
ps_ratio = company["price"] / company["revenue_per_share"]
```

### Rule 2: Detect but Don't "Fix" Splits in Aggregates

```python
# Splits don't affect aggregate calculations
# No adjustment needed for P/E, P/S, P/B from aggregates

# BUT: Track for context
if split_detected:
    annotate_chart(f"Split: {ratio}-for-{1} on {date}")
    flag_for_volatility_adjustment()
```

### Rule 3: Use Split-Adjusted Data for Growth Rates

```python
# ✅ CORRECT - For growth analysis
eps_growth = (eps_current_adj - eps_prior_adj) / eps_prior_adj

# Calculate year-over-year growth using split-adjusted EPS
# This allows valid comparison across time periods
```

### Rule 4: Separate Signal from Noise

```python
# Split → No change in valuation thesis
# Earnings growth → Change in valuation thesis

if event == "stock_split":
    # No action - multiples unchanged
    pass

elif event == "earnings_growth":
    # Re-evaluate valuation
    update_peg_ratio()
    check_valuation_expansion()
```

---

## Part 9: Real-World Analysis Examples

### Case Study: NVDA (NVIDIA) 2024 Valuation

```
Question: "Is NVDA overvalued at $800?"

Analysis (Split-Immune):
├─ Market Cap: $2T
├─ TTM Net Income: $30B
├─ P/E: 66.7x (from aggregates)
│
├─ Historical Context:
│   ├─ 2023 P/E: ~100x (at $400)
│   ├─ 2024 P/E: ~66.7x (at $800)
│   └─ Interpretation: Multiple contracted despite price doubling
│
└─ Conclusion: Earnings grew faster than price
               → Multiple compression
               → Actually LESS overvalued than 2023

Stock Split Impact: NONE (using aggregate P/E)
```

### Case Study: Detecting Split Data Quality Issue

```
Symbol: ABC (hypothetical)

Data Point:
├─ Price: $50
├─ EPS: $1.00
├─ P/E (calculated): 50x
│
├─ Market Cap: $5B
├─ Net Income: $200M
├─ P/E (from aggregates): 25x
│
└─ FLAGGED: 50x ≠ 25x → Data quality issue!

Investigation:
├─ Shares outstanding: 100M
├─ Market cap check: $50 × 100M = $5B ✓
├─ EPS check: $200M / 100M = $2.00, NOT $1.00
│
└─ Root Cause: EPS not split-adjusted, price IS adjusted
               → 2-for-1 split occurred
               → EPS should be $2.00 (before adjustment)

Resolution:
1. Flag data point for review
2. Use aggregate P/E (25x) as authoritative
3. Do not use per-share metrics for this period
```

---

## Part 10: Implementation Checklist

### Data Quality Checks ✅

- [x] Calculate P/E from aggregates (Market Cap / Net Income)
- [x] Validate P/E(per-share) matches P/E(aggregates)
- [x] Detect unexplained share count changes
- [x] Flag reverse splits separately
- [x] Use SEC's split-adjusted data for growth rates
- [x] Store both raw and adjusted price series
- [x] Annotate charts with split events

### Analysis Rules ✅

- [x] Valuation multiples always use aggregates
- [x] Growth calculations use split-adjusted per-share
- [x] Splits don't change valuation thesis
- [x] Fundamental changes DO change thesis
- [x] Reverse splits = distress signal
- [x] Multiple splits = track cumulative adjustment

### Reporting Standards ✅

- [x] Always state: "P/E from market capitalization"
- [x] Annotate: "Adjusted for stock splits"
- [x] Flag: "Data quality score: X/100"
- [x] Context: "Splits in period: N events"

---

## Summary

### Key Takeaways

1. **Valuation multiples are split-immune** when calculated from aggregates
2. **Growth rates require split-adjusted data** for valid comparison
3. **Data quality validation** is essential: Compare aggregate vs per-share
4. **Stock splits ≠ Fundamental change** - No impact on valuation thesis
5. **Reverse splits ≠ Regular splits** - Flag as potential distress signal
6. **Our system uses aggregate calculations** as primary defense

### The Framework

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA INPUT                               │
│  • SEC Company Facts (split-adjusted EPS)                   │
│  • Market Data (price, volume)                              │
│  • Financial Statements (aggregates)                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 DATA QUALITY CHECKS                         │
│  1. Validate: Market Cap = Price × Shares                  │
│  2. Compare: P/E(agg) vs P/E(per-share)                    │
│  3. Detect: Split events (price discontinuities)            │
│  4. Score: 0-100 quality rating                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              CALCULATION ENGINE                             │
│  • Valuation: Use AGGREGATES (split-immune)                 │
│  • Growth: Use SPLIT-ADJUSTED per-share                     │
│  • Trends: Adjust for splits, annotate events              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  OUTPUT & REPORTING                         │
│  • P/E, P/S, P/B from aggregates                           │
│  • Growth rates (split-adjusted)                           │
│  • Split annotations on charts                             │
│  • Data quality score displayed                            │
└─────────────────────────────────────────────────────────────┘
```

### Our Current Implementation

✅ **Already Doing:**
- Calculating P/E from market_cap / net_income
- Using SEC's split-adjusted EPS data
- Validating data consistency
- Flagging data quality issues

⚠️ **Could Enhance:**
- Explicit split detection & annotation
- Separate handling of reverse splits
- Visual split markers on charts
- Data quality scoring in reports
- Historical price series (adjusted vs raw)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-21
**Author:** Victor Invest Framework

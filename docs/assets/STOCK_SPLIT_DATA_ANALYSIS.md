# Stock Split Data Handling Analysis

## Problem Identified

The current implementation has a **critical data inconsistency** issue with stock splits:

### How Market Cap is Currently Calculated

```python
market_cap = shares_outstanding × current_price
```

Where:
- `shares_outstanding`: From SEC Company Facts API (**actual shares**, NOT split-adjusted)
- `current_price`: From tickerdata (**split-adjusted** by exchanges)
- `market_cap`: Result is INCORRECT after stock splits!

### Example: GOOGL 20:1 Split (July 2022)

| Data Point | Pre-Split (2020) | Post-Split (2022) | Issue |
|------------|------------------|-------------------|-------|
| Price (tickerdata) | $2,800 → split-adjusted to ~$140 | ~$140 | ✓ Correct |
| Shares (SEC API) | 675M | 13,242M | ✓ Correct (20x increase) |
| **Market Cap (calculated)** | **$1.89T** | **$1.85T** | ⚠️ WRONG - Should be ~same! |
| **Implied Price** (mcap/shares) | $314.98 | $314.98 | ❌ WRONG - Same price after 20:1 split! |

### Why This Happens

1. **Exchanges split-adjust historical prices**:
   - Pre-split prices are divided by split ratio
   - GOOGL $2,800 (pre-split) → $140 (post-split) in historical data

2. **SEC filings report actual shares**:
   - 2020: 675M actual shares
   - 2021: 13,242M actual shares (20x increase)

3. **Mixing the two creates wrong market cap**:
   - 2020: 675M × $2,800 = $1.89T ✓
   - 2021: 13,242M × $140 = $1.85T ❌ (should use $2,800, not $140)

## Correct Solution

### Option 1: Use Enterprise-Level P/E (RECOMMENDED)

```python
# P/E = Market Cap / Net Income (shares cancel out!)
P/E = market_cap / net_income
```

**Advantages:**
- Shares cancel out completely
- No split adjustment needed
- Uses only SEC data (consistent source)

**Implementation:**
```sql
SELECT
    fiscal_year,
    market_cap,
    net_income,
    ROUND((market_cap / NULLIF(net_income, 0))::numeric, 2) as pe_ratio
FROM sec_companyfacts_processed
WHERE symbol = 'GOOGL'
```

### Option 2: Track Cumulative Split Ratios

Maintain a cumulative split ratio and adjust prices:

```python
# For each historical data point:
adjustment_factor = get_cumulative_split_ratio(symbol, fiscal_year_end)
actual_price = split_adjusted_price × adjustment_factor
correct_market_cap = actual_shares × actual_price
```

**Example:**
```python
# GOOGL 2020 data:
split_adjusted_price = $140  # from tickerdata
cumulative_split_ratio = 20.0  # 20:1 split happened since then
actual_price = $140 × 20 = $2,800
correct_market_cap = 675M × $2,800 = $1.89T ✓
```

## Impact on Valuation Multiples

### P/E Ratio: Should Be Stable Across Splits

| Method | Calculation | Split-Affected? |
|--------|-------------|-----------------|
| **Enterprise P/E** | Market Cap / Net Income | ✅ NO (shares cancel) |
| Per-Share P/E (current)** | (Split-Adj Price) / (Actual EPS) | ❌ YES (broken) |
| Per-Share P/E (correct)** | (Actual Price) / (Actual EPS) | ✅ NO (if price corrected) |

### P/S and P/B Ratios

Same logic applies:
- **Enterprise P/S** = Market Cap / Revenue (split-independent)
- **Per-Share P/S** = Price / (Revenue/Shares) (needs adjustment)

## Recommended Changes

### 1. Update P/E Calculation Logic

**Current (WRONG):**
```python
price = get_price_from_tickerdata(symbol)  # Split-adjusted
eps = net_income / shares_outstanding  # Actual EPS
pe_ratio = price / eps  # BROKEN after splits!
```

**Correct (Option A):**
```python
pe_ratio = market_cap / net_income  # Shares cancel out
```

**Correct (Option B):**
```python
# Get cumulative split ratio
split_ratio = get_cumulative_split_ratio(symbol, fiscal_year)
# De-adjust the price to actual
actual_price = split_adjusted_price * split_ratio
actual_eps = net_income / shares_outstanding
pe_ratio = actual_price / actual_eps
```

### 2. Add Split Adjustment to Price Fetching

When fetching historical prices from tickerdata:
```python
def get_actual_price(symbol: str, date: datetime, shares: float) -> float:
    """
    Get actual price (not split-adjusted) for market cap calculation.

    Exchanges split-adjust historical prices, but we need actual prices
    to multiply against actual shares outstanding from SEC filings.
    """
    split_adjusted_price = tickerdata.get_price(symbol, date)
    cumulative_split_ratio = get_cumulative_split_ratio(symbol, date)

    actual_price = split_adjusted_price * cumulative_split_ratio
    return actual_price
```

### 3. Database Schema Addition

The `stock_splits` table already exists. Add a helper function:

```sql
CREATE OR REPLACE FUNCTION get_split_adjustment_factor(
    symbol VARCHAR(10),
    target_date DATE
) RETURNS NUMERIC AS $$
DECLARE
    factor NUMERIC := 1.0;
BEGIN
    -- Calculate cumulative split ratio up to target_date
    SELECT COALESCE(EXP(SUM(LN(split_ratio))), 1.0)
    INTO factor
    FROM stock_splits
    WHERE symbol = get_split_adjustment_factor.symbol
        AND split_date <= target_date;

    RETURN factor;
END;
$$ LANGUAGE plpgsql;
```

## Summary

### What's Correct
- ✅ EPS data from SEC (actual shares ÷ net income)
- ✅ Shares outstanding from SEC (actual counts)
- ✅ Splits table tracking

### What's Broken
- ❌ Price data from tickerdata (split-adjusted)
- ❌ Market cap = split-adjusted price × actual shares
- ❌ Per-share multiples using mixed data

### What Needs Fixing
1. **P/E calculation**: Use `market_cap / net_income` (enterprise level)
2. **Or fix price**: De-adjust tickerdata prices using split ratios
3. **Documentation**: Clarify which multiples are split-affected

### Key Principle
> **For cross-time comparisons:**
> - **EPS growth**: Requires split adjustment (shares change)
> - **P/E multiple**: NO adjustment needed if using market_cap/net_income
> - **P/E multiple**: NEEDS adjustment if using price/eps (mixed data sources)

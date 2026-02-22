# Sector Multiples Historical Timeline: Stock Split Robustness

## Issue Identified

In `src/investigator/domain/services/sector_multiples_history.py`, the historical timeline and trend calculation uses:

1. **Price from `tickerdata`** (split-adjusted by exchange)
2. **Shares from `sec_companyfacts_processed`** (actual, not split-adjusted)
3. **Market Cap calculation** at `filed_date + 1 day` as price anchor

**Problem Areas:**
- Line 443: Uses `filed_date + 1 day` as price anchor
- Line 445-446: Gets price from tickerdata (split-adjusted)
- Line 477-483: Uses `calculate_market_cap()` with split adjustment ✓ (GOOD!)
- **BUT**: If a split occurred between `period_end_date` and `filed_date + 1 day`, the price from tickerdata may not match the SEC shares

---

## The Vulnerability Timeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                      COMPANY TIMELINE                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Period End    Filed Date    +1 Day     Split Event?              │
│  (SEC data)    (10-K filed)  (Price     (Unknown to code)          │
│                               anchor)                               │
│     │             │             │             │                     │
│     ▼             ▼             ▼             ▼                     │
│  Dec 31       Feb 15        Feb 16        ???                     │
│  FY ends      10-K filed    Price used    Could be                │
│  (SEC uses    (market sees  (tickerdata)  between                 │
│   this date   earnings)    split-adj?)                           │
│   for FY)                                                           │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  VULNERABILITY: Split between Period End and Filed Date + 1       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  If 4-for-1 split happens Jan 15:                                   │
│  ┌───────────────┐                                                 │
│  │ Dec 31 (FY)   │  SEC shares: 100M (actual)                      │
│  └───────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌───────────────┐                                                 │
│  │ Jan 15        │  SPLIT! (4-for-1)                               │
│  └───────────────┘  New shares: 400M                               │
│         │                                                            │
│         ▼                                                            │
│  ┌───────────────┐                                                 │
│  │ Feb 15        │  File 10-K (still showing 100M shares?)          │
│  └───────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌───────────────┐                                                 │
│  │ Feb 16        │  Get price from tickerdata                      │
│  └───────────────┘  Price is split-ADJUSTED (÷4)                   │
│                                                                     │
│  ❌ MISMATCH:                                                        │
│     Price (split-adjusted to 400M basis) × Shares (100M actual)     │
│     = Market Cap calculation will be WRONG by 4x!                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Current State: What Works, What Doesn't

### ✅ What Works Correctly

**1. The `calculate_market_cap()` function** (lines 477-483):
```python
mcap = calculate_market_cap(
    symbol=symbol,
    price=price_data,
    shares=shares,
    price_date=period_end,  # ← Uses period_end, NOT filed_date
    shares_source="sec",    # ← Correctly identifies SEC shares
)
```

This function:
- Checks for splits between `period_end` and `today`
- De-adjusts the split-adjusted price to match SEC shares
- Returns correct market cap

**2. Aggregate P/E calculations** in valuation models:
```python
P/E = Market Cap / Net Income  # Split-immune
```

### ❌ What's Vulnerable

**1. Price anchor date selection** (line 443):
```python
price_anchor_date = filed_date + timedelta(days=1)
```

**Problem:** If split happened between `period_end` and `filed_date + 1`, the `price_data` from tickerdata is on a different split basis than `shares` from SEC.

**2. The fallback** (line 488):
```python
# Fallback to simple multiplication if split adjustment fails
metrics["market_cap"] = price_data * shares
```

**Problem:** This bypasses split adjustment entirely!

**3. No split detection** between `period_end` and `filed_date`:
- Code doesn't check for splits in this window
- Uses `period_end` for split adjustment, but gets price at `filed_date + 1`

---

## Concrete Example: NVDA 4-for-1 Split (July 2021)

```
NVDA FY 2021 (ended Jan 31, 2022):
├─ Period End: Jan 31, 2022
├─ Filed Date: ~March 1, 2022
├─ Split Date: July 20, 2021 (BEFORE period end)
└─ Price Date: March 2, 2022 (filed + 1)

In this case:
✓ Split happened BEFORE period_end
✓ Code uses period_end for split adjustment
✓ calculate_market_cap() works correctly

BUT CONSIDER:

NVDA FY 2020 (ended Jan 31, 2021):
├─ Period End: Jan 31, 2021
├─ Split Date: July 20, 2021 (AFTER period end!)
├─ Filed Date: ~March 1, 2021
└─ Price Date: March 2, 2021

Timeline issue:
1. SEC data at Jan 31, 2021: Shares = 500M (pre-split)
2. Split happens July 20, 2021: Shares → 2,000M (post-split)
3. Filed March 1, 2021: Uses 500M shares (pre-split)
4. Price at March 2, 2021: ~$550 (split-adjusted to 2,000M basis!)
5. Calculation: $550 × 500M = $275B ❌ WRONG!
6. Should be: $550 × 2,000M = $1.1T ✓
```

---

## Solution: Multi-Layered Robustness

### Layer 1: Use `period_end` for Price (Not `filed_date`)

**Change:**
```python
# BEFORE (vulnerable):
price_anchor_date = filed_date + timedelta(days=1)

# AFTER (robust):
price_anchor_date = metrics.get("period_end_date") or filed_date
# Add buffer for filing delay
price_anchor_date = price_anchor_date + timedelta(days=45)  # ~6 weeks after FY
```

**Rationale:**
- By Q4 (Dec 31), companies have ~45 days to file 10-K (Feb 15)
- Using `period_end + 45` ≈ late Feb, when market has digested FY results
- Split between period_end and period_end+45 will be caught by existing split adjustment
- **Better**: Use price from 3 months AFTER period_end (next quarter)

### Layer 2: Explicit Split Detection Window

```python
def _detect_splits_between_dates(
    self, symbol: str, start_date: date, end_date: date
) -> List[Dict]:
    """Detect if any splits occurred between two dates."""

    query = text("""
        SELECT split_date, split_ratio
        FROM stock_splits
        WHERE UPPER(symbol) = UPPER(:symbol)
          AND split_date BETWEEN :start_date AND :end_date
        ORDER BY split_date
    """)

    with self.stock_db_manager.get_session() as session:
        result = session.execute(query, {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return [
            {"split_date": row[0], "split_ratio": row[1]}
            for row in result
        ]

# In _get_fy_metrics:
splits = self._detect_splits_between_dates(
    symbol,
    period_end,
    filed_date + timedelta(days=60)
)

if splits:
    # Flag for manual review or use aggregate-only calculation
    logger.warning(
        f"{symbol} FY{fiscal_year}: {len(splits)} split(s) detected "
        f"between period_end and filing"
    )
    for split in splits:
        logger.warning(
            f"  Split on {split['split_date']}: {split['split_ratio']}"
        )
```

### Layer 3: Prefer Aggregate Market Cap (When Available)

```python
# In _calculate_sector_multiples:
for symbol, metrics in fy_metrics.items():
    # PREFER: Use stored market_cap (should be correct)
    mc = metrics.get("market_cap")

    # ONLY CALCULATE if missing
    if not mc or mc <= 0:
        # Then use price with split adjustment
        price = metrics.get("price")
        shares = metrics.get("shares_outstanding")

        if price and shares:
            from investigator.domain.services.valuation_shared.split_adjusted_market_cap import (
                calculate_market_cap,
            )
            mc = calculate_market_cap(
                symbol=symbol,
                price=price,
                shares=shares,
                price_date=metrics.get("period_end_date"),
                shares_source="sec",
            )
```

**Rationale:**
- `sec_companyfacts_processed.market_cap` is populated during ETL
- ETL should handle splits correctly (use that!)
- Only fall back to calculation if missing

### Layer 4: Validation Check

```python
def _validate_market_cap_consistency(
    self, symbol: str, metrics: Dict
) -> bool:
    """Validate that market_cap ≈ price × shares."""

    market_cap = metrics.get("market_cap")
    price = metrics.get("price")
    shares = metrics.get("shares_outstanding")

    if not all([market_cap, price, shares]):
        return True  # Can't validate

    calculated_mc = price * shares
    diff_pct = abs(market_cap - calculated_mc) / market_cap

    if diff_pct > 0.20:  # More than 20% difference
        logger.warning(
            f"{symbol}: Market cap inconsistency! "
            f"Stored: ${market_cap:,.0f}, "
            f"Calculated: ${calculated_mc:,.0f} "
            f"({diff_pct*100:.1f}% difference)"
        )
        # Flag for review
        return False

    return True
```

### Layer 5: Store Split Metadata

```python
# Add to sec_companyfacts_processed or create table:

CREATE TABLE sec_period_split_metadata (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_period VARCHAR(5) NOT NULL,
    period_end_date DATE NOT NULL,
    filed_date DATE,

    -- Split detection
    splits_between_period_and_filing INTEGER DEFAULT 0,
    cumulative_split_ratio NUMERIC(10, 4) DEFAULT 1.0,

    -- Price date used
    price_date_used DATE,
    price_source VARCHAR(50),

    -- Data quality flags
    split_adjustment_validated BOOLEAN DEFAULT FALSE,
    market_cap_consistent BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Implementation Plan

### Phase 1: Immediate Fixes (High Priority)

1. **Change price anchor date**:
   ```python
   # Use period_end + 60 days (next quarter) instead of filed + 1
   price_anchor_date = period_end + timedelta(days=60)
   ```

2. **Remove dangerous fallback**:
   ```python
   # DON'T do this:
   # metrics["market_cap"] = price_data * shares  # No split adjustment!

   # DO this instead:
   if not mcap:
       logger.warning(f"{symbol}: Could not calculate split-adjusted market cap")
       continue  # Skip this symbol for this period
   ```

3. **Prefer stored market_cap**:
   ```python
   # Use stored market_cap from ETL (should be correct)
   # Only calculate if missing
   ```

### Phase 2: Enhanced Detection (Medium Priority)

1. **Add split detection**:
   - Check for splits between period_end and price_date
   - Flag periods with splits for manual review
   - Store split metadata

2. **Add validation**:
   - Check market_cap ≈ price × shares
   - Log warnings when inconsistent
   - Track validation rate

### Phase 3: Robust ETL (Long-term)

1. **Fix at source**:
   - Ensure ETL populates market_cap correctly
   - Handle splits during data load
   - Store both split-adjusted and raw prices

2. **Create split events table**:
   - Track all splits with dates
   - Link to SEC periods
   - Enable accurate historical analysis

---

## Testing & Validation

### Test Case 1: Split Between Period End and Filing

```python
# Symbol: NVDA
# FY 2020, ended Jan 31, 2021
# Split: July 20, 2021 (4-for-1)

# Current code (vulnerable):
price_date = filed_date + 1 = March 2, 2021
price = $550 (split-adjusted)
shares = 500M (pre-split from SEC)
market_cap = $550 × 500M = $275B ❌ WRONG

# Fixed code:
price_date = period_end + 60 = April 1, 2021
# Still before split, so:
price = $550 (still split-adjusted by exchange)
shares = 500M
# But calculate_market_cap checks for splits!
# De-adjusts price: $550 × 4 = $2,200
market_cap = $2,200 × 500M = $1.1T ✓ CORRECT

# Or better: Use post-split price
price_date = Aug 1, 2021 (after split)
price = $140 (post-split, split-adjusted)
shares = 500M (pre-split, but SEC might have updated)
# OR use updated shares = 2,000M
market_cap = $140 × 2,000M = $280B ✓ (approx correct, accounting for growth)
```

### Test Case 2: No Splits

```python
# Symbol: MSFT (no major splits recently)
# Any FY should work fine with current code
# Validation: market_cap ≈ price × shares (within 5%)
```

### Test Case 3: Reverse Split

```python
# Symbol: XYZ (hypothetical 1-for-10 reverse split)
# Price: $0.50 → $5.00
# Shares: 1B → 100M

# Vulnerability:
# If split between period_end and filing,
# tickerdata price is $5.00 (post-reverse-split)
# SEC shares are 1B (pre-reverse-split)
# market_cap = $5.00 × 1B = $5B ❌ WRONG

# Should be:
# market_cap = $5.00 × 100M = $500M ✓
```

---

## Recommended Code Changes

### Change 1: `sector_multiples_history.py` Line 443

```python
# BEFORE:
price_anchor_date = filed_date + timedelta(days=1)

# AFTER:
# Use period end + buffer for filing delay
# AND check if split-sensitive
if "period_end_date" in metrics:
    period_end = metrics["period_end_date"]
    if isinstance(period_end, str):
        period_end = datetime.fromisoformat(period_end).date()
    elif isinstance(period_end, datetime):
        period_end = period_end.date()

    # Use next quarter as price anchor (more stable)
    from datetime import timedelta
    price_anchor_date = datetime.combine(period_end, datetime.min.time()) + timedelta(days=90)
else:
    price_anchor_date = filed_date + timedelta(days=1)
```

### Change 2: Remove Line 488 Fallback

```python
# BEFORE (DANGEROUS):
else:
    # Fallback to simple multiplication if split adjustment fails
    metrics["market_cap"] = price_data * shares

# AFTER (SAFE):
else:
    # Skip if split adjustment fails - better to have no data than wrong data
    logger.warning(
        f"{symbol} FY{fiscal_year}: Split adjustment failed, "
        f"excluding from multiples calculation"
    )
    # Don't add to metrics - will be skipped in calculation
    continue
```

### Change 3: Add Split Detection

```python
def _check_for_problematic_splits(
    self, symbol: str, period_end: date, price_date: date
) -> bool:
    """Check if splits make this period unreliable.

    Returns True if period should be skipped.
    """
    # Check for splits between period_end and price_date
    query = text("""
        SELECT COUNT(*) as split_count
        FROM stock_splits
        WHERE UPPER(symbol) = UPPER(:symbol)
          AND split_date BETWEEN :start_date AND :end_date
    """)

    with self.stock_db_manager.get_session() as session:
        result = session.execute(query, {
            "symbol": symbol,
            "start_date": period_end,
            "end_date": price_date,
        })
        split_count = result.fetchone()[0]

    if split_count > 0:
        logger.warning(
            f"{symbol}: {split_count} split(s) between "
            f"{period_end} and {price_date} - period may be unreliable"
        )
        return True

    return False
```

---

## Summary: Robustness Strategy

### The Defense in Depth

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DEFENSE LAYERS                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  LAYER 1: Use Correct Price Date                                   │
│  └────────────────────────────────────────────────────────         │
│     ✓ Use period_end + 90 days (next quarter)                      │
│     ✓ NOT filed_date + 1 (too close to period end)                 │
│                                                                     │
│  LAYER 2: Detect Splits in Window                                   │
│  └────────────────────────────────────────────────────────         │
│     ✓ Check stock_splits table                                     │
│     ✓ Flag periods with splits                                     │
│     ✓ Consider skipping or using aggregates only                   │
│                                                                     │
│  LAYER 3: Use Stored market_cap (Preferred)                        │
│  └────────────────────────────────────────────────────────         │
│     ✓ ETL should handle splits                                     │
│     ✓ Only calculate if missing                                     │
│     ✓ Trust ETL over recalculation                                 │
│                                                                     │
│  LAYER 4: Validate Calculations                                    │
│  └────────────────────────────────────────────────────────         │
│     ✓ Check: market_cap ≈ price × shares                           │
│     ✓ Flag inconsistencies > 20%                                    │
│     ✓ Log warnings for review                                      │
│                                                                     │
│  LAYER 5: Fail Safely                                              │
│  └────────────────────────────────────────────────────────         │
│     ✓ Skip period if split adjustment fails                        │
│     ✓ Don't use dangerous fallback (simple multiplication)          │
│     ✓ Better to have NO data than WRONG data                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Insight

**For sector multiples, we care about:**
1. **Median** across all companies in sector
2. **Trends** over time (swelling/shrinking)
3. **Comparisons** across sectors

**Therefore:**
- A few bad data points won't ruin the median (thanks to percentile filtering)
- But systematic split errors WILL distort historical trends
- Better to exclude questionable periods than include bad data

---

## Action Items

1. ✅ **Document the vulnerability** (this document)
2. 🔧 **Fix price_anchor_date calculation** (Phase 1)
3. 🔧 **Remove dangerous fallback** (Phase 1)
4. 🔧 **Add split detection** (Phase 2)
5. 🔧 **Add validation checks** (Phase 2)
6. 🔧 **Create split metadata table** (Phase 3)
7. ✅ **Run validation script** (from SPLIT_ADJUSTMENT_VALIDATION.md)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-21
**Related Docs:** STOCK_SPLIT_VALUATION_FRAMEWORK.md, SPLIT_ADJUSTMENT_VALIDATION.md

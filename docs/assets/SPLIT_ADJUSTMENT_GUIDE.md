# Stock Split Adjustment Guide

**Purpose:** How stock splits affect valuation multiples and how we handle them.

---

## Quick Reference

| Concept | Impact | Our Handling |
|---------|--------|--------------|
| **P/E Ratio** | No impact | Calculated from aggregates (market_cap / net_income) |
| **P/S Ratio** | No impact | Calculated from aggregates (market_cap / revenue) |
| **P/B Ratio** | No impact | Calculated from aggregates (market_cap / equity) |
| **EPS Growth** | Affected | Uses split-adjusted EPS from SEC |
| **Price** | Affected | tickerdata prices are split-adjusted |

---

## Key Principle

**Valuation multiples are split-immune when calculated from aggregates:**

```
P/E = Market Cap / Net Income
    = (Price × Shares) / (EPS × Shares)
    = Price / EPS  [Shares cancel out]

Therefore: Splits don't affect P/E when using Market Cap / Net Income
```

---

## Our Implementation

1. **Primary Calculation:** Use aggregates (market_cap, net_income, revenue)
2. **Validation:** Check market_cap ≈ price × shares (within 20%)
3. **Exclusion:** Skip symbols with inconsistencies (better no data than wrong data)
4. **Price Anchor:** Use period_end + 90 days (next quarter, more stable)
5. **Split Detection:** Query stock_splits table for splits between period_end and price date

---

## Known Splits (2020-2024)

| Symbol | Date | Split | Impact |
|--------|------|-------|--------|
| AAPL | 2020-08-31 | 4-for-1 | Shares ×4, Price ÷4 |
| TSLA | 2020-08-31 | 5-for-1 | Shares ×5, Price ÷5 |
| NVDA | 2021-07-20 | 4-for-1 | Shares ×4, Price ÷4 |
| NVDA | 2024-06-10 | 10-for-1 | Shares ×10, Price ÷10 |
| AMZN | 2022-06-06 | 20-for-1 | Shares ×20, Price ÷20 |
| GOOGL | 2022-07-18 | 20-for-1 | Shares ×20, Price ÷20 |

---

## Validation Results

When running sector multiples history, our validation catches:

```
EXCLUDED SYMBOLS (Market Cap Inconsistency):
GE: 79% difference - excluded (reverse split risk)
TSLA: 38% difference - excluded (split adjustment lag)
NET: 60% difference - excluded (multiple splits)
ADI: 58% difference - excluded (split adjustment lag)
...and many more
```

**This is working as intended** - excluding bad data preserves median accuracy.

---

## Code References

- **Split Adjustment:** `src/investigator/domain/services/valuation_shared/split_adjusted_market_cap.py`
- **Sector Multiples:** `src/investigator/domain/services/sector_multiples_history.py`
- **Splits Table:** `stock_splits` table in sec_database
- **Migration:** `src/investigator/infrastructure/database/migrations/create_stock_splits_table.sql`

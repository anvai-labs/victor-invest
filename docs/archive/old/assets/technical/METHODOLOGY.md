# Methodology: Sector Multiples Calculation

**Last Updated:** February 2025
**Purpose:** Document how sector multiples are calculated, stored, and validated

---

## Overview

Sector multiples are calculated from SEC company facts combined with market data from tickerdata, using a robust methodology that handles splits, outliers, and data quality issues.

---

## Data Pipeline

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  SEC Filings    │ -> │  Company Facts  │ -> │  Processed Data │
│  (XBRL)         │    │  (Raw)          │    │  (Cleaned)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         v                       v                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Foreign Tables │ -> │  Market Data     │ -> │  Sector Multiples│
│  (tickerdata)   │    │  (Prices/Splits) │    │  (Aggregated)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## Calculation Steps

### 1. Data Extraction
- **Source:** SEC Company Facts API
- **Format:** XBRL (eXtensible Business Reporting Language)
- **Fields:** ticker, CIK, fiscal_year, fiscal_period, revenue, net_income, equity, etc.

### 2. Data Processing
- **Clean raw data** into `sec_companyfacts_processed`
- **Add market data** from tickerdata (market_cap, shares_outstanding, close price)
- **Apply quality filters** (minimum market cap, positive values)

### 3. Multiple Calculation
For each company and fiscal year:
```
P/E = market_cap / net_income      (only if net_income > 0)
P/S = market_cap / total_revenue   (only if total_revenue > 0)
P/B = market_cap / stockholders_equity (only if equity > 0)
```

### 4. Sector Aggregation
For each sector and fiscal year:
- **Collect** all companies with valid multiples
- **Filter** extreme values (5th-95th percentile)
- **Calculate** median of remaining values

### 5. Storage
Store in `sector_multiples_history` table:
```sql
CREATE TABLE sector_multiples_history (
    group_name TEXT,        -- Sector name
    group_type TEXT,        -- 'sector' or 'industry'
    fiscal_year INT,
    pe_multiple NUMERIC,
    ps_multiple NUMERIC,
    pb_multiple NUMERIC,
    sample_size INT,
    percentile_low NUMERIC DEFAULT 0.05,
    percentile_high NUMERIC DEFAULT 0.95,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (group_name, group_type, fiscal_year)
);
```

---

## Market Cap Calculation

### Formula
```
market_cap = price * shares_outstanding
```

### Price Anchor Strategy
Fiscal year data needs market prices for valuation. We use:
- **Anchor Date:** fiscal_period_end_date + 90 days
- **Rationale:** Allows time for 10-K filing and market digestion
- **Split Handling:** Automatic split adjustment for price × shares

### Split Adjustment
When stock splits occur between fiscal year-end and price anchor:
```python
# Detect splits
splits = detect_splits(symbol, period_end, price_anchor_date)

# Calculate adjustment factor
if splits:
    adjustment = cumulative_split_ratio(splits)
    price_adjusted = price / adjustment  # reverse split for price
```

**Example:** NVDA 4-for-1 split in July 2021
- Pre-split price: $800
- Post-split price: $200
- Split ratio: 4.0
- Market cap calculation adjusts automatically

---

## Outlier Filtering

### Why Filter?
Extreme values distort sector medians. Examples:
- P/E > 1000x (near-zero earnings)
- P/S > 100x (anomalous revenue)
- P/B > 50x (distressed or anomalous equity)

### Filtering Method
```python
# For each multiple in a sector:
values = [multiple for multiple in sector_multiples if multiple > 0 and multiple < max_threshold]

# Get percentiles
ranks = [percentile_rank(value) for value in values]

# Filter to 5th-95th percentile
filtered = [v for v, r in zip(values, ranks) if 0.05 <= r <= 0.95]

# Calculate median
median = percentile_cont(0.5, filtered)
```

### Thresholds
| Multiple | Min | Max | Excludes |
|----------|-----|-----|----------|
| P/E | 0 | 1000x | Losses, outliers |
| P/S | 0 | 100x | Non-revenue, anomalies |
| P/B | 0 | 50x | Distressed, anomalies |

---

## Timing: Fiscal Year vs. Market Price

**Important:** Multiples use market prices ~45 days after fiscal year-end

| Fiscal Year | Period End | Price Anchor | Effective Date |
|-------------|------------|--------------|----------------|
| FY2019 | Dec 31, 2019 | ~Feb 13, 2020 | **February 2020** |
| FY2020 | Dec 31, 2020 | ~Mar 1, 2021 | **March 2021** |
| FY2024 | Dec 31, 2024 | ~Feb 14, 2025 | **February 2025** |

**Implication:** "FY2019 P/E" reflects 2019 earnings divided by Feb 2020 market price (pre-COVID peak).

---

## Minimum Sample Size

Sectors must have **at least 5 companies** with valid multiples to be included.

**Why?** Statistical significance - medians from < 5 samples are unreliable.

---

## Quality Controls

### Data Validation Checks
1. **Market Cap Consistency:** MCAP ≈ shares × EPS × P/E (within 20%)
2. **Split Detection:** Check for splits between period_end and price_anchor
3. **Value Ranges:** Validate P/E < 1000, P/S < 100, P/B < 50
4. **Positive Values:** Ensure market_cap > 0, shares > 0

### Error Handling
```python
if market_cap_inconsistency > 20%:
    logger.warning(f"{symbol}: Market cap inconsistency (split issue?)")
    # Option 1: Exclude from calculation
    # Option 2: Use split-adjusted calculation
```

---

## Symbol Universe

### Primary Source: sector_mapping.json
- **Total Symbols:** 906
- **Sectors:** 11 (Technology, Healthcare, Financials, etc.)
- **Coverage:** Large-cap and mid-cap US equities

### Sector Classification
Symbols mapped to sectors via:
1. `symbol` table (ticker → Sector/Industry)
2. Fallback: `sector_mapping.json` (manual mapping)

---

## Verification & Validation

### Automated Checks
- ✓ No negative market caps or shares
- ✓ Top holdings match known values (NVDA, AAPL, etc.)
- ✓ Consistent year-over-year coverage
- ✓ No duplicate records

### Manual Verification
- Spot-check mega-cap companies
- Verify sector classifications
- Validate split adjustments

---

## Related Documentation

- **Data Quality:** [../insights/DATA_QUALITY.md](../insights/DATA_QUALITY.md)
- **Split Adjustment Guide:** [SPLITS.md](#splits-guide)
- **Tool Reference:** [TOOL_REFERENCE.md](./TOOL_REFERENCE.md)

---

*For questions or issues, see the troubleshooting section in TOOL_REFERENCE.md*

# Data Pipeline

**SEC filings → Company facts → Market data → Valuation**

---

## 🔄 Pipeline Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  SEC Filings    │ →  │  Company Facts  │ →  │  Processed Data │
│  (XBRL)         │    │  (Raw)          │    │  (Cleaned)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ↓                       ↓                       ↓
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Foreign Tables │ →  │  Market Data    │ →  │  Sector Multiples│
│  (tickerdata)   │    │  (Prices/Splits)│    │  (Aggregated)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 📊 Data Extraction

### Source: SEC Company Facts API

```
┌─────────────────────────────────────────────────────────────┐
│  Format:  XBRL (eXtensible Business Reporting Language)     │
│  Fields:  ticker, CIK, fiscal_year, fiscal_period          │
│           revenue, net_income, equity, EBITDA, etc.         │
└─────────────────────────────────────────────────────────────┘
```

### Processing Steps

```
┌─────────────────────────────────────────────────────────────┐
│  1. Clean raw data into sec_companyfacts_processed          │
│  2. Add market data from tickerdata                         │
│     • market_cap, shares_outstanding, close price           │
│  3. Apply quality filters                                   │
│     • Minimum market cap                                    │
│     • Positive values only                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 💹 Market Cap Calculation

### Formula

```
market_cap = price × shares_outstanding
```

### Price Anchor Strategy

```
┌─────────────────────────────────────────────────────────────┐
│  Anchor Date:  fiscal_period_end_date + 90 days             │
│  Rationale:   Allows time for 10-K filing + market digestion│
│  Split Adjust: Automatic split adjustment for price × shares│
└─────────────────────────────────────────────────────────────┘
```

### Timing Table

```
┌─────────────────────────────────────────────────────────────┐
│  Fiscal Year │  Period End  │  Price Anchor  │ Effective    │
├─────────────────────────────────────────────────────────────┤
│  FY2019      │  Dec 31, 2019│  ~Feb 13, 2020  │ Feb 2020    │
│  FY2020      │  Dec 31, 2020│  ~Mar 1, 2021   │ Mar 2021    │
│  FY2024      │  Dec 31, 2024│  ~Feb 14, 2025  │ Feb 2025    │
└─────────────────────────────────────────────────────────────┘
```

---

## ✂️ Split Adjustment

### Detection & Adjustment

```python
# Detect splits
splits = detect_splits(symbol, period_end, price_anchor_date)

# Calculate adjustment factor
if splits:
    adjustment = cumulative_split_ratio(splits)
    price_adjusted = price / adjustment  # reverse split for price
```

### Example: NVDA 4-for-1 Split (July 2021)

```
┌─────────────────────────────────────────────────────────────┐
│  Pre-split price:    $800                                   │
│  Post-split price:   $200                                   │
│  Split ratio:        4.0                                    │
│  Market cap:         Adjusts automatically                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Multiple Calculation

### Formulas

```
P/E  = market_cap / net_income       (if net_income > 0)
P/S  = market_cap / total_revenue    (if revenue > 0)
P/B  = market_cap / stockholders_equity (if equity > 0)
```

### Sector Aggregation

```
For each sector and fiscal year:
  1. Collect all companies with valid multiples
  2. Filter extreme values (5th-95th percentile)
  3. Calculate median of remaining values
```

---

## 🔍 Outlier Filtering

### Why Filter?

Extreme values distort sector medians:
- P/E > 1000x (near-zero earnings)
- P/S > 100x (anomalous revenue)
- P/B > 50x (distressed equity)

### Filtering Method

```python
# Filter to valid range
values = [m for m in multiples if m > 0 and m < max_threshold]

# Get percentiles
ranks = [percentile_rank(v) for v in values]

# Keep 5th-95th percentile
filtered = [v for v, r in zip(values, ranks) if 0.05 <= r <= 0.95]

# Calculate median
median = percentile_cont(0.5, filtered)
```

### Thresholds

```
┌─────────────────────────────────────────────────────────────┐
│  Multiple  │  Min  │  Max   │  Excludes                     │
├─────────────────────────────────────────────────────────────┤
│  P/E       │  0    │  1000x │  Losses, outliers             │
│  P/S       │  0    │  100x  │  Non-revenue, anomalies       │
│  P/B       │  0    │  50x   │  Distressed, anomalies       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Storage Schema

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

## ✅ Quality Controls

### Validation Checks

```
┌─────────────────────────────────────────────────────────────┐
│  ✓ Market Cap Consistency  │  MCAP ≈ shares × EPS × P/E    │
│  ✓ Split Detection         │  Check period_end → anchor    │
│  ✓ Value Ranges            │  P/E < 1000, P/S < 100        │
│  ✓ Positive Values         │  market_cap > 0, shares > 0   │
└─────────────────────────────────────────────────────────────┘
```

### Minimum Sample Size

```
Sectors must have ≥ 5 companies with valid multiples
```

### Error Handling

```python
if market_cap_inconsistency > 20%:
    logger.warning(f"{symbol}: Market cap inconsistency (split issue?)")
    # Option 1: Exclude from calculation
    # Option 2: Use split-adjusted calculation
```

---

## 📊 Symbol Universe

```
┌─────────────────────────────────────────────────────────────┐
│  Source:  sector_mapping.json                               │
│  Total:   906 symbols                                       │
│  Sectors: 11 (Technology, Healthcare, Financials, etc.)     │
│  Coverage: Large-cap and mid-cap US equities                │
└─────────────────────────────────────────────────────────────┘
```

### Sector Classification

```
1. symbol table (ticker → Sector/Industry)
2. Fallback: sector_mapping.json (manual mapping)
```

---

## 🔗 Related

- [Valuation Methods](valuation-methods.md) - Model assumptions
- [Sector Multiples](sector-multiples.md) - Comparison tool
- [Cache System](../developer/architecture.md#cache-system) - Data caching

# Data Pipeline

**SEC filings → Analysis → Results**

---

## 🔄 Pipeline Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  SEC Filings    │ →  │  Company Facts  │ →  │  Processed Data │
│  (XBRL)         │    │  (Raw)          │    │  (Cleaned)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ↓                       ↓                       ↓
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Market Data    │ →  │  Valuation      │ →  │  Results        │
│  (Prices/Splits)│    │  Models         │    │  (Cache)        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 📊 Market Cap Calculation

```
market_cap = price × shares_outstanding
```

### Price Anchor

```
fiscal_period_end_date + 90 days
```

### Split Adjustment

```python
splits = detect_splits(symbol, period_end, anchor_date)
adjustment = cumulative_split_ratio(splits)
price_adjusted = price / adjustment
```

---

## 🔍 Outlier Filtering

```
┌─────────────────────────────────────────────────────────────┐
│  Multiple  │  Min  │  Max   │  Excludes                     │
├─────────────────────────────────────────────────────────────┤
│  P/E       │  0    │  1000x │  Losses, outliers             │
│  P/S       │  0    │  100x  │  Non-revenue, anomalies       │
│  P/B       │  0    │  50x   │  Distressed, anomalies       │
└─────────────────────────────────────────────────────────────┘
```

### Filtering Method

```
1. Collect valid multiples (positive values)
2. Filter to 5th-95th percentile
3. Calculate median
```

---

## ✅ Quality Controls

```
✓ Market Cap Consistency
✓ Split Detection
✓ Value Ranges
✓ Positive Values
```

---

## 🔗 Related

- [Valuation Methods](valuation-methods.md) - Model assumptions
- [Sector Multiples](sector-multiples.md) - Comparison

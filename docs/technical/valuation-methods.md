# Valuation Methods

**Multi-model sector-weighted valuation framework**

---

## 🎯 Core Philosophy

```
┌─────────────────────────────────────────────────────────────┐
│  Multi-Model Approach → Sector-Specific → Conservative Bias  │
│                                                         │
│  • No single method is reliable                             │
│  • Different business models need different approaches      │
│  • Err toward conservative when uncertain                   │
│  • Transparency over false precision                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Model Weighting by Sector

### Technology

```
┌─────────────────────────────────────────────────────────────┐
│  P/E: 55%              │  EV/EBITDA: 45%                   │
│  Growth-focused        │  Cash flow focus                  │
└─────────────────────────────────────────────────────────────┘
```

### Semiconductors

```
┌─────────────────────────────────────────────────────────────┐
│  P/E: 40%              │  EV/EBITDA: 60%                   │
│  Cycle-aware           │  Margin normalization             │
└─────────────────────────────────────────────────────────────┘
```

### Financials (Banks)

```
┌─────────────────────────────────────────────────────────────┐
│  P/E: 30%              │  P/B: 65%             │  EV/EBITDA: 5% │
│  Earnings quality      │  ROE-driven          │  Tangible      │
└─────────────────────────────────────────────────────────────┘
```

### Insurance

```
┌─────────────────────────────────────────────────────────────┐
│  P/E: 30%              │  P/B: 65%             │  EV/EBITDA: 5% │
│  Underwriting disc.    │  Combined ratio      │  Book value    │
└─────────────────────────────────────────────────────────────┘
```

### Healthcare

```
┌─────────────────────────────────────────────────────────────┐
│  P/E: 50%              │  EV/EBITDA: 40%       │  P/S: 10%    │
│  Earnings stability    │  Cash flow           │  Pipeline opt.│
└─────────────────────────────────────────────────────────────┘
```

---

## 📈 Growth Profiles & Base P/E

```
┌──────────────────────────────────────────────────────────────┐
│  Profile          │  Growth   │  Base P/E  │  PEG Target    │
├──────────────────────────────────────────────────────────────┤
│  Hyper-Growth     │  >50%     │  35x       │  0.8          │
│  High-Growth      │  25-50%   │  30x       │  0.9          │
│  Moderate-Growth  │  10-25%   │  25x       │  1.0          │
│  Low-Growth       │  0-10%    │  20x       │  1.2          │
│  Stable           │  ~0%      │  18x       │  —            │
│  Declining        │  <0%      │  12x       │  —            │
└──────────────────────────────────────────────────────────────┘
```

### Sustainability Discounts

```
┌─────────────────────────────────────────────────────────────┐
│  Hyper-Growth: 15% discount  │  >50% growth rarely sustains│
│  High-Growth: 10% discount   │  Deceleration to 15-25%     │
│  Moderate-Growth: 5% discount│  Above-market competition   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏦 Sector-Specific Logic

### Banks (P/B by ROE)

```
┌─────────────────────────────────────────────────────────────┐
│  ROE ≥ 15%      │  P/B 1.75x  │  Exceptional profitability  │
│  ROE 10-15%     │  P/B 1.25x  │  Good bank                  │
│  ROE < 10%      │  P/B 0.90x  │  Challenged                 │
└─────────────────────────────────────────────────────────────┘
```

### Insurance (Combined Ratio → P/B)

```
┌─────────────────────────────────────────────────────────────┐
│  Combined Ratio  │  Quality     │  P/B Multiple             │
├─────────────────────────────────────────────────────────────┤
│  <90%            │  Excellent   │  1.3-1.5x                 │
│  90-95%          │  Good        │  1.1-1.3x                 │
│  95-100%         │  Acceptable  │  0.9-1.1x                 │
│  100-105%        │  Weak        │  0.7-0.9x                 │
│  >105%           │  Poor        │  <0.7x                    │
└─────────────────────────────────────────────────────────────┘
```

### REITs (FFO by Property Type)

```
┌─────────────────────────────────────────────────────────────┐
│  Property Type           │  FFO Multiple                   │
├─────────────────────────────────────────────────────────────┤
│  Data Centers            │  20-24x                         │
│  Industrial/Logistics    │  22-25x                         │
│  Cell Towers             │  22-26x                         │
│  Sunbelt Apartments      │  18-20x                         │
│  Healthcare              │  14-16x                         │
│  Office (Class A)        │  12-14x                         │
│  Regional Malls          │  6-10x                          │
└─────────────────────────────────────────────────────────────┘
```

### Biotech (Pipeline Phase Probabilities)

```
┌─────────────────────────────────────────────────────────────┐
│  Phase           │  Approval Probability                   │
├─────────────────────────────────────────────────────────────┤
│  Preclinical     │  5%                                     │
│  Phase 1         │  10%                                    │
│  Phase 2         │  15%                                    │
│  Phase 3         │  50%                                    │
│  Filed NDA       │  85%                                    │
│  Approved        │  100%                                   │
└─────────────────────────────────────────────────────────────┘
```

### Semiconductors (Cycle Position)

```
┌─────────────────────────────────────────────────────────────┐
│  Cycle Position   │  Margin    │  Valuation Adjustment      │
├─────────────────────────────────────────────────────────────┤
│  Peak             │  35%       │  -20% discount             │
│  Peak→Normal      │  Normalizing│  -10% discount             │
│  Normal           │  25%       │  0% (baseline)             │
│  Normal→Trough    │  Declining │  +5% premium               │
│  Trough           │  15%       │  +15% premium              │
└─────────────────────────────────────────────────────────────┘
```

**Cycle Detection Signals:**
- Inventory days > 15% of sales → likely peak
- Inventory days < 8% of sales → likely trough
- Book-to-bill > 1.15 → expansion
- Book-to-bill < 0.85 → contraction

---

## 💰 DCF Parameters

```
┌─────────────────────────────────────────────────────────────┐
│  Parameter               │  Default Value                   │
├─────────────────────────────────────────────────────────────┤
│  Risk-Free Rate          │  10Y Treasury                    │
│  Equity Risk Premium     │  5.5%                            │
│  Terminal Growth         │  3.0% (sector-adjusted)          │
│  Projection Period       │  5 years                         │
└─────────────────────────────────────────────────────────────┘
```

### Sector Terminal Growth

```
┌─────────────────────────────────────────────────────────────┐
│  Technology/Semiconductors │  4.0%  │  Secular tailwinds     │
│  Healthcare                │  4.0%  │  Aging demographics    │
│  Defense                   │  2.5%  │  Gov spending limits   │
│  Utilities/Energy          │  2.0%  │  Regulated/commodity   │
│  General                   │  3.0%  │  GDP proxy             │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Model Applicability Rules

```
┌─────────────────────────────────────────────────────────────┐
│  Model       │  Required                          │  Condition│
├─────────────────────────────────────────────────────────────┤
│  P/E         │  Net Income > 0                   │  Positive │
│  EV/EBITDA   │  EBITDA > 0                       │  Positive │
│  DCF         │  FCF available                   │  4+ qtrs   │
│  GGM         │  Dividends + NI > 0              │  40% payout│
│  P/S         │  Revenue > 0                     │  Any       │
│  P/B         │  Book Value > 0                  │  Positive  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Data Quality Tiers

```
┌─────────────────────────────────────────────────────────────┐
│  Quality      │  Min Quarters  │  Max Missing  │  Penalty   │
├─────────────────────────────────────────────────────────────┤
│  Excellent    │  12            │  0            │  0%        │
│  Good         │  8             │  1            │  0%        │
│  Fair         │  4             │  2            │  -10%      │
│  Poor         │  2             │  4            │  -25%      │
│  Insufficient │  <2            │  >4           │  Exclude   │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚡ Known Limitations

**NOT Implemented:**
- Earnings quality analysis (non-recurring items)
- Macro adjustments (interest rates, credit cycle)
- Competitive moat scoring
- Management quality factors
- Biotech comparable deals (15% weight listed)
- Confidence intervals (point estimates only)

**Sector Caps:**
- Technology: 100x P/E max
- Healthcare: 60x P/E max
- Financials: 25x P/E max

---

## 🔗 Related

- [Sector Multiples](sector-multiples.md) - Multiple comparison
- [Architecture](../developer/architecture.md) - System design
- [Development](../developer/development.md) - Contributing

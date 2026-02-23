# Historical Sector Analysis - Complete Guide

**Generated:** February 22, 2026

---

## 🎯 Goal

Create a comprehensive historical timeline visualization showing:
- **X-axis:** Fiscal Year (2015-2024)
- **Y-axis:** Multiple value (P/E, P/S, P/B, EV/EBITDA)
- **Lines:** Sector medians (colored, different line styles)
- **Points:** Representative stocks (top 10 per sector, sized by market cap)
- **4 separate charts:** One for each metric

---

## 📋 Step 1: Calculate Historical Multiples

### Quick Command (All years at once)
```bash
source ~/.investigator/env
source .venv/bin/activate

# Calculate for all years (2015-2024)
# This will take 30-60 minutes
for year in {2015..2024}; do
    echo "Calculating FY$year..."
    investigator sector-multiples historical --fiscal-year $year --store
done

# Or run the automated script
python3 scripts/generate_historical_sector_analysis.py
```

### Progress Monitoring
```bash
# Check what's been calculated
python3 << 'EOF'
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database")
df = pd.read_sql("""
    SELECT fiscal_year, COUNT(DISTINCT group_name) as sectors
    FROM sector_multiples_history
    WHERE group_type = 'sector'
    GROUP BY fiscal_year
    ORDER BY fiscal_year DESC
""", engine)
print(df.to_string(index=False))
EOF
```

---

## 📊 Step 2: Generate Visualization

After calculation completes, generate the visualization:

```bash
python3 scripts/generate_historical_timeline.py
```

This will create:
- **docs/assets/visualizations/sector_timeline_historical.html**
- Interactive Plotly charts with:
  - Toggleable sector lines
  - Zoom/pan capabilities
  - Hover tooltips
  - Export to PNG functionality

---

## 🎨 Visualization Design

### Chart Layout (4 Charts)

```
┌─────────────────────────────────────────────┐
│  P/E Multiple Timeline (2015-2024)          │
│  ┌──────────────────────────────────────┐   │
│  │ 45┤                                 │   │
│  │ 40┤  ●●● Technology               │   │
│  │ 35┤  ── Finance                  │   │
│  │ 30┤  ─ ─ Healthcare              │   │
│  │ 25┤  - - - Consumer Disc.         │   │
│  │ 20┤                            │   │
│  │ 15┤                            │   │
│  │ 10┤                            │   │
│  │  5┤                            │   │
│  │  └───────────────────────────────│   │
│  └──────────────────────────────────────┘   │
│  ▔─────────────────────────────────────────┘
│  X: Fiscal Year    Y: P/E Multiple          │
└─────────────────────────────────────────────┘
```

### Line Styles (Sector Distinction)

| Sector | Line Style | Color |
|--------|-----------|-------|
| Technology | Solid | Blue |
| Health Care | Dashed | Purple |
| Finance | Dotted | Green |
| Consumer Disc. | Dash-dot | Orange |
| Telecom. | Long Dash | Red |
| Industrials | Solid | Yellow |

### Point Sizes (Market Cap)

| Market Cap | Point Size | Symbol |
|------------|------------|--------|
| Mega ($200B+) | 15px | ● |
| Large ($10-200B) | 10px | ● |
| Mid ($2-10B) | 7px | ● |
| Small (<$2B) | 4px | ● |

---

## 🚀 Commands

### Option A: Full Automated (Recommended)
```bash
# Calculate all historical data (30-60 min)
python3 scripts/generate_historical_sector_analysis.py
```

### Option B: Manual Step-by-Step
```bash
# 1. Calculate each year
for year in 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024; do
    investigator sector-multiples historical --fiscal-year $year --store
done

# 2. Generate visualization
python3 scripts/generate_historical_timeline.py
```

### Option C: Quick Test (Single Year)
```bash
# Test with one year first
investigator sector-multiples historical --fiscal-year 2024 --store

# Verify it worked
python3 << 'EOF'
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine("postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database")
df = pd.read_sql("SELECT * FROM sector_multiples_history WHERE fiscal_year=2024 LIMIT 5", engine)
print(df)
EOF
```

---

## 📦 Data Requirements

### Already Available ✅

From your batch job, you already have data for:
- **2015-2024:** Full coverage
- **4,605 symbols** in FY2024 alone
- **10 major sectors** represented

### EV/EBITDA Consideration

EV/EBITDA requires:
1. Enterprise Value (Market Cap + Debt - Cash)
2. EBITDA (Operating Income + Depreciation + Amortization)

**Status:** May not be available for all symbols. The visualization will handle missing data gracefully.

---

## 📊 Expected Output

### Sector Coverage (10 Years)

| Sector | Expected Years | Sample Size Range |
|--------|---------------|------------------|
| Technology | 2015-2024 | 150-600 symbols |
| Health Care | 2015-2024 | 100-500 symbols |
| Finance | 2015-2024 | 140-450 symbols |
| Consumer Disc. | 2015-2024 | 170-450 symbols |
| Industrials | 2015-2024 | 110-400 symbols |
| Consumer Staples | 2015-2024 | 35-150 symbols |
| Energy | 2015-2024 | 40-200 symbols |
| Utilities | 2015-2024 | 50-200 symbols |
| Real Estate | 2015-2024 | 40-200 symbols |
| Telecom. | 2015-2024 | 20-100 symbols |

### Timeline Coverage

```
2015: Post-Financial crisis recovery
2016: Moderate growth
2017: Bull market acceleration
2018: Volatility increase
2019: Trade war tensions
2020: COVID crash & recovery
2021: Stimulus-driven growth
2022: Rate hike cycle begins
2023: Rate hikes continue
2024: Market normalization
```

---

## ⚡ Performance Estimates

| Operation | Time | Notes |
|------------|------|-------|
| Calculate 1 year | 2-4 min | Per sector |
| Calculate all 10 years | 30-60 min | Full automation |
| Generate visualization | 5-10 sec | Plotly rendering |
| **Total** | **~1 hour** | Mostly unattended |

---

## 🎨 Visualization Features

### Interactive Capabilities
- **Zoom:** Double-click to reset, scroll to zoom
- **Pan:** Click and drag
- **Hover:** Shows exact values and sector info
- **Toggle sectors:** Click legend to show/hide
- **Export:** Download as PNG

### Visual Elements
- **Sector lines:** Different colors + line styles for accessibility
- **Representative stocks:** Top 10 per sector (larger bubbles = larger market cap)
- **Confidence intervals:** Shaded areas (optional)
- **Annotations:** Key events (COVID, rate changes, etc.)

---

## 🔧 Troubleshooting

### Issue: "No data for FY2015"
```
Solution: Some years may have insufficient data (<5 symbols per sector)
Check: investigator sector-multiples historical --fiscal-year 2015
```

### Issue: "Calculation is slow"
```
Solution: This is expected due to:
- 10 years × 10 sectors = 100 calculations
- Each calculation queries thousands of symbols
- Market cap adjustments require additional joins

Optimization: Run overnight or use --years flag for specific years
```

### Issue: "EV/EBITDA chart is empty"
```
Reason: EBITDA data may not be available for all sectors/years
Solution: Focus on P/E, P/S, P/B which are more complete
```

---

## 📝 Next Steps After Generation

1. **Review the visualization** - Open the HTML file in browser
2. **Verify sector coverage** - Ensure all sectors are present
3. **Update insights docs** - Add findings to assets/insights/
4. **Share with stakeholders** - Link from README.md

---

## 🎯 Success Criteria

✅ All 10 sectors represented
✅ 10 years of data (2015-2024)
✅ 4 metric charts (P/E, P/S, P/B, EV/EBITDA)
✅ Interactive Plotly visualization
✅ Representative stocks (top 10 per sector)
✅ Line styles distinguishable
✅ Color-coded for accessibility

---

*For questions or issues, refer to:*
- *Methodology:* `docs/assets/technical/METHODOLOGY.md`
- *Operations:* `docs/reference/OPERATIONS_RUNBOOK.md`
- *Tool Reference:* `docs/assets/technical/TOOL_REFERENCE.md`

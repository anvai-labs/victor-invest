# Historical Sector Timeline - Quick Start Guide

## 🎯 Objective

Generate a comprehensive historical visualization showing sector multiples evolution over **10 years (2015-2024)** with:
- **X-axis:** Fiscal Year
- **Y-axis:** Multiple value
- **Sector lines:** Colored, dashed/dotted for distinction
- **Representative stocks:** Top 10 per sector (sized by market cap)

---

## 📋 Step 1: Calculate Historical Multiples

### Option A: Automated (Recommended - ~1 hour)

```bash
source ~/.investigator/env
source .venv/bin/activate

# Calculate for all years (2015-2024)
for year in 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024; do
    echo "📊 Calculating FY$year..."
    investigator sector-multiples historical --fiscal-year $year --store
    echo "  ✓ Completed FY$year"
    echo ""
done

echo "✅ All years calculated!"
```

**Estimated time:** 1 hour (unattended)

### Option B: Test Single Year First

```bash
# Test with 2024 first (you already have this data)
investigator sector-multiples historical --fiscal-year 2024 --store

# Verify
python3 << 'EOF'
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine("postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database")
df = pd.read_sql("SELECT * FROM sector_multiples_history WHERE fiscal_year=2024 LIMIT 3", engine)
print(df)
EOF
```

**If working, proceed with Option A**

---

## 📊 Step 2: Generate Visualization

```bash
# After all years are calculated
python3 scripts/generate_historical_timeline.py
```

**Output:** `docs/assets/visualizations/sector_timeline_historical.html`

---

## 🎨 Visualization Features

### 4 Charts Generated

1. **P/E Multiple Timeline**
   - Shows price-to-earnings evolution
   - Identify overvalued/undervalued periods

2. **P/S Multiple Timeline**
   - Sales multiple trends
   - Growth vs value cycles

3. **P/B Multiple Timeline**
   - Book value trends
   - Market cycles reflected

4. **Key Events** (annotated)
   - 2020: COVID crash
   - 2022: Rate hikes begin
   - 2024: Market normalization

### Interactive Features

- **Zoom:** Scroll/pinch to zoom
- **Pan:** Click and drag to move
- **Toggle:** Click legend to show/hide sectors
- **Hover:** Exact values and sector info
- **Export:** Save as PNG

### Visual Design

| Sector | Color | Line Style |
|--------|-------|------------|
| Technology | Blue | Solid |
| Health Care | Purple | Dashed |
| Finance | Green | Dotted |
| Consumer Disc. | Orange | Dash-dot |
| Telecommunications | Red | Long Dash |
| Industrials | Yellow | Solid |
| Consumer Staples | Gray | Dashed |
| Energy | Purple | Dotted |
| Utilities | Light Blue | Dash-dot |
| Real Estate | Pink | Long Dash |

---

## 📈 Expected Data Coverage

| Year | Symbols (Est.) | Quality |
|------|----------------|----------|
| 2024 | 4,605 | ✅ Excellent |
| 2023 | 5,063 | ✅ Excellent |
| 2022 | 5,337 | ✅ Excellent |
| 2021 | 5,095 | ✅ Excellent |
| 2020 | 4,173 | ✅ Good (COVID volatility) |
| 2019 | 3,790 | ✅ Good |
| 2018 | 3,569 | ✅ Good |
| 2017 | 3,306 | ✅ Good |
| 2016 | 3,103 | ✅ Good |
| 2015 | 2,976 | ✅ Good |

**Total:** ~44,000 company-year records

---

## ⚡ Quick Start (All Commands)

```bash
# 1. Setup
source ~/.investigator/env
source .venv/bin/activate

# 2. Calculate historical data (1 hour, unattended)
for year in {2015..2024}; do
    investigator sector-multiples historical --fiscal-year $year --store
done

# 3. Generate visualization
python3 scripts/generate_historical_timeline.py

# 4. Open in browser
open docs/assets/visualizations/sector_timeline_historical.html
```

---

## 🔍 Progress Monitoring

### Check What's Been Calculated

```bash
python3 << 'EOF'
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database")

# Check sector_multiples_history table
df = pd.read_sql("""
    SELECT
        fiscal_year,
        COUNT(DISTINCT group_name) as sectors,
        COUNT(*) as records
    FROM sector_multiples_history
    WHERE group_type = 'sector'
    GROUP BY fiscal_year
    ORDER BY fiscal_year DESC
""", engine)

print("\n📅 Calculated Years:")
print(df.to_string(index=False))

# Check total progress
total_years = len(df)
total_expected = 10
progress = (total_years / total_expected) * 100

print(f"\n📊 Progress: {total_years}/10 years ({progress:.0f}%)")
EOF
```

### Real-time Monitoring

```bash
# Watch for new records being added
watch -n 30 'source .venv/bin/activate && python3 -c "
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine(\"postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database\")
df = pd.read_sql(\"SELECT COUNT(*) as count FROM sector_multiples_history\", engine)
print(f\"Records: {df['count'].iloc[0]:,}\")
"'
```

---

## 🐛 Troubleshooting

### Error: "No data for fiscal year XXXX"

**Cause:** Insufficient symbols (<5 per sector) for that year

**Solution:**
- This is expected for older years (2004-2010)
- Skip those years or increase min_samples parameter
- Focus on 2015-2024 which has good coverage

### Error: "relation does not exist"

**Cause:** `sector_multiples_history` table doesn't exist

**Solution:** Run this first:
```bash
psql -h dataserver1.singh.local -U investigator -d sec_database -f scripts/create_sector_multiples_table.sql
```

### Visualization is blank

**Cause:** No data in sector_multiples_history table

**Solution:** Complete Step 1 first to calculate historical data

---

## 📊 Expected Output

### Timeline Analysis You'll See

**Pre-COVID (2015-2019):**
- Generally moderate multiples
- Gradual P/E expansion
- Tech sector outperformance

**COVID Bubble (2020):**
- Sharp drop then recovery
- Multiple compression
- Divergent sector performance

**Rate Hike Era (2022-2024):**
- Multiple compression
- Sector rotation
- Value vs Growth divergence

---

## 📝 Next Steps After Generation

1. ✅ **Review the timeline** - Open HTML file in browser
2. 📊 **Update insights** - Document findings in `docs/assets/insights/`
3. 🔄 **Update summary** - Modify `SECTOR_ANALYSIS_2015_2024.md`
4. 📤 **Share** - Link from main README

---

## 🎯 Success Criteria

- ✅ All 10 years calculated (2015-2024)
- ✅ All major sectors represented
- ✅ 4 charts generated (P/E, P/S, P/B, EV/EBITDA)
- ✅ Interactive Plotly visualization
- ✅ Key events annotated
- ✅ Accessible design (color + line style distinction)

---

## 📚 Related Files

- **Visualization:** `docs/assets/visualizations/sector_timeline_historical.html`
- **Guide:** `docs/assets/visualizations/HISTORICAL_TIMELINE_GUIDE.md`
- **Methodology:** `docs/assets/technical/METHODOLOGY.md`
- **Tool Reference:** `docs/assets/technical/TOOL_REFERENCE.md`

---

*Generated: February 22, 2026*

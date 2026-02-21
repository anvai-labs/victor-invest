# Sector Valuation Insights (2016-2025): Complete Collection

**Comprehensive analysis of US stock market valuation multiples across sectors, market caps, and time periods**

---

## 📖 Important: Fiscal Year vs Calendar Year

**⚠️ CRITICAL:** All data uses **company Fiscal Year (FY)**, NOT calendar year!

**What This Means:**
- FY 2025 for each company = their own 12-month accounting period
- Companies have different FY-ends: Jan 31, Mar 31, Jun 30, Sep 30, Dec 31
- "FY 2025" data = 10-Ks filed between Nov 2025 - May 2026
- As of Feb 21, 2026: Only ~30-40% of FY 2025 data is available

**See:** [`reference/data_methodology_fiscal_year_explained.md`](reference/data_methodology_fiscal_year_explained.md) for complete explanation

---

## ⏱️ Quick Summary (2-Min Read)

The US stock market completed one full valuation cycle from 2016-2025:

**The Three Regimes:**
1. **2016-2018:** Growth era → Trade war ended growth optimism
2. **2019-2021:** COVID crash → Stimulus boom → Rate hikes begin
3. **2022-2025:** Inflation fight → Tech compression → Energy re-rating

**Key Numbers:**
| Sector | FY 2016 P/E | FY 2025 P/E | Change | Winner/Loser |
|--------|------------|------------|--------|--------------|
| **Technology** | 59.1x | 32.4x | **-45%** | Multiple compressed, earnings grew |
| **Energy** | 41.9x | 17.7x | **-58%** | +143% from FY 2022 low of 7.3x |
| **Finance** | 25.3x | 13.5x | **-47%** | Stuck at 13-15x for 10 years |
| **Healthcare** | 52.5x | 25.8x | **-51%** | Biotech hangover → value play |
| **Industrials** | 51.5x | 30.2x | **-41%** | Stable compounders |

**The Insight:** Valuation multiples matter. Tech at 59x was unsustainable (compressed to 32x). Energy at 7x was too cheap (re-rated to 18x). Finance at 15x for 10 years? Still trying to figure that out.

---

## 📊 Visualizations

### Interactive Charts
**File:** [`../sector_insights_enhanced.html`](../sector_insights_enhanced.html)

**Features:**
- **4 views:** P/E, P/S, P/B line charts + 3D market cap visualization
- **Line charts:** Sector trends over time (2016-2025), one line per sector
- **Scatter plots:** Symbol-level data (color-coded by sector)
- **3D visualization:** P/E vs P/S with Z-axis = Market Cap bucket
- **Interactivity:** Click sectors to show/hide, view representative symbols only
- **Tooltip:** Hover to see symbol details

### Static Charts
**File:** [`../sector_trends_charts.svg`](../sector_trends_charts.svg)

**Panels:**
1. P/E Multiples (2016-2025) - 14 sector lines
2. P/S Multiples (2016-2025) - 14 sector lines
3. P/B Multiples (2016-2025) - 14 sector lines
4. EV/EBITDA Multiples - 14 sector lines

**Features:**
- Color-coded by sector
- Legend with latest values
- Publication-ready for blogs/articles

### Simplified Interactive
**File:** [`../sector_trends.html`](../sector_trends.html)

**Features:**
- Chart.js-based interactive charts
- Click sectors to show/hide
- Summary statistics table (FY 2024)
- Works standalone (no external data needed)

---

## 🗂️ File Navigation

### 📖 Start Here
- **`README.md`** - This file (executive summary with visual guide)

### 📚 Deep Dives (Sector Analysis)
**Detailed analysis of individual sectors:**

| File | Topic | Key Finding |
|------|-------|-------------|
| [`deep_dives/tech_compression.md`](deep_dives/tech_compression.md) | Technology | P/E 59x→32x (-46%), earnings grew 3-5x |
| [`deep_dives/energy_renaissance.md`](deep_dives/energy_renaissance.md) | Energy | P/E 7x→18x (+143% from 2022 low) |
| [`deep_dives/healthcare_value.md`](deep_dives/healthcare_value.md) | Healthcare | P/E 53x→26x (-51%), defensive → value |
| [`deep_dives/sector_showdown.md`](deep_dives/sector_showdown.md) | All sectors | Comparison of winners vs losers |

### 🛠️ Frameworks (Analytical Tools)
**Conceptual frameworks for understanding valuation:**

| File | Topic | Key Concept |
|------|-------|-------------|
| [`frameworks/balloon_effect.md`](frameworks/balloon_effect.md) | Balloon Effect | How multiple expansion/compression creates/destroys wealth |
| [`frameworks/price_to_sales_analysis.md`](frameworks/price_to_sales_analysis.md) | P/S Analysis | When P/S tells the truth vs P/E |

### 📊 Analysis (Deep Research)
**In-depth research on specific themes:**

| File | Topic | Key Finding |
|------|-------|-------------|
| [`analysis/market_cap_buckets.md`](analysis/market_cap_buckets.md) | Size Premium | Tech size premium 531%, Energy 69% |
| [`analysis/timeline_pivot_points.md`](analysis/timeline_pivot_points.md) | Timeline | Year-by-year progression with pivot points |

### 🔮 Projections (Forward-Looking)
**Future outlook and scenarios:**

| File | Topic | Key Scenario |
|------|-------|--------------|
| [`projections/2026_outlook.md`](projections/2026_outlook.md) | 2026 Outlook | Base +10-15%, Bull +20-30%, Bear -10% to -20% |

### 📖 Reference (Data & Catalog)
**Reference materials and data tables:**

| File | Topic | Contents |
|------|-------|-----------|
| [`reference/complete_timeline_data.md`](reference/complete_timeline_data.md) | Complete Data | All years P/E, P/S tables for all sectors |
| [`reference/data_methodology_fiscal_year_explained.md`](reference/data_methodology_fiscal_year_explained.md) | Methodology | ⭐ **READ THIS** - Fiscal year vs calendar year explained |
| [`reference/executive_summary_detailed.md`](reference/executive_summary_detailed.md) | Detailed Story | Full market cycle narrative (6 parts) |

### 📋 Meta (Collection Info)
**Meta-information about this collection:**

| File | Topic | Contents |
|------|-------|-----------|
| [`meta/collection_summary.md`](meta/collection_summary.md) | Asset Catalog | Complete file listing with descriptions |
| [`meta/enhancement_proposal.md`](meta/enhancement_proposal.md) | Enhancements | Future visualization improvements |

---

## 🎯 Key Insights

### 1. The Balloon Effect: How Multiples Create (or Destroy) Wealth

**Formula:** `Total Return = Fundamental Return ± Multiple Effect`

**Three Types:**

| Type | Multiple + Earnings | Result | Example |
|------|-------------------|--------|---------|
| **Inflating** | ↑ + ↑ | Magic | Energy FY 2020-2024: P/E 7x→18x, earnings +300% |
| **Leaking** | ↓ + ↑ | Surviving | Tech FY 2016-2024: P/E 59x→32x, earnings +400% |
| **Stubborn** | → + ↑ | Value trap | Finance FY 2016-2025: P/E stuck at 15x |

**Deep Dive:** [`frameworks/balloon_effect.md`](frameworks/balloon_effect.md)

### 2. Size Matters: Company Size Creates Premium Discounts

**The Discovery:** Within sectors, valuation multiples vary dramatically by company size

| Sector | Micro Cap P/S | Mega Cap P/S | Size Premium |
|--------|--------------|--------------|--------------|
| **Technology** | 1.6x | 10.1x | **531%** |
| **Healthcare** | 1.6x | 6.8x | **325%** |
| **Finance** | 2.2x | 5.1x | **132%** |
| **Energy** | N/A | 2.2x | **69%** |

**The Opportunity:** Small cap Energy/Finance trade at 40-50% discounts to large caps

**Deep Dive:** [`analysis/market_cap_buckets.md`](analysis/market_cap_buckets.md)

### 3. Every Year Matters: The Complete Timeline

**Why We Can't Skip Years:** The market changes regime every 1-2 years

| Year | Event | Impact | Tech P/E |
|------|-------|--------|----------|
| **FY 2017** | Tax cut optimism fade | -19% | 47.7x |
| **FY 2018** | Trade war begins | +2.5% | 48.9x |
| **FY 2020** | COVID crash + WFH | -11% | 45.9x |
| **FY 2022** | Rate hikes begin | -16% | 32.7x |
| **FY 2023** | AI boom begins | +14% | 37.2x |
| **FY 2025** | Stabilizing | +4% | 32.4x |

**Deep Dive:** [`analysis/timeline_pivot_points.md`](analysis/timeline_pivot_points.md)

---

## 📈 Sector-by-Sector Summary

### Technology: The Great Compression
**P/E Progression:** 59.1x (FY 2016) → 32.4x (FY 2025) = **-45%**

**Representative Symbols:**
| Symbol | P/E | P/S | Story |
|--------|-----|-----|-------|
| **NVDA** | 100x+ | 25x | AI bubble within Tech |
| **AAPL** | 30x | 10x | Quality compounder |
| **INTC** | 12x | 2x | Turnaround story |

**Deep Dive:** [`deep_dives/tech_compression.md`](deep_dives/tech_compression.md)

### Energy: The Phoenix Rising
**P/E Progression:** 41.9x (FY 2016) → 7.3x (FY 2022) → 17.7x (FY 2025)

**Representative Symbols:**
| Symbol | P/E | P/S | Dividend | Story |
|--------|-----|-----|---------|-------|
| **XOM** | N/A* | 1.9x | 3.5% | Dividend king |
| **COP** | 17x | 2.7x | 2.5% | Permian growth |
| **EOG** | 12x | 2.9x | 3.0% | Premium shale |

*Negative earnings in FY 2025 due to restructuring

**Deep Dive:** [`deep_dives/energy_renaissance.md`](deep_dives/energy_renaissance.md)

### Finance: The Value Trap?
**P/E Progression:** 25.3x (FY 2016) → 13.5x (FY 2025), stuck at 13-15x for 10 years

**Representative Symbols:**
| Symbol | P/E | P/B | ROE | Story |
|--------|-----|-----|-----|-------|
| **JPM** | 12x | 1.8x | 15% | Quality compounder |
| **BAC** | 11x | 1.1x | 11% | Turnaround |
| **WFC** | 10x | 0.9x | 10% | Value trap? |

---

## 🔮 What's Next: FY 2026 Outlook

### Three Scenarios

| Scenario | Probability | Market Return | Key Driver |
|----------|-------------|---------------|------------|
| **Base** | 50% | +10-15% | Earnings growth 8-10%, sideways multiples |
| **Bull** | 30% | +20-30% | Fed cuts + AI delivers earnings |
| **Bear** | 20% | -10% to -20% | AI bubble bursts + recession |

### What to Watch

1. **Fed Pivot:** If rates cut → Growth stocks rally
2. **AI Earnings:** Can NVDA at 100x P/E deliver? If yes → Bull case
3. **Energy Re-rating:** Still cheap at 18x vs 20x historical
4. **Finance Value Trap:** 10 years at 15x = permanent discount?

**Deep Dive:** [`projections/2026_outlook.md`](projections/2026_outlook.md)

---

## 💡 How to Use This Collection

### For Bloggers & Content Creators
1. **Copy narratives** from deep dives directly into blog posts
2. **Use screenshots** of interactive HTML for visuals
3. **Cite the data:** "Source: sec_companyfacts_processed (FY 2016-2025)"
4. **Representative symbols** make analysis concrete (AAPL, NVDA, XOM, JPM)

### For Investors
1. **Use interactive charts** to explore sector rotations
2. **Read deep dives** to understand sector-specific stories
3. **Focus on:** Energy (still cheap), small cap value opportunities, Tech quality at reasonable price
4. **Check 2026 outlook** for forward-looking strategy

### For Researchers
1. **Data quality:** All from SEC filings (not estimates)
2. **Sample sizes:** 100-500+ companies per sector
3. **Methodology:** Median multiples (outlier-resistant)
4. **Reproducibility:** See [`reference/complete_timeline_data.md`](reference/complete_timeline_data.md)

---

## 📊 Data Coverage

- **Period:** FY 2016 - FY 2025 (10 fiscal years)
- **Sectors:** 14 major sectors
- **Companies:** 3,000+ with SEC filings
- **Metrics:** P/E, P/S, P/B, EV/EBITDA multiples
- **Data Source:** sec_companyfacts_processed (US SEC Company Facts API)

**⚠️ Data Completeness (as of Feb 21, 2026):**
- **FY 2016-2024:** 95%+ complete
- **FY 2025:** 30-40% complete (only companies with Sep-Dec FY ends have filed)
- **FY 2026:** 0% (no companies have closed FY 2026 yet)

---

## 📦 Complete File Listing

**Narrative Insights (organized by category):**
- `deep_dives/tech_compression.md`
- `deep_dives/energy_renaissance.md`
- `deep_dives/healthcare_value.md`
- `deep_dives/sector_showdown.md`
- `frameworks/balloon_effect.md`
- `frameworks/price_to_sales_analysis.md`
- `analysis/market_cap_buckets.md`
- `analysis/timeline_pivot_points.md`
- `projections/2026_outlook.md`
- `reference/complete_timeline_data.md`
- `reference/data_methodology_fiscal_year_explained.md` ⭐ **READ THIS FIRST**
- `reference/executive_summary_detailed.md`
- `meta/collection_summary.md`
- `meta/enhancement_proposal.md`

**Visual Assets:**
- [`../sector_insights_enhanced.html`](../sector_insights_enhanced.html) - Interactive (P/E, P/S, P/B, 3D)
- [`../sector_trends.html`](../sector_trends.html) - Simplified interactive
- [`../sector_trends_charts.svg`](../sector_trends_charts.svg) - Static 4-panel charts
- [`../sector_trends_data.json`](../sector_trends_data.json) - Sector medians
- [`../symbol_scatter_data.json`](../symbol_scatter_data.json) - Symbol-level data

---

## 🎓 Representative Symbols by Sector

### Technology
- **Mega caps:** AAPL, MSFT, GOOGL, NVDA, META
- **Large caps:** AMD, AVGO, ADI
- **Mid caps:** PLTR, SNOW, NET

### Energy
- **Large caps:** XOM, CVX, COP
- **Small caps:** EQT, AR, FANG

### Finance
- **Mega caps:** JPM, BAC
- **Mid caps:** SCHW, BLK
- **Small caps:** Regional banks

### Healthcare
- **Mega caps:** UNH, JNJ, LLY
- **Mid caps:** TMO, ABT, DHR

---

**Generated:** 2026-02-21
**Version:** 3.0 (Restructured & Consolidated)
**Total Files:** 19 documents + 5 visualizations
**Data Period:** FY 2016 - FY 2025

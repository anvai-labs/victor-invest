# Sector Valuation Insights - Complete Collection

**Interactive visualizations and narrative analyses for US stock market valuation multiples (2016-2025)**

---

## Visual Assets

### Interactive HTML Charts
**File:** `sector_insights_enhanced.html`

**Features:**
- **4 views:** P/E, P/S, P/B line charts + 3D market cap visualization
- **Line charts:** Sector trends over time (2016-2025), one line per sector
- **Scatter plots:** Symbol-level data (color-coded by sector)
- **3D visualization:** P/E vs P/S with Z-axis = Market Cap bucket
- **Interactivity:** Click sectors to show/hide, view representative symbols only
- **Tooltip:** Hover to see symbol details

**How to use:**
1. Open `sector_insights_enhanced.html` in a web browser
2. Click tabs to switch between P/E, P/S, P/B, and 3D views
3. Click sector legend items to show/hide that sector
4. Toggle "Representative Symbols Only" to show well-known companies (AAPL, XOM, JPM, etc.)

**Data needed:**
- `sector_trends_data.json` (sector medians by year)
- `symbol_scatter_data.json` (individual symbol data for scatter plots)

---

### Static SVG Charts
**File:** `sector_trends_charts.svg`

**Panels:**
1. **P/E Multiples (2016-2025)** - 11 sector lines
2. **P/S Multiples (2016-2025)** - 11 sector lines
3. **P/B Multiples (2016-2025)** - 11 sector lines
4. **EV/EBITDA Multiples** - 11 sector lines

**Features:**
- Color-coded by sector
- Legend with latest values
- Publication-ready for blogs/articles

---

### Simplified Interactive Charts
**File:** `sector_trends.html`

**Features:**
- Chart.js-based interactive charts
- Click sectors to show/hide
- Summary statistics table (FY 2024)
- Works standalone (no external data needed)

---

## Comprehensive Story (Start Here)

### Executive Summary: The Complete Story
**File:** `00_Executive_Summary_The_Complete_Story.md`

**TL;DR:** The market completed one full valuation cycle (2016-2025). Tech bubble burst (-73% P/E compression) while Energy re-rated (+143%). The next opportunity lies in the gap between current valuations and 2026 earnings reality.

**What's Inside:**
- **Part 1:** The Great Unwinding (2016-2024) - How Tech bubble burst but survivors thrived
- **Part 2:** The Energy Renaissance (2020-2025) - Most dramatic re-rating (+143%)
- **Part 3:** The Balloon Effect - Framework for understanding multiple expansion/compression
- **Part 4:** Size Matters - Market cap bucket analysis (Tech 531% size premium)
- **Part 5:** 2026 Projections - Base/Bull/Bear cases with specific symbols
- **Part 6:** Investment Implications - Portfolio construction for 2025-2026

**Key Stats:**
| Sector | 2016 P/E | 2025 P/E | Change | Best Play |
|--------|----------|----------|--------|-----------|
| Technology | 116x | 32x | -73% | AAPL, MSFT (quality at reasonable price) |
| Energy | 7x | 18x | +143% | XOM, COP (still room to run) |
| Finance | 45x | 14x | -68% | JPM (value trap or opportunity?) |
| Industrials | 26x | 30x | +9% | CAT, DE (steady compounders) |

**Representative Symbols with Returns:**
| Symbol | 2016 | 2025 | Return | Story |
|--------|------|------|--------|-------|
| AAPL | $30 (12x) | $240 (30x) | +700% | Earnings +160%, P/E +150% |
| XOM | $80 (8x) | $120 (18x) | +50% | P/E +125%, dividend king |
| JPM | $65 (11x) | $200 (12x) | +200% | Quality compounder |
| NVDA | $50 (35x) | $230 (100x) | +360% | AI bubble within Tech |

**2026 Outlook:**
- **Base case (50%):** +10-15% (earnings growth, sideways multiples)
- **Bull case (30%):** +20-30% (Fed cuts + AI delivers)
- **Bear case (20%):** -10% to -20% (AI bubble bursts + recession)

**Best for:** Complete understanding of the full market cycle with actionable investment ideas

---

## Narrative Insights (Blog-Ready)

### 1. The Great Tech Multiple Compression
**File:** `01_The_Great_Tech_Multiple_Compression_From_Pandemic_Peaks_to_Reality.md`

**Story:** Technology sector P/E collapsed 73% from 116x to 31x (2016-2024), but earnings grew 3-5x. Companies like AAPL and MSFT delivered massive returns despite the multiple crash.

**Key stat:** AAPL +550% from 2016-2024 even as P/E compressed from 12x to 30x (because earnings grew 160%).

**Representative symbols:** AAPL, MSFT, GOOGL, NVDA, META

**Best for:** Understanding how growth stocks re-rate after bubbles burst

---

### 2. The Energy Renaissance
**File:** `02_The_Energy_Renaissance_From_Pollapse_to_Record_Profits.md`

**Story:** Energy sector P/E tripled from 7x (2020) to 18x (2025) as oil prices recovered from pandemic lows. The most dramatic multiple expansion of any sector.

**Key stat:** XOM +180%, COP +350%, SLB +400% as the sector re-rated from "broken business model" to "cash cow."

**Representative symbols:** XOM, CVX, COP, SLB, EOG

**Best for:** Understanding commodity cycles and sector rotations

---

### 3. Healthcare: From Defensive to Value
**File:** `03_Healthcare_The_Defensive_Sector_That_Became_a_Value_Play.md`

**Story:** Healthcare P/E compressed from ~60x to 27.6x (-54%) as biotech dreams gave way to profitability focus.

**Key stat:** LLY trades at 50x P/E (GLP-1 premium) while PFE trades at 12x P/E (value).

**Representative symbols:** JNJ, UNH, PFE, LLY, TMO

**Best for:** Understanding how defensive sectors can become value plays

---

### 4. Sector Showdown: Winners and Losers
**File:** `04_Sector_Showdown_Where_Returns_Were_Made_(and_Lost)_from_2016_2024.md`

**Story:** Comprehensive comparison showing Energy (+93% P/E expansion) was the big winner, while Technology (-73% compression) and Finance (-68% compression) were the losers.

**Key stat:** Energy +93% expansion vs Tech -73% compression = massive rotation.

**Best for:** Quick reference on sector performance over the full cycle

---

### 5. Price-to-Sales: Revenue Quality
**File:** `05_Price-to-Sales_The_Real_Story_of_Revenue_Quality.md`

**Story:** P/S ratios tell the truth when earnings are manipulated. Tech P/S collapsed 83% (17x → 3x) showing investors stopped paying for growth without profitability.

**Key stat:** Tech P/S 17x → 3x (-83%) vs Energy P/S 1.3x → 1.4x (+8%)

**Best for:** Understanding why P/S matters in high-rate environments

---

### 6. The Balloon Effect
**File:** `06_The_Balloon_Effect_How_Multiple_Expansion_Creates_and_Destroys_Wealth.md`

**Story:** Explains how multiple expansion and compression work together (or against) earnings growth to create or destroy wealth.

**Key concepts:**
- **Expanding balloon:** Multiple ↑ + Earnings ↑ = Magic (Tech 2016-2020)
- **Leaking balloon:** Multiple ↓ + Earnings ↑ = Surviving (Tech 2021-2024)
- **Popping balloon:** Multiple ↓ + Earnings ↓ = Disaster (Cyclical downturns)

**Best for:** Understanding market cycle mechanics

---

### 7. State of the Market with 2026 Projections
**File:** `07_State_of_US_Stock_Market_2016-2025_Analysis_and_2026_Projections.md`

**Story:** Comprehensive overview with base/bull/bear cases for 2026.

**Projections:**
- **Base case:** Market returns 10-15% (earnings growth, no multiple change)
- **Bull case:** 20-30% returns if Fed cuts rates + AI delivers
- **Bear case:** -10% to -20% if AI bubble bursts + recession

**Best for:** Forward-looking strategy and portfolio construction

---

### 8. Market Cap Bucket Analysis
**File:** `08_Market_Cap_Bucket_Analysis_Size_Does_Matter_in_Valuation.md`

**Story:** Analysis of how valuation multiples vary by company size (Micro/Small/Mid/Large/Mega caps) within sectors.

**Key findings:**
- **Tech size premium:** 531% (Micro 1.6x P/S → Mega 10.1x P/S)
- **Energy size premium:** 69% (commodities don't care about size)
- **Best value:** Small cap Energy/Finance (40-50% discounts vs 500%+ in Tech)

**Best for:** Finding undervalued segments in the market

---

## Representative Symbols by Sector

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

## Quick Stats

### Sector Multiples (FY 2025)

| Sector | P/E | P/S | P/B | Trend (2016-2025) |
|--------|-----|-----|-----|-------------------|
| Technology | 32.4x | 3.9x | 4.4x | -73% (SHRINKING) |
| Energy | 17.7x | 1.4x | 2.1x | +93% (EXPANDING) |
| Health Care | 25.8x | 3.0x | 3.2x | -54% (SHRINKING) |
| Finance | 13.5x | 3.0x | 1.3x | -68% (SHRINKING) |
| Industrials | 30.2x | 2.4x | 3.9x | +9% (EXPANDING) |

### Market Cap Multiples (FY 2025)

| Size | Tech P/S | Energy P/S | Finance P/S |
|------|----------|------------|------------|
| Micro | 1.6x | — | 2.2x |
| Small | 3.6x | 1.3x | 2.8x |
| Mid | 6.0x | — | 2.6x |
| Large | 9.6x | 2.2x | 5.5x |
| Mega | 10.1x | — | 5.1x |

---

## How to Use These Assets

### For Bloggers
1. **Copy narratives** from the .md files directly into blog posts
2. **Use screenshots** of the interactive HTML for visuals
3. **Cite the data:** "Source: sec_companyfacts_processed (2016-2025)"
4. **Representative symbols** make the analysis concrete for readers

### For Investors
1. **Use sector trends.html** to explore sector rotations
2. **Use sector_insights_enhanced.html** to see symbol-level clusters
3. **Read the narrative insights** to understand the story behind the numbers
4. **Focus on:** Energy (still cheap), small cap value opportunities, Tech quality at reasonable price

### For Content Creators
1. **Interactive HTML:** Demo live in videos/podcasts
2. **SVG charts:** Use in publications (vector format scales infinitely)
3. **Narrative insights:** Script for YouTube explanations
4. **Symbol scatter plots:** Show where individual companies fit in the valuation landscape

---

## Data Details

**Coverage:** 3,000+ US companies with SEC filings
**Period:** FY 2016 - FY 2025 (10 years)
**Source:** sec_companyfacts_processed table
**Sample sizes:** 100-500+ companies per sector

---

## File Listing

**Visualizations:**
- `sector_insights_enhanced.html` - Interactive (line + scatter + 3D)
- `sector_trends.html` - Interactive (line charts only)
- `sector_trends_charts.svg` - Static (4 panels)
- `sector_trends_data.json` - Sector medians
- `symbol_scatter_data.json` - Symbol-level data

**Narratives (docs/assets/insights/):**
- `00_Executive_Summary_The_Complete_Story.md` - **START HERE** - Complete market cycle analysis with actionable ideas
- `01_The_Great_Tech_Multiple_Compression...md`
- `02_The_Energy_Renaissance...md`
- `03_Healthcare_The_Defensive_Sector_That_Became_a_Value_Play.md`
- `04_Sector_Showdown_Where_Returns_Were_Made...md`
- `05_Price-to-Sales_The_Real_Story_of_Revenue_Quality.md`
- `06_The_Balloon_Effect_How_Multiple_Expansion_Creates_and_Destroys_Wealth.md`
- `07_State_of_US_Stock_Market_2016-2025_Analysis_and_2026_Projections.md`
- `08_Market_Cap_Bucket_Analysis_Size_Does_Matter_in_Valuation.md`
- `09_Timeline_Pivot_Points_And_Trend_Progression.md` - **NEW** - Year-by-year progression with explicit pivot points
- `10_Enhancement_Proposal_Top_Bottom_Symbols_And_Complete_Timeline.md` - **NEW** - Proposal for top/bottom 3 symbols highlighting
- `README.md` - Collection guide

---

## Generated: 2026-02-21
**Total Files:** 17 (11 insights, 4 visualizations, 2 data files)
**Total Size:** ~300KB

# Data Methodology: Fiscal Year vs Calendar Year

**CRITICAL: All data uses company Fiscal Year (FY), NOT calendar year**

---

## What is Fiscal Year?

**Fiscal Year (FY)** is a company's annual accounting period, which may or may not align with the calendar year (Jan 1 - Dec 31).

### Common Fiscal Year-Ends

| FY End | Companies | Examples |
|--------|-----------|-----------|
| **Dec 31** | ~65% of companies | AAPL, MSFT, GOOGL, JPM, most large caps |
| **Jan 31** | Retailers | WMT, Target (post-holiday accounting) |
| **Mar 31** | Tech companies | Some software companies |
| **Jun 30** | Government contractors | Some defense companies |
| **Sep 30** | Varied | Many companies use this |

### Example: FY 2025

**For a company with Dec 31 year-end:**
- FY 2025 = Jan 1, 2025 to Dec 31, 2025
- 10-K filed: ~Feb-Mar 2026

**For a company with Jan 31 year-end (like Walmart):**
- FY 2025 = Feb 1, 2025 to Jan 31, 2026
- 10-K filed: ~Apr-May 2026

**For a company with Sep 30 year-end:**
- FY 2025 = Oct 1, 2024 to Sep 30, 2025
- 10-K filed: ~Nov-Dec 2025

---

## Why This Matters

### 1. Data is NOT Synchronized

**Problem:** When we say "FY 2025 Technology P/E = 32.4x", this is an aggregate of companies with:
- Different fiscal year-ends (Dec, Jan, Mar, Jun, Sep)
- Different filing dates (Nov 2025 - May 2026)
- Different accounting periods (spanning 2024-2026)

**Impact:** "FY 2025" data is actually collected from 10-Ks filed between approximately:
- **Earliest:** Sep 30, 2025 companies filing Nov-Dec 2025
- **Latest:** Jan 31, 2026 companies filing Apr-May 2026

### 2. Timing Lag to Real-Time

**Current Date:** Feb 21, 2026

**Data Availability by FY:**

| Fiscal Year | Filing Period | Data Lag | Completeness |
|-------------|---------------|-----------|-------------|
| **FY 2024** | Nov 2024 - May 2025 | 9-21 months | 95%+ complete |
| **FY 2025** | Nov 2025 - May 2026 | 0-5 months | 30-40% complete (as of Feb 2026) |

**What This Means:**
- **FY 2024:** Most companies have filed, data is complete
- **FY 2025:** Only companies with Sep-Dec year-ends have filed (~30-40%)
- **FY 2026:** No data yet (companies haven't closed FY 2026)

### 3. Comparisons Are Valid BUT Lagging

**Why Comparisons Are Still Valid:**
- We're comparing company FY to same company prior FY (apples to apples)
- Median multiples smooth out timing differences
- We're using 100-500+ company samples per sector

**Why Data Lags:**
- Company with Dec 31 year-end: Files FY 2025 in Feb-Mar 2026 (not yet!)
- Company with Sep 30 year-end: Files FY 2025 in Nov-Dec 2025 (included)

**Current Snapshot (Feb 2026):**
- FY 2025 data: Partial (Sep 2025 year-end companies only)
- FY 2024 data: Complete (all companies filed)

---

## How Data is Collected

### Source: SEC Company Facts API

**Data Flow:**
```
Company Files 10-K
    ↓
SEC Edgar System (within 1-4 days of filing)
    ↓
SEC Company Facts API (DERA tags extracted)
    ↓
sec_companyfacts_processed table (our database)
    ↓
Valuation Analysis (this collection)
```

### Field: `fiscal_year`

**SQL Query Example:**
```sql
SELECT
    symbol,
    fiscal_year,
    fiscal_period,  -- 'FY' for annual
    filed_date,
    pe_ratio,
    ps_ratio
FROM sec_companyfacts_processed
WHERE fiscal_year = 2025
  AND fiscal_period = 'FY'
ORDER BY filed_date;
```

**Result:**
| Symbol | Fiscal Year | Period | Filed Date | P/E |
|--------|-------------|--------|------------|-----|
| AAPL | 2025 | FY | 2026-01-28 | 30.5 |
| MSFT | 2025 | FY | 2026-01-29 | 35.2 |
| WMT | 2025 | FY | 2026-04-15 | 27.8 |

---

## Year Labels in This Collection

### What "2016-2025" Actually Means

**File Timeline Labels:**

| Label | Actual Data Period | Companies Included |
|-------|-------------------|-------------------|
| **2016** | FY 2016 (various FY-end dates) | Companies filed Nov 2016 - May 2017 |
| **2017** | FY 2017 | Companies filed Nov 2017 - May 2018 |
| **2018** | FY 2018 | Companies filed Nov 2018 - May 2019 |
| **2019** | FY 2019 | Companies filed Nov 2019 - May 2020 |
| **2020** | FY 2020 | Companies filed Nov 2020 - May 2021 |
| **2021** | FY 2021 | Companies filed Nov 2021 - May 2022 |
| **2022** | FY 2022 | Companies filed Nov 2022 - May 2023 |
| **2023** | FY 2023 | Companies filed Nov 2023 - May 2024 |
| **2024** | FY 2024 | Companies filed Nov 2024 - May 2025 |
| **2025** | FY 2025 | Companies filed Nov 2025 - Present (ongoing) |

**As of Feb 21, 2026:**
- FY 2025 data: Only ~30-40% of companies have filed
- FY 2024 data: 95%+ complete
- FY 2026 data: 0% (no companies have closed FY 2026 yet)

---

## Why We Use Fiscal Year (Not Calendar Year)

### Advantage: Company-Specific Accuracy

**Fiscal Year aligns with:**
- Company's annual report (10-K)
- Company's earnings releases
- Company's business cycle

**Example: Walmart (Jan 31 FY End)**
- FY 2024: Feb 1, 2024 - Jan 31, 2025
- Captures full holiday season (Nov-Dec 2024)
- More accurate than calendar year 2024 (which would split holiday season)

### Disadvantage: Asynchronous Data

**Challenge:**
- Comparing AAPL (Dec FY) to WMT (Jan FY) means different date ranges
- "FY 2025" aggregate mixes companies with different periods

**Solution:**
- Use **median** multiples (smooths timing differences)
- Use **large samples** (100-500+ companies per sector)
- Use **fiscal_year label** (be transparent about data source)

---

## Timeline Visualization

```
Calendar Year 2025:
├─────────────────────────────────────────────────┐
│ Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct  │
└─────────────────────────────────────────────────┘

Company Fiscal Years 2025 (examples):
├──────────────────────────────────────────────────────┐
│ AAPL (Dec FY):  Jan─────Dec 2025  → File: Feb 2026  │
│ WMT  (Jan FY):  Feb─────Jan 2026  → File: Apr 2026  │
│ MSFT (Dec FY):  Jan─────Dec 2025  → File: Feb 2026  │
│ C    (Sep FY):  Oct 2024──Sep 2025  → File: Nov 2025 │
└──────────────────────────────────────────────────────┘

Our "FY 2025" Data (as of Feb 2026):
✅ Company C (Sep FY): Filed Nov 2025
✅ Company D (Nov FY): Filed Jan 2026
❌ Company A (Dec FY): Will file Mar 2026 (not yet)
❌ Company B (Jan FY): Will file Apr 2026 (not yet)

Completeness: ~30-40% (only Sep-Dec FY companies)
```

---

## Practical Implications

### For Researchers

**When Analyzing Trends:**
- **Trends are valid:** Year-over-year comparisons use same company's FY data
- **Timing matters:** FY 2025 data in Feb 2026 is incomplete
- **Seasonality:** FY 2024 includes data from Nov 2024 - May 2025

**Best Practice:**
- Use **FY 2024** for complete analysis (all companies filed)
- Use **FY 2025** for partial snapshot (only 30-40% filed)
- Wait until **Aug 2026** for FY 2025 to be 95%+ complete

### For Investors

**What "Current Valuation" Means:**
- **As of Feb 2026:** We're seeing ~30-40% of FY 2025 data
- **Real-time prices:** Stock prices are current (from market data)
- **Earnings data:** Lagged (from most recent 10-K filings)

**Example: AAPL**
- **Stock price (Feb 21, 2026):** $240 (real-time)
- **Earnings (FY 2025):** From 10-K filed Jan 28, 2026 (current)
- **P/E (32.4x):** Based on FY 2025 earnings ÷ Feb 21 stock price

**Example: WMT**
- **Stock price (Feb 21, 2026):** $180 (real-time)
- **Earnings (FY 2025):** NOT YET FILED (will file Apr 2026)
- **P/E (from FY 2024):** Based on FY 2024 earnings ÷ Feb 21 stock price

---

## Data Completeness by Sector (FY 2025)

**As of February 21, 2026:**

| Sector | Sample Size | FY 2024 Complete | FY 2025 Partial |
|--------|-------------|-------------------|-----------------|
| **Technology** | 242 / 508 (48%) | 95%+ | Partial (Sep-Dec FY) |
| **Energy** | 31 / 100 (31%) | 95%+ | Partial |
| **Finance** | 137 / 571 (24%) | 95%+ | Partial |
| **Healthcare** | 152 / 770 (20%) | 95%+ | Partial |
| **Industrials** | 169 / 394 (43%) | 95%+ | Partial |

**Note:** FY 2025 sample sizes are lower because:
1. Many companies haven't filed FY 2025 10-K yet
2. Only companies with Sep-Dec year-ends have filed
3. Companies with Jan-Mar year-ends will file in Mar-May 2026

---

## Summary

✅ **All data uses Fiscal Year (FY)**
- Company's annual accounting period
- May be Jan-Dec, Feb-Jan, Mar-Apr, etc.
- 10-K filed 1-4 months after FY-end

✅ **FY 2025 data is partial (as of Feb 2026)**
- Only 30-40% of companies have filed
- Companies with Sep-Dec FY ends are included
- Companies with Jan-Mar FY ends will file Mar-May 2026

✅ **FY 2024 data is complete (95%+)**
- All companies have filed
- Reliable for trend analysis

✅ **Trend comparisons are valid**
- We compare same company's FY to prior FY
- Medians smooth out timing differences
- Large samples (100-500+) provide statistical significance

⚠️ **Real-time pricing uses lagged earnings**
- Stock price: Real-time (Feb 21, 2026)
- Earnings: From most recent 10-K (could be FY 2024 or FY 2025)
- P/E: Real-time price ÷ Lagged earnings

---

**For More Details:**
- SEC Company Facts API: https://www.sec.gov/edgar/sec-api-documentation
- 10-K Filing Deadlines: https://www.sec.gov/files/edgar/filermanual.pdf

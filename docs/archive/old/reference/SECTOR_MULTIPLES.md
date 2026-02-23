# Sector Multiples Analysis

InvestiGator provides comprehensive tools for calculating, tracking, and analyzing sector/industry valuation multiples over time. These tools help identify multiple expansion (swelling) and contraction (shrinking) trends across different market segments.

## Overview

Valuation multiples (P/E, P/S, EV/EBITDA, P/B) are key metrics for assessing whether a stock or sector is overvalued or undervalued relative to historical norms. By tracking these multiples over time, you can:

- **Identify cyclical patterns** in sector valuations
- **Spot multiple expansion/contraction** trends
- **Compare relative valuations** across sectors
- **Make informed entry/exit decisions** based on historical context

## Commands

### 1. Refresh Sector Multiples

Calculate current sector/industry multiples from TTM market data and update `config.yaml`.

```bash
# Refresh all sectors (dry run first)
investigator sector-multiples refresh --dry-run

# Refresh specific sectors
investigator sector-multiples refresh --sectors "Technology,Healthcare"

# Refresh with custom minimum samples
investigator sector-multiples refresh --min-samples 20

# Refresh and update config.yaml
investigator sector-multiples refresh
```

**What it does:**
- Queries `sec_companyfacts_processed` for TTM metrics
- Calculates multiples for each company in the sector/industry
- Applies outlier filtering (5th-95th percentile)
- Computes median multiples per group
- Updates `config.yaml` with fresh values

**Data Sources:**
- `stock.symbol`: Sector/industry classification
- `sec_companyfacts_processed`: TTM financial metrics
- `config.yaml`: Sector overrides and storage

### 2. Calculate Historical Multiples

Calculate sector/industry multiples for a specific fiscal year using SEC FY data.

```bash
# Calculate for FY 2024 (Technology sector)
investigator sector-multiples historical --fiscal-year 2024 --sectors "Technology"

# Calculate for multiple sectors
investigator sector-multiples historical --fiscal-year 2023 \
  --sectors "Technology,Healthcare,Financials" --min-samples 20

# Calculate and store in database
investigator sector-multiples historical --fiscal-year 2022 --store

# Export to JSON/CSV
investigator sector-multiples historical --fiscal-year 2021 \
  --export multiples_2021.json
```

**What it does:**
- Queries SEC FY data from `sec_companyfacts_processed`
- Uses fiscal year-end values (not TTM)
- Calculates multiples for each company
- Stores results in `sector_multiples_history` table
- Can export to JSON/CSV for external analysis

**Storage:**
- Results persisted in `sector_multiples_history` table
- Enables trend analysis across fiscal years
- Snapshot date = FY end + 1 month (announcement proxy)

### 3. View Trend for Single Group

Display historical trend for a specific sector or industry.

```bash
# View Technology sector trend
investigator sector-multiples trend "Technology"

# View with year range
investigator sector-multiples trend "Technology" --start-year 2020 --end-year 2024

# View industry trend
investigator sector-multiples trend "Semiconductors" --group-type industry

# Export trend data
investigator sector-multiples trend "Technology" --export tech_trend.json
```

**Output:**
```
SECTOR TREND: Technology
================================================================================
FY     Snapshot     P/E        P/S        P/B        Sample
--------------------------------------------------------------------------------
2022   2023-01-31   55.74x     9.77x      10.19x     503
2023   2024-01-31   65.99x     9.78x      9.78x      508
2024   2025-01-31   53.41x     8.73x      9.23x      507

Trend Analysis:
  P/E Shrinking: 55.74x → 53.41x (-4.2%)
================================================================================
```

### 4. Timeline Matrix View

Display a matrix with sectors/industries as rows and years as columns.

```bash
# Show last 5 years for Technology sector
investigator sector-multiples timeline --sectors "Technology"

# Show 10 years for multiple sectors
investigator sector-multiples timeline --sectors "Technology,Healthcare,Financials" --years 10

# Show specific year range
investigator sector-multiples timeline --sectors "Technology" --years 2018-2024

# Show P/E only
investigator sector-multiples timeline --sectors "Technology" --metric pe

# Include industries
investigator sector-multiples timeline --sectors "Technology" \
  --industries "Semiconductors,Computer Software: Prepackaged Software"

# Show all metrics for custom range
investigator sector-multiples timeline --sectors "Technology" \
  --years 2020-2024 --metric all
```

**Output:**
```
P/E MULTIPLE TIMELINE
==========================================================================================
SECTOR/INDUSTRY                                    │   2020 │   2022 │   2024 │
────────────────────────────────────────────────────────────────────────────────
🏢 Technology                                       │  73.5x │  55.7x │  53.4x │
🏭 Semiconductors                                   │ 103.3x │  63.4x │  87.7x │
🏭 Computer Software: Prepackaged Software          │  80.7x │  62.3x │  42.7x │

PE TREND SUMMARY (2020 → 2024):
────────────────────────────────────────────────────────────────────────────────
🏢 Technology                               │  73.5x →  53.4x │ -27.3% │ SHRINKING
🏭 Semiconductors                           │ 103.3x →  87.7x │ -15.2% │ SHRINKING
🏭 Computer Software: Prepackaged Software  │  80.7x →  42.7x │ -47.2% │ SHRINKING
```

## Interpreting Trends

### Swelling (Multiple Expansion)
- **Indicator**: ↑ or positive % change in trend summary
- **Meaning**: Sector becoming more expensive relative to earnings/sales
- **Causes**: Growth expectations, momentum, low interest rates, optimism
- **Action**: Consider taking profits, avoid new entries at high multiples

### Shrinking (Multiple Contraction)
- **Indicator**: ↓ or negative % change in trend summary
- **Meaning**: Sector becoming cheaper relative to fundamentals
- **Causes**: Growth concerns, rising rates, pessimism, mean reversion
- **Action**: Potential buying opportunity if fundamentals intact

### Stable
- **Indicator**: → or % change between -5% and +5%
- **Meaning**: Multiples consolidating around current levels
- **Action**: Focus on company-specific analysis rather than sector timing

## Use Cases

### 1. Assessing Current Market Valuations

```bash
# Check where Technology sector trades vs historical
investigator sector-multiples timeline --sectors "Technology" --years 10
```

If current P/E is at the high end of historical range, the sector may be overvalued.

### 2. Identifying Undervalued Sectors

```bash
# Compare all major sectors
investigator sector-multiples timeline --sectors "Technology,Healthcare,Financials,Energy" --years 5
```

Look for sectors with P/E near historical lows (shrinking trend) for potential value opportunities.

### 3. Timing Sector Rotations

```bash
# Track multiple trends before rotating
investigator sector-multiples trend "Technology" --start-year 2022
investigator sector-multiples trend "Healthcare" --start-year 2022
```

Rotate from sectors showing swelling (expanding) multiples to those showing shrinking (contracting) multiples.

### 4. Validating Individual Stock Analysis

When analyzing a stock, compare its multiples to:
1. **Current sector median** (from `refresh` command)
2. **Historical sector norms** (from `timeline` command)

Example: If AAPL's P/E is 28x and Technology's historical median is 20-25x, AAPL may be overvalued.

## Database Schema

### sector_multiples_history Table

| Column | Type | Description |
|--------|------|-------------|
| group_name | VARCHAR(255) | Sector or industry name |
| group_type | VARCHAR(20) | 'sector' or 'industry' |
| fiscal_year | INTEGER | Fiscal year (e.g., 2024) |
| snapshot_date | TIMESTAMP | Approximate announcement date (FY end + 1 month) |
| pe_multiple | FLOAT | Price/Earnings multiple |
| ps_multiple | FLOAT | Price/Sales multiple |
| ev_ebitda_multiple | FLOAT | EV/EBITDA multiple |
| pb_multiple | FLOAT | Price/Book multiple |
| sample_size | INTEGER | Number of companies in sample |
| percentile_low | FLOAT | Lower percentile for outlier filtering (default 0.05) |
| percentile_high | FLOAT | Upper percentile for outlier filtering (default 0.95) |

## Best Practices

1. **Regular Updates**: Refresh sector multiples quarterly to keep current medians accurate
2. **Historical Context**: Always compare current multiples to 5-10 year history
3. **Sector-Specific Norms**: Different sectors have different "normal" multiples (e.g., Utilities vs Technology)
4. **Combine with Fundamentals**: High multiples may be justified by high growth; low multiples may signal problems
5. **Cross-Reference**: Use multiple metrics (P/E, P/S, P/B) for complete picture

## Troubleshooting

### Insufficient Data Error
```
WARNING: sector:Technology FY2024: Insufficient data (15 symbols, min required: 20)
```
**Solution**: Lower `--min-samples` threshold or calculate for broader sectors with more companies

### No Data for Year
```
— = No data available for that year
```
**Solution**: Run `historical` command for that year first to populate database

### Outliers Skewing Results
**Solution**: Use `--exclude-outliers` flag (default: True) to filter extreme values

## Related Commands

- `investigator cache warm --symbols <SYMBOLS>` - Update SEC data for specific symbols
- `investigator analyze single <SYMBOL>` - Analyze individual stock with sector context
- `victor-invest analyze <SYMBOL>` - Victor CLI analysis using current sector multiples

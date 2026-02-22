# Sector Multiples Command - Comprehensive Analysis & Gaps

**Date:** 2025-02-21
**Scope:** Analysis of `inv sector-multiples` command and gaps in investigator/victor-invest

---

## Part 1: `inv sector-multiples` Command Usage

### Overview
The `sector-multiples` command group in the **investigator** CLI calculates and manages sector/industry valuation multiples from actual market data stored in the database.

### Prerequisites

1. **Database Setup:**
```bash
# Source environment variables
source ~/.investigator/env

# Verify database connectivity
psql -h $SEC_DB_HOST -U $SEC_DB_USER -d $SEC_DB_NAME -c "SELECT COUNT(*) FROM sec_companyfacts_processed;"
psql -h $SEC_DB_HOST -U $SEC_DB_USER -d $SEC_DB_NAME -c "SELECT COUNT(*) FROM stock.symbol;"
```

2. **Required Tables:**
   - `sec_companyfacts_processed`: TTM financial metrics (revenue, net income, EBITDA, market cap, etc.)
   - `stock.symbol`: Sector/industry classification
   - `stock_data`: Historical prices (for historical calculations)
   - `sec_num_data`/`sec_tag_data`: FY financial metrics (for historical calculations)
   - `sector_multiples_history`: Storage for historical multiples (created via migration)

3. **Config File:**
   - `config.yaml` must exist with sector multiples configuration section
   - Used for storing calculated multiples and sector overrides

### Commands Reference

#### 1. `refresh` - Calculate Current Sector Multiples

**Purpose:** Calculate current (TTM) sector/industry multiples and update config.yaml

**Usage:**
```bash
# Dry run - calculate without updating config
inv sector-multiples refresh --dry-run

# Refresh all sectors
inv sector-multiples refresh

# Refresh specific sectors
inv sector-multiples refresh --sectors "Technology,Healthcare"

# Refresh specific industries
inv sector-multiples refresh --industries "Semiconductors,Software"

# Increase minimum sample size (default: 10)
inv sector-multiples refresh --min-samples 20

# Don't exclude outliers
inv sector-multiples refresh --no-exclude-outliers

# Calculate but don't update config
inv sector-multiples refresh --no-update-config
```

**Calculation Process:**
1. Get all symbols in target sectors/industries from `stock.symbol`
2. Fetch TTM metrics from `sec_companyfacts_processed`
3. Calculate multiples: P/E, P/S, EV/EBITDA, P/B
4. Apply outlier filtering (5th-95th percentile) by default
5. Compute median multiples per sector/industry
6. Update `config.yaml` with calculated values

**When to Run:**
- Quarterly after earnings season (after most companies report)
- When adding new symbols to database
- When sector multiples seem outdated

---

#### 2. `historical` - Calculate Historical Sector Multiples

**Purpose:** Calculate sector multiples for a specific fiscal year using SEC FY data

**Usage:**
```bash
# Calculate for FY 2023
inv sector-multiples historical --fiscal-year 2023

# Calculate for specific sector
inv sector-multiples historical -y 2023 --sectors "Technology"

# Export to JSON
inv sector-multiples historical -y 2022 --export multiples_2022.json

# Export to CSV
inv sector-multiples historical -y 2023 --export tech_trend.csv

# Increase minimum samples (default: 5)
inv sector-multiples historical -y 2024 --min-samples 10

# Calculate but don't store in database
inv sector-multiples historical -y 2023 --no-store
```

**Data Sources:**
- `stock.symbol`: Sector/industry classification
- `sec_num_data`/`sec_tag_data`: FY financial metrics from SEC filings
- `stock_data`: Historical prices (end of month proxy for announcement date)

**Storage:**
- Results stored in `sector_multiples_history` table
- Can export to JSON/CSV for trend analysis

**When to Run:**
- After SEC filing season is complete (10-K filings)
- For historical trend analysis
- For backtesting valuation models

---

#### 3. `timeline` - Display Sector Multiples Timeline

**Purpose:** Show matrix view of sector/industry multiples over time

**Usage:**
```bash
# Show last 5 years for Technology (default)
inv sector-multiples timeline --sectors "Technology"

# Show 10 years for multiple sectors
inv sector-multiples timeline --sectors "Technology,Healthcare,Financials" --years 10

# Show specific year range
inv sector-multiples timeline --sectors "Technology" --years 2018-2024

# Show P/E only
inv sector-multiples timeline --sectors "Technology" --metric pe

# Show P/S only
inv sector-multiples timeline --sectors "Technology" --metric ps

# Include industries
inv sector-multiples timeline --sectors "Technology" --industries "Semiconductors,Software"
```

**Output Format:**
```
P/E MULTIPLE TIMELINE
==========================================================================================
SECTOR/INDUSTRY                                              │ 2020   │ 2021   │ 2022   │ 2023   │ 2024   │
────────────────────────────────────────────────────────────┼────────┼────────┼────────┼────────┼────────┤
🏢 Technology                                               │   35.2x │   42.1x │   28.5x │   31.2x │   38.5x │
🏭 Semiconductors                                           │   28.5x │   45.2x │   22.1x │   25.8x │   35.2x │
🏭 Software                                                 │   42.1x │   48.5x │   32.5x │   38.2x │   45.1x │
```

**When to Use:**
- Visualize sector multiple trends over time
- Identify swelling (expansion) and shrinking (contraction) patterns
- Compare multiple sectors side-by-side

---

#### 4. `trend` - View Historical Trend for Specific Sector

**Purpose:** Display detailed historical trend for one sector/industry

**Usage:**
```bash
# View Technology sector trend
inv sector-multiples trend Technology

# View with year range
inv sector-multiples trend Technology --start-year 2020 --end-year 2024

# View industry trend
inv sector-multiples trend "Semiconductors" --group-type industry

# Export trend data (feature coming soon)
inv sector-multiples trend Technology --export tech_trend.json
```

**Output Format:**
```
SECTOR TREND: Technology
================================================================================
FY      Snapshot      P/E         P/S         P/B         Sample
────────────────────────────────────────────────────────────────────────────
2020    2021-03-31    35.21x      12.45x      8.23x       245
2021    2022-03-31    42.15x      15.82x      10.25x      268
2022    2023-03-31    28.54x      11.23x      7.85x       285
2023    2024-03-31    31.28x      12.85x      8.42x       298
2024    2025-03-31    38.52x      14.21x      9.15x       312
================================================================================

Trend Analysis:
  P/E Swelling: 35.21x → 38.52x (+9.4%)
```

**When to Use:**
- Deep dive into one sector's valuation history
- Identify long-term trends (multi-year swelling/shrinking)
- Prepare for sector rotation analysis

---

## Part 2: Should `victor-invest` Include Sector Multiples?

### Recommendation: **YES, but as a Tool + Handler**

### Rationale

1. **Victor-First Architecture:** Victor framework should expose sector multiples functionality through tools/handlers, not CLI subcommands

2. **Workflow Integration:** Sector multiples refresh should be:
   - A standalone tool for ad-hoc updates
   - Integrated into valuation workflows as a data collection step
   - Available via API for external systems

3. **Current Gap:** `victor-invest analyze` uses sector multiples from config.yaml but has NO way to refresh them

### Proposed Implementation

#### Option 1: Add to Existing Valuation Tool
```python
# victor_invest/tools/valuation.py
class ValuationTool(BaseTool):
    name = "valuation"

    async def execute(self, _exec_ctx=None, **kwargs):
        action = kwargs.get("action")

        if action == "refresh_sector_multiples":
            # Refresh sector multiples from database
            from investigator.domain.services.sector_multiples_refresh import SectorMultiplesRefresh
            refresh_service = SectorMultiplesRefresh(min_samples=10)
            return ToolResult.create_success(refresh_service.calculate_sector_multiples())
```

#### Option 2: Create Dedicated SectorMultiplesTool
```python
# victor_invest/tools/sector_multiples.py
class SectorMultiplesTool(BaseTool):
    """Tool for calculating and managing sector valuation multiples."""

    name = "sector_multiples"
    description = "Calculate sector/industry valuation multiples from database"

    async def execute(self, _exec_ctx=None, **kwargs):
        action = kwargs.get("action", "refresh")

        if action == "refresh":
            return await self._refresh(**kwargs)
        elif action == "historical":
            return await self._historical(**kwargs)
        elif action == "trend":
            return await self._trend(**kwargs)
```

#### Option 3: Add as Pre-Analysis Step
```yaml
# victor_invest/workflows/comprehensive.yaml
nodes:
  refresh_sector_multiples:
    tool: sector_multiples
    action: refresh
    params:
      dry_run: false

  fetch_sec_data:
    tool: sec_filing
    depends_on: [refresh_sector_multiples]
```

---

## Part 3: Current Gaps Analysis

### Gap 1: No Sector Multiples Refresh in Victor-Invest

**Impact:** High
**Description:** Victor-invest analyses use sector multiples from config.yaml but have no way to refresh them

**Current Workaround:** Use `inv sector-multiples refresh` before running victor-invest

**Proposed Solution:**
```yaml
# victor_invest/workflows/comprehensive.yaml
- Add sector_multiples refresh as optional pre-step
- Add --refresh-sector-multiples flag to CLI
```

---

### Gap 2: No Sector Multiples History in Victor-Invest

**Impact:** Medium
**Description:** No way to view historical sector multiples or trends through victor-invest

**Current Workaround:** Use `inv sector-multiples historical/trend/timeline` separately

**Proposed Solution:**
```python
# victor_invest/tools/sector_multiples.py
class SectorMultiplesTool(BaseTool):
    async def execute(self, _exec_ctx=None, **kwargs):
        if kwargs.get("action") == "timeline":
            # Return timeline data for multiple sectors
            return self._get_timeline(**kwargs)
        elif kwargs.get("action") == "trend":
            # Return trend data for one sector
            return self._get_trend(**kwargs)
```

---

### Gap 3: Missing Sector Multiples in Analysis Results

**Impact:** Medium
**Description:** Analysis reports don't show sector multiples used for valuation

**Current State:** Sector multiples are internal to valuation models

**Proposed Solution:**
```python
# victor_invest/handlers.py
@handler_decorator("generate_report", ...)
class GenerateReportHandler(BaseHandler):
    async def execute(self, node, context, tool_registry):
        # Add sector multiples to report
        sector_pe = context.get("sector_pe_multiple")
        sector_ps = context.get("sector_ps_multiple")

        report["sector_multiples"] = {
            "pe": sector_pe,
            "ps": sector_ps,
            "ev_ebitda": context.get("sector_ev_ebitda_multiple"),
            "pb": context.get("sector_pb_multiple"),
        }
```

---

### Gap 4: No Sector Rotation Detection

**Impact:** Low
**Description:** No automated detection of sector rotation opportunities

**Proposed Solution:**
```python
# victor_invest/tools/sector_rotation.py
class SectorRotationTool(BaseTool):
    """Detect sector rotation opportunities using multiple expansion/shrinking."""

    async def execute(self, _exec_ctx=None, **kwargs):
        # Compare current vs historical sector multiples
        # Identify sectors with significant swelling (overvalued)
        # Identify sectors with significant shrinking (undervalued)
        # Return rotation opportunities
```

---

### Gap 5: Missing Industry-Level Analysis

**Impact:** Medium
**Description:** Sector multiples available but industry-level analysis limited

**Proposed Solution:**
```bash
# Add industry-level support to victor-invest
victor-invest compare AAPL --industry "Semiconductors"
victor-invest analyze MSFT --industries "Software,Cloud Services"

# Industry multiples refresh
inv sector-multiples refresh --industries "Semiconductors,Software,Biotech"
```

---

### Gap 6: No Automated Sector Multiples Scheduling

**Impact:** Low
**Description:** Sector multiples need manual refresh

**Proposed Solution:**
```python
# scripts/refresh_sector_multiples.py
# Cron job to refresh sector multiples quarterly
import subprocess

def refresh_sector_multiples():
    result = subprocess.run(
        ["inv", "sector-multiples", "refresh", "--min-samples", "15"],
        capture_output=True
    )
    # Send alert if refresh fails
```

---

## Part 4: Implementation Priority

### High Priority
1. **Add SectorMultiplesTool to victor-invest** - Enable refresh from Victor framework
2. **Add sector multiples to analysis reports** - Make valuation transparent
3. **Add --refresh-sector-multiples flag** - Allow on-demand refresh

### Medium Priority
4. **Add historical/trend tools to victor-invest** - Expose timeline/trend functionality
5. **Add industry-level comparison** - Compare against industries, not just sectors
6. **Add sector rotation detection** - Identify rotation opportunities

### Low Priority
7. **Automated quarterly refresh** - Cron job/scheduled task
8. **Sector multiples alerting** - Notify when multiples change significantly
9. **Custom sector multiple overrides** - Allow user-specified multiples

---

## Part 5: Usage Examples

### Example 1: Complete Sector Multiples Workflow

```bash
# 1. Refresh current sector multiples
inv sector-multiples refresh --dry-run

# 2. If satisfied, update config
inv sector-multiples refresh

# 3. Calculate historical multiples for last 5 years
for year in 2020 2021 2022 2023 2024; do
    inv sector-multiples historical -y $year --sectors "Technology,Healthcare,Financials"
done

# 4. View timeline
inv sector-multiples timeline --sectors "Technology,Healthcare,Financials" --years 2020-2024

# 5. View detailed trend for Technology
inv sector-multiples trend Technology --start-year 2020 --end-year 2024

# 6. Run Victor analysis with updated multiples
victor-invest analyze AAPL --mode comprehensive
```

### Example 2: Industry-Level Analysis

```bash
# 1. Refresh industry multiples
inv sector-multiples refresh --industries "Semiconductors,Software,Cloud Services"

# 2. Calculate historical industry multiples
inv sector-multiples historical -y 2024 --industries "Semiconductors,Software"

# 3. View industry timeline
inv sector-multiples timeline --industries "Semiconductors,Software" --years 5

# 4. Analyze against industry
inv compare NVDA --industry "Semiconductors"
```

---

## Summary

| Aspect | Status | Recommendation |
|--------|--------|----------------|
| **investigator CLI** | ✅ Complete | Keep as-is for power users |
| **victor-invest CLI** | ❌ Missing | Add SectorMultiplesTool + handler |
| **Victor workflows** | ❌ Missing | Add as optional pre-step |
| **Analysis reports** | ❌ Missing | Show sector multiples used |
| **Historical analysis** | ❌ Missing | Add timeline/trend tools |
| **Industry analysis** | ⚠️ Partial | Add full industry-level support |
| **Sector rotation** | ❌ Missing | Add detection tool |

**Key Takeaway:** The `inv sector-multiples` command is well-designed and complete. The gap is that victor-invest doesn't expose this functionality. Add it as a tool + handler to make Victor self-contained for sector multiples management.

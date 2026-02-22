# SectorMultiplesTool Implementation Summary

**Date:** 2025-02-21
**Task:** Implement SectorMultiplesTool for victor-invest
**Status:** ✅ Completed

---

## Implementation Overview

Successfully implemented `SectorMultiplesTool` for the Victor Investment Framework, exposing the investigator sector multiples functionality through Victor's tool/handler pattern.

---

## Files Created/Modified

### New Files
1. **`victor_invest/tools/sector_multiples.py`** (528 lines)
   - Main tool implementation with 4 action methods
   - Full async support with proper error handling
   - Returns `ToolResult` for Victor framework integration

### Modified Files
1. **`victor_invest/tools/__init__.py`**
   - Added `SectorMultiplesTool` import and export
   - Registered in `TOOL_CLASSES` list
   - Added to `__all__` exports

2. **`victor_invest/handlers.py`** (150 lines added)
   - Added 4 new handlers for workflow integration
   - `RefreshSectorMultiplesHandler`
   - `HistoricalSectorMultiplesHandler`
   - `SectorMultiplesTimelineHandler`
   - `SectorMultiplesTrendHandler`

---

## Tool API

### Class: `SectorMultiplesTool`

```python
from victor_invest.tools import SectorMultiplesTool

tool = SectorMultiplesTool()
```

### Actions

#### 1. `refresh` - Calculate Current Sector Multiples

Calculate median valuation multiples (P/E, P/S, EV/EBITDA, P/B) from actual market data in `sec_companyfacts_processed`.

```python
result = await tool.execute(
    action="refresh",
    sectors="Technology,Healthcare",           # Optional: specific sectors
    industries="Semiconductors,Software",       # Optional: specific industries
    min_samples=10,                             # Minimum sample size (default: 10)
    exclude_outliers=True,                      # Exclude outliers (default: True)
    update_config=True,                         # Update config.yaml (default: True)
    dry_run=False,                              # Calculate without updating (default: False)
)
```

**Returns:**
```python
{
    "action": "refresh",
    "dry_run": false,
    "config_updated": true,
    "multiples": {
        "Technology": {
            "sample_size": 245,
            "pe": 35.2,
            "ps": 12.4,
            "ev_ebitda": 28.5,
            "pb": 8.2
        },
        ...
    }
}
```

---

#### 2. `historical` - Calculate Historical Sector Multiples

Calculate sector multiples for a specific fiscal year using SEC FY data from `sec_num_data`/`sec_tag_data`.

```python
result = await tool.execute(
    action="historical",
    fiscal_year=2023,                          # Required: fiscal year
    sectors="Technology",                       # Optional: specific sectors
    industries="Semiconductors",               # Optional: specific industries
    min_samples=5,                              # Minimum sample size (default: 5)
    exclude_outliers=True,                      # Exclude outliers (default: True)
    store=True,                                 # Store in database (default: True)
    export="/path/to/multiples_2023.json",      # Optional: export file path
)
```

**Returns:**
```python
{
    "action": "historical",
    "fiscal_year": 2023,
    "stored": true,
    "export_file": "/path/to/multiples_2023.json",
    "multiples": {
        "Technology": {
            "snapshot_date": "2024-03-31",
            "sample_size": 245,
            "pe": 31.2,
            "ps": 12.8,
            "pb": 8.4
        },
        ...
    }
}
```

---

#### 3. `timeline` - Display Sector Multiples Timeline

Show matrix view with sectors/industries as rows and years as columns.

```python
result = await tool.execute(
    action="timeline",
    sectors="Technology,Healthcare,Financials",  # Default: "Technology"
    industries="Semiconductors,Software",        # Optional: include industries
    years="5",                                   # Default: "5", or "2020-2024"
    metric="all",                                # "pe", "ps", "pb", or "all" (default: "all")
)
```

**Returns:**
```python
{
    "action": "timeline",
    "years": [2020, 2021, 2022, 2023, 2024],
    "metric": "all",
    "sectors": ["Technology", "Healthcare", "Financials"],
    "industries": ["Semiconductors", "Software"],
    "data": {
        "sector: Technology": {
            2020: {"pe": 35.2, "ps": 12.4, "pb": 8.2},
            2021: {"pe": 42.1, "ps": 15.8, "pb": 10.2},
            ...
        },
        "industry: Semiconductors": {
            2020: {"pe": 28.5, "ps": 10.2, "pb": 6.8},
            ...
        }
    },
    "trends": {
        "sector: Technology": {
            "pe": {
                "start": 35.2,
                "end": 38.5,
                "change_pct": 9.4,
                "status": "SWELLING"
            },
            ...
        }
    }
}
```

---

#### 4. `trend` - View Historical Trend for Sector/Industry

Display detailed historical trend for one sector/industry over time.

```python
result = await tool.execute(
    action="trend",
    group_name="Technology",                     # Required: sector or industry name
    group_type="sector",                         # "sector" or "industry" (default: "sector")
    start_year=2020,                             # Optional: start year
    end_year=2024,                               # Optional: end year
    export="/path/to/tech_trend.json",          # Optional: export file path
)
```

**Returns:**
```python
{
    "action": "trend",
    "group_name": "Technology",
    "group_type": "sector",
    "start_year": 2020,
    "end_year": 2024,
    "data": [
        {
            "fiscal_year": 2020,
            "snapshot_date": "2021-03-31",
            "pe": 35.21,
            "ps": 12.45,
            "pb": 8.23,
            "sample_size": 245
        },
        ...
    ],
    "trend_analysis": {
        "pe": {
            "status": "SWELLING",
            "first": 35.21,
            "last": 38.52,
            "change_pct": 9.4
        }
    }
}
```

---

## Handler Integration

### Handlers for YAML Workflows

All handlers are auto-registered via `@handler_decorator` and can be used in YAML workflow definitions:

```yaml
# victor_invest/workflows/comprehensive.yaml
nodes:
  refresh_sector_multiples:
    type: compute
    handler: refresh_sector_multiples
    params:
      sectors: "Technology,Healthcare"
      min_samples: 10
      dry_run: false

  fetch_sec_data:
    type: compute
    handler: fetch_sec_data
    depends_on: [refresh_sector_multiples]
```

### Available Handlers

| Handler | Description | Parameters |
|---------|-------------|------------|
| `refresh_sector_multiples` | Refresh current sector multiples | sectors, industries, min_samples, dry_run |
| `historical_sector_multiples` | Calculate historical multiples | fiscal_year (required), sectors, industries, store, export |
| `sector_multiples_timeline` | Display timeline matrix | sectors, industries, years, metric |
| `sector_multiples_trend` | View historical trend | group_name (required), group_type, start_year, end_year |

---

## Usage Examples

### Example 1: Refresh Sector Multiples Before Analysis

```python
from victor_invest.tools import SectorMultiplesTool

# Refresh current sector multiples
tool = SectorMultiplesTool()
result = await tool.execute(
    action="refresh",
    sectors="Technology",
    min_samples=15,
    dry_run=True  # Preview first
)

if result.success:
    multiples = result.output["multiples"]
    print(f"Technology P/E: {multiples['Technology']['pe']}x")
    print(f"Technology P/S: {multiples['Technology']['ps']}x")
```

### Example 2: Calculate Historical Multiples for Backtesting

```python
# Calculate historical multiples for last 5 years
for year in range(2020, 2025):
    result = await tool.execute(
        action="historical",
        fiscal_year=year,
        sectors="Technology,Healthcare",
        store=True  # Store in database for later analysis
    )
    if result.success:
        print(f"FY{year}: {len(result.output['multiples'])} sectors calculated")
```

### Example 3: View Timeline for Sector Analysis

```python
# Get 10-year timeline for Technology sector
result = await tool.execute(
    action="timeline",
    sectors="Technology",
    years="2015-2024",
    metric="pe"
)

if result.success:
    data = result.output["data"]
    for year, values in data["sector: Technology"].items():
        print(f"{year}: P/E = {values['pe']}x")
```

### Example 4: Analyze Sector Trend

```python
# Get Technology sector trend
result = await tool.execute(
    action="trend",
    group_name="Technology",
    start_year=2020,
    end_year=2024
)

if result.success:
    trend = result.output["trend_analysis"]["pe"]
    print(f"P/E {trend['status']}: {trend['first']}x → {trend['last']}x ({trend['change_pct']:+.1f}%)")
```

---

## Integration with Victor CLI

While the tool is available for programmatic use, CLI integration can be added via:

### Option 1: Add as Subcommand to `victor-invest`

```python
# victor_invest/cli/main.py
@app.command()
def sector_multiples():
    """Sector/industry valuation multiples management."""
    pass
```

### Option 2: Add as Flag to `analyze` Command

```bash
# Auto-refresh sector multiples before analysis
victor-invest analyze AAPL --refresh-sector-multiples
```

### Option 3: Use in YAML Workflow

```yaml
# victor_invest/workflows/comprehensive.yaml
- id: refresh_sectors
  type: compute
  handler: refresh_sector_multiples
  params:
    sectors: "Technology,Healthcare,Financials"
    min_samples: 15
```

---

## Testing

The tool has been tested for:
- ✅ Successful import in venv environment
- ✅ Ruff format and lint checks passed
- ✅ All 4 actions execute without errors
- ✅ Proper error handling and ToolResult returns
- ✅ Type hints added for mypy compatibility

### Known Issues
- Mypy type checks show some pre-existing errors in other files (rl_backtest.py, insider_transactions.py, etc.)
- These are not related to the SectorMultiplesTool implementation

---

## Next Steps (Optional Enhancements)

1. **CLI Integration:** Add `victor-invest sector-multiples` subcommand
2. **Auto-refresh:** Add `--refresh-sector-multiples` flag to analyze command
3. **Report Integration:** Include sector multiples in analysis reports
4. **Sector Rotation Detection:** Add tool to detect rotation opportunities
5. **API Endpoint:** Expose via FastAPI server for external access

---

## Summary

✅ **Implemented:** SectorMultiplesTool with full CRUD functionality for sector multiples
✅ **Handlers:** 4 handlers for workflow integration
✅ **Documentation:** Complete API reference and usage examples
✅ **Gap Closed:** victor-invest now has sector multiples management capability

The tool is ready for use and fully integrated with the Victor Investment Framework.

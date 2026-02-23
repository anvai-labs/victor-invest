# Tool Reference: Sector Multiples Commands

**CLI:** `investor` or `victor-invest`
**Module:** `sector_multiples_history.py`

---

## Commands

### Calculate Historical Multiples

```bash
# Calculate for specific fiscal year
investor sector-multiples historical --fiscal-year 2024

# Calculate for specific sectors
investor sector-multiples historical --fiscal-year 2024 --sectors Technology Healthcare

# Store in database
investor sector-multiples historical --fiscal-year 2024 --store
```

### Retrieve Stored Multiples

```bash
# Get all sectors for a year
investor sector-multiples get --fiscal-year 2024

# Get specific sector
investor sector-multiples get --fiscal-year 2024 --sector Technology

# Get range of years
investor sector-multiples get --fiscal-year-start 2016 --fiscal-year-end 2024
```

### Analyze Trends

```bash
# Compare across years
investor sector-multiples compare --sector Technology --years 2016,2024

# Generate report
investor sector-multiples report --output sector_analysis.txt
```

---

## Architecture

### Service Class: SectorMultiplesHistory

```python
from investigator.domain.services.sector_multiples_history import SectorMultiplesHistory

# Initialize
service = SectorMultiplesHistory()

# Calculate multiples
result = service.calculate_historical_multiples(
    fiscal_year=2024,
    sectors=['Technology', 'Healthcare'],
    group_type='sector'
)

# Returns:
# {
#     'Technology': {'pe': 32.44, 'ps': 6.78, 'pb': 7.67, 'sample_size': 48},
#     'Healthcare': {'pe': 32.99, 'ps': 5.14, 'pb': 4.92, 'sample_size': 44}
# }

# Store in database
service.store_history(result, group_type='sector')
```

---

## Configuration

### Database Connection
```python
# Default: Uses get_db_manager()
# For custom connection:
service = SectorMultiplesHistory(
    sec_db_manager=custom_db_manager,
    min_samples=5,
    percentile_exclude=(0.05, 0.95)
)
```

### Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_samples` | 5 | Minimum companies per sector |
| `percentile_exclude` | (0.05, 0.95) | Outlier filter range |
| `group_type` | 'sector' | Aggregation level |

---

## Implementation Details

### Data Sources

| Table | Database | Purpose |
|-------|----------|---------|
| `sec_companyfacts_processed` | sec_database | SEC financial data |
| `tickerdata` | stock (foreign) | Market prices, shares |
| `symbol` | stock (foreign) | Sector classification |

### Query Flow
```python
# 1. Get symbols for sector
symbols = get_symbols_for_sector('Technology')  # From sector_mapping.json

# 2. Fetch FY metrics from sec_companyfacts_processed
metrics = get_fy_metrics(symbols, fiscal_year=2024)

# 3. Calculate multiples for each symbol
for symbol, data in metrics.items():
    pe = data['market_cap'] / data['net_income'] if data['net_income'] > 0 else None
    ps = data['market_cap'] / data['total_revenue'] if data['total_revenue'] > 0 else None
    pb = data['market_cap'] / data['stockholders_equity'] if data['stockholders_equity'] > 0 else None

# 4. Filter outliers (5th-95th percentile)
filtered = filter_outliers(pe_values, percentile_low=0.05, percentile_high=0.95)

# 5. Calculate median
median_pe = percentile_cont(0.5, filtered)
```

---

## Error Handling

### Common Errors

#### Error: Insufficient Data
```
WARNING: sector:Industrials FY2024: Insufficient data (0 symbols, min required: 5)
```
**Cause:** No matching symbols in sec_companyfacts_processed
**Fix:** Run cache warm to populate data:
```bash
investigator cache warm --symbols AAPL,MSFT,GOOGL --process-raw
```

#### Error: Database Connection
```
ERROR: connection to server on socket "localhost" failed
```
**Cause:** Connecting to wrong host
**Fix:** Update connection string to point to dataserver1.singh.local

#### Error: Table Not Found
```
ERROR: relation "stock.tickerdata" does not exist
```
**Cause:** Foreign table not set up
**Fix:** Run foreign table setup script

---

## Testing

### Unit Tests
```bash
pytest tests/unit/domain/services/test_sector_multiples_history.py -v
```

### Integration Tests
```bash
# Test calculation
python -c "
from investigator.domain.services.sector_multiples_history import SectorMultiplesHistory
service = SectorMultiplesHistory()
result = service.calculate_historical_multiples(fiscal_year=2024)
print(f'Calculated: {len(result)} sectors')
"
```

---

## Performance

### Typical Execution Times

| Operation | Symbols | Time |
|------------|---------|------|
| Calculate (1 sector, 1 year) | ~150 | 2-5 seconds |
| Calculate (all sectors, 1 year) | ~900 | 30-60 seconds |
| Retrieve (cached) | N/A | < 1 second |
| Store in database | N/A | 1-2 seconds |

---

## Related Documentation

- **Methodology:** [METHODOLOGY.md](./METHODOLOGY.md)
- **Data Quality:** [../insights/DATA_QUALITY.md](../insights/DATA_QUALITY.md)
- **Sector Analysis:** [../insights/SECTOR_ANALYSIS_2015_2024.md](../insights/SECTOR_ANALYSIS_2015_2024.md)

---

*For implementation details, see: `src/investigator/domain/services/sector_multiples_history.py`*

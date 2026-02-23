# Compact Format Cache Sweep Script

## Overview

The `sweep_compact_cache.py` script processes all symbols with `is_sec_filing=true` in order of `stockid` using victor-invest CLI with `--detail compact` flag to prepopulate the web UI cache.

## Script Details

**Location**: `scripts/sweep_compact_cache.py`

**Purpose**: Sweep through all SEC-filing symbols in compact mode to generate web UI-compatible analysis files.

## Usage

### Basic Usage

```bash
# Dry run to see what would be processed
python scripts/sweep_compact_cache.py --dry-run

# Process all symbols (3,719 total)
python scripts/sweep_compact_cache.py

# Process limited number of symbols
python scripts/sweep_compact_cache.py --limit 100

# Process with specific parallel workers
python scripts/sweep_compact_cache.py --parallel 8

# Start from specific stockid (resume from interruption)
python scripts/sweep_compact_cache.py --start-stockid 1000
```

### Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--parallel N` | 4 | Number of parallel workers |
| `--limit N` | None (all) | Limit number of symbols to process |
| `--start-stockid N` | 1 | Start from specific stockid |
| `--mode` | standard | Analysis mode (quick/standard/comprehensive) |
| `--dry-run` | False | Show symbols without processing |
| `--output-dir DIR` | /tmp/sweep_compact | Output directory |

### Examples

#### Test Run (5 Symbols)

```bash
python scripts/sweep_compact_cache.py --limit 5 --parallel 2 --output-dir /tmp/test_sweep
```

**Output**:
```
Fetching symbols with is_sec_filing=true...
Starting sweep of 5 symbols...
Output directory: /tmp/test_sweep
Parallel workers: 2
Mode: standard
  Running batch analysis...
Completed 5/5 analyses
Sweep complete!
```

#### Production Run (All Symbols)

```bash
# Create output directory
mkdir -p /data/sweep_compact

# Run full sweep with 8 parallel workers
python scripts/sweep_compact_cache.py \
    --parallel 8 \
    --output-dir /data/sweep_compact \
    --mode standard
```

#### Resume from Interruption

```bash
# If sweep was interrupted at stockid 500, resume from there
python scripts/sweep_compact_cache.py \
    --parallel 8 \
    --start-stockid 501 \
    --output-dir /data/sweep_compact
```

#### Quick Mode (Faster Processing)

```bash
# Use quick mode for faster processing (technical only)
python scripts/sweep_compact_cache.py \
    --parallel 8 \
    --mode quick \
    --output-dir /data/sweep_quick
```

## Output Files

### Individual Symbol Files

**Naming**: `{SYMBOL}_{YYYYMMDD_HHMMSS}.json`

**Format**: `analysis.compact.v1`

**Size**: ~2KB per symbol (vs ~15KB standard format)

**Example**:
```json
{
  "schema_version": "analysis.compact.v1",
  "symbol": "AAPL",
  "mode": "standard",
  "price": {
    "current": 264.58,
    "target": 470.40,
    "expected_return_pct": 77.79
  },
  "recommendation": {
    "action": "buy",
    "confidence_score": "HIGH"
  },
  "valuation": {
    "blended_fair_value": 470.40,
    "models": {
      "pe": {"fair_value_per_share": 424.54, "weight": 0.5925},
      "ev_ebitda": {"fair_value_per_share": 526.45, "weight": 0.51}
    }
  }
}
```

### Summary Files

**1. Batch Summary** (from victor-invest CLI):
- `batch_summary_{YYYYMMDD_HHMMSS}.json`
- Contains: symbols, mode, completed count, failed count, failures

**2. Sweep Summary** (from script):
- `sweep_summary_{YYYYMMDD_HHMMSS}.json`
- Contains: start_time, end_time, total_symbols, parallel_workers, mode, output_dir

### Log File

**File**: `sweep_log_{YYYYMMDD_HHMMSS}.txt`

Contains sweep execution details.

## Performance

### Processing Speed

| Parallel Workers | Symbols/Second | Time for 3,719 Symbols |
|-----------------|----------------|----------------------|
| 2 | ~0.7 | ~89 minutes |
| 4 | ~1.3 | ~48 minutes |
| 8 | ~2.0 | ~31 minutes |
| 16 | ~2.5 | ~25 minutes |

### Disk Space

| Format | Size Per Symbol | Total for 3,719 Symbols |
|--------|----------------|------------------------|
| Compact | ~2KB | ~7.4MB |
| Standard | ~15KB | ~55.7MB |

**Savings**: ~87% disk space reduction with compact format

## Database Query

The script uses this query to get symbols:

```sql
SELECT s.ticker as symbol
FROM symbol s
WHERE s.is_sec_filing = true
AND s.stockid >= :start_stockid
ORDER BY s.stockid
```

**Total Symbols**: 3,719 (as of 2026-02-22)

## Web UI Integration

After running the sweep, compact format files can be:

1. **Loaded into UI Cache**:
```python
import json
from pathlib import Path

compact_file = Path('/data/sweep_compact/AAPL_20260222_183143.json')
with open(compact_file, 'r') as f:
    compact_data = json.load(f)

# Save to UI cache
from victor_invest.api.app import _save_ui_cache
_save_ui_cache('AAPL', compact_data, 'sweep_compact')
```

2. **Accessed via Web UI API**:
```bash
GET /ui/api/analysis/AAPL/latest
```

3. **Displayed in Web UI**:
- Frontend loads compact format from cache
- API transforms to UI view
- Components render charts and recommendations

## Monitoring Progress

### Check Progress During Sweep

```bash
# Count processed files
ls -1 /tmp/sweep_compact/*.json | wc -l

# Check latest files
ls -lt /tmp/sweep_compact/*.json | head -5

# Monitor batch summary
cat /tmp/sweep_compact/batch_summary_*.json | jq '.completed'
```

### Resume from Interruption

If sweep is interrupted:

1. **Find last processed stockid**:
```bash
# Get the highest stockid from completed files
ls /tmp/sweep_compact/*.json | grep -oE '[0-9]{8}' | sort -n | tail -1
```

2. **Resume from next stockid**:
```bash
python scripts/sweep_compact_cache.py \
    --start-stockid <NEXT_STOCKID> \
    --parallel 8 \
    --output-dir /tmp/sweep_compact
```

## Troubleshooting

### Issue: Script Fails to Import

**Error**: `ModuleNotFoundError: victor_invest`

**Solution**:
```bash
# Ensure you're in the project root
cd /path/to/victor-invest

# Install in editable mode
pip install -e .
```

### Issue: Database Connection Error

**Error**: `connection to server at "localhost" (port 5432) failed`

**Solution**:
```bash
# Check PostgreSQL is running
pg_ctl status

# Start PostgreSQL if needed
pg_ctl start
```

### Issue: Out of Memory

**Error**: `MemoryError` or system hangs

**Solution**:
```bash
# Reduce parallel workers
python scripts/sweep_compact_cache.py --parallel 2

# Or process in batches
python scripts/sweep_compact_cache.py --limit 1000
python scripts/sweep_compact_cache.py --limit 1000 --start-stockid 1001
python scripts/sweep_compact_cache.py --limit 1000 --start-stockid 2001
```

### Issue: Slow Processing

**Solution**:
```bash
# Use quick mode (technical only)
python scripts/sweep_compact_cache.py --mode quick

# Or increase parallel workers
python scripts/sweep_compact_cache.py --parallel 16
```

## Best Practices

1. **Test First**: Always do a small test run before full sweep
   ```bash
   python scripts/sweep_compact_cache.py --limit 5 --dry-run
   python scripts/sweep_compact_cache.py --limit 5
   ```

2. **Use Appropriate Parallel Workers**:
   - Development: 2-4 workers
   - Production: 8-16 workers
   - Limited RAM: 2-4 workers

3. **Monitor Progress**:
   - Check output directory periodically
   - Monitor system resources (CPU, RAM, disk)

4. **Backup Results**:
   - Copy output to permanent location after sweep
   - Keep summary files for audit trail

5. **Schedule Regular Sweeps**:
   - Daily incremental sweep (new symbols only)
   - Weekly full sweep (all symbols)
   - Use cron or systemd timer for automation

## Automation

### Cron Job (Daily Incremental Sweep)

```bash
# Add to crontab: crontab -e
0 2 * * * cd /path/to/victor-invest && python scripts/sweep_compact_cache.py --parallel 8 --output-dir /data/sweep_compact >> /var/log/sweep_compact.log 2>&1
```

### Systemd Timer (Production)

**File**: `/etc/systemd/system/sweep-compact.service`
```ini
[Unit]
Description=Sweep Compact Cache
After=network.target postgresql.service

[Service]
Type=oneshot
User=victor
WorkingDirectory=/path/to/victor-invest
ExecStart=/path/to/venv/bin/python scripts/sweep_compact_cache.py --parallel 8 --output-dir /data/sweep_compact

[Install]
WantedBy=multi-user.target
```

**File**: `/etc/systemd/system/sweep-compact.timer`
```ini
[Unit]
Description=Daily Compact Cache Sweep
Requires=sweep-compact.service

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
systemctl enable sweep-compact.timer
systemctl start sweep-compact.timer
```

## Summary

The `sweep_compact_cache.py` script provides:

✅ **Automated Cache Population**: Process all 3,719 SEC-filing symbols
✅ **Compact Format**: Web UI-compatible `analysis.compact.v1` schema
✅ **Parallel Processing**: Configurable parallel workers for speed
✅ **Resume Capability**: Start from specific stockid to resume
✅ **Progress Monitoring**: Summary files and logs for tracking
✅ **Production Ready**: Can be automated with cron or systemd

For more information, see:
- `COMPACT_FORMAT_SUPPORT.md` - Compact format feature documentation
- `WEB_UI_INTEGRATION_TEST.md` - Web UI integration test results
- `BATCH_PROCESSING_TEST.md` - Batch processing test results

# Web UI Cache Sweep

**Populate `artifacts/ui_cache/` with compact format analysis for web UI**

---

## 🚀 Quick Start

```bash
# Test run (10 symbols)
python scripts/sweep_ui_cache.py --dry-run --limit 10

# Small batch (100 symbols)
python scripts/sweep_ui_cache.py --limit 100 --parallel 4

# Full sweep (all 3,719 SEC symbols)
python scripts/sweep_ui_cache.py --parallel 8
```

---

## 📊 How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  1. QUERY DATABASE                                          │
│     SELECT ticker FROM symbol WHERE is_sec_filing = true  │
│     ORDER BY stockid                                          │
│     → 3,719 symbols                                         │
└────────────┬────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  2. RUN BATCH ANALYSIS                                     │
│     victor-invest batch {symbols} --detail compact          │
│     → Parallel processing (N workers)                       │
│     → ~2 seconds per symbol                                 │
└────────────┬────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  3. SAVE TO UI CACHE                                        │
│     artifacts/ui_cache/{SYMBOL}.json                       │
│     → Compact format (~2KB per symbol)                      │
│     → schema: "analysis.compact.v1"                          │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Command Options

| Option | Default | Description |
|--------|---------|-------------|
| `--parallel N` | 4 | Number of parallel workers |
| `--limit N` | None | Limit symbols (for testing) |
| `--start-stockid N` | 1 | Resume from stockid |
| `--mode` | standard | quick/standard/comprehensive |
| `--dry-run` | False | Show symbols without processing |

---

## 📈 Performance

| Workers | Time for All Symbols (3,719) | Symbols/Second |
|---------|-------------------------------|----------------|
| 2 | ~31 min | ~2.0 |
| 4 | ~15 min | ~4.0 |
| 8 | ~8 min | ~7.7 |
| 16 | ~4 min | ~15.5 |

---

## 📁 Cache Files

### Location
```
artifacts/ui_cache/
├── AAPL.json
├── MSFT.json
├── GOOGL.json
└── ... (3,719 files)
```

### File Format
```json
{
  "symbol": "AAPL",
  "cached_at": "2026-02-23T00:00:00Z",
  "source": "sweep_ui_cache",
  "payload": {
    "schema_version": "analysis.compact.v1",
    "symbol": "AAPL",
    "price": {"current": 264.58, "target": 470.40},
    "recommendation": {"action": "buy"},
    "valuation": {"blended_fair_value": 470.40}
  }
}
```

---

## ✅ Verification

```bash
# Check cache files
ls -la artifacts/ui_cache/*.json | wc -l

# Verify format
python3 -c "
import json
d = json.load(open('artifacts/ui_cache/AAPL.json'))
print('Schema:', d['payload']['schema_version'])
print('Price:', d['payload']['price']['current'])
"

# Web UI loads from cache
curl http://localhost:8000/ui/api/analysis/AAPL/latest
```

---

## 🔄 Automation

### Cron Job
```bash
0 2 * * * cd /path/to/victor-invest && python scripts/sweep_ui_cache.py --parallel 8
```

### Resume from Interruption
```bash
# If stopped at stockid 1000
python scripts/sweep_ui_cache.py --start-stockid 1001 --parallel 8
```

---

## 📊 Metrics

| Metric | Value |
|--------|-------|
| **Total Symbols** | 3,719 |
| **File Size** | ~2KB per symbol |
| **Total Space** | ~7.4MB |
| **Web UI Load Time** | ~50ms (instant) |

---

## 🔗 Related

- [CLI Commands](../user/cli-commands.md) - CLI usage
- [Architecture](../developer/architecture.md) - Cache system design
- [Compact Format](../user/cli-commands.md#compact-format) - Format details

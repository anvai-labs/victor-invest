# Quick Reference

**Common commands and patterns**

---

## 💻 CLI Commands

```
┌─────────────────────────────────────────────────────────────┐
│  SINGLE SYMBOL                                                │
├─────────────────────────────────────────────────────────────┤
│  victor-invest analyze AAPL                                 │
│  victor-invest analyze AAPL --mode standard               │
│  victor-invest analyze AAPL --detail compact --output results/│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  BATCH PROCESSING                                            │
├─────────────────────────────────────────────────────────────┤
│  victor-invest batch AAPL MSFT GOOGL                        │
│  victor-invest batch AAPL MSFT GOOGL --parallel 4            │
│  victor-invest batch AAPL MSFT GOOGL --detail compact         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  SECTOR MULTIPLES                                             │
├─────────────────────────────────────────────────────────────┤
│  victor-invest sector-multiples compare AAPL MSFT GOOGL       │
│  victor-invest sector-multiples timeline Technology            │
│  victor-invest sector-multiples refresh                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Analysis Modes

| Mode | What It Does | Time |
|------|--------------|------|
| `quick` | Technical indicators only | ~30s |
| `standard` | Technical + Fundamental | ~1min |
| `comprehensive` | All agents + LLM synthesis | ~5min |

---

## 📁 Output Formats

```
┌─────────────────────────────────────────────────────────────┐
│  --detail LEVEL                                                │
├──────────────┬──────────────┬──────────────┬──────────────┤
│  minimal      │  standard     │  compact      │  verbose     │
│  Executive    │  Investor    │  Machine-     │  Everything  │
│  summary      │  decision     │  readable     │              │
│  (~5 lines)   │  (~50 lines)  │  (~100 lines)  │ (~500 lines)  │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**Recommendation**: Use `compact` for web UI, `standard` for CLI.

---

## 🗂️ Database Queries

### Check Data Availability

```sql
-- SEC filings with EBITDA data
SELECT COUNT(*) FROM sec_companyfacts_processed
WHERE depreciation_amortization IS NOT NULL;

-- Symbol list
SELECT ticker FROM symbol
WHERE is_sec_filing = true
ORDER BY stockid
LIMIT 10;

-- Market data points
SELECT COUNT(*) FROM market_data
WHERE symbol = 'AAPL';
```

---

## 🔧 Maintenance

```
┌─────────────────────────────────────────────────────────────┐
│  CACHE MANAGEMENT                                             │
├─────────────────────────────────────────────────────────────┤
│  # Warm cache                                                 │
│  curl -X POST http://localhost:8000/cache/warm \          │
│    -H "Content-Type: application/json" \                    │
│    -d '{"symbols": ["AAPL", "MSFT"]}'                       │
│                                                              │
│  # Cache stats                                                │
│  curl http://localhost:8000/cache/stats                     │
│                                                              │
│  # Clear symbol cache                                        │
│  curl -X DELETE http://localhost:8000/cache/symbol/AAPL      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  WEB UI CACHE SWEEP                                           │
├─────────────────────────────────────────────────────────────┤
│  # Full sweep (all 3,719 symbols)                           │
│  python scripts/sweep_ui_cache.py --parallel 8              │
│                                                              │
│  # Limited test                                              │
│  python scripts/sweep_ui_cache.py --limit 100 --dry-run     │
│                                                              │
│  # Resume from interruption                                 │
│  python scripts/sweep_ui_cache.py --start-stockid 1000      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Unit tests only
pytest tests/ -v -m unit

# Skip slow tests
pytest tests/ -v -m "not slow"

# Single test file
pytest tests/unit/victor_invest/ -v

# Coverage
pytest --cov=src/investigator --cov=victor_invest tests/
```

---

## 📊 Monitoring

```bash
# Check cache size
du -sh artifacts/ui_cache/

# Count cache files
ls -1 artifacts/ui_cache/*.json | wc -l

# Latest cache files
ls -lt artifacts/ui_cache/*.json | head -10

# Monitor Ollama
curl http://localhost:11434/api/tags
```

---

## 🚨 Quick Fixes

| Problem | Fix |
|---------|-----|
| Database not running | `pg_ctl start` |
| Ollama not responding | `ollama serve` |
| Import error | `cd /path/to/victor-invest` |
| Module not found | `pip install -e ".[dev]"` |
| Cache empty | `python scripts/sweep_ui_cache.py` |

---

## 🔗 Key Files

| File | Purpose |
|------|---------|
| `config.yaml` | Configuration |
| `victor_invest/cli.py` | CLI entry point |
| `victor_invest/workflows/*.yaml` | Workflow definitions |
| `artifacts/ui_cache/` | Web UI cache |
| `logs/` | Application logs |

---

## 📚 Documentation

- [Getting Started](docs/user/getting-started.md) - Installation
- [CLI Commands](docs/user/cli-commands.md) - Command reference
- [Architecture](docs/developer/architecture.md) - System design
- [Troubleshooting](docs/user/troubleshooting.md) - Common issues

---

## 🎯 Sector Weights Quick Reference

```
Semiconductors → PE=40%, EV/EBITDA=60%
Insurance     → PE=30%, P/B=65%, EV/EBITDA=5%
Banks          → PE=80%, EV/EBITDA=20%
Technology     → PE=55%, EV/EBITDA=45%
Healthcare     → PE=30%, EV/EBITDA=70%
```

---

## ⚡ Performance Tips

1. **Use `quick` mode** for rapid screening
2. **Use `--parallel 8`** for batch processing
3. **Use `--detail compact`** for web UI
4. **Warm cache** before web UI access
5. **Use `--mode standard`** for investment decisions

---

**Last Updated**: 2026-02-22

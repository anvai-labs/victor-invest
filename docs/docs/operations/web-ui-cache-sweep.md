# Web UI Cache Sweep

**Prepopulate web UI cache for all symbols**

---

## 🔄 Cache Sweep Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Query Symbols (3,719 total)  →  Run Analysis  →  Save Cache│
│  is_sec_filing = true           victor-invest       artifacts/ui_cache/│
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Run Sweep

```bash
# Full sweep (all symbols)
python scripts/sweep_ui_cache.py --parallel 8

# From specific stockid
python scripts/sweep_ui_cache.py --min-stockid 100 --parallel 8

# Test with limited symbols
python scripts/sweep_ui_cache.py --limit 10
```

---

## 📊 Performance

```
┌─────────────────────────────────────────────────────────────┐
│  Symbols    │  Time (parallel=8)  │  Cache Size             │
├─────────────────────────────────────────────────────────────┤
│  10         │  ~2 minutes         │  ~20 KB                 │
│  100        │  ~10 minutes        │  ~200 KB                │
│  3,719      │  ~4 hours           │  ~7 MB                  │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Verification

```bash
# Check cache directory
ls -lh artifacts/ui_cache/ | head -20

# Count files
ls -1 artifacts/ui_cache/*.json | wc -l

# Check file format
cat artifacts/ui_cache/AAPL.json | jq '.schema'
```

---

## 🔧 Options

```
┌─────────────────────────────────────────────────────────────┐
│  Option          │  Default  │  Description                 │
├─────────────────────────────────────────────────────────────┤
│  --parallel      │  8        │  Parallel workers            │
│  --min-stockid   │  1        │  Start from stockid          │
│  --limit         │  None     │  Max symbols to process      │
│  --mode          │  standard │  Analysis mode               │
│  --detail        │  compact  │  Output format               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔗 Related

- [Operations Runbook](runbook.md) - Deployment guide
- [Web UI](../user/ui-dashboard.md) - Dashboard guide

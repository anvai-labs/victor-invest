# User Guide

## 🚀 Quick Start

### Installation
```bash
git clone https://github.com/vjsingh1984/victor-invest.git
cd victor-invest
pip install -e ".[dev]"
```

### First Analysis
```bash
victor-invest analyze AAPL
```

### Web UI
```bash
uvicorn victor_invest.api.app:app --reload --port 8000
open http://localhost:8000/dashboard
```

---

## 📊 Analysis Modes

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│   QUICK      │   STANDARD   │COMPREHENSIVE│   CUSTOM     │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ Technical    │ Technical +  │ All agents   │ Custom YAML  │
│ indicators   │ Fundamental  │ + Synthesis   │ workflow      │
│              │              │              │              │
│ ~30 seconds  │ ~1 minute    │ ~5 minutes    │ Varies       │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

### Mode Selection Guide

| Your Need | Use Mode |
|-----------|----------|
| Quick price check | **quick** |
| Investment decision | **standard** |
| Deep analysis | **comprehensive** |
| Custom workflow | Create YAML file |

---

## 💻 CLI Commands

### Single Symbol

```bash
# Basic usage
victor-invest analyze AAPL

# With mode
victor-invest analyze AAPL --mode standard

# With output
victor-invest analyze AAPL --output results/

# With compact format (for web UI)
victor-invest analyze AAPL --detail compact --output results/
```

### Batch Processing

```bash
# Multiple symbols
victor-invest batch AAPL MSFT GOOGL

# With parallel processing
victor-invest batch AAPL MSFT GOOGL --parallel 4

# With mode and output
victor-invest batch AAPL MSFT GOOGL --mode quick --output-dir results/
```

### Sector Multiples

```bash
# Compare sector multiples
victor-invest sector-multiples compare AAPL MSFT GOOGL

# Generate timeline
victor-invest sector-multiples timeline Technology --multiples pe,ev_ebitda

# Refresh sector data
victor-invest sector-multiples refresh
```

### Web UI Cache Sweep

```bash
# Populate web UI cache (all 3,719 SEC symbols)
python scripts/sweep_ui_cache.py --parallel 8

# Test run
python scripts/sweep_ui_cache.py --dry-run --limit 10

# Limited sweep
python scripts/sweep_ui_cache.py --limit 100 --parallel 4
```

---

## 🌐 Web Dashboard

### Features

```
┌─────────────────────────────────────────────────────┐
│  ANALYSIS        RANKINGS         HISTORY         │
│  • Single symbol • Top/Bottom       • Recent       │
│  • Compare       • By Sector        • By Symbol    │
│  • Watchlist     • By Valuation    • Performance  │
└─────────────────────────────────────────────────────┘
```

### URL Routes

| Page | URL |
|------|-----|
| Dashboard | `/dashboard` |
| Analysis | `/dashboard?symbol=AAPL` |
| Rankings | `/rankings` |
| Compare | `/compare?symbols=AAPL,MSFT,GOOGL` |
| History | `/history` |

---

## 📖 Detailed Guides

- [Getting Started](#getting-started) - Installation and setup
- [CLI Commands](#cli-commands) - Complete command reference
- [Web Dashboard](#web-dashboard) - UI features and usage

---

## ❓ Frequently Asked Questions

**Q: Which CLI should I use?**
A: Use `victor-invest` (primary). `investigator` is legacy.

**Q: How do I get web UI data?**
A: Run `python scripts/sweep_ui_cache.py` to prepopulate cache.

**Q: What's compact format?**
A: Optimized JSON for web UI (~87% smaller than standard).

**Q: How long does analysis take?**
A: Quick: ~30s, Standard: ~1min, Comprehensive: ~5min.

---

## 🆘 Troubleshooting

### Common Errors

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: victor-ai` | `pip install 'victor-ai>=0.5.0,<0.6.0'` |
| Database connection failed | `pg_ctl start` (PostgreSQL) |
| Ollama not responding | `ollama serve` |
| Cache empty | Run `python scripts/sweep_ui_cache.py` |

→ Full guide: [TROUBLESHOOTING.md](troubleshooting.md)

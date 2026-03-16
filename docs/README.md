# Victor Invest Documentation

**AI-Powered Investment Analysis Platform**

---

## 📑 Navigation

```
┌─────────────────────────────────────────────────────────────┐
│  [USER DOCS]         │  [DEVELOPER]      │  [TECHNICAL]     │
│  Getting Started     │  Architecture     │  Valuation       │
│  CLI Commands        │  Development      │  Data Pipeline   │
│  Troubleshooting     │  System Diagram   │  Sector Multiples│
├─────────────────────────────────────────────────────────────┤
│  [API]              │  [OPERATIONS]      │  [ARCHIVE]       │
│  API Reference      │  Runbook          │  Old Docs        │
│                     │  Cache Sweep      │                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

```bash
# Install
pip install -e ".[dev]"

# Start services
pg_ctl start && ollama serve

# Analyze
victor-invest analyze AAPL --mode standard

# Web UI
uvicorn victor_invest.api.app:app --reload
# Open: http://localhost:8000/ui
```

---

## 📚 Documentation

### User Documentation
- [Getting Started](user/getting-started.md) - Installation guide
- [CLI Commands](user/cli-commands.md) - Command reference
- [Troubleshooting](user/troubleshooting.md) - Common issues

### Developer Documentation
- [Architecture](developer/architecture.md) - System design
- [Development](developer/development.md) - Dev workflow
- [System Diagram](developer/system-diagram.md) - Visual diagrams
- [Platform Review and Roadmap](developer/platform-review-roadmap.md) - Tiered assessment and execution plan

### Technical Documentation
- [Valuation Methods](technical/valuation-methods.md) - Model assumptions
- [Data Pipeline](technical/data-pipeline.md) - Data flow
- [Sector Multiples](technical/sector-multiples.md) - Comparison tool

### API & Operations
- [API Reference](api/api-reference.md) - REST endpoints
- [Operations Runbook](operations/runbook.md) - Deployment guide
- [Cache Sweep](operations/web-ui-cache-sweep.md) - Cache operations

---

## 📊 Analysis Modes

```
┌─────────────────────────────────────────────────────────────┐
│  Mode          │  Scope              │  Time   │  Output    │
├─────────────────────────────────────────────────────────────┤
│  quick         │  Technical only     │  ~30s   │  Console   │
│  standard      │  Tech + Fundamental │  ~1min  │  JSON      │
│  comprehensive │  All + LLM synthesis│  ~5min  │  Report    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🆘 Quick Help

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | `pip install -e ".[dev]"` |
| Database failed | `pg_ctl start` |
| Ollama not responding | `ollama serve` |
| Cache empty | `python scripts/sweep_ui_cache.py` |

---

**Last Updated**: 2026-03-15

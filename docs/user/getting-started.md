# Getting Started

**Installation & first analysis**

---

## 📦 Prerequisites

```
┌─────────────────────────────────────────────────────────────┐
│  Python 3.11+     │  PostgreSQL 14+     │  Ollama           │
│  (python.org)     │  (postgresql.org)   │  (ollama.com)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation

```bash
# Install
pip install -e ".[dev]"

# Setup git hooks
./scripts/setup-git-hooks.sh
```

---

## ⚙️ Services

```bash
# Start PostgreSQL
pg_ctl start

# Start Ollama
ollama serve

# Optional: Pull model
ollama pull qwen2.5-coder-tools:32b-262K
```

---

## ✅ Verify

```bash
# Check CLI
victor-invest --help

# Quick test
victor-invest analyze AAPL --mode quick
```

---

## 🎯 First Analysis

```bash
# Technical only (~30s)
victor-invest analyze AAPL --mode quick

# Standard (~1 min)
victor-invest analyze AAPL --mode standard

# Comprehensive (~5 min)
victor-invest analyze AAPL --mode comprehensive

# With compact output (for web UI)
victor-invest analyze AAPL --mode standard --detail compact
```

---

## 🌐 Web UI

```bash
# Start server
uvicorn victor_invest.api.app:app --reload

# Open browser
open http://localhost:8000/dashboard
```

---

## 📊 Populate Cache

```bash
# Prepopulate web UI cache (all 3,719 symbols)
python scripts/sweep_ui_cache.py --parallel 8
```

---

## 🔗 Next Steps

- [CLI Commands](cli-commands.md) - Full reference
- [Troubleshooting](troubleshooting.md) - Common issues
- [Development](../developer/development.md) - Dev setup

# Getting Started

**Installation & first analysis**

---

## 📦 Prerequisites

```
┌─────────────────────────────────────────────────────────────┐
│  Python 3.11+     │  PostgreSQL 14+     │  Ollama           │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation

```bash
# Install
pip install -e ".[dev]"

# Git hooks
./scripts/setup-git-hooks.sh
```

---

## ⚙️ Services

```bash
# Start services
pg_ctl start
ollama serve
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
# Technical (~30s)
victor-invest analyze AAPL --mode quick

# Standard (~1 min)
victor-invest analyze AAPL --mode standard

# Compact (for web UI)
victor-invest analyze AAPL --mode standard --detail compact
```

---

## 🌐 Web UI

```bash
# Start server
uvicorn victor_invest.api.app:app --reload

# Open
open http://localhost:8000/dashboard
```

---

## 🔗 Next Steps

- [CLI Commands](cli-commands.md) - Full reference
- [Troubleshooting](troubleshooting.md) - Common issues

# Troubleshooting

**Common issues & quick fixes**

---

## 🚨 Quick Fixes

```
┌─────────────────────────────────────────────────────────────┐
│  Problem                    │  Solution                     │
├─────────────────────────────────────────────────────────────┤
│  ModuleNotFoundError         │  pip install -e ".[dev]"     │
│  Database connection failed │  pg_ctl start                 │
│  Ollama not responding       │  ollama serve                 │
│  Cache empty / miss          │  python scripts/sweep_ui_cache.py│
│  Permission denied           │  chmod +x scripts/*.sh        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Diagnostics

```bash
# Health check
curl http://localhost:8000/api/health

# Database status
pg_ctl status

# Ollama status
curl http://localhost:11434/api/tags

# Cache stats
curl http://localhost:8000/cache/stats
```

---

## 📋 Error Patterns

| Error | Cause | Fix |
|-------|-------|-----|
| `relation "symbol" does not exist` | Wrong database | Check `DATABASE_URL` |
| `Connection refused` | Service not running | Start PostgreSQL/Ollama |
| `Cache miss` | No cached data | Run cache sweep |
| `KeyError: 'fiscal_period'` | Missing cache key | Clear cache, re-run |

---

## 🔗 Related

- [Operations Runbook](../operations/runbook.md) - Deployment guide
- [Getting Started](getting-started.md) - Installation

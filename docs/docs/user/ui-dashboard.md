# Web UI Dashboard

**Browser-based investment analysis**

---

## 🚀 Launch

```bash
# Development
uvicorn victor_invest.api.app:app --reload

# Production
uvicorn victor_invest.api.app:app --host 0.0.0.0 --port 8000
```

**Access**: http://localhost:8000/dashboard

---

## 📊 Features

```
┌─────────────────────────────────────────────────────────────┐
│  Analysis Results  │  Rankings  │  History  │  Compare      │
├─────────────────────────────────────────────────────────────┤
│  • Summary          │  • Top buys       │  • Timeline      │
│  • Fundamental      │  • Top sells      │  • By symbol     │
│  • Technical        │  • By sector      │  • Performance   │
│  • Valuation        │  • Watchlist      │  • Charts        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Cache Loading

```
Priority:
  1. Database (synthesis_results)
  2. UI Cache (artifacts/ui_cache/{SYMBOL}.json)
  3. Logs fallback
```

---

## 🔧 Endpoints

```bash
# Health
GET /api/health

# Analysis
GET /ui/api/analysis/{symbol}/latest

# Rankings
GET /ui/api/rankings

# History
GET /ui/api/history
```

---

## 🔗 Related

- [API Reference](../api/api-reference.md) - Full API docs
- [Cache Sweep](../operations/web-ui-cache-sweep.md) - Cache operations

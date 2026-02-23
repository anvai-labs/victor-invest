# Web UI Dashboard

**Browser-based investment analysis interface**

---

## 🚀 Launch Dashboard

```bash
# Development server
uvicorn victor_invest.api.app:app --reload

# Production
uvicorn victor_invest.api.app:app --host 0.0.0.0 --port 8000
```

**Access**: http://localhost:8000/dashboard

---

## 📊 Dashboard Features

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

## 🎯 Key Pages

### Analysis Results

```
GET /ui/api/analysis/{symbol}/latest
```

**Displays**:
- Summary (action, current price, target)
- Fundamental analysis (valuation models)
- Technical analysis (indicators)
- Investment thesis

### Rankings

```
GET /ui/api/rankings?limit=20
```

**Displays**:
- Top buy/sell recommendations
- Score by sector
- Watchlist performance

### Compare

```
Compare multiple symbols side-by-side
```

**Features**:
- Fundamental metrics
- Technical indicators
- Valuation multiples

---

## 🗄️ Cache System

### Loading Priority

```
┌─────────────────────────────────────────────────────────────┐
│  1. Database (synthesis_results)                            │
│  2. UI Cache (artifacts/ui_cache/{SYMBOL}.json)             │
│  3. Logs fallback                                          │
└─────────────────────────────────────────────────────────────┘
```

### Refresh Cache

```bash
# Single symbol
curl -X POST http://localhost:8000/ui/api/analysis/AAPL/refresh

# Batch sweep
python scripts/sweep_ui_cache.py --parallel 8
```

---

## 🔧 API Endpoints

```bash
# Health check
GET /api/health

# Run analysis
POST /api/analyze/{symbol}

# Get cached result
GET /ui/api/analysis/{symbol}/latest

# Rankings
GET /ui/api/rankings

# History
GET /ui/api/history
```

**Full API Reference**: [API Reference](../api/api-reference.md)

---

## 🔗 Related

- [API Reference](../api/api-reference.md) - Full API docs
- [Cache Sweep](../operations/web-ui-cache-sweep.md) - Cache operations
- [CLI Commands](cli-commands.md) - CLI alternative

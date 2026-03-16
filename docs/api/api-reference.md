# API Reference

**REST API endpoints for victor-invest**

---

## 🚀 Base URL

```
http://localhost:8000
```

Canonical backend routes live at `/health`, `/analyze/{symbol}`, `/batch`, and `/batch/{job_id}`.
Compatibility aliases under `/api/*` are also supported.

For non-local deployment, set `VICTOR_API_BEARER_TOKEN` and send `Authorization: Bearer <token>` to mutating or compute-heavy endpoints such as analysis, batch, cache warm, cache clear, and UI refresh.

---

## 📊 Analysis Endpoints

### Run Analysis

```
POST /analyze/{symbol}
```

**Request**:
```json
{
  "mode": "standard",
  "provider": "ollama",
  "model": "qwen2.5-coder-tools:32b-262K"
}
```

**Response**:
```json
{
  "symbol": "AAPL",
  "mode": "standard",
  "status": "completed",
  "recommendation": {"action": "BUY"},
  "timestamp": "2026-03-15T12:00:00"
}
```

---

### Batch Analysis

```
POST /batch
```

**Request**:
```json
{
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "mode": "standard",
  "parallel": 4
}
```

**Response**:
```json
{
  "submitted": 3,
  "job_id": "batch_20260315_120000",
  "status": "pending"
}
```

### Get Status

```
GET /batch/{job_id}
```

---

## 🌐 Web UI Endpoints

### Get Cached Analysis

```
GET /ui/api/analysis/{symbol}/latest
```

**Response** (Compact Format):
```json
{
  "schema": "compact",
  "summary": {
    "symbol": "AAPL",
    "action": "buy",
    "current_price": 264.58,
    "target_price": 470.40
  },
  "fundamental": {...},
  "technical": {...}
}
```

---

### Refresh Analysis

```
POST /ui/api/analysis/{symbol}/refresh
```

### Symbol History

```
GET /ui/api/analysis/{symbol}/history
```

---

### Rankings

```
GET /ui/api/rankings
```

**Query Params**:
- `limit` (int, default=20)
- `per_sector` (bool, default=false)

**Response**:
```json
{
  "rankings": [
    {"symbol": "AAPL", "score": 85, "action": "buy"},
    {"symbol": "MSFT", "score": 82, "action": "buy"}
  ]
}
```

---

### History

```
GET /ui/api/history?limit=20
```

### UI Health

```
GET /ui/api/health
```

---

## 🗄️ Cache Endpoints

### Warm Cache

```
POST /cache/warm
```

**Request**:
```json
{
  "symbols": ["AAPL", "MSFT"]
}
```

### Get Stats

```
GET /cache/stats
```

**Response**:
```json
{
  "cache_stats": {...},
  "hit_rate": 0.85
}
```

### Clear Symbol Cache

```
DELETE /cache/symbol/{symbol}
```

---

## 🔧 Utility Endpoints

### Health Check

```
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "version": "0.5.0",
  "database": "healthy",
  "cache": "healthy",
  "llm": "healthy"
}
```

### Models List

```
GET /models
```

---

## 📋 Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request |
| 404 | Not Found |
| 500 | Server Error |

---

## 🧪 Testing API

```bash
# Health check
curl http://localhost:8000/health

# Run analysis
curl -X POST http://localhost:8000/analyze/AAPL \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $VICTOR_API_BEARER_TOKEN" \
  -d '{"mode": "quick"}'

# Get cached analysis
curl http://localhost:8000/ui/api/analysis/AAPL/latest

# Symbol history
curl http://localhost:8000/ui/api/analysis/AAPL/history

# Rankings
curl http://localhost:8000/ui/api/rankings?limit=10
```

---

## 🔗 Related

- [Architecture](../developer/architecture.md#api) - API design
- [Cache Sweep](../operations/web-ui-cache-sweep.md) - Cache implementation notes
- [Web Dashboard](../user/ui-dashboard.md) - UI usage

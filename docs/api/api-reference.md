# API Reference

**REST API endpoints for victor-invest**

---

## 🚀 Base URL

```
http://localhost:8000
```

---

## 📊 Analysis Endpoints

### Run Analysis

```
POST /api/analyze/{symbol}
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
  "status": "success",
  "result": {
    "symbol": "AAPL",
    "mode": "standard",
    "recommendation": "BUY",
    "price_target": 470.40
  }
}
```

---

### Batch Analysis

```
POST /api/batch
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
  "job_id": "uuid",
  "status": "running",
  "total": 3
}
```

### Get Status

```
GET /api/batch/{job_id}
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
GET /api/health
```

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "ollama": "connected"
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
curl http://localhost:8000/api/health

# Run analysis
curl -X POST http://localhost:8000/api/analyze/AAPL \
  -H "Content-Type: application/json" \
  -d '{"mode": "quick"}'

# Get cached analysis
curl http://localhost:8000/ui/api/analysis/AAPL/latest

# Rankings
curl http://localhost:8000/ui/api/rankings?limit=10
```

---

## 🔗 Related

- [Architecture](../developer/architecture.md#api) - API design
- [Cache System](../technical/cache-system.md) - Cache implementation
- [Web Dashboard](../user/ui-dashboard.md) - UI usage

# API Reference

**REST API endpoints**

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

---

## 🌐 Web UI Endpoints

### Get Cached Analysis

```
GET /ui/api/analysis/{symbol}/latest
```

**Response**:
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

### Rankings

```
GET /ui/api/rankings?limit=20
```

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

---

## 📋 Response Codes

```
200 → Success
400 → Bad Request
404 → Not Found
500 → Server Error
```

---

## 🔗 Related

- [Web UI](../user/ui-dashboard.md) - Dashboard guide
- [Operations](../operations/runbook.md) - Deployment

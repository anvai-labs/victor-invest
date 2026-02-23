# CLI Commands

**Victor Invest CLI reference**

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

## 🎯 Main Commands

### Analyze

```bash
# Basic analysis
victor-invest analyze AAPL

# With mode
victor-invest analyze AAPL --mode standard

# With output detail
victor-invest analyze AAPL --detail compact

# Save to file
victor-invest analyze AAPL --output results/
```

### Batch

```bash
# Multiple symbols
victor-invest batch AAPL MSFT GOOGL

# With parallel processing
victor-invest batch AAPL MSFT GOOGL --parallel 4

# With mode
victor-invest batch AAPL MSFT GOOGL --mode standard
```

---

## 🔧 Output Detail Levels

```
┌─────────────────────────────────────────────────────────────┐
│  Level      │  Size   │  Use Case                         │
├─────────────────────────────────────────────────────────────┤
│  minimal    │  ~1KB   │  Quick checks                     │
│  standard   │  ~15KB  │  Default output                   │
│  compact    │  ~2KB   │  Web UI integration (recommended)  │
│  verbose    │  ~50KB  │  Full debugging                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📈 Sector Multiples

```bash
# Compare companies
victor-invest sector-multiples compare AAPL MSFT GOOGL

# Generate timeline
victor-invest sector-multiples timeline Technology --multiples pe,ev_ebitda

# Refresh data
victor-invest sector-multiples refresh
```

---

## 🔗 Related

- [Getting Started](getting-started.md) - Installation
- [Web UI](ui-dashboard.md) - Dashboard guide

# Sector Multiples

**Compare sector valuation multiples across companies**

---

## 🎯 Quick Start

```bash
# Compare companies
victor-invest sector-multiples compare AAPL MSFT GOOGL

# Generate timeline
victor-invest sector-multiples timeline Technology --multiples pe,ev_ebitda

# Refresh data
victor-invest sector-multiples refresh
```

---

## 📊 Available Multiples

```
┌─────────────────────────────────────────────────────────────┐
│  VALUATION MULTIPLES                                         │
├─────────────────────────────────────────────────────────────┤
│  P/E        → Price to Earnings                               │
│  P/S        → Price to Sales                                 │
│  P/B        → Price to Book Value                            │
│  EV/Sales   → Enterprise Value to Sales                        │
│  EV/EBITDA  → Enterprise Value to EBITDA                       │
│  P/FCF      → Price to Free Cash Flow                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Sector List

```bash
victor-invest sector-multiples --list-sectors
```

**Output**:
- Technology
- Healthcare
- Financials
- Energy
- Consumer Discretionary
- [15+ more...]

---

## 📈 Timeline Generation

```bash
# Timeline for Technology sector
victor-invest sector-multiples timeline Technology \
  --multiples pe,ev_ebitda \
  --period 3y
```

**Output**: HTML timeline chart showing multiple trends

---

## 🔧 Command Reference

### Compare

```bash
victor-invest sector-multiples compare AAPL MSFT GOOGL \
  --multiples pe,ev_ebitda \
  --benchmark snp500
```

### Refresh

```bash
# All sectors
victor-invest sector-multiples refresh

# Specific sector
victor-invest sector-multiples refresh --sector Technology
```

---

## 📊 Comparison Output

```
┌──────────────────────────────────────────────────────────────┐
│  Symbol │  P/E   │  EV/EBITDA │  P/B   │  P/S   │          │
├─────────┼────────┼────────────┼───────┼──────┼──────────┤
│  AAPL    │  28.5  │  32.1      │ 45.2  │  7.8  │  Growth   │
│  MSFT    │  35.2  │  28.5      │ 12.3  │  10.2 │  Value    │
│  GOOGL   │  25.8  │  20.1      │   6.8  │  5.9  │  Growth   │
└─────────┴────────┴────────────┴───────┴──────┴──────────┘
```

---

## 🎯 Use Cases

1. **Screening**: Find undervalued stocks in a sector
2. **Comparison**: Compare peer multiples
3. **Trends**: Track multiple changes over time
4. **Benchmarks**: Compare to sector/index averages

---

## 🔗 Related

- [Valuation Methods](../technical/valuation-methods.md) - Model details
- [CLI Commands](../user/cli-commands.md) - Complete CLI reference

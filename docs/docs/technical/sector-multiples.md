# Sector Multiples

**Compare sector valuation multiples**

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
│  P/E        →  Price to Earnings                            │
│  P/S        →  Price to Sales                              │
│  P/B        →  Price to Book Value                         │
│  EV/Sales   →  Enterprise Value to Sales                   │
│  EV/EBITDA  →  Enterprise Value to EBITDA                  │
│  P/FCF      →  Price to Free Cash Flow                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Sector List

```bash
victor-invest sector-multiples --list-sectors
```

**Output**: Technology, Healthcare, Financials, Energy, [10+ more]

---

## 📈 Comparison Output

```
┌─────────────────────────────────────────────────────────────┐
│  Symbol │  P/E   │  EV/EBITDA │  P/B   │  Category          │
├─────────┼────────┼────────────┼───────┼───────────────────┤
│  AAPL   │  28.5  │  32.1      │  45.2  │  Growth           │
│  MSFT   │  35.2  │  28.5      │  12.3  │  Value            │
│  GOOGL  │  25.8  │  20.1      │  6.8   │  Growth           │
└─────────┴────────┴────────────┴───────┴───────────────────┘
```

---

## 🔗 Related

- [Valuation Methods](valuation-methods.md) - Model details
- [CLI Commands](../user/cli-commands.md) - Command reference

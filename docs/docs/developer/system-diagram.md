# System Diagram

**Visual system architecture**

---

## 🏗️ Overall Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  USER LAYER                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  CLI         │  │  Web UI      │  │  API         │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
└─────────┼───────────────┼───────────────┼───────────────────┘
          ↓              ↓               ↓
┌─────────┼───────────────┼───────────────┼───────────────────┐
│         ↓              ↓               ↓                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    VICTOR FRAMEWORK                  │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │  │ YAML         │  │ Handlers     │  │ Tools        │ │   │
│  │  │ Workflows    │→→│ (@handler)   │→→│ (Services)   │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                 OUTPUT LAYER                         │   │
│  │  Console  │  JSON Files  │  UI Cache                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Data Flow

```
USER INPUT
   ↓
FETCH STAGE (Handlers + Tools)
  • SEC filings
  • Market data
  • Sector metadata
   ↓
ANALYSIS STAGE (Valuation Models)
  • DCF, GGM, P/E, P/S, P/B, EV/EBITDA
  • Sector-weighted blending
   ↓
SYNTHESIS STAGE
  • Combine signals
  • Generate recommendation
   ↓
OUTPUT STAGE
  • Console / JSON / UI Cache
```

---

## 🔗 Related

- [Architecture](architecture.md) - System design
- [Development](development.md) - Dev workflow

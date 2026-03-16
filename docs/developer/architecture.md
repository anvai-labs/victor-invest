# Architecture Overview

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         VICTOR-INVEST CLI                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ YAML         │  │ Handlers     │  │ Tools        │           │
│  │ Workflows    │→→│ (@handler)   │→→│ (Domain      │           │
│  │              │  │              │  │  Services)   │           │
│  │ quick.yaml   │  │ fundamental  │  │ valuation    │           │
│  │ standard.yaml│  │ technical    │  │ market_data  │           │
│  │ compr...yaml │  │ synthesis    │  │ sector_...   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│         ↓                  ↓                  ↓                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           InvestmentWorkflowProvider (YAML Loader)      │   │
│  └──────────────────────────────────────────────────────────┘   │
│         ↓                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              WorkflowExecutor (StateGraph)              │   │
│  │  • Executes handlers in order                             │   │
│  │  • Passes state between nodes                             │   │
│  │  • Handles async execution                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│         ↓                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         AnalysisWorkflowState (Results)                  │   │
│  │  • fundamental_analysis    • technical_analysis           │   │
│  │  • market_context          • synthesis                   │   │
│  │  • recommendation          • errors                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│         ↓                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │       Compact Format → UI Cache (artifacts/ui_cache/)     │   │
│  │  • schema: "analysis.compact.v1"                         │   │
│  │  • ~2KB per symbol (87% reduction)                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow

### Analysis Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│ 1. INPUT                                                      │
│    Symbol → Mode → Options                                   │
└────────────┬─────────────────────────────────────────────────┘
             ↓
┌──────────────────────────────────────────────────────────────┐
│ 2. FETCH DATA (Handlers + Tools)                             │
│    • SEC filings (via sec_companyfacts_processed)            │
│    • Market data (price history, technicals)                  │
│    • Sector/industry metadata                                │
└────────────┬─────────────────────────────────────────────────┘
             ↓
┌──────────────────────────────────────────────────────────────┐
│ 3. ANALYZE (Valuation Models)                               │
│    • DCF, GGM, P/E, P/S, P/B, EV/EBITDA                       │
│    • Sector-weighted blending (DynamicModelWeightingService) │
│    • Individual model fair values                            │
└────────────┬─────────────────────────────────────────────────┘
             ↓
┌──────────────────────────────────────────────────────────────┐
│ 4. SYNTHESIZE (LLM or Rule-based)                           │
│    • Combine all signals                                      │
│    • Generate recommendation                                   │
│    • Investment thesis                                       │
└────────────┬─────────────────────────────────────────────────┘
             ↓
┌──────────────────────────────────────────────────────────────┐
│ 5. OUTPUT                                                     │
│    • Console display                                          │
│    • JSON file (standard/compact)                            │
│    • UI cache (artifacts/ui_cache/{SYMBOL}.json)             │
└──────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Component Breakdown

### YAML Workflows (`victor_invest/workflows/`)

```
quick/
├── quick.yaml       # Technical analysis only
└── nodes:
    ├── fetch_market_data
    ├── calculate_technicals
    └── display_results

standard/
├── standard.yaml     # Technical + Fundamental
└── nodes:
    ├── fetch_market_data
    ├── calculate_technicals
    ├── run_valuation
    └── display_results

comprehensive/
├── comprehensive.yaml # All agents + LLM synthesis
└── nodes:
    ├── [all standard nodes]
    ├── llm_synthesis
    └── generate_report
```

### Handlers (`victor_invest/handlers.py`)

```
@handler_decorator("fetch_market_data")
→ MarketDataTool → Database queries

@handler_decorator("calculate_technicals")
→ TechnicalIndicatorsTool → RSI, MACD, etc.

@handler_decorator("run_valuation")
→ ValuationTool → DCF, PE, EV/EBITDA models

@handler_decorator("llm_synthesis")
→ Ollama LLM → Investment recommendation
```

### Tools (`victor_invest/tools/`)

```
Domain Service Wrappers:
├── market_data.py           → DatabaseMarketDataFetcher
├── technical_indicators.py  → TechnicalIndicators
├── valuation.py              → ValuationEngine (sector-weighted)
├── sector_multiples.py       → SectorMultiplesTool
└── robust_valuation.py       → RobustValuationService
```

---

## 🗄️ Database Schema

### Key Tables

```
sec_companyfacts_processed     # SEC filing data
├── symbol                     # Ticker
├── fiscal_year, fiscal_period # Reporting period
├── total_revenue              # Revenue
├── net_income                 # Net income
├── operating_income           # Operating income
├── depreciation_amortization  # D&A (for EBITDA)
└── [30+ more fields]

symbol                        # Stock universe
├── stockid                    # Primary key
├── ticker                     # JSON with symbol info
├── is_sec_filing             # Has SEC filings?
└── [more fields]

market_data                   # Price history
├── symbol
├── date
├── open, high, low, close
└── volume

synthesis_results             # Analysis cache
├── symbol
├── recommendation
├── price_target
└── scores
```

---

## 🎯 Sector-Weighted Valuation

```
┌─────────────────────────────────────────────────────────────┐
│  DynamicModelWeightingService                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 1. Get Sector/Industry (CompanyMetadataService)         ││
│  │ 2. Determine Tier (15+ tiers based on sector/industry)  ││
│  │ 3. Apply Model Applicability Rules                       ││
│  │ 4. Assign Weights (from config.yaml tier_weights)         ││
│  │ 5. Normalize to 100%                                     ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘

Example Weights:
├── Semiconductors (NVDA) → PE=40%, EV/EBITDA=60%
├── Insurance (TRV)      → PE=30%, P/B=65%, EV/EBITDA=5%
├── Banks (JPM)          → PE=80%, EV/EBITDA=20%
└── Technology (AAPL)    → PE=55%, EV/EBITDA=45%
```

---

## 🚀 Cache System

### Multi-Tier Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  L1: In-Memory Cache (Python dict)                          │
│  • Fastest access                                          │
│  • Single-session only                                      │
│  • TTL: 5 minutes                                          │
└────────────┬────────────────────────────────────────────────┘
             ↓ (cache miss)
┌─────────────────────────────────────────────────────────────┐
│  L2: Disk Cache (Parquet files)                            │
│  • Persistent across sessions                               │
│  • Located in cache_root/                                   │
│  • TTL: 24 hours                                           │
└────────────┬────────────────────────────────────────────────┘
             ↓ (cache miss)
┌─────────────────────────────────────────────────────────────┐
│  L3: Database (PostgreSQL)                                 │
│  • sec_companyfacts_processed table                        │
│  • synthesis_results table                                  │
│  • Persistent storage                                       │
└─────────────────────────────────────────────────────────────┘
```

### UI Cache

```
artifacts/ui_cache/
├── AAPL.json         # Canonical cache file
├── MSFT.json
├── GOOGL.json
└── {SYMBOL}.json

Format:
{
  "symbol": "AAPL",
  "cached_at": "2026-02-23T00:00:00Z",
  "source": "sweep_ui_cache",
  "payload": {
    "schema_version": "analysis.compact.v1",
    "price": {...},
    "recommendation": {...},
    "valuation": {...}
  }
}
```

---

## 🔌 REST API

### Core Endpoints

```
GET  /health                        # Health check
POST /analyze/{symbol}              # Run analysis
POST /batch                         # Batch analysis
GET  /batch/{job_id}                # Batch status

# Compatibility aliases
GET  /api/health
POST /api/analyze/{symbol}
POST /api/batch
```

### Web UI Endpoints

```
GET  /ui/api/health                     # UI-oriented health payload
GET  /ui/api/analysis/{symbol}/latest   # Load latest cached analysis
GET  /ui/api/analysis/{symbol}/history  # Symbol history rows
POST /ui/api/analysis/{symbol}/refresh  # Refresh analysis
GET  /ui/api/chart/{symbol}             # Chart data
GET  /ui/api/predictions/{symbol}       # RL prediction history
GET  /ui/api/rankings                   # Rankings
GET  /ui/api/history                    # Recent analyses
GET  /ui/api/search                     # Symbol lookup
```

---

## 🧩 Configuration

### Config Structure (`config.yaml`)

```yaml
database:
  stock_db_url: "postgresql://user:pass@localhost/db"
  sec_db_url: "postgresql://user:pass@localhost/db"

ollama:
  host: "localhost"
  port: 11434
  models:
    default: "qwen2.5-coder-tools:32b-262K"

valuation:
  tier_weights:
    insurance_high_quality: {pb: 60, pe: 25, ev_ebitda: 5}
    semiconductor_cyclical: {ev_ebitda: 40, dcf: 25, pe: 25}
    balanced_default: {dcf: 30, pe: 25, ev_ebitda: 20}

  thresholds:
    dcf:
      min_fcf_quarters: 4
      max_wacc: 0.20
```

---

## 📚 Documentation Navigation

```
docs/
├── README.md                 # This file (navigation hub)
├── user/                     # End-user documentation
│   ├── cli-commands.md
│   ├── troubleshooting.md
│   └── getting-started.md
├── developer/                # Developer documentation
│   ├── architecture.md       # This file (detailed)
│   ├── development.md        # Setup, testing, contributing
│   └── workflows.md          # YAML workflow guide
├── technical/                # Technical reference
│   ├── agents.md
│   ├── valuation-methods.md
│   └── cache-system.md
├── api/                       # API documentation
│   └── api-reference.md
└── operations/                # Operations & deployment
    ├── runbook.md
    └── configuration.md
```

---

## 🔗 Related Documentation

- [Development Guide](../developer/development.md) - Setup and contribution
- [Operations Runbook](../operations/runbook.md) - Deployment guide
- [API Reference](../api/api-reference.md) - Complete API documentation
- [VALUATION_METHODS](../technical/valuation-methods.md) - Model details

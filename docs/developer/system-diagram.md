# System Architecture Diagram

**Visual overview of victor-invest system**

---

## 🏗️ Overall Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                          USER LAYER                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  CLI         │  │  Web UI      │  │  API         │  │  Scripts     │    │
│  │  (terminal)  │  │  (browser)   │  │  (REST)      │  │  (utility)   │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼───────────────┼───────────────┼───────────────┼──────────────┘
          │              │               │               │
┌─────────┼───────────────┼───────────────┼───────────────┴───────────────────┐
│         ↓              ↓               ↓                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                    VICTOR-INVEST FRAMEWORK                         │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │ │
│  │  │ YAML         │  │ Handlers     │  │ Tools        │                   │ │
│  │  │ Workflows    │→→│ (@handler)   │→→│ (Domain      │                   │ │
│  │  │              │  │              │  │  Services)   │                   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                   │ │
│  │         ↓                    ↓                  ↓                           │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
│  │  │           InvestmentWorkflowProvider (StateGraph)                 │ │ │
│  │  └───────────────────────────────────────────────────────────────────┘ │ │
│  │                              ↓                                     │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
│  │  │       AnalysisWorkflowState (Results)                           │ │ │
│  │  │  • fundamental_analysis    • technical_analysis                   │ │ │
│  │  │  • market_context          • synthesis                         │ │
│  │  └───────────────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                              ↓                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                    OUTPUT LAYER                                   │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │ │
│  │  │ Console      │  │ JSON Files   │  │ UI Cache     │                   │ │
│  │  │ (terminal)   │  │ (results/)   │  │ (ui_cache/)   │                   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Data Flow

### Input → Output

```
USER INPUT
   ↓
┌─────────────────────────────────────────────┐
│  Symbol → Mode → Options (format, output)  │
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│  FETCH STAGE (Handlers + Tools)            │
│  • SEC filings ( quarterly data)           │
│  • Market data (price, volume)             │
│  • Sector/industry metadata              │
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│  ANALYSIS STAGE (Valuation Models)        │
│  • DCF, GGM, P/E, P/S, P/B, EV/EBITDA        │
│  • Sector-weighted blending                │
│  • Individual model fair values           │
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│  SYNTHESIS STAGE                        │
│  • Combine all signals                    │
│  • Generate recommendation              │
│  • Investment thesis                    │
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│  OUTPUT STAGE                            │
│  • Console display                       │
│  • JSON file (standard/compact)          │
│  • UI cache (artifacts/ui_cache/)        │
└─────────────────────────────────────────────┘
```

---

## 🧩 Component Details

### YAML Workflows

```
victor_invest/workflows/
├── quick.yaml          # Technical only
│   └── nodes: fetch_market_data → calculate_technicals → display
│
├── standard.yaml        # Technical + Fundamental
│   └── nodes: fetch_market_data → calculate_technicals → run_valuation → display
│
└── comprehensive.yaml  # All + LLM synthesis
    └── nodes: [all standard nodes] → llm_synthesis → generate_report
```

### Handler Decorator Pattern

```python
@handler_decorator("run_valuation", vertical="investment")
@dataclass
class ValuationHandler(BaseHandler):
    async def execute(self, node, context, tool_registry):
        # Extract parameters
        symbol = context.get("symbol")
        financials = context.get("fundamental_analysis", {})

        # Call tool
        tool = ValuationTool()
        result = await tool.execute({}, symbol=symbol, financials=financials)

        # Return result
        return {"valuation": result}, 0  # (output_dict, tool_calls_count)
```

---

## 🎯 Sector-Weighted Valuation

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT: Symbol + Financial Data                                 │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  1. Get Sector/Industry (CompanyMetadataService)                   │
│     Query: SELECT sector, industry FROM symbol_metadata            │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Determine Tier (15+ tiers)                                       │
│     • semiconductor_cyclical, insurance_high_quality, etc.        │
│     • Based on: Sector + Industry + ROE + Growth + Size           │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  3. Apply Model Applicability Rules                                   │
│     • DCF: Excluded for Financials                                 │
│     • P/S: Excluded if revenue=0                                     │
│     • P/B: Excluded if book_value=0                                  │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  4. Assign Weights (from config.yaml tier_weights)                  │
│     • Semiconductor: PE=40%, EV/EBITDA=60%                        │
│     • Insurance: PE=30%, P/B=65%, EV/EBITDA=5%                     │
│     • Technology: PE=55%, EV/EBITDA=45%                           │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  5. Normalize to 100%                                              │
│     • Re-distribute filtered weights                           │
│     • Ensure sum = 100%                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Cache System

```
┌─────────────────────────────────────────────────────────────┐
│  REQUEST: Analysis for AAPL                                      │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  L1: In-Memory Cache (Python dict)                              │
│  • Key: tuple(symbol, mode, provider)                         │
│  • TTL: 5 minutes                                             │
│  • Check: `if key in cache`                                    │
└────────────┬──────────────────────────────────────────────────┘
             ↓ (cache miss)
┌─────────────────────────────────────────────────────────────┐
│  L2: Disk Cache (Parquet files)                                │
│  • Location: cache_root/                                     │
│  • File: cache_root/symbol/mode/provider.parquet             │
│  • TTL: 24 hours                                             │
│  • Load: `pd.read_parquet(path)`                              │
└────────────┬──────────────────────────────────────────────────┘
             ↓ (cache miss)
┌─────────────────────────────────────────────────────────────┐
│  L3: Database (PostgreSQL)                                     │
│  • Tables: sec_companyfacts_processed, symbol                │
│  • Queries: SQLAlchemy ORM                                   │
│  • Connection: Async engine with pool                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🌐 Web UI Integration

```
┌─────────────────────────────────────────────────────────────┐
│  Web UI Request: GET /ui/api/analysis/AAPL/latest                │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  Load from Cache (Priority Order):                             │
│  1. Database (synthesis_results table)                          │
│  2. UI Cache (artifacts/ui_cache/AAPL.json)                     │
│  3. Logs fallback                                            │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  Transform to UI View                                           │
│  • Extract: summary, fundamental, technical                    │
│  • Validate: schema_version, required fields                    │
│  • Return: UIView structure                                  │
└────────────┬──────────────────────────────────────────────────┘
             ↓
┌─────────────────────────────────────────────────────────────┐
│  Render to Browser (React Components)                           │
│  • Dashboard cards                                             │
│  • Charts and graphs                                           │
│  • Tables and rankings                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 File Organization

```
victor-invest/
├── cli.py                          # CLI entry point
├── workflows/
│   ├── quick.yaml                   # Workflow definitions
│   ├── standard.yaml
│   └── comprehensive.yaml
├── handlers.py                     # Analysis handlers
├── tools/                          # Domain service wrappers
│   ├── market_data.py
│   ├── technical_indicators.py
│   ├── valuation.py
│   └── sector_multiples.py
├── api/
│   └── app.py                      # FastAPI app
└── escape_hatches.py              # YAML conditionals

src/investigator/
├── domain/
│   ├── services/
│   │   ├── valuation/              # Valuation models
│   │   ├── company_metadata_service/
│   │   └── dynamic_model_weighting.py
│   └── agents/
│       └── fundamental/
└── infrastructure/
    ├── database/
    │   └── db.py                # Database manager
    └── sec/                       # SEC filings
```

---

## 🔗 Related Documentation

- [Development Guide](development.md) - Setup and contribution
- [API Reference](../api/api-reference.md) - Complete API docs
- [Operations Runbook](../operations/runbook.md) - Deployment guide
- [Quick Reference](../QUICK_REFERENCE.md) - Common commands

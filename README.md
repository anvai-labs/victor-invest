# Victor Invest Documentation

**Last Updated:** February 2025

---

## Quick Start

1. **[Getting Started](guides/GETTING_STARTED.md)** - Installation and first steps
2. **[Sector Analysis](assets/insights/SECTOR_ANALYSIS_2015_2024.md)** - 10-year sector valuation analysis
3. **[Interactive Timeline](assets/visualizations/sector_timeline_2024.html)** - Market multiples visualization

---

## Documentation Structure

```
docs/
├── guides/           # Getting started, how-to guides
├── reference/        # Architecture, API, operations
├── insights/         # Analysis, findings, playbooks
├── assets/           # Sector analysis & visualizations
└── archive/          # Historical/obsolete documentation
```

---

## Guides

| Document | Purpose |
|----------|---------|
| [Getting Started](guides/GETTING_STARTED.md) | Installation, setup, first run |
| [Fiscal Year Handling](guides/FISCAL_YEAR_HANDLING.md) | FY periods, timing nuances |
| [Scripts Consolidation](guides/SCRIPTS_CONSOLIDATION_ANALYSIS.md) | Script organization and usage |

---

## Reference

| Document | Purpose |
|----------|---------|
| [Architecture](reference/ARCHITECTURE.md) | System design and components |
| [Victor Framework Migration](reference/MIGRATION_VICTOR_FRAMEWORK.md) | Victor framework overview |
| [Operations Runbook](reference/OPERATIONS_RUNBOOK.md) | Deployment and operations |
| [Agents](reference/AGENTS.md) | Agent system documentation |
| [Sector Multiples](reference/SECTOR_MULTIPLES.md) | Sector multiples tool reference |
| [UI Dashboard](reference/UI_DASHBOARD.md) | Dashboard documentation |

---

## Insights

| Document | Purpose |
|----------|---------|
| [Sector Analysis (2015-2024)](assets/insights/SECTOR_ANALYSIS_2015_2024.md) | Complete 10-year analysis |
| [Market Regimes](assets/insights/MARKET_REGIMES.md) | Three market regimes (2015-2024) |
| [Data Quality](assets/insights/DATA_QUALITY.md) | Data verification and metrics |

### Analysis & Playbooks
- [Valuation Playbook](insights/VALUATION_PLAYBOOK.md) - Valuation frameworks and strategies
- [Valuation Assumptions](insights/VALUATION_ASSUMPTIONS.md) - Key assumptions and constraints
- [STX Analysis Issues](insights/STX_ANALYSIS_ISSUES.md) - STX index analysis
- [Data Pipeline Status](insights/sec_data_pipeline_status.md) - SEC data pipeline
- [Victor Alignment Review](insights/VICTOR_ALIGNMENT_REVIEW_20260211.md) | Framework alignment

---

## Interactive Visualizations

- **[Sector Timeline 2024](assets/visualizations/sector_timeline_2024.html)** - Interactive scatter plots with market cap bubbles

**Features:**
- Sector median lines (P/E, P/S, P/B)
- Individual stock bubbles (500 companies)
- Hover tooltips with company details
- Color-coded by sector

---

## Quick Reference

### CLI Commands

```bash
# Quick analysis
victor-invest analyze AAPL --mode quick

# Batch analysis
victor-invest batch AAPL MSFT GOOGL --parallel 4

# Sector multiples
investor sector-multiples historical --fiscal-year 2024

# Cache management
investigator cache warm --symbols AAPL,MSFT --force-refresh
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `victor_invest/` | Victor framework (workflows, tools) |
| `src/investigator/` | Legacy engine (domain services, agents) |
| `scripts/` | Utility scripts |
| `tests/` | Test suite |
| `config.yaml` | Main configuration file |

---

## Related Resources

- **Project README:** [../README.md](../README.md)
- **Architecture:** [reference/ARCHITECTURE.md](reference/ARCHITECTURE.md)
- **Sector Analysis:** [assets/insights/](assets/insights/)

---

*For CLI help: `victor-invest --help` or `investor --help`*

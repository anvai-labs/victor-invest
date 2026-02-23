# Documentation Structure

**Last Updated:** February 2025

---

## Quick Navigation

### For Users
- **[Getting Started](guides/GETTING_STARTED.md)** - Installation and first steps
- **[Sector Analysis](assets/visualizations/sector_timeline_2024.html)** ⭐ Interactive market multiples visualization

### For Analysis
- **[Sector Analysis (2015-2024)](assets/insights/SECTOR_ANALYSIS_2015_2024.md)** - 10-year sector trends
- **[Market Regimes](assets/insights/MARKET_REGIMES.md)** - Three market regimes (2015-2024)
- **[Valuation Playbook](insights/VALUATION_PLAYBOOK.md)** - Valuation frameworks

### For Developers
- **[Architecture](reference/ARCHITECTURE.md)** - System design and components
- **[Operations Runbook](reference/OPERATIONS_RUNBOOK.md)** - Deployment and operations
- **[Methodology](assets/technical/METHODOLOGY.md)** - Calculation methodology
- **[Tool Reference](assets/technical/TOOL_REFERENCE.md)** - CLI commands and API

---

## Folder Structure

```
docs/
├── README.md                   (This file - navigation)
│
├── guides/                     # Getting started & how-to
│   ├── GETTING_STARTED.md
│   ├── FISCAL_YEAR_HANDLING.md
│   └── SCRIPTS_CONSOLIDATION_ANALYSIS.md
│
├── reference/                  # Architecture, operations, reference
│   ├── ARCHITECTURE.md
│   ├── CLEAN_ARCHITECTURE_MIGRATION.md
│   ├── MIGRATION_VICTOR_FRAMEWORK.md
│   ├── OPERATIONS_RUNBOOK.md
│   ├── DEPLOYMENT.md
│   ├── CLI_DATA_COMMANDS.md
│   ├── AGENTS.md
│   ├── SECTOR_MULTIPLES.md
│   └── UI_DASHBOARD.md
│
├── insights/                   # Analysis & findings
│   ├── VALUATION_PLAYBOOK.md
│   ├── VALUATION_ASSUMPTIONS.md
│   ├── STX_ANALYSIS_ISSUES.md
│   ├── sector_multiples_data_quality_validation.md
│   ├── sec_data_pipeline_status.md
│   └── VICTOR_ALIGNMENT_REVIEW_20260211.md
│
├── assets/                     # Sector analysis & visualizations
│   ├── insights/
│   │   ├── SECTOR_ANALYSIS_2015_2024.md      (10-year analysis)
│   │   ├── MARKET_REGIMES.md                   (Market regimes)
│   │   └── DATA_QUALITY.md                     (Data verification)
│   ├── visualizations/
│   │   └── sector_timeline_2024.html          (Interactive charts)
│   ├── technical/
│   │   ├── METHODOLOGY.md                       (Calculation methods)
│   │   └── TOOL_REFERENCE.md                     (CLI/API)
│   └── README.md
│
└── archive/                    # Historical/obsolete
    ├── EXECUTIVE_SUMMARY.md
    └── MIGRATION_GUIDE.md
```

---

## By Purpose

### Getting Started (3 files)
| File | Description |
|------|-------------|
| [GETTING_STARTED.md](guides/GETTING_STARTED.md) | Installation, setup, first run |
| [FISCAL_YEAR_HANDLING.md](guides/FISCAL_YEAR_HANDLING.md) | FY periods, timing nuances |
| [SCRIPTS_CONSOLIDATION_ANALYSIS.md](guides/SCRIPTS_CONSOLIDATION_ANALYSIS.md) | Script organization |

### Reference (9 files)
| File | Description |
|------|-------------|
| [ARCHITECTURE.md](reference/ARCHITECTURE.md) | System design and components |
| [CLEAN_ARCHITECTURE_MIGRATION.md](reference/CLEAN_ARCHITECTURE_MIGRATION.md) | Architecture migration |
| [MIGRATION_VICTOR_FRAMEWORK.md](reference/MIGRATION_VICTOR_FRAMEWORK.md) | Victor framework |
| [OPERATIONS_RUNBOOK.md](reference/OPERATIONS_RUNBOOK.md) | Deployment and operations |
| [DEPLOYMENT.md](reference/DEPLOYMENT.md) | Deployment guide |
| [CLI_DATA_COMMANDS.md](reference/CLI_DATA_COMMANDS.md) | CLI command reference |
| [AGENTS.md](reference/AGENTS.md) | Agent system |
| [SECTOR_MULTIPLES.md](reference/SECTOR_MULTIPLES.md) | Sector multiples tool |
| [UI_DASHBOARD.md](reference/UI_DASHBOARD.md) | Dashboard UI |

### Insights (7 files)
| File | Description |
|------|-------------|
| [VALUATION_PLAYBOOK.md](insights/VALUATION_PLAYBOOK.md) | Valuation frameworks |
| [VALUATION_ASSUMPTIONS.md](insights/VALUATION_ASSUMPTIONS.md) | Key assumptions |
| [STX_ANALYSIS_ISSUES.md](insights/STX_ANALYSIS_ISSUES.md) | STX index analysis |
| [sector_multiples_data_quality_validation.md](insights/sector_multiples_data_quality_validation.md) | Data quality |
| [sec_data_pipeline_status.md](insights/sec_data_pipeline_status.md) | Pipeline status |
| [VICTOR_ALIGNMENT_REVIEW_20260211.md](insights/VICTOR_ALIGNMENT_REVIEW_20260211.md) | Alignment review |

### Sector Analysis (4 files)
| File | Description |
|------|-------------|
| [SECTOR_ANALYSIS_2015_2024.md](assets/insights/SECTOR_ANALYSIS_2015_2024.md) | 10-year sector analysis |
| [MARKET_REGIMES.md](assets/insights/MARKET_REGIMES.md) | Market regimes (2015-2024) |
| [DATA_QUALITY.md](assets/insights/DATA_QUALITY.md) | Data quality verification |
| [sector_timeline_2024.html](assets/visualizations/sector_timeline_2024.html) | Interactive visualization |

### Technical (2 files)
| File | Description |
|------|-------------|
| [METHODOLOGY.md](assets/technical/METHODOLOGY.md) | Calculation methodology |
| [TOOL_REFERENCE.md](assets/technical/TOOL_REFERENCE.md) | CLI/API reference |

---

## Key Documents by Role

### Investors/Analysts
1. [Sector Analysis 2015-2024](assets/insights/SECTOR_ANALYSIS_2015_2024.md)
2. [Market Regimes](assets/insights/MARKET_REGIMES.md)
3. [Sector Timeline](assets/visualizations/sector_timeline_2024.html)

### Developers
1. [Getting Started](guides/GETTING_STARTED.md)
2. [Architecture](reference/ARCHITECTURE.md)
3. [Operations Runbook](reference/OPERATIONS_RUNBOOK.md)

### Researchers
1. [Valuation Playbook](insights/VALUATION_PLAYBOOK.md)
2. [Methodology](assets/technical/METHODOLOGY.md)
3. [Data Quality](assets/insights/DATA_QUALITY.md)

---

## File Count Summary

| Folder | Files | Purpose |
|--------|-------|---------|
| guides/ | 3 | Getting started |
| reference/ | 9 | Technical reference |
| insights/ | 7 | Analysis & findings |
| assets/ | 7 | Sector analysis & visualizations |
| archive/ | 2 | Historical |
| **Total** | **28** | **Organized by purpose** |

---

*See [../README.md](../README.md) for project overview*

# Victor Invest

Victor Invest is an AI-assisted investment research platform that combines SEC fundamentals, multi-model valuation, technical analysis, market context, and a React dashboard/API surface.

The repo is in a Victor-first transition state:
- `victor_invest/` is the primary workflow, API, and UI integration layer.
- `src/investigator/` still contains most domain logic, data access, and legacy compatibility paths.

## Quick Start

```bash
pip install -e ".[dev]"
uvicorn victor_invest.api.app:app --reload --port 8000
victor-invest analyze AAPL --mode standard
```

Open the UI at `http://localhost:8000/ui`.

## Core Features

- Victor-based workflows for `quick`, `standard`, `comprehensive`, `peer_comparison`, and `rl_backtest`
- SEC filing ingestion and normalized company facts
- Multi-model valuation across DCF, GGM, P/E, P/S, P/B, EV/EBITDA, and sector-specialized models
- Technical indicators, entry/exit signals, and market regime context
- FastAPI service plus React dashboard backed by UI cache artifacts
- Batch analysis, rankings, and RL prediction history

## Canonical Entry Points

```bash
# CLI
victor-invest analyze AAPL --mode standard

# API
uvicorn victor_invest.api.app:app --reload --port 8000

# Frontend
open http://localhost:8000/ui
```

Legacy compatibility aliases still exist, but `victor-invest`, `/ui`, `/health`, `/analyze/{symbol}`, and `/batch` are the canonical paths.

## Repository Layout

- `victor_invest/`: Victor workflows, tools, API, frontend integration
- `src/investigator/`: legacy engine, domain services, infrastructure, CLI groups
- `frontend/`: React dashboard
- `tests/`: unit and integration coverage
- `docs/`: user, developer, operations, and technical documentation

## Documentation

- [Docs Index](docs/README.md)
- [Getting Started](docs/user/getting-started.md)
- [API Reference](docs/api/api-reference.md)
- [Architecture](docs/developer/architecture.md)
- [Platform Review and Roadmap](docs/developer/platform-review-roadmap.md)

## Development

```bash
make format
make lint
make type-check
make test
```

The package metadata points at this `README.md`, so keep this file aligned with the actual active surfaces in `victor_invest/` and `docs/`.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InvestiGator is an AI-powered investment analysis platform that combines SEC financial data, technical indicators, and multi-agent AI synthesis to provide stock evaluations. It uses Clean Architecture with domain-driven design, built on Victor AI Framework for workflow orchestration.

**Key Principle**: This is a Victor-first codebase. Use `victor-invest` CLI and YAML workflows. Legacy paths exist for backwards compatibility but should not be used for new development.

## Common Commands

```bash
# Installation
pip install -e ".[dev,viz,jupyter]"  # Full dev environment
make dev-install                       # Via Makefile

# Primary CLI (Victor-powered)
victor-invest analyze AAPL --mode quick          # Technical only (~5s)
victor-invest analyze AAPL --mode standard       # Tech + Fundamental (~30s)
victor-invest analyze AAPL --mode comprehensive  # Full analysis (~60s)
victor-invest batch AAPL MSFT GOOGL --parallel 4

# System status
victor-invest status
victor-invest cache-sizes
victor-invest clean-cache --symbol AAPL

# Testing
pytest tests/ -v                    # All tests
pytest tests/ -v -m unit            # Unit tests only
pytest tests/ -v -m "not slow"      # Skip slow tests
pytest tests/ -v -m "not llm"       # Skip tests requiring Ollama
pytest tests/unit/domain/test_agents.py -v  # Single file

# Code quality
make format                         # Black + isort
make format-check                   # Check formatting without changes
make lint                           # Flake8
make type-check                     # mypy
make pre-commit                     # All checks
make ci                             # CI pipeline (format-check + lint + type-check + test-cov)

# Git hooks (auto-run on commit)
./scripts/setup-git-hooks.sh        # Install git hooks (runs ruff, black, mypy before commit)
# To bypass: git commit --no-verify

# Makefile shortcuts
make analyze SYMBOL=AAPL            # Run analysis
make analyze-force SYMBOL=AAPL      # Force refresh cache
make batch SYMBOLS="AAPL MSFT"      # Batch analysis
make cache-inspect SYMBOL=AAPL      # Inspect cache
make benchmark-workflows SYMBOL=AAPL  # Benchmark latency budgets
```

## Architecture

### Dual Execution Paths

**Victor Path (Recommended - Primary)**
- Entry: `victor-invest` CLI
- YAML workflows in `victor_invest/workflows/*.yaml`
- Handlers in `victor_invest/handlers.py` using `@handler_decorator` pattern
- Tools in `victor_invest/tools/` implementing Victor `BaseTool`

**Legacy Path (Deprecated - Use Only for Backwards Compatibility)**
- Entry: `investigator` CLI
- Uses `InvestigatorOrchestrator` with multi-agent synthesis
- Will forward to Victor path unless `INVESTIGATOR_LEGACY=1` is set

### Directory Structure

```
src/investigator/                    # Legacy analysis engine (Clean Architecture)
├── domain/           # Core business logic (no external deps)
│   ├── agents/       # SECAgent, TechnicalAgent, FundamentalAgent, SynthesisAgent
│   ├── models/       # Domain objects (analysis, recommendation)
│   └── services/     # Valuation (DCF, P/E, GGM), RL policy, data sources
├── application/      # Use case orchestration
│   ├── orchestrator.py    # Main workflow coordinator (legacy)
│   └── synthesizer.py     # Multi-agent synthesis
├── infrastructure/   # External integrations
│   ├── cache/        # Multi-layer: File/Parquet + RDBMS
│   ├── database/     # SQLAlchemy models, PostgreSQL/SQLite
│   ├── llm/          # Ollama client, multi-server pool
│   └── sec/          # SEC EDGAR API integration
└── interfaces/cli/   # Legacy CLI commands

victor_invest/                       # Victor AI Framework integration (Primary)
├── workflows/        # YAML-defined analysis workflows
│   ├── quick.yaml              # Technical analysis only (~5s)
│   ├── standard.yaml           # Technical + Fundamental (~30s)
│   ├── comprehensive.yaml      # Full institutional-grade (~60s)
│   ├── peer_comparison.yaml    # Relative valuation analysis
│   └── rl_backtest.yaml        # Historical RL training data
├── handlers.py               # Compute node handlers using @handler_decorator
├── escape_hatches.py         # CONDITIONS & TRANSFORMS for YAML workflows
├── tools/                    # Victor tool implementations (BaseTool)
│   ├── sec_filing.py         # SEC data fetching
│   ├── market_data.py        # Price/market data
│   ├── technical_indicators.py # RSI, MACD, etc.
│   └── valuation.py          # DCF, P/E, GGM models
├── vertical/                 # Investment vertical definition (YAML-configured)
│   └── config/
│       ├── vertical.yaml     # Vertical configuration
│       └── investment_system_prompt.txt
├── framework_bootstrap.py    # Shared Victor bootstrap (orchestrator creation)
└── cli.py                    # Victor-powered CLI (primary entry point)
```

## Victor Framework Integration

### InvestmentWorkflowProvider

```python
from victor_invest.workflows import InvestmentWorkflowProvider

provider = InvestmentWorkflowProvider()

# List available workflows
print(provider.get_workflow_names())  # ['quick', 'standard', 'comprehensive', 'peer_comparison', 'rl_backtest']

# Agentic execution (with LLM support)
result = await provider.run_agentic_workflow(
    "comprehensive",
    context={"symbol": "AAPL"},
    provider="ollama",
    model="gpt-oss:20b",
)

# Compute-only execution (no LLM, faster)
result = await provider.run_workflow_with_handlers(
    "standard",
    context={"symbol": "AAPL"},
)
```

### Key Victor Patterns

**1. Handler Registration (`@handler_decorator`)**
```python
from victor.framework.handler_registry import handler_decorator
from victor.framework.workflows.base_handler import BaseHandler

@handler_decorator("fetch_sec_data", vertical="investment", description="Fetch SEC filing data")
@dataclass
class FetchSECDataHandler(BaseHandler):
    async def execute(self, node, context, tool_registry):
        # Handler implementation
        return {"status": "success", "data": {...}}, 0
```

**2. Tool Implementation (Victor BaseTool)**
```python
from victor_invest.tools.base import InvestmentTool
from victor.tools.base import ToolResult

class SECFilingTool(InvestmentTool):
    async def execute(self, _exec_ctx, symbol: str, action: str):
        # Tool implementation
        return ToolResult.create_success(output={...})
```

**3. YAML Workflow Node Types**
```yaml
nodes:
  - id: fetch_data
    type: compute              # Calls handler
    handler: fetch_sec_data
    constraints:
      llm_allowed: false
      timeout: 60

  - id: check_quality
    type: condition            # Uses escape hatch
    condition: "data_quality_check"
    branches:
      "high": synthesize
      "low": request_review

  - id: parallel_analysis
    type: parallel             # Parallel execution
    parallel_nodes: [fundamental, technical]
    join_strategy: all
```

### Handlers vs Escape Hatches vs Tools

- **Handlers** (`victor_invest/handlers.py`): Compute node implementations for YAML workflows
  - Registered via `@handler_decorator` at module load time
  - Referenced in YAML: `handler: fetch_sec_data`
  - Call tools directly (context-stuffing pattern)

- **Escape Hatches** (`victor_invest/escape_hatches.py`): Python functions for conditions/transforms
  - Used in condition nodes: `condition: "data_quality_check"`
  - Returns branch name ("high", "low", etc.)

- **Tools** (`victor_invest/tools/`): Victor tool implementations for data operations
  - Implement Victor `BaseTool` protocol
  - Called by handlers, not directly by YAML

## Context-Stuffing Pattern

**Critical**: Victor workflows use the context-stuffing pattern:
- **Phase 1-2**: Direct tool/handler calls (deterministic, no LLM)
- **Phase 3**: Single LLM inference with all collected data (if needed)

This avoids orchestrator overhead and enables fast, reproducible analysis.

## Framework Bootstrap

**All Victor paths must use shared bootstrap**:
```python
from victor_invest.framework_bootstrap import create_investment_orchestrator

orchestrator = await create_investment_orchestrator(
    provider="ollama",
    model="gpt-oss:20b",
    ensure_handlers=ensure_handlers_registered,
    warning_callback=logger.warning,
)
```

This ensures consistent vertical registration, role provider setup, tool enabling, and handler sync.

## Configuration

- `config.yaml` - Main configuration (database, LLM, analysis settings, ~2300 lines)
- `.env` - Environment variables (DB credentials, API keys)
- Environment variables override config.yaml

Key env vars: `STOCK_DB_*`, `SEC_DB_*`, `OLLAMA_HOST_*`, `DATABASE_URL`

## Test Markers

```python
@pytest.mark.unit           # Fast unit tests (no external dependencies)
@pytest.mark.integration    # Requires DB/API
@pytest.mark.slow           # Long-running tests (may take several minutes)
@pytest.mark.llm            # Requires Ollama
@pytest.mark.db             # Requires database
@pytest.mark.cache          # Cache-related tests
@pytest.mark.performance    # Performance/benchmark tests
```

## Code Style

- **Line length**: 120 (black default)
- **Type hints**: Required on public functions
- **Async-first**: Python 3.11+ with async/await
- **Formatting**: Black + isort (enforced via Makefile and git hooks)
- **Linting**: Flake8 for code style
- **Type checking**: mypy for type safety (configured in pyproject.toml)
- **Python versions**: 3.11, 3.12, 3.13 supported

## Git Hooks

The repository uses git hooks to enforce code quality and commit message standards:

**Setup:**
```bash
./scripts/setup-git-hooks.sh  # Install hooks
git config core.hooksPath .githooks  # Manual alternative
```

**Pre-commit Hook:**
- Runs `ruff format --check` on staged Python files
- Runs `ruff check` for linting
- Runs `mypy` on files in `src/` and `victor_invest/`
- Blocks commit if any check fails

**Commit-msg Hook:**
- Rejects commits with AI model co-author references (Claude, Sonnet, Opus, Haiku)
- Warns about other AI assistance references (non-blocking)

**Bypass Hooks (if needed):**
```bash
git commit --no-verify -m "message"
```

**Uninstall Hooks:**
```bash
git config --unset core.hooksPath
```

## Development Workflow

When adding new features to Victor workflows:

1. **Add tools** in `victor_invest/tools/` (if new data operations needed)
2. **Add handlers** in `victor_invest/handlers.py` using `@handler_decorator` pattern
3. **Register handlers** via `register_handlers()` call
4. **Define workflow** in `victor_invest/workflows/*.yaml` (YAML-first)
5. **Add escape hatches** in `victor_invest/escape_hatches.py` (only if needed for complex logic)
6. **Write tests** in `tests/victor_invest/` with appropriate markers

**Important**:
- Always use `create_investment_orchestrator()` for bootstrap
- Always use the context-stuffing pattern
- Tools must inherit from Victor `BaseTool` (via `InvestmentTool`)
- Use `ToolResult.create_success/create_failure` for results

## Special Architectural Features

**Multi-Layer Cache System:**
- File cache (priority 10) - Fastest, JSON-based
- Parquet cache for technical data - Columnar storage
- RDBMS cache (priority 5) - PostgreSQL/SQLite persistent storage
- Automatic promotion between layers based on access patterns

**Cache Key Generation:** Must include `fiscal_period` to ensure proper cache hits:
```python
cache_key = SHA256({symbol, analysis_type, context_keys, fiscal_period})
```

**VRAM-Aware Resource Management:**
- Dynamic LLM semaphore based on actual GPU memory availability
- Multi-server Ollama pool with load balancing
- Model weight calculation for optimal concurrent task scheduling

**Reinforcement Learning:**
- Adaptive model weighting based on historical prediction accuracy
- Contextual bandit policy for model selection
- A/B testing capabilities for model comparison

**Valuation Models:** DCF, P/E, P/S, EV/EBITDA, GGM, plus sector-specific models for banks, insurance, biotech, semiconductors, REITs. Weights determined by RL policy engine.

## Key Files for New Development

| Task | Primary Files |
|------|---------------|
| Add new analysis workflow | `victor_invest/workflows/*.yaml`, `victor_invest/handlers.py` |
| Add new data source | `victor_invest/tools/*.py` (new tool), `victor_invest/handlers.py` (new handler) |
| Modify valuation logic | `src/investigator/domain/services/valuation/*.py` |
| Add new test markers | `pytest.ini`, `tests/conftest.py` |
| Update vertical config | `victor_invest/vertical/config/vertical.yaml` |
| Bootstrap changes | `victor_invest/framework_bootstrap.py` |

## Legacy Path Migration Notes

When working with legacy code (`src/investigator/`), be aware:
- Large monolithic modules exist (e.g., `agent.py` ~6340 lines, `synthesizer.py` ~6018 lines)
- Progressive decomposition is ongoing (see `docs/VICTOR_ALIGNMENT_REVIEW_20260211.md`)
- Use delegating wrappers when extracting functionality
- Add unit tests for extracted helpers

## Quality Gates

CI enforces:
- Victor compatibility matrix (`victor-ai>=0.5.0,<0.6.0`)
- Tool registration contract tests
- Handler registration sync assertions
- Workflow golden-output checks
- Latency budget enforcement (quick: 5s, standard: 30s, comprehensive: 60s)
- Victor-first entrypoint conformance (no legacy CLI in active docs)

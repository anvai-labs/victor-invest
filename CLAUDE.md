# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Rules

- This is a **Victor-first** codebase. Prefer `victor-invest` CLI and YAML workflows for all new work.
- Legacy `src/investigator/` path exists for compatibility; avoid adding new logic there.
- Keep workflows **deterministic-first**: tools/handlers execute data collection and analysis without LLM calls. LLM synthesis is optional and only used in the final synthesis step.
- Use shared bootstrap: `create_investment_orchestrator()` from `victor_invest/framework_bootstrap.py`.
- **Never add `Co-Authored-By` or any AI attribution trailers to commit messages.** The commit-msg hook will reject them.

## Commands

```bash
# Install
make dev-install          # or: pip install -e ".[dev,viz,jupyter]"

# Run analysis
victor-invest analyze AAPL --mode quick|standard|comprehensive
victor-invest batch AAPL MSFT GOOGL --parallel 4

# Tests
pytest tests/ -v                     # all tests
pytest tests/ -v -m unit             # unit only
pytest tests/ -v -m "not slow"       # skip slow
pytest tests/unit/victor_invest/ -v  # Victor framework tests only
pytest tests/unit/domain/services/test_fiscal_period_service.py -v  # single file
pytest tests/unit/domain/services/test_fiscal_period_service.py::test_name -v  # single test

# Quality
make format       # black + isort
make lint         # flake8
make type-check   # mypy
make ci           # format-check + lint + type-check + test-cov

# Dev server
make run-dev      # uvicorn on port 8000
```

## Architecture

### Execution Flow (Context Stuffing Pattern)

The system uses **direct tool invocation**, not LLM tool calling, for data collection:

```
YAML Workflow → WorkflowExecutor → Handlers → Tools → Legacy Domain Services
                                                          ↓
                                                   Database / External APIs
```

**Three-phase pipeline:**
1. **Data Collection** (parallel, deterministic, no LLM): SEC filings + market data fetched via tools
2. **Analysis** (parallel, deterministic): Fundamental valuation + technical indicators computed
3. **Synthesis** (rule-based, optional LLM): Weighted composite score → recommendation

Entry point: `run_analysis()` in `victor_invest/workflows/graphs.py` tries YAML workflow first, falls back to StateGraph execution.

### Key Directories

- **`victor_invest/`** — Primary framework code
  - `workflows/*.yaml` — Declarative workflow definitions (quick, standard, comprehensive, peer_comparison, rl_backtest)
  - `workflows/graphs.py` — StateGraph builders and node functions (fetch_sec_data, run_synthesis, etc.)
  - `workflows/state.py` — `AnalysisWorkflowState` dataclass
  - `handlers.py` — `@handler_decorator` compute handlers for YAML workflow nodes
  - `tools/` — 15+ tools wrapping domain services (BaseTool → ToolResult pattern)
  - `escape_hatches.py` — Python condition/transform functions for YAML branching logic
  - `framework_bootstrap.py` — `create_investment_orchestrator()` setup
  - `compat/handlers.py` — Compatibility shim for handler_decorator across Victor versions
- **`src/investigator/`** — Legacy engine (domain services, agents, infrastructure)
  - `domain/agents/` — FundamentalAnalysisAgent, TechnicalAnalysisAgent, etc.
  - `domain/services/valuation/` — DCF, GGM, P/E, P/S, EV/EBITDA, sector-specific models
  - `domain/services/rl/` — Reinforcement learning policy (contextual bandits, reward calculation)
  - `infrastructure/cache/` — Multi-tier cache (disk/RDBMS/Parquet) with CacheType enum
  - `infrastructure/sec/` — SEC EDGAR API, CompanyFacts extraction, XBRL parsing
  - `infrastructure/llm/` — Ollama multi-server pool with load balancing
  - `config/config.py` — Config loader (`get_config()` reads `config.yaml` + env vars)
- **`config.yaml`** — Single config source (~2300 lines): database, Ollama, valuation thresholds, RL params

### Adding or Changing Workflow Logic

1. Add/extend tool in `victor_invest/tools/` (inherit `BaseTool`, return `ToolResult`)
2. Add/extend handler in `victor_invest/handlers.py` (`@handler_decorator` + `BaseHandler`)
3. Update YAML in `victor_invest/workflows/*.yaml`
4. Add escape hatch in `escape_hatches.py` only if YAML condition/transform needs Python logic
5. Add tests under `tests/` (prefer `tests/unit/victor_invest/`)

### Handler Pattern

```python
@handler_decorator("handler_name", vertical="investment", description="...")
@dataclass
class MyHandler(BaseHandler):
    async def execute(self, node, context, tool_registry) -> Tuple[Any, int]:
        symbol = context.get("symbol", "")
        tool = MyTool()
        result = await tool.execute({}, symbol=symbol, action="...")
        return {"status": "success", "data": result.output}, 0  # (output_dict, tool_calls_count)
```

### Tool Pattern

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does"

    async def execute(self, _exec_ctx=None, **kwargs) -> ToolResult:
        try:
            # Call legacy domain service
            return ToolResult.create_success(data)
        except Exception as e:
            return ToolResult.create_failure(str(e))
```

Tools never raise exceptions to callers — they return `ToolResult.create_failure()`.

## Implementation Conventions

- Python 3.11+, 120-char line length
- Black + isort formatting, flake8 linting, mypy type checks
- Type hints on public APIs, async-first where appropriate
- Cache keys must include `fiscal_period` for correct cache behavior
- Prefer small, composable handlers/tools over monolithic logic
- If working in legacy modules, use extraction + wrapper pattern and add tests

## Config and Environment

- Main config: `config.yaml` (with `${ENV_VAR:-default}` substitution)
- Common env keys: `STOCK_DB_*`, `SEC_DB_*`, `OLLAMA_HOST_*`, `DATABASE_URL`
- Config access: `from investigator.config import get_config; config = get_config()`

## Testing

- Markers: `unit`, `integration`, `slow`, `llm`, `db`, `cache`, `performance`
- Fixtures in `tests/conftest.py`: `cache_root` (tmp dir), `sample_llm_response`, `sample_company_facts`
- `asyncio_mode = "auto"` in pytest config (no need for `@pytest.mark.asyncio`)
- Coverage targets: `src/investigator` and `victor_invest`

## Git Hooks

```bash
./scripts/setup-git-hooks.sh   # setup
git commit --no-verify          # bypass when necessary
```

- **pre-commit**: ruff format, ruff lint, mypy on staged Python files in `src/` and `victor_invest/`
- **commit-msg**: rejects any `Co-Authored-By` trailer (AI attribution is forbidden)

## CLI Entry Points

- `victor-invest` — Primary CLI (Victor-powered, YAML workflows)
- `investigator` / `inv` — Legacy CLI
- `investigator cache warm --symbols STX --process-raw --force-refresh` — Refresh SEC data

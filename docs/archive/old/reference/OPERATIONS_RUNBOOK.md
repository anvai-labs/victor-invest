# Operations Runbook

## Environment & Services
- **Python/venv:** Python 3.11+, activate `venv` before running commands.
- **LLM pool:** Ollama running locally; pool settings loaded via `config.json` (servers, capacity caps). Restart Ollama if LLM calls hang.
- **Database:** PostgreSQL for market data; ensure `config.json` holds correct DSN.

## Routine Commands
- Health/status: `python3 -m victor_invest.cli status`
- Cache maintenance: `make cache-inspect SYMBOL=AAPL`, `make cache-clean SYMBOL=AAPL`, wipe all via `make clean-all`
- Core checks: `make format lint type-check test` or one-shot `make ci`
- Coverage review: `make test-cov` → open `htmlcov/index.html`
- API dev server: `make run-dev` (uvicorn on :8000)

## Fresh SEC Filing Refresh (Two-Step)
- Use this when logs show older fiscal periods and you need latest CompanyFacts pulled from SEC.
- Step 1 (ingest fresh raw + processed SEC data):
  `investigator cache warm --symbols <TICKER> --process-raw --force-refresh`
- Step 2 (run analysis with refreshed symbol context):
  `investigator analyze single <TICKER> --mode comprehensive --force-refresh`
- Optional cleanup before Step 1 (if cache corruption/stale symbol cache suspected):
  `investigator cache clean --symbol <TICKER> --force`

## Deterministic Synthesis Controls
- Use deterministic synthesis stages to avoid intermittent local-LLM JSON failures in scenarios/recommendation/action-plan/report generation.
- Config path: `valuation.deterministic` in your runtime config (`config.yaml` / environment-loaded config).
- Available flags (all default to `true` when unspecified):
  - `enabled`
  - `valuation_synthesis`
  - `competitive_analysis`
  - `conflict_resolution`
  - `insight_extraction`
  - `thesis_generation`
  - `forecast_generation`
  - `fundamental_report_generation`
  - `technical_pattern_recognition`
  - `technical_signal_generation`
  - `technical_report_generation`
  - `market_sentiment_generation`
  - `risk_assessment_generation`
  - `scenario_generation`
  - `recommendation_generation`
  - `action_plan_generation`
  - `report_generation`
- Example snippet:
  ```json
  {
    "valuation": {
      "deterministic": {
        "enabled": true,
        "forecast_generation": true,
        "fundamental_report_generation": true,
        "technical_pattern_recognition": true,
        "technical_signal_generation": true,
        "technical_report_generation": true,
        "market_sentiment_generation": true,
        "risk_assessment_generation": true,
        "scenario_generation": true,
        "recommendation_generation": true,
        "action_plan_generation": true,
        "report_generation": true
      }
    }
  }
  ```

## Failure Recovery
- **Orchestrator startup fails:** Restart after confirming Ollama servers are available and DB is reachable; review logs for resource pool errors.
- **Agent hangs:** Cancel running job and restart orchestrator; verify Ollama and network to SEC are responsive; clear caches for the symbol with `make cache-clean SYMBOL=<TICKER>`.
- **Database connectivity errors:** Validate DSN in `config.json`, check network/firewall, and run a simple SQL ping via `psql`.
- **Corrupted caches:** Remove affected symbol caches (`make cache-clean SYMBOL=<TICKER>`) or fully reset with `make clean-all` (clears SEC/LLM/technical caches and artifacts).

## Observability & Logging
- Metrics are emitted via `MetricsCollector`; orchestrator logs report worker health and queue stats every minute. Monitor for repeated worker error logs.
- Long-running tasks mark failures in `completed_tasks` with `error`; fetch status via API/CLI status endpoints if exposed.

## Change Management
- Before releases: run `make ci`, verify coverage, and ensure `README.adoc` + `docs/AGENTS.md` are current.
- Secrets: keep SEC user agent, DB creds, and tokens in `config.json` or `.env` (git-ignored). Never commit secrets.

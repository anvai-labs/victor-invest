# Platform Review and Roadmap

**Date:** 2026-03-15

## Scope

This review covers the active `victor_invest/` workflow/API/UI surface, the legacy-but-still-critical `src/investigator/` domain stack, the current docs set, and delivery mechanics around tests, CI, and operations.

## Snapshot

| Metric | Current |
|---|---:|
| Python files under `src/` + `victor_invest/` | 398 |
| Test files | 145 |
| Python LOC scanned | 230,791 |
| Largest file | `src/investigator/application/synthesizer.py` at 5,749 LOC |
| Primary product posture | Victor-first orchestration over legacy domain/infrastructure |

## Product Direction

Victor Invest should behave like a deterministic research platform first and an LLM-assisted synthesis layer second:

- deterministic market, SEC, valuation, and ranking pipelines
- optional LLM synthesis for narrative, recommendation framing, and comparative reasoning
- stable CLI, API, and UI contracts for local-first research workflows
- explicit separation between platform/orchestration code and investment-domain logic

## Tiered Assessment

| Tier | Goal | Current State | Risk | Recommended Direction |
|---|---|---|---|---|
| Foundational | Keep one canonical product surface | Active docs, routes, and UI contracts had drift around `/ui`, `/dashboard`, `/health`, `/api/*`, and missing UI endpoints | Onboarding friction and client breakage | Treat `victor-invest`, `/ui`, `/health`, `/analyze/{symbol}`, and `/batch` as canonical; keep aliases only for compatibility |
| Security | Safe-by-default local deployment | API used wildcard CORS with credentials enabled and no explicit deployment guidance on trusted origins | Browser inconsistency and accidental exposure | Default to localhost-only origins, require env opt-in for broader access, then add auth for non-local use |
| Design | Reduce dual-stack ambiguity | `victor_invest/` is primary, but most business logic still lives in `src/investigator/`; legacy and modern paths coexist | Behavior drift and slow refactors | Make Victor orchestration thin; move shared contracts/boundaries into explicit adapters and continue shrinking legacy entrypoints |
| Quality | Contract drift should fail fast | Test suite is broad, but active docs checks were stale and some UI/API paths were unverified | Silent regressions | Keep route/documentation conformance tests close to public surfaces and add end-to-end contract checks for UI payloads |
| Operations | Prefer observable, durable workflows | Batch jobs are in-memory; UI history leans on cache/log fallbacks; health response shape was split | Weak production operability | Persist batch state, publish SLOs, and standardize health/reporting payloads |
| Vision | Clarify the north star | Repo shows strong domain depth but an oversized feature surface | Scope creep | Focus on institutional-style single-name research, rankings, and repeatable watchlist workflows before expanding side capabilities |
| Roadmap | Sequence work by dependency | Historical roadmap notes existed in archive only | Execution churn | Keep one active roadmap in `docs/developer/` and map major tiers to GitHub issues |
| Technical Debt | Burn down large-file and deprecated-path risk | Multiple 1k-5k LOC modules remain, plus deprecated forwarding and compatibility shims | High regression cost | Continue extraction around `synthesizer`, `fundamental` agent orchestration, reporting, and cache/database adapters |

## Actions Completed In This Pass

- stabilized public API compatibility by adding aliases for `/api/health`, `/api/analyze/{symbol}`, `/api/batch`, `/api/batch/{job_id}`, and `/api/analysis/{symbol}/latest`
- added missing UI-facing routes for `/ui/api/health` and `/ui/api/analysis/{symbol}/history`
- restored a legacy dashboard entrypoint via `/dashboard` redirect to canonical `/ui`
- replaced wildcard CORS defaults with environment-driven trusted origins and wildcard opt-in
- added opt-in bearer-token protection for analysis, batch, cache mutation, and UI refresh endpoints via `VICTOR_API_BEARER_TOKEN`
- added startup warnings for risky API exposure combinations such as broad CORS without bearer auth
- persisted batch-job state to `artifacts/batch_jobs/` and normalize unfinished jobs to `interrupted` after restart
- extracted technical signal parsing and technical-context helpers from `src/investigator/application/synthesizer.py` into `src/investigator/application/synthesizer_technicals.py`
- extracted quarterly-trend, financial-metric, sector-context, and market-environment helpers from `src/investigator/application/synthesizer.py` into `src/investigator/application/synthesizer_context.py`
- extracted fallback recommendation parsing from `src/investigator/application/synthesizer.py` into `src/investigator/application/synthesizer_recommendation.py`
- extracted component-score and quarterly business-quality helpers from `src/investigator/application/synthesizer.py` into `src/investigator/application/synthesizer_component_scores.py`
- extracted core fundamental/technical scoring, weighted-score, data-quality, and synthesis-response parsing helpers from `src/investigator/application/synthesizer.py` into `src/investigator/application/synthesizer_scoring.py`
- extracted quarterly trend calculation, SEC comprehensive normalization, direct LLM recommendation shaping, and detailed data-quality helpers from `src/investigator/application/synthesizer.py` into `src/investigator/application/synthesizer_structured.py`
- extracted deterministic forecast/report payload builders and weighted quality-score helper from `src/investigator/domain/agents/fundamental/agent.py` into `src/investigator/domain/agents/fundamental/deterministic_payloads.py`
- extracted sector-multiple lookup, enterprise-value calculation, model-selection rule loading, and model-selection filtering from `src/investigator/domain/agents/fundamental/agent.py` into `src/investigator/domain/agents/fundamental/valuation_selection.py`
- refreshed the active docs set and fixed the docs conformance test so it checks files that actually exist

## Active GitHub Tracking

- Issue #18: Foundation and public-contract convergence
- Issue #20: Security posture for non-local deployment
- Issue #19: Technical-debt reduction and legacy-surface shrinkage
- Issue #21: Reliability, persistence, and observability improvements

## Detailed Design Follow-Up

The low-level design for the next fair-value, decision-policy, persistence, and Victor/codingagent alignment work is maintained in [Fair Value and Agentic Workflow LLD](fair-value-agentic-lld.md). Treat that document as the implementation spec for surgical TDD slices rather than expanding this roadmap with file-level details.

## Recommended Execution Order

### Phase 1: Foundation and Safety

- finish converging active docs on canonical UI/API paths
- add API auth strategy for any non-local deployment mode
- standardize response contracts used by the React frontend

### Phase 2: Architecture Simplification

- keep routing/orchestration in `victor_invest/`
- keep valuation, SEC normalization, and data-source logic in explicit `investigator` modules
- remove duplicated compatibility shims once downstream callers no longer rely on them

### Phase 3: Reliability and Observability

- move batch job state out of process memory
- define benchmark, latency, and cache freshness SLOs
- expose a production-usable health/reporting surface

### Phase 4: Technical-Debt Burn-Down

- decompose the largest remaining modules into smaller orchestration helpers and pure domain services
- tighten type-check coverage around API, cache, reporting, and valuation boundaries
- add high-signal integration tests around the canonical workflows and dashboard payload generation

## Success Criteria

- one documented canonical UI path and one documented canonical API surface
- no active docs pointing at removed or compatibility-only entrypoints
- secure-by-default local API settings with explicit opt-in for broader exposure
- reduced reliance on legacy forwarding paths
- measurable progress on the largest-module count and public contract coverage

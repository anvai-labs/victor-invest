# Module Guide

Victor Invest has two Python package roots:

- `investigator` in `src/investigator`: clean-architecture application, domain, infrastructure, and legacy CLI surfaces.
- `victor_invest` in `victor_invest`: agent/workflow runtime, API server, compatibility wrappers, and vertical-specific orchestration.

Use this map with `make coverage-report` to decide where a coverage result belongs and which tests should own a behavior.

## `investigator`

| Module | Purpose | Primary test style |
| --- | --- | --- |
| `investigator.application` | Use-case orchestration, result formatting, decision input extraction, and application services. | Unit tests with mocked infrastructure boundaries. |
| `investigator.application.orchestration` | Workflow coordination for analysis execution. | Contract tests around step ordering and error handling. |
| `investigator.application.processors` | Data processing helpers used by analysis flows. | Unit tests with representative payload fixtures. |
| `investigator.application.prompts` | Prompt construction for analysis agents. | Snapshot or fixture tests for deterministic prompt text. |
| `investigator.cli` | Typer/CLI command surfaces. | CLI runner tests and thin integration tests. |
| `investigator.config` | Runtime configuration loading and defaults. | Unit tests for env/config precedence. |
| `investigator.core` | Older shared core primitives. | Characterization tests before refactors. |
| `investigator.domain` | Business models, value objects, valuation services, investment decision policy, and symbol update logic. | High-coverage deterministic unit tests. |
| `investigator.infrastructure.cache` | Cache storage and cache inspection helpers. | Unit tests with temporary directories. |
| `investigator.infrastructure.data` | Data loading/persistence adapters. | Adapter tests with fake data sources. |
| `investigator.infrastructure.database` | Database repositories, schema-facing persistence, and valuation audit storage. | Repository tests against in-memory or temporary SQLite fixtures. |
| `investigator.infrastructure.events` | Event abstractions and dispatching. | Unit tests for published payloads. |
| `investigator.infrastructure.external` | External data adapters such as FRED. | Unit tests with mocked HTTP responses and parser fixtures. |
| `investigator.infrastructure.formatters` | Presentation and serialization helpers. | Unit tests for output contracts. |
| `investigator.infrastructure.http` | HTTP client utilities. | Unit tests with fake sessions/responses. |
| `investigator.infrastructure.indicators` | Technical/fundamental indicator calculations and wrappers. | Deterministic unit tests from known input series. |
| `investigator.infrastructure.llm` | LLM provider adapters and prompt execution. | Boundary tests with fake providers; no live LLM in unit tests. |
| `investigator.infrastructure.monitoring` | Metrics and runtime observability helpers. | Unit tests for emitted metrics/log payloads. |
| `investigator.infrastructure.reporting` | Report generation and export surfaces. | Golden-file or structure tests for reports. |
| `investigator.infrastructure.sec` | SEC data access, document parsing, and filing adapters. | Fixture-based parser and adapter tests. |
| `investigator.infrastructure.ui` | UI-facing helper code. | Contract tests for API/UI payloads. |
| `investigator.infrastructure.utils` | Shared infrastructure utilities. | Focused unit tests. |
| `investigator.interfaces` | Interface adapters, including CLI-facing boundaries. | Contract tests at public entrypoints. |
| `investigator.shared` | Shared utilities used across layers. | Unit tests for stable helpers. |
| `investigator.workflows` | Legacy workflow definitions. | Characterization and contract tests before migration. |

## `victor_invest`

| Module | Purpose | Primary test style |
| --- | --- | --- |
| `victor_invest.agents` | Agent definitions and specs used by the agentic investing runtime. | Contract tests around agent inputs/outputs. |
| `victor_invest.api` | FastAPI app, ranking endpoints, exports, health, and UI payload assembly. | API tests with `TestClient` and mocked services. |
| `victor_invest.compat` | Compatibility shims for older import paths and contracts. | Import and behavior-preservation tests. |
| `victor_invest.prompts` | Prompt assets used by workflows and agents. | Fixture tests for prompt assembly where dynamic. |
| `victor_invest.tools` | Tool wrappers exposed to workflows and agents. | Unit tests with fake external dependencies. |
| `victor_invest.vertical` | Vertical configuration and domain alignment for investment workflows. | Config and contract tests. |
| `victor_invest.workflows` | Graph/workflow synthesis and decision-policy integration. | Workflow contract tests using deterministic state fixtures. |

## How To Use This Map

1. Run `make coverage-report`.
2. Review the terminal summary or `htmlcov/index.html`.
3. Match low-coverage files to the module above.
4. Add the narrowest deterministic test at that layer.
5. Use integration tests only when behavior crosses process, database, network, or API boundaries.

New deterministic domain/application modules should clear the 66.67% target before merge. Repo-wide coverage is tracked across both package roots and is expected to rise as legacy surfaces get characterization tests or are retired.

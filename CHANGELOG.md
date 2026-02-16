# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-02-15

### Added
- Victor-first CLI (`victor-invest`) with YAML-driven workflows (quick, standard, comprehensive)
- React + TypeScript research dashboard with TanStack Query and Recharts
- Deterministic multi-model valuation: DCF, P/E, P/S, EV/EBITDA, GGM with dynamic weighting
- SEC EDGAR integration with CompanyFacts extraction and XBRL parsing
- Reinforcement learning model weighting via contextual bandits
- Sector-specific valuation models (banks, insurance, REITs, biotech, defense, semiconductors)
- Credit risk scoring: Altman Z-Score, Beneish M-Score, Piotroski F-Score
- Market regime detection with yield curve, credit cycle, and recession indicators
- Multi-tier caching (disk, RDBMS, Parquet) with fiscal-period-aware keys
- Batch analysis with parallel execution and portfolio rankings
- Docker Compose stack with PostgreSQL, Redis, Ollama, Prometheus, Grafana

### Changed
- Migrated from legacy `investigator` CLI to `victor-invest` as primary entry point
- Switched workflow engine from custom orchestrator to Victor StateGraph
- Replaced LLM-dependent analysis with deterministic-first pipeline (LLM synthesis optional)

### Fixed
- Fiscal year assignment for non-calendar fiscal year companies (e.g., MSFT, ORCL)
- Q1 quarterly calculation regression for companies with January fiscal year end
- Negative revenue edge cases in DCF valuation bounds checker

[0.5.0]: https://github.com/vjsingh1984/victor-invest/releases/tag/v0.5.0

.PHONY: help install dev-install test test-cov coverage-report coverage-modules coverage-critical coverage-rl coverage-gate lint format type-check clean run analyze status cache-clean benchmark-workflows frontend-install frontend-dev frontend-build frontend-lint frontend-type-check

.DEFAULT_GOAL := help

# Python >=3.11 required. Prefer the workspace venv used by local automation,
# then python3.11 if available, else fall back to python3.
PYTHON := $(shell if [ -x ../.venv/bin/python ]; then echo ../.venv/bin/python; elif command -v python3.11 >/dev/null 2>&1; then command -v python3.11; else echo python3; fi)
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
COVERAGE_MIN ?= 66.67
COVERAGE_PATHS := investigator victor_invest

# Colors for output
CYAN := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

help: ## Show this help message
	@echo "$(CYAN)InvestiGator - Investment Research Platform$(RESET)"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

install: ## Install package in editable mode
	$(PIP) install -e .

dev-install: ## Install package with development dependencies
	$(PIP) install -e ".[dev,viz,jupyter]"

test: ## Run tests
	$(PYTEST) tests/ -v

test-cov: coverage-report ## Run unit tests with repo-wide coverage report

coverage-report: ## Generate repo-wide module coverage reports without enforcing a threshold
	$(PYTEST) tests/unit/ -v --cov=investigator --cov=victor_invest --cov-report=term-missing --cov-report=html --cov-report=xml --cov-report=json

coverage-modules: coverage-report ## Generate repo-wide coverage and print grouped package/module summary
	$(PYTHON) scripts/report_module_coverage.py coverage.json

coverage-critical: coverage-report ## Enforce 67% coverage for critical valuation and macro modules
	$(PYTHON) scripts/assert_critical_coverage.py coverage.json

coverage-rl: ## Enforce 67% coverage for deterministic RL core and training modules
	$(PYTEST) tests/unit/domain/services/rl -q --cov=investigator --cov-report=term-missing --cov-report=json:rl-coverage.json
	$(PYTHON) scripts/assert_rl_coverage.py rl-coverage.json

coverage-gate: ## Enforce repo-wide coverage threshold (default COVERAGE_MIN=66.67)
	$(PYTEST) tests/unit/ -v --cov=investigator --cov=victor_invest --cov-report=term-missing --cov-report=html --cov-report=xml --cov-report=json --cov-fail-under=$(COVERAGE_MIN)

test-unit: ## Run unit tests only
	$(PYTEST) tests/ -v -m unit

test-integration: ## Run integration tests only
	$(PYTEST) tests/ -v -m integration

test-fast: ## Run tests excluding slow tests
	$(PYTEST) tests/ -v -m "not slow"

lint: ## Run blocking Flake8 checks
	flake8 src/ victor_invest/ --count --select=E9,F63,F7,F82 --show-source --statistics

format: ## Format code with ruff and isort
	ruff format src/ victor_invest/ tests/
	isort src/investigator/ tests/

format-check: ## Check code formatting without making changes
	ruff format --check src/ victor_invest/ tests/
	isort --check src/investigator/ tests/

type-check: ## Run type checking with mypy
	mypy src/investigator/

clean: ## Clean build artifacts and cache files
	rm -rf build/ dist/ *.egg-info .pytest_cache/ .coverage htmlcov/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

clean-all: clean ## Clean everything including data caches
	rm -rf data/sec_cache/* data/llm_cache/* data/technical_cache/* data/market_context_cache/*
	rm -rf artifacts/results/* artifacts/metrics/* artifacts/logs/*
	@echo "$(GREEN)All caches and artifacts cleared$(RESET)"

analyze: ## Run analysis on a symbol (usage: make analyze SYMBOL=AAPL)
	python3 -m victor_invest.cli analyze $(SYMBOL) --mode standard

analyze-force: ## Run analysis with force refresh (usage: make analyze-force SYMBOL=AAPL)
	python3 -m victor_invest.cli analyze $(SYMBOL) --mode standard --force-refresh

batch: ## Run batch analysis (usage: make batch SYMBOLS="AAPL MSFT GOOGL")
	python3 -m victor_invest.cli batch $(SYMBOLS) --mode standard

status: ## Check system status
	python3 -m victor_invest.cli status

cache-inspect: ## Inspect cache for symbol (usage: make cache-inspect SYMBOL=AAPL)
	python3 -m victor_invest.cli inspect-cache --symbol $(SYMBOL) --verbose

cache-clean: ## Clean cache for symbol (usage: make cache-clean SYMBOL=AAPL)
	python3 -m victor_invest.cli clean-cache --symbol $(SYMBOL)

benchmark-workflows: ## Benchmark quick/standard/comprehensive latency budgets (usage: make benchmark-workflows SYMBOL=AAPL)
	python3 scripts/benchmark_victor_workflows.py --symbol $(if $(SYMBOL),$(SYMBOL),AAPL) --output-json artifacts/benchmarks/workflow_benchmark_$(if $(SYMBOL),$(SYMBOL),AAPL).json

run-dev: ## Run development server (if API exists)
	uvicorn victor_invest.api.app:app --reload --port 8000

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

frontend-dev: ## Start frontend dev server (proxies API to :8000)
	cd frontend && npm run dev

frontend-build: ## Build frontend for production
	cd frontend && npm run build

frontend-lint: ## Lint frontend code
	cd frontend && npm run lint

frontend-type-check: ## Type-check frontend code
	cd frontend && npm run type-check

docker-build: ## Build Docker image
	docker build -t investigator:latest .

docker-run: ## Run Docker container
	docker run -p 8000:8000 investigator:latest

pre-commit: format lint type-check test ## Run all pre-commit checks

ci: format-check lint test-cov ## Run CI pipeline checks

build: clean ## Build distribution packages
	$(PYTHON) -m build

publish-test: build ## Publish to Test PyPI
	$(PYTHON) -m twine upload --repository testpypi dist/*

publish: build ## Publish to PyPI
	$(PYTHON) -m twine upload dist/*

verify-structure: ## Verify package structure is correct
	@echo "$(CYAN)Verifying package structure...$(RESET)"
	@test -d src/investigator || (echo "❌ src/investigator/ not found" && exit 1)
	@test -f src/investigator/__init__.py || (echo "❌ src/investigator/__init__.py not found" && exit 1)
	@test -d src/investigator/domain || (echo "❌ src/investigator/domain/ not found" && exit 1)
	@test -d src/investigator/infrastructure || (echo "❌ src/investigator/infrastructure/ not found" && exit 1)
	@test -d src/investigator/application || (echo "❌ src/investigator/application/ not found" && exit 1)
	@test -d src/investigator/interfaces || (echo "❌ src/investigator/interfaces/ not found" && exit 1)
	@echo "$(GREEN)✓ Package structure verified$(RESET)"

tag-release: ## Tag a new release (usage: make tag-release VERSION=v0.5.0)
	git tag -a $(VERSION) -m "Release $(VERSION)"
	git push origin $(VERSION)

show-todos: ## Show implementation tracker status
	@if [ -f REFACTORING_IMPLEMENTATION_TRACKER.md ]; then \
		echo "$(CYAN)Implementation Progress:$(RESET)"; \
		grep -E "^\- \[(x| )\]" REFACTORING_IMPLEMENTATION_TRACKER.md | head -20; \
	fi

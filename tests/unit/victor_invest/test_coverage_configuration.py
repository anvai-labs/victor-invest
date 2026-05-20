from pathlib import Path


def test_makefile_exposes_repo_wide_coverage_targets():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "coverage-report:" in makefile
    assert "coverage-modules:" in makefile
    assert "coverage-critical:" in makefile
    assert "coverage-rl:" in makefile
    assert "coverage-gate:" in makefile
    assert "PYTEST := $(PYTHON) -m pytest" in makefile
    assert "--cov=investigator --cov=victor_invest" in makefile
    assert "--cov-report=term-missing" in makefile
    assert "--cov-report=html" in makefile
    assert "--cov-report=xml" in makefile
    assert "--cov-report=json" in makefile
    assert "--cov-fail-under=$(COVERAGE_MIN)" in makefile
    assert "COVERAGE_MIN ?= 66.67" in makefile


def test_pyproject_configures_coverage_source_roots():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.coverage.run]" in pyproject
    assert 'source = ["investigator", "victor_invest"]' in pyproject
    assert "[tool.coverage.report]" in pyproject
    assert "precision = 2" in pyproject


def test_user_docs_describe_coverage_reports_and_current_baseline():
    docs = Path("docs/user/test-coverage.md").read_text(encoding="utf-8")
    module_guide = Path("docs/user/module-guide.md").read_text(encoding="utf-8")
    docs_readme = Path("docs/README.md").read_text(encoding="utf-8")

    assert "make coverage-report" in docs
    assert "make coverage-modules" in docs
    assert "make coverage-critical" in docs
    assert "make coverage-rl" in docs
    assert "make coverage-gate" in docs
    assert "COVERAGE_MIN=66.67" in docs
    assert "repo-wide coverage: `29.92%`" in docs
    assert "scripts/assert_rl_coverage.py" in docs
    assert "htmlcov/index.html" in docs
    assert "[Module Guide](module-guide.md)" in docs
    assert "[Module Guide](user/module-guide.md)" in docs_readme
    assert "`investigator.application`" in module_guide
    assert "`investigator.infrastructure.database`" in module_guide
    assert "`victor_invest.api`" in module_guide
    assert "`victor_invest.workflows`" in module_guide


def test_module_coverage_reporter_groups_source_roots():
    from scripts.report_module_coverage import CoverageBucket, format_rows, module_name_for_path

    assert module_name_for_path("src/investigator/application/result_formatter.py") == "investigator.application"
    assert module_name_for_path("src/investigator/infrastructure/database/repository.py") == (
        "investigator.infrastructure"
    )
    assert module_name_for_path("victor_invest/api/app.py") == "victor_invest.api"
    assert module_name_for_path("victor_invest/workflows/graphs.py") == "victor_invest.workflows"

    rows = format_rows({"victor_invest.api": CoverageBucket(covered=2, statements=4)})

    assert "victor_invest.api" in "\n".join(rows)
    assert "50.00%" in "\n".join(rows)


def test_critical_coverage_gate_tracks_fair_value_and_macro_modules():
    from scripts.assert_critical_coverage import CRITICAL_MODULES, THRESHOLD

    assert THRESHOLD == 67.0
    assert "src/investigator/domain/agents/symbol_update.py" in CRITICAL_MODULES
    assert "src/investigator/domain/services/unified_valuation_executor.py" in CRITICAL_MODULES
    assert "src/investigator/infrastructure/external/fred/macro_indicators.py" in CRITICAL_MODULES
    assert "src/investigator/infrastructure/database/valuation_run_repository.py" in CRITICAL_MODULES


def test_rl_coverage_gate_tracks_core_and_training_modules():
    from scripts.assert_rl_coverage import RL_MODULES, THRESHOLD

    assert THRESHOLD == 67.0
    assert "src/investigator/domain/services/rl/reward_calculator.py" in RL_MODULES
    assert "src/investigator/domain/services/rl/feature_extractor.py" in RL_MODULES
    assert "src/investigator/domain/services/rl/feature_normalizer.py" in RL_MODULES
    assert "src/investigator/domain/services/rl/policy/dual_policy.py" in RL_MODULES
    assert "src/investigator/domain/services/rl/training/experience_collector.py" in RL_MODULES

from pathlib import Path


def test_makefile_primary_targets_use_victor_cli():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    expected_commands = [
        "python3 -m victor_invest.cli analyze $(SYMBOL) --mode standard",
        "python3 -m victor_invest.cli analyze $(SYMBOL) --mode standard --force-refresh",
        "python3 -m victor_invest.cli batch $(SYMBOLS) --mode standard",
        "python3 -m victor_invest.cli status",
        "python3 -m victor_invest.cli inspect-cache --symbol $(SYMBOL) --verbose",
        "python3 -m victor_invest.cli clean-cache --symbol $(SYMBOL)",
    ]

    for expected in expected_commands:
        assert expected in makefile


def test_version_is_consistent_across_package_and_vertical_metadata():
    import tomllib

    import victor_invest
    from victor_invest.vertical import InvestmentVertical

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]

    # Package version (pyproject + __version__) must be in sync.
    # The vertical API version (InvestmentVertical.version) is independently versioned
    # and need not match the package version.
    assert victor_invest.__version__ == project_version
    assert InvestmentVertical.version is not None


def test_pyproject_pins_supported_victor_version_range():
    """Both Victor packages must carry a floor and an upper bound.

    Asserted by meaning rather than by exact string: the previous version compared
    literal pins, so correcting the victor-contracts upper bound to exclude the
    0.10.0 removal release failed here for no substantive reason. See
    test_contracts_deprecation_debt for why that bound is 0.10 and not 1.0.
    """
    import tomllib

    from packaging.requirements import Requirement

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    declared = list(data["project"]["dependencies"])
    for extra in data["project"].get("optional-dependencies", {}).values():
        declared.extend(extra)

    pins = {
        req.name: req.specifier
        for req in (Requirement(d) for d in declared)
        if req.name in {"victor-contracts", "victor-ai"}
    }

    for name in ("victor-contracts", "victor-ai"):
        assert name in pins, f"{name} must be declared in pyproject.toml"
        spec = str(pins[name])
        assert ">=0.7.0" in spec, f"{name} must keep a >=0.7.0 floor, got {spec!r}"
        assert "<" in spec, f"{name} must carry an upper bound so a major release cannot land silently, got {spec!r}"


def test_pyproject_registers_investment_plugin_entrypoint():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '[project.entry-points."victor.plugins"]' in pyproject
    assert 'investment = "victor_invest.vertical:plugin"' in pyproject


def test_investment_plugin_implements_victor_plugin_protocol():
    from victor_contracts import VerticalBase, VictorPlugin

    from victor_invest.vertical import InvestmentPlugin, plugin
    from victor_invest.vertical.investment_vertical import InvestmentVertical

    assert isinstance(plugin, VictorPlugin)
    assert isinstance(plugin, InvestmentPlugin)
    assert plugin.name == "investment"
    assert issubclass(InvestmentVertical, VerticalBase)


def test_makefile_run_dev_uses_victor_api():
    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "uvicorn victor_invest.api.app:app --reload --port 8000" in makefile


def test_legacy_cli_declares_deprecated_forwarding_mode():
    legacy_cli = Path("cli_orchestrator.py").read_text(encoding="utf-8")

    assert "DEPRECATED: This CLI is maintained for backwards compatibility only." in legacy_cli
    assert "python -m victor_invest.cli analyze AAPL --mode standard" in legacy_cli
    assert '[sys.executable, "-m", "victor_invest.cli"] + args' in legacy_cli

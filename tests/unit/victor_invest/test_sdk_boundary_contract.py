"""SDK Boundary Contract Tests for victor-invest.

Validates that the investment vertical adheres to SDK boundary rules:
1. Plugin.py and vertical definition use SDK imports only (module-level)
2. pyproject.toml keeps victor-sdk in base deps, victor-ai in optional
3. Vertical class inherits from SDK VerticalBase
4. Core imports are banned from production modules
"""

from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Modules that MUST NOT have module-level victor.core/agent imports
_MODULES = [
    "victor_invest/plugin.py",
    "victor_invest/tool_dependencies.py",
    "victor_invest/prompts/contributor.py",
]

_BANNED_IMPORTS = (
    "victor.core.verticals.protocols",
    "victor.core.verticals.registration",
    "victor.core.verticals.base",
    "victor.agent.orchestrator",
)


class TestSDKBoundaryContract:
    """Ensure invest production code respects SDK boundary."""

    def test_sdk_boundary_modules_avoid_core_imports(self):
        """Key modules must not have module-level core imports."""
        for module in _MODULES:
            filepath = _REPO_ROOT / module
            if not filepath.exists():
                continue
            source = filepath.read_text(encoding="utf-8")
            for banned in _BANNED_IMPORTS:
                assert banned not in source, f"{module} imports from banned path '{banned}'. Use victor_sdk instead."

    def test_pyproject_sdk_in_base_deps(self):
        """victor-sdk must be in base dependencies, not optional."""
        pyproject = _REPO_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        deps = data["project"]["dependencies"]
        assert any(d.startswith("victor-sdk") for d in deps), "victor-sdk must be in [project.dependencies]"

    def test_pyproject_framework_is_optional(self):
        """victor-ai must NOT be in base dependencies."""
        pyproject = _REPO_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        deps = data["project"]["dependencies"]
        assert all("victor-ai" not in d for d in deps), (
            "victor-ai must be in [project.optional-dependencies.runtime], not base dependencies"
        )

    def test_pyproject_has_entry_points(self):
        """pyproject.toml must declare at least 3 entry point groups."""
        pyproject = _REPO_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        entry_points = data.get("project", {}).get("entry-points", {})
        groups = [k for k in entry_points if k.startswith("victor.")]
        assert len(groups) >= 3, f"Expected >= 3 victor.* entry point groups, found {len(groups)}: {groups}"

    def test_vertical_inherits_sdk_base(self):
        """InvestmentVertical must inherit from SDK VerticalBase."""
        from victor_sdk.verticals.protocols.base import VerticalBase

        from victor_invest.vertical.investment_vertical import InvestmentVertical

        assert issubclass(InvestmentVertical, VerticalBase), (
            "InvestmentVertical must inherit from victor_sdk VerticalBase"
        )

    def test_plugin_implements_victor_plugin(self):
        """Plugin must implement VictorPlugin protocol."""
        from victor_invest.plugin import InvestPlugin

        assert hasattr(InvestPlugin, "name")
        assert hasattr(InvestPlugin, "register")
        assert hasattr(InvestPlugin, "health_check")

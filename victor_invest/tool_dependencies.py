"""Investment Tool Dependencies — tool relationships for investment workflows.

YAML-based configuration loaded from tool_dependencies.yaml.
Provides tool transition probabilities, clusters, and composed patterns
for the framework's intelligent tool selection.
"""

from pathlib import Path

from victor_contracts.verticals.tool_dependencies import YAMLToolDependencyProvider

_YAML_PATH = Path(__file__).parent / "tool_dependencies.yaml"


class InvestmentToolDependencyProvider(YAMLToolDependencyProvider):
    """Tool dependency provider for the investment vertical."""

    def __init__(self) -> None:
        super().__init__(_YAML_PATH)


def get_provider() -> InvestmentToolDependencyProvider:
    """Entry point factory for victor.tool_dependencies."""
    return InvestmentToolDependencyProvider()

# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Investment verticals for Victor framework.

Exports:
- InvestmentVertical: Main investment research vertical (VerticalBase pattern)
- InvestmentPlugin: VictorPlugin implementation for plugin discovery
- plugin: Module-level plugin instance for entry point resolution
"""

from typing import Any, Dict, Optional

from victor_sdk import PluginContext, VictorPlugin

from victor_invest.vertical.investment_vertical import InvestmentVertical


class InvestmentPlugin(VictorPlugin):
    """Victor Plugin for Investment vertical.

    Discovered via the 'victor.plugins' entry point. Registers the
    InvestmentVertical and its tools with the framework.
    """

    @property
    def name(self) -> str:
        return "investment"

    def register(self, context: PluginContext) -> None:
        """Register investment vertical and tools."""
        context.register_vertical(InvestmentVertical)

    def get_cli_app(self) -> Optional[Any]:
        """No CLI subcommand — victor-invest has its own CLI."""
        return None

    def on_activate(self) -> None:
        """Called when investment vertical is activated."""
        pass

    def on_deactivate(self) -> None:
        """Called when investment vertical is deactivated."""
        pass

    def health_check(self) -> Dict[str, Any]:
        """Return health status for investment plugin."""
        try:
            from investigator.config import get_config

            config = get_config()
            return {
                "healthy": True,
                "vertical": "investment",
                "config_loaded": config is not None,
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}


# Module-level plugin instance for entry point resolution
plugin = InvestmentPlugin()

__all__ = ["InvestmentVertical", "InvestmentPlugin", "plugin"]

# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
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

Plugin paradigm (consolidated, contract >= 0.7.0):
  The single `victor.plugins` entry point at `investment = "victor_invest.vertical:plugin"`
  replaces sidecar entry points. register(context) wires up tools, dependencies,
  and safety rules in one call. Sidecar entry points are kept for backward compat
  with older Victor hosts that scan them independently.
"""

import logging
from typing import Any, Dict, Optional

from victor_contracts import PluginContext, VictorPlugin

logger = logging.getLogger(__name__)


class InvestmentPlugin(VictorPlugin):
    """Victor Plugin for Investment vertical.

    Discovered via the 'victor.plugins' entry point. Consolidates all
    registration into register(context) per contract >= 0.7.0 paradigm:
    tools, vertical, tool dependencies, and safety rules are all wired
    here instead of across separate sidecar entry points.
    """

    @property
    def name(self) -> str:
        return "investment"

    def register(self, context: PluginContext) -> None:
        """Register all investment components with the host framework.

        Consolidates what was previously spread across four sidecar entry points
        (victor.tool_dependencies, victor.safety_rules, victor.prompt_contributors,
        victor.workflow_providers) into a single register() call. Hosts running
        Hosts with contract < 0.7.0 that do not expose the new PluginContext methods still get the
        vertical and tools; the rest is silently skipped with hasattr guards.
        """
        from victor_invest.vertical.investment_vertical import InvestmentVertical

        # 1. Register the vertical (canonical — enables system prompt, stage defs, tool names)
        context.register_vertical(InvestmentVertical)

        # 2. Register tool instances so the host ToolRegistry can resolve them by name.
        #    Without this, the framework knows the tool names from get_tools() but has no
        #    instances to invoke when running as a plugin (no standalone bootstrap).
        try:
            from victor_contracts.verticals.protocols import ToolPluginHelper

            from victor_invest.tools import get_all_tools

            tool_map = {t.name: t for t in get_all_tools()}
            ToolPluginHelper.from_instances(tool_map).register(context)
        except Exception as exc:
            logger.debug("Investment tool registration via PluginContext skipped: %s", exc)

        # 3. Tool dependency provider (consolidated API — hasattr-guarded for older hosts)
        if hasattr(context, "register_tool_dependency"):
            try:
                from victor_invest.tool_dependencies import get_provider

                context.register_tool_dependency("invest", get_provider())
            except Exception as exc:
                logger.debug("Tool dependency registration skipped: %s", exc)

        # 4. Safety rules (consolidated API — hasattr-guarded)
        if hasattr(context, "register_safety_rule"):
            try:
                from victor_invest.safety_enhanced import create_investment_safety_rules

                context.register_safety_rule(create_investment_safety_rules())
            except Exception as exc:
                logger.debug("Safety rule registration skipped: %s", exc)

    def get_cli_app(self) -> Optional[Any]:
        """No CLI subcommand — victor-invest ships its own `victor-invest` CLI."""
        return None

    def on_activate(self) -> None:
        """Register role provider when the investment vertical becomes active.

        The RoleToolProvider configures subagent tool budgets for investment
        workflows. Registered here (not in register()) because it modifies
        global subagent routing state that should only apply while this
        vertical is the active vertical.
        """
        try:
            from victor_invest.role_provider import register_investment_role_provider

            register_investment_role_provider()
        except Exception as exc:
            logger.debug("Role provider registration skipped: %s", exc)

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
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}


# Canonical plugin singleton — referenced by the victor.plugins entry point.
plugin = InvestmentPlugin()


def __getattr__(name: str) -> Any:
    if name == "InvestmentVertical":
        from victor_invest.vertical.investment_vertical import InvestmentVertical

        return InvestmentVertical
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["InvestmentVertical", "InvestmentPlugin", "plugin"]

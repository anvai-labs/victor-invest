"""Backward-compatible plugin shim for the invest vertical.

The canonical entry point is now ``victor_invest.vertical:plugin``
(``InvestmentPlugin``). This module remains for any host or test that
directly imports ``victor_invest.plugin``. ``InvestPlugin`` delegates all
registration to ``InvestmentPlugin`` so both surfaces stay in sync.
"""

from __future__ import annotations

import logging
from typing import Any

from victor_contracts import PluginContext, VictorPlugin

logger = logging.getLogger(__name__)


class InvestPlugin(VictorPlugin):
    """Thin VictorPlugin shim that delegates to InvestmentPlugin.

    Kept for backward compatibility. The preferred plugin surface is
    ``victor_invest.vertical.InvestmentPlugin`` (entry point key
    ``investment``).  This class uses plugin name ``"invest"`` so that
    both can coexist in a registry without name collisions.
    """

    def __init__(self) -> None:
        from victor_invest.vertical import InvestmentPlugin

        self._delegate = InvestmentPlugin()

    @property
    def name(self) -> str:
        return "invest"

    def register(self, context: PluginContext) -> None:
        """Delegate full registration to InvestmentPlugin."""
        self._delegate.register(context)

    def get_cli_app(self) -> Any | None:
        return None

    def on_activate(self) -> None:
        self._delegate.on_activate()

    def on_deactivate(self) -> None:
        self._delegate.on_deactivate()

    async def on_activate_async(self) -> None:
        await self._delegate.on_activate_async()

    async def on_deactivate_async(self) -> None:
        await self._delegate.on_deactivate_async()

    def health_check(self) -> dict[str, Any]:
        health = self._delegate.health_check()
        health["plugin_name"] = self.name
        return health


# Singleton for any legacy import of victor_invest.plugin:plugin
plugin = InvestPlugin()

__all__ = ["InvestPlugin", "plugin"]

"""Victor plugin entry point for the invest vertical."""

from __future__ import annotations

from typing import Any, Dict, Optional

from victor_sdk import PluginContext, VictorPlugin


class InvestPlugin(VictorPlugin):
    """VictorPlugin adapter for the invest vertical package.

    This plugin registers the InvestmentVertical with Victor,
    enabling investment research and analysis capabilities.
    """

    @property
    def name(self) -> str:
        """Return stable plugin identifier."""
        return "invest"

    def register(self, context: PluginContext) -> None:
        """
        Register plugin components with the host framework.

        Args:
            context: PluginContext for registering components
        """
        from victor_invest.vertical import InvestmentVertical

        context.register_vertical(InvestmentVertical)

    def get_cli_app(self) -> Optional[Any]:
        """
        Return Typer app for CLI commands (optional).

        Note: Deprecated - use context.register_command() in register() instead.
        """
        return None

    def on_activate(self) -> None:
        """
        Called when plugin's vertical is activated (sync variant).

        Use this for:
        - Initializing resources
        - Loading configuration
        - Setup that doesn't require I/O
        """
        pass

    def on_deactivate(self) -> None:
        """
        Called when plugin's vertical is deactivated (sync variant).

        Use this for:
        - Releasing resources
        - Saving state
        - Cleanup that doesn't require I/O
        """
        pass

    async def on_activate_async(self) -> None:
        """
        Called when plugin's vertical is activated (async variant).

        When implemented, this is called instead of on_activate()
        in async contexts. Use this for I/O operations.

        Use this for:
        - Async database connections
        - Async HTTP client initialization
        - Async resource loading
        """
        pass

    async def on_deactivate_async(self) -> None:
        """
        Called when plugin's vertical is deactivated (async variant).

        When implemented, this is called instead of on_deactivate()
        in async contexts. Use this for I/O operations.

        Use this for:
        - Async connection cleanup
        - Async state saving
        - Async resource release
        """
        pass

    def health_check(self) -> Dict[str, Any]:
        """
        Return health status for this plugin.

        Returns a dictionary with at minimum a 'healthy' boolean key.
        Additional keys can provide detail about plugin status.

        Returns:
            Dict with 'healthy' key and optional detail keys
        """
        return {
            "healthy": True,
            "vertical": "invest",
            "vertical_class": "InvestmentVertical",
            "version": "0.5.0",
        }


# Singleton instance for entry point
plugin = InvestPlugin()


__all__ = ["InvestPlugin", "plugin"]

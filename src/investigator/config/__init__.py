"""
Configuration Layer

Application configuration with environment variable support.
"""

from investigator.config.config import (
    DatabaseConfig,
    ModelSpec,
    OllamaConfig,
    SECConfig,
    get_config,
)
from investigator.config.settings import InvestiGatorConfig  # noqa: F401
from investigator.config.settings import (
    AppSettings,
    CacheControlSettings,
    DatabaseSettings,
    MonitoringSettings,
    OllamaSettings,
    SECSettings,
    get_settings,
    settings,
)

# Backward compatibility alias
CacheSettings = CacheControlSettings

__all__ = [
    # New Pydantic settings
    "AppSettings",
    "CacheSettings",
    # Legacy config (dataclasses)
    "DatabaseConfig",
    "DatabaseSettings",
    "ModelSpec",
    "MonitoringSettings",
    "OllamaConfig",
    "OllamaSettings",
    "SECConfig",
    "SECSettings",
    "get_config",
    "get_settings",
    "settings",
]

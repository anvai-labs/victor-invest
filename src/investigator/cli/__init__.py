"""
InvestiGator CLI Package

Provides a unified command-line interface for investment analysis.

Usage:
    from investigator.cli import cli, main

Entry Points:
    investigator - Main CLI command (configured in pyproject.toml)
"""

from .main import cli, main
from .utils import (
    MutuallyExclusiveOption,
    error_exit,
    format_currency,
    format_percent,
    load_config,
    print_table,
    require_database,
    require_ollama,
    setup_logging,
    validate_date,
    validate_symbols,
)

__all__ = [
    "MutuallyExclusiveOption",
    "cli",
    "error_exit",
    "format_currency",
    "format_percent",
    "load_config",
    "main",
    "print_table",
    "require_database",
    "require_ollama",
    "setup_logging",
    "validate_date",
    "validate_symbols",
]

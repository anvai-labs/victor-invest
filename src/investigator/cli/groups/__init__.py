"""
CLI command groups for InvestiGator
"""

from .analyze import analyze
from .backtest import backtest
from .cache import cache
from .data import data
from .macro import macro
from .sector_multiples import sector_multiples
from .system import system

__all__ = [
    "analyze",
    "backtest",
    "cache",
    "data",
    "macro",
    "sector_multiples",
    "system",
]

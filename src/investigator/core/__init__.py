"""
InvestiGator - Core Pattern Interfaces Initialization
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

Core Pattern Interfaces and Base Implementations
"""

# Barrel module: re-exports via star imports.
# ruff: noqa: F403, F405

from .interfaces import *

__all__ = [
    # Interfaces
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisStrategy",
    "DataSourceType",
    "IAnalysisCommand",
    "IAnalysisObserver",
    "IAnalysisRepository",
    "IAnalysisStrategy",
    "IAnalysisSubject",
    "IAnalysisTemplate",
    "IDataProcessor",
    "IDataSourceAdapter",
    "IDataValidator",
    "IFundamentalAnalysisFacade",
    "QuarterlyMetrics",
]

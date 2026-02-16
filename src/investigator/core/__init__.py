#!/usr/bin/env python3
"""
InvestiGator - Core Pattern Interfaces Initialization
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

Core Pattern Interfaces and Base Implementations
"""

from .interfaces import *  # noqa: F403

__all__ = [  # noqa: F405
    # Interfaces
    "AnalysisRequest",  # noqa: F405
    "AnalysisResult",  # noqa: F405
    "QuarterlyMetrics",  # noqa: F405
    "DataSourceType",  # noqa: F405
    "AnalysisStrategy",
    "IAnalysisStrategy",
    "IDataProcessor",
    "IAnalysisObserver",
    "IAnalysisSubject",
    "IDataSourceAdapter",
    "IAnalysisRepository",
    "IDataValidator",
    "IAnalysisCommand",
    "IFundamentalAnalysisFacade",
    "IAnalysisTemplate",
]

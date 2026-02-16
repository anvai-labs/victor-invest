#!/usr/bin/env python3
"""
InvestiGator - SEC Pattern Implementations Initialization
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

SEC Pattern Implementations
SEC data fetching and analysis patterns
"""

from .sec_adapters import *  # noqa: F403
from .sec_facade import *  # noqa: F403
from .sec_strategies import *  # noqa: F403

__all__ = [  # noqa: F405
    # Facades
    "SECDataFacade",  # noqa: F405
    "FundamentalAnalysisFacadeV2",  # noqa: F405
    # Strategies
    "CompanyFactsStrategy",  # noqa: F405
    "SubmissionsStrategy",
    "CachedDataStrategy",
    "HybridFetchStrategy",
    # Adapters
    "SECToInternalAdapter",
    "InternalToLLMAdapter",
    "FilingContentAdapter",
    "CompanyFactsToDetailedAdapter",
]

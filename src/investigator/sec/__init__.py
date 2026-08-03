#!/usr/bin/env python3
"""
InvestiGator - SEC Pattern Implementations Initialization
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

SEC Pattern Implementations
SEC data fetching and analysis patterns
"""

from .sec_adapters import *
from .sec_facade import *
from .sec_strategies import *

__all__ = [
    "CachedDataStrategy",
    # Strategies
    "CompanyFactsStrategy",
    "CompanyFactsToDetailedAdapter",
    "FilingContentAdapter",
    "FundamentalAnalysisFacadeV2",
    "HybridFetchStrategy",
    "InternalToLLMAdapter",
    # Facades
    "SECDataFacade",
    # Adapters
    "SECToInternalAdapter",
    "SubmissionsStrategy",
]

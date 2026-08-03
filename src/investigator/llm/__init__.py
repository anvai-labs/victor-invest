#!/usr/bin/env python3
"""
InvestiGator - LLM Pattern Implementations Initialization
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

LLM Pattern Implementations
LLM processing and interaction patterns
"""

from .llm_facade import *
from .llm_interfaces import *
from .llm_processors import *
from .llm_strategies import *

__all__ = [
    "AggressiveLLMCacheStrategy",
    # Strategies
    "ComprehensiveLLMStrategy",
    "ILLMAnalysisTemplate",
    "ILLMCacheStrategy",
    "ILLMFactory",
    "ILLMHandler",
    "ILLMObserver",
    "ILLMProcessor",
    "ILLMStrategy",
    "ILLMSubject",
    # Observer
    "LLMAnalysisObserver",
    # Processors
    "LLMCacheHandler",
    "LLMExecutionHandler",
    # Facade and factories
    "LLMFacade",
    "LLMPriority",
    # Interfaces
    "LLMRequest",
    "LLMResponse",
    "LLMTaskType",
    "LLMValidationHandler",
    "QueuedLLMProcessor",
    "QuickLLMStrategy",
    "StandardLLMAnalysisTemplate",
    "StandardLLMCacheStrategy",
    "create_comprehensive_llm_facade",
    "create_llm_facade",
    "create_quick_llm_facade",
]

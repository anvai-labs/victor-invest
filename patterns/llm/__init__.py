#!/usr/bin/env python3
"""
InvestiGator - LLM Pattern Implementations Initialization
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

LLM Pattern Implementations
LLM processing and interaction patterns
"""

from .llm_facade import *  # noqa: F403
from .llm_interfaces import *  # noqa: F403
from .llm_processors import *  # noqa: F403
from .llm_strategies import *  # noqa: F403

__all__ = [  # noqa: F405
    # Facade and factories
    "LLMFacade",  # noqa: F405
    "create_llm_facade",  # noqa: F405
    "create_comprehensive_llm_facade",  # noqa: F405
    "create_quick_llm_facade",  # noqa: F405
    # Interfaces
    "LLMRequest",
    "LLMResponse",
    "LLMTaskType",
    "LLMPriority",
    "ILLMStrategy",
    "ILLMProcessor",
    "ILLMHandler",
    "ILLMObserver",
    "ILLMSubject",
    "ILLMAnalysisTemplate",
    "ILLMFactory",
    "ILLMCacheStrategy",
    # Strategies
    "ComprehensiveLLMStrategy",
    "QuickLLMStrategy",
    "StandardLLMCacheStrategy",
    "AggressiveLLMCacheStrategy",
    # Processors
    "LLMCacheHandler",
    "LLMValidationHandler",
    "LLMExecutionHandler",
    "QueuedLLMProcessor",
    "StandardLLMAnalysisTemplate",
    # Observer
    "LLMAnalysisObserver",
]

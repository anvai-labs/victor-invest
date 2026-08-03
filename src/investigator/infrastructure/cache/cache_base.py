"""
InvestiGator - Cache Base Classes
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

Abstract base class for cache storage handlers
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from .cache_types import CacheType

logger = logging.getLogger(__name__)


class CacheStorageHandler(ABC):
    """Abstract base class for cache storage handlers"""

    def __init__(self, cache_type: CacheType, priority: int = 0):
        """
        Initialize cache handler

        Args:
            cache_type: Type of cache (SEC_RESPONSE, LLM_RESPONSE, etc.)
            priority: Priority for lookup (negative means no lookup)
        """
        self.cache_type = cache_type
        self.priority = priority

    @abstractmethod
    def get(self, key: tuple | dict) -> dict[str, Any] | None:
        """
        Retrieve data from cache

        Args:
            key: Tuple or Dict containing lookup keys

        Returns:
            Cached data if found, None otherwise
        """

    @abstractmethod
    def set(self, key: tuple | dict, value: dict[str, Any]) -> bool:
        """
        Store data in cache

        Args:
            key: Tuple or Dict containing storage keys
            value: Data to cache

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def exists(self, key: tuple | dict) -> bool:
        """
        Check if key exists in cache

        Args:
            key: Tuple or Dict containing lookup keys

        Returns:
            True if key exists, False otherwise
        """

    @abstractmethod
    def delete(self, key: tuple | dict) -> bool:
        """
        Delete data from cache

        Args:
            key: Tuple or Dict containing keys to delete

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def delete_by_pattern(self, pattern: str) -> int:
        """
        Delete all cache entries matching a pattern

        Args:
            pattern: Pattern to match keys (e.g., "AAPL_*", "*_sec_*")

        Returns:
            Number of entries deleted
        """

    @abstractmethod
    def clear_all(self) -> bool:
        """
        Clear all data from this cache handler

        Returns:
            True if successful, False otherwise
        """

    def _normalize_key(self, key: tuple | dict) -> dict[str, str]:
        """
        Normalize key to dictionary format

        Args:
            key: Tuple or Dict containing keys

        Returns:
            Dictionary with normalized keys
        """
        if isinstance(key, tuple):
            # Define standard key mappings for each cache type
            if self.cache_type == CacheType.SEC_RESPONSE:
                # Order: (symbol, category, period, form_type)
                if len(key) >= 4:
                    return {
                        "symbol": str(key[0]),
                        "category": str(key[1]),
                        "period": str(key[2]),
                        "form_type": str(key[3]),
                    }
            elif self.cache_type == CacheType.LLM_RESPONSE:
                # Order: (symbol, llm_type, period, form_type, fiscal_year, fiscal_period)
                if len(key) >= 4:
                    normalized = {
                        "symbol": str(key[0]),
                        "llm_type": str(key[1]),
                        "period": str(key[2]),
                        "form_type": str(key[3]),
                    }
                    # Include fiscal information if available (for quarterly analysis)
                    if len(key) >= 6:
                        normalized["fiscal_year"] = str(key[4])
                        normalized["fiscal_period"] = str(key[5])
                    return normalized
            elif self.cache_type == CacheType.TECHNICAL_DATA:
                # Order: (symbol, data_type)
                if len(key) >= 2:
                    return {"symbol": str(key[0]), "data_type": str(key[1])}
            elif self.cache_type == CacheType.SUBMISSION_DATA:
                # Order: (symbol, cik)
                if len(key) >= 2:
                    return {"symbol": str(key[0]), "cik": str(key[1])}
            elif self.cache_type == CacheType.COMPANY_FACTS:
                # Order: (symbol,) or (symbol, cik)
                if len(key) >= 1:
                    normalized = {"symbol": str(key[0])}
                    if len(key) >= 2:
                        normalized["cik"] = str(key[1])
                    return normalized
            elif self.cache_type == CacheType.QUARTERLY_METRICS:
                # Order: (symbol, period)
                if len(key) >= 2:
                    return {"symbol": str(key[0]), "period": str(key[1])}
        elif isinstance(key, dict):
            return {k: str(v) for k, v in key.items()}

        raise ValueError(f"Invalid key format: {key}")

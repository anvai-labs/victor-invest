# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Data Source Interfaces.

Defines abstract interfaces for data sources following Interface Segregation.
Each interface is focused on a specific data type.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class DataSourceType(Enum):
    """Types of data sources."""

    INSIDER_SENTIMENT = "insider_sentiment"
    INSTITUTIONAL_HOLDINGS = "institutional_holdings"
    SHORT_INTEREST = "short_interest"
    TREASURY_YIELDS = "treasury_yields"
    MACRO_INDICATORS = "macro_indicators"
    MARKET_REGIME = "market_regime"
    CREDIT_RISK = "credit_risk"
    TECHNICAL_INDICATORS = "technical_indicators"
    PRICE_DATA = "price_data"
    # Regional Fed and CBOE economic indicators
    REGIONAL_FED = "regional_fed"
    CBOE_VOLATILITY = "cboe_volatility"


@dataclass
class DataSourceResult:
    """Result from a data source query."""

    source_type: DataSourceType
    symbol: str | None = None
    as_of_date: date | None = None
    data: dict[str, Any] = field(default_factory=dict)
    is_stale: bool = False
    last_updated: datetime | None = None
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """Check if result has valid data."""
        return self.error is None and len(self.data) > 0


class DataSourceInterface(ABC):
    """Abstract interface for all data sources."""

    @property
    @abstractmethod
    def source_type(self) -> DataSourceType:
        """Return the type of data this source provides."""

    @abstractmethod
    async def get_for_symbol(
        self,
        symbol: str,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get data for a specific symbol.

        Args:
            symbol: Stock ticker symbol.
            as_of_date: Date to get data as of (for historical queries).

        Returns:
            DataSourceResult with the data.
        """

    @abstractmethod
    async def get_batch(
        self,
        symbols: list[str],
        as_of_date: date | None = None,
    ) -> dict[str, DataSourceResult]:
        """Get data for multiple symbols efficiently.

        Args:
            symbols: List of stock ticker symbols.
            as_of_date: Date to get data as of.

        Returns:
            Dict mapping symbol to DataSourceResult.
        """


class InsiderDataInterface(DataSourceInterface):
    """Interface for insider sentiment data."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.INSIDER_SENTIMENT

    @abstractmethod
    async def get_sentiment(
        self,
        symbol: str,
        days: int = 90,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get insider sentiment score for a symbol."""

    @abstractmethod
    async def get_recent_transactions(
        self,
        symbol: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get recent insider transactions."""


class InstitutionalDataInterface(DataSourceInterface):
    """Interface for institutional holdings data."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.INSTITUTIONAL_HOLDINGS

    @abstractmethod
    async def get_top_holders(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get top institutional holders."""

    @abstractmethod
    async def get_ownership_changes(
        self,
        symbol: str,
        quarters: int = 4,
    ) -> list[dict[str, Any]]:
        """Get quarterly ownership changes."""


class ShortInterestInterface(DataSourceInterface):
    """Interface for short interest data."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.SHORT_INTEREST

    @abstractmethod
    async def get_short_ratio(
        self,
        symbol: str,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get current short interest ratio."""

    @abstractmethod
    async def get_short_history(
        self,
        symbol: str,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get short interest history."""


class MacroDataInterface(DataSourceInterface):
    """Interface for macro/economic indicator data."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.MACRO_INDICATORS

    @abstractmethod
    async def get_indicator(
        self,
        indicator_id: str,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get a specific macro indicator value."""

    @abstractmethod
    async def get_indicators_batch(
        self,
        indicator_ids: list[str],
        as_of_date: date | None = None,
    ) -> dict[str, DataSourceResult]:
        """Get multiple indicators efficiently."""


class MarketRegimeInterface(DataSourceInterface):
    """Interface for market regime classification."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.MARKET_REGIME

    @abstractmethod
    async def get_current_regime(self) -> DataSourceResult:
        """Get current market regime classification."""

    @abstractmethod
    async def get_regime_history(
        self,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get regime history with transitions."""


class CreditRiskInterface(DataSourceInterface):
    """Interface for credit risk scores."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.CREDIT_RISK

    @abstractmethod
    async def get_credit_scores(
        self,
        symbol: str,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get Altman Z, Beneish M, Piotroski F scores."""

    @abstractmethod
    async def get_distress_tier(
        self,
        symbol: str,
    ) -> str:
        """Get distress tier classification."""


class TechnicalDataInterface(DataSourceInterface):
    """Interface for technical indicator data."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.TECHNICAL_INDICATORS

    @abstractmethod
    async def get_indicators(
        self,
        symbol: str,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get technical indicators (RSI, MACD, etc.)."""

    @abstractmethod
    async def get_entry_exit_signals(
        self,
        symbol: str,
        as_of_date: date | None = None,
    ) -> DataSourceResult:
        """Get entry/exit signal analysis."""

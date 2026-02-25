# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
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

"""Valuation Tool for Victor Invest.

This tool wraps the existing valuation services to provide multi-model
valuation analysis including DCF, P/E, P/S, P/B, GGM, and EV/EBITDA.

Infrastructure wrapped:
- investigator.domain.services.valuation.DCFValuation
- investigator.domain.services.valuation.GordonGrowthModel
- investigator.domain.services.valuation.SectorValuationRouter
- investigator.domain.services.valuation.models (PE, PS, PB, EV/EBITDA)

Example:
    tool = ValuationTool()

    # Run DCF valuation
    result = await tool.execute(
        symbol="AAPL",
        model="dcf"
    )

    # Run all applicable valuation models
    result = await tool.execute(
        symbol="AAPL",
        model="all"
    )

    # Get sector-appropriate valuation
    result = await tool.execute(
        symbol="AAPL",
        model="sector_routed"
    )
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

# Shared market data services (used by rl_backtest, batch_analysis_runner, victor_invest)
from investigator.domain.services.market_data import (
    DataValidationService,
    PriceService,
    SharesService,
    SymbolMetadataService,
)

# Sector name mapper for normalization
from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

# Shared valuation config services (single source of truth for sector multiples, CAPM, GGM)
from investigator.domain.services.valuation_shared import (
    SectorMultiplesService,
    ValuationConfigService,
)
from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Sector median multiples (used as fallback if not available from database)
DEFAULT_SECTOR_MULTIPLES = {
    "Technology": {"pe": 28.0, "ps": 6.0, "pb": 8.0, "ev_ebitda": 18.0},
    "Healthcare": {"pe": 22.0, "ps": 3.5, "pb": 4.0, "ev_ebitda": 14.0},
    "Financials": {"pe": 12.0, "ps": 2.5, "pb": 1.2, "ev_ebitda": 10.0},
    "Consumer Discretionary": {"pe": 20.0, "ps": 1.5, "pb": 3.5, "ev_ebitda": 12.0},
    "Consumer Staples": {"pe": 18.0, "ps": 1.8, "pb": 4.0, "ev_ebitda": 12.0},
    "Industrials": {"pe": 18.0, "ps": 1.5, "pb": 3.0, "ev_ebitda": 11.0},
    "Materials": {"pe": 14.0, "ps": 1.2, "pb": 2.0, "ev_ebitda": 8.0},
    "Energy": {"pe": 10.0, "ps": 1.0, "pb": 1.5, "ev_ebitda": 6.0},
    "Utilities": {"pe": 16.0, "ps": 2.0, "pb": 1.5, "ev_ebitda": 10.0},
    "Real Estate": {"pe": 35.0, "ps": 6.0, "pb": 2.0, "ev_ebitda": 16.0},
    "Communication Services": {"pe": 20.0, "ps": 3.0, "pb": 3.0, "ev_ebitda": 10.0},
}

# Industry-specific P/E fallbacks that override sector defaults
# These provide more accurate valuations for industries that differ significantly
# from their sector averages
INDUSTRY_PE_FALLBACKS = {
    "Semiconductors": 18,  # Not 28x tech default
    "Auto Manufacturing": 8,  # Not 20x consumer default
    "Automobile Manufacturers": 8,
    "Aerospace & Defense": 16,  # Backlog stability
    "Pharmaceuticals": 14,  # Patent cliff risk
    "Software - Application": 35,  # High growth SaaS
    "Software - Infrastructure": 30,  # Infrastructure software
    "Property-Casualty Insurers": 10,  # Asset-heavy
    "Major Banks": 10,  # Asset-heavy
    "Regional Banks": 9,  # Credit risk
    "Banks": 10,
}


class ValuationTool(BaseTool):
    """Tool for multi-model company valuation.

    Provides access to various valuation models including:
    - DCF (Discounted Cash Flow)
    - GGM (Gordon Growth Model / Dividend Discount)
    - P/E Multiple
    - P/S Multiple
    - P/B Multiple
    - EV/EBITDA Multiple
    - Sector-routed valuation (automatic model selection)

    Attributes:
        name: "valuation"
        description: Tool description for agent discovery
    """

    name = "valuation"
    description = """Perform company valuation using multiple models.

Models available:
- dcf: Discounted Cash Flow - projects future free cash flows
- ggm: Gordon Growth Model - dividend discount for dividend payers
- pe: P/E Multiple - price-to-earnings based valuation
- ps: P/S Multiple - price-to-sales for growth companies
- pb: P/B Multiple - price-to-book for asset-heavy companies
- ev_ebitda: EV/EBITDA - enterprise value based
- sector_routed: Automatic model selection based on company sector
- all: Run all applicable models

Parameters:
- symbol: Stock ticker symbol (required)
- model: Valuation model to use (default: "all")
- quarterly_metrics: Pre-fetched quarterly data (optional)
- current_price: Current stock price for upside calculation (optional)
- cost_of_equity: Required return rate for DCF/GGM (optional)
- terminal_growth_rate: Terminal growth for DCF (optional)

Returns fair value estimates, model assumptions, and upside/downside vs current price.
"""

    def __init__(self, config: Optional[Any] = None):
        """Initialize Valuation Tool.

        Args:
            config: Optional investigator config object
        """
        super().__init__(config)
        self._db_manager: Optional[Any] = None
        # Shared services will be initialized lazily
        self._shares_service: Optional[Any] = None
        self._price_service: Optional[Any] = None
        self._metadata_service: Optional[Any] = None
        self._validation_service: Optional[Any] = None
        # Shared valuation config services
        self._valuation_config_service: Optional[Any] = None
        self._sector_multiples_service: Optional[Any] = None

    async def initialize(self) -> None:
        """Initialize valuation infrastructure components."""
        try:
            if self.config is None:
                try:
                    from investigator.config import get_config

                    self.config = get_config()
                except ImportError:
                    pass

            # Initialize database components for data access
            # Try to use database engine if available
            try:
                from investigator.infrastructure.database import get_database_engine

                self._db_engine = get_database_engine()
            except (ImportError, Exception) as e:
                logger.debug(f"Database engine not available: {e}")
                self._db_engine = None

            # db_manager is optional - valuation can work with pre-fetched data
            self._db_manager = None

            # Initialize shared market data services
            # These provide consistent implementations across rl_backtest, batch_analysis_runner, and victor_invest
            try:
                self._shares_service = SharesService()
                self._price_service = PriceService()
                self._metadata_service = SymbolMetadataService()
                self._validation_service = DataValidationService()
                logger.debug("Shared market data services initialized")
            except Exception as e:
                logger.warning(f"Could not initialize shared services: {e}")

            # Initialize shared valuation config services
            # Single source of truth for sector multiples, CAPM, GGM defaults
            try:
                self._valuation_config_service = ValuationConfigService()
                self._sector_multiples_service = SectorMultiplesService(
                    self._valuation_config_service
                )
                logger.debug("Shared valuation config services initialized")
            except Exception as e:
                logger.warning(f"Could not initialize valuation config services: {e}")

            self._initialized = True
            logger.info("ValuationTool initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize ValuationTool: {e}")
            # Set as initialized anyway - will work with pre-fetched data
            self._initialized = True

    async def execute(
        self,
        _exec_ctx: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        model: str = "all",
        quarterly_metrics: Optional[List[Dict]] = None,
        multi_year_data: Optional[List[Dict]] = None,
        current_price: Optional[float] = None,
        cost_of_equity: Optional[float] = None,
        terminal_growth_rate: Optional[float] = None,
        **kwargs,
    ) -> ToolResult:
        """Execute valuation model(s) for a symbol.

        Args:
            symbol: Stock ticker symbol
            model: Valuation model to run:
                - "dcf": Discounted Cash Flow
                - "ggm": Gordon Growth Model
                - "pe": P/E Multiple
                - "ps": P/S Multiple
                - "pb": P/B Multiple
                - "ev_ebitda": EV/EBITDA Multiple
                - "sector_routed": Auto-select based on sector
                - "all": Run all applicable models
            quarterly_metrics: Pre-fetched quarterly financial data
            multi_year_data: Multi-year historical data for trend analysis
            current_price: Current stock price for upside calculation
            cost_of_equity: Required rate of return (default: calculated from CAPM)
            terminal_growth_rate: Long-term growth rate for DCF (default: sector-based)
            **kwargs: Additional model-specific parameters

        Returns:
            ToolResult with valuation results or error
        """
        try:
            await self.ensure_initialized()

            symbol = symbol.upper().strip()
            if not symbol:
                return ToolResult.create_failure("Symbol is required")

            model = model.lower().strip()

            # Fetch data if not provided
            if quarterly_metrics is None or multi_year_data is None:
                data_result = await self._fetch_valuation_data(symbol)
                if not data_result["success"]:
                    return ToolResult.create_failure(
                        f"Failed to fetch data for valuation: {data_result.get('error')}",
                        metadata={"symbol": symbol},
                    )
                if quarterly_metrics is None:
                    quarterly_metrics = data_result.get("quarterly_metrics", [])
                if multi_year_data is None:
                    multi_year_data = data_result.get("multi_year_data", [])

            # Get current price if not provided
            if current_price is None:
                current_price = await self._get_current_price(symbol)

            # Route to appropriate model(s)
            if model == "all":
                return await self._run_all_models(
                    symbol,
                    quarterly_metrics,
                    multi_year_data,
                    current_price,
                    cost_of_equity,
                    terminal_growth_rate,
                )
            elif model == "sector_routed":
                return await self._run_sector_routed(
                    symbol, quarterly_metrics, multi_year_data, current_price
                )
            elif model == "dcf":
                return await self._run_dcf(
                    symbol,
                    quarterly_metrics,
                    multi_year_data,
                    current_price,
                    cost_of_equity,
                    terminal_growth_rate,
                )
            elif model == "ggm":
                return await self._run_ggm(
                    symbol,
                    quarterly_metrics,
                    multi_year_data,
                    current_price,
                    cost_of_equity,
                    terminal_growth_rate,
                )
            elif model == "pe":
                return await self._run_pe_multiple(
                    symbol, quarterly_metrics, current_price
                )
            elif model == "ps":
                return await self._run_ps_multiple(
                    symbol, quarterly_metrics, current_price
                )
            elif model == "pb":
                return await self._run_pb_multiple(
                    symbol, quarterly_metrics, current_price
                )
            elif model == "ev_ebitda":
                return await self._run_ev_ebitda(
                    symbol, quarterly_metrics, current_price
                )
            else:
                return ToolResult.create_failure(
                    f"Unknown model: {model}. Valid models: "
                    "dcf, ggm, pe, ps, pb, ev_ebitda, sector_routed, all"
                )

        except Exception as e:
            logger.error(f"ValuationTool execute error for {symbol}: {e}")
            return ToolResult.create_failure(
                f"Valuation failed: {str(e)}",
                metadata={"symbol": symbol, "model": model},
            )

    async def _fetch_valuation_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch required data for valuation.

        Attempts multiple sources:
        1. Database manager (if available)
        2. SEC filing tool (direct XBRL data)

        Args:
            symbol: Stock ticker

        Returns:
            Dict with quarterly_metrics, multi_year_data, and success flag
        """
        try:
            quarterly_metrics: list[Any] = []
            multi_year_data: list[Any] = []

            # Try database manager first
            if self._db_manager:
                db_manager = self._db_manager
                loop = asyncio.get_event_loop()
                try:
                    quarterly_metrics = await loop.run_in_executor(
                        None,
                        lambda: (
                            db_manager.get_quarterly_metrics(symbol)
                            if hasattr(db_manager, "get_quarterly_metrics")
                            else []
                        ),
                    )
                    multi_year_data = await loop.run_in_executor(
                        None,
                        lambda: (
                            db_manager.get_multi_year_data(symbol)
                            if hasattr(db_manager, "get_multi_year_data")
                            else []
                        ),
                    )
                except Exception as e:
                    logger.debug(f"Database fetch failed for {symbol}: {e}")

            # If database didn't return data, try SEC filing tool
            if not quarterly_metrics:
                try:
                    from victor_invest.tools.sec_filing import SECFilingTool

                    sec_tool = SECFilingTool()
                    await sec_tool.initialize()

                    # Get quarterly financial data from processed table
                    quarterly_result = await sec_tool.execute(
                        {},
                        symbol=symbol,
                        action="get_quarterly_financials",
                        num_periods=12,
                    )

                    if quarterly_result.success and quarterly_result.output:
                        quarterly_metrics = quarterly_result.output.get(
                            "quarterly_metrics", []
                        )
                        logger.info(
                            f"Fetched {len(quarterly_metrics)} quarterly periods from SEC processed data for {symbol}"
                        )

                except Exception as e:
                    logger.debug(f"SEC fetch failed for {symbol}: {e}")

            return {
                "success": bool(quarterly_metrics),
                "quarterly_metrics": quarterly_metrics or [],
                "multi_year_data": multi_year_data or [],
            }

        except Exception as e:
            logger.error(f"Error fetching valuation data for {symbol}: {e}")
            return {
                "success": False,
                "error": str(e),
                "quarterly_metrics": [],
                "multi_year_data": [],
            }

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current stock price.

        Delegates to shared PriceService for consistent implementation
        across rl_backtest, batch_analysis_runner, and victor_invest.
        """
        try:
            if self._price_service:
                result: float | None = self._price_service.get_current_price(symbol)
                return result

            # Fallback to legacy method if shared service not available
            from investigator.infrastructure.database.market_data import (
                get_market_data_fetcher,
            )

            fetcher = get_market_data_fetcher(self.config)
            info = fetcher.get_stock_info(symbol)
            price: float | None = info.get("current_price")
            return price
        except Exception as e:
            logger.warning(f"Could not get current price for {symbol}: {e}")
            return None

    async def _get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive stock info including sector, shares outstanding, etc.

        Delegates to shared SymbolMetadataService for consistent implementation
        across rl_backtest, batch_analysis_runner, and victor_invest.
        """
        try:
            if self._metadata_service:
                metadata = self._metadata_service.get_metadata(symbol)
                if metadata:
                    # Get SEC shares for source of truth (consistent with rl_backtest)
                    sec_shares = None
                    if self._shares_service:
                        sec_shares = self._shares_service.get_sec_shares(symbol)

                    return {
                        "sector": metadata.sector,
                        "industry": metadata.industry,
                        "shares_outstanding": sec_shares or metadata.shares_outstanding,
                        "market_cap": metadata.market_cap,
                        "beta": metadata.beta,
                    }

            # Fallback to legacy method if shared service not available
            from investigator.infrastructure.database.market_data import (
                get_market_data_fetcher,
            )

            fetcher = get_market_data_fetcher(self.config)
            info = fetcher.get_stock_info(symbol)
            return info or {}
        except Exception as e:
            logger.warning(f"Could not get stock info for {symbol}: {e}")
            return {}

    def _build_company_profile(
        self, symbol: str, stock_info: Dict[str, Any], quarterly_metrics: List[Dict]
    ):
        """Build a CompanyProfile from available data.

        Handles two formats:
        1. Direct quarterly metrics: [{"net_income": x, "revenue": y, ...}]
        2. SEC filing tool format: [{"income_statement": {...}, "balance_sheet": {...}}]
        """
        try:
            from investigator.domain.services.valuation.models.company_profile import (
                CompanyProfile,
            )

            sector = stock_info.get("sector", "Unknown")
            industry = stock_info.get("industry")

            # Calculate profitability indicators from quarterly metrics
            has_positive_fcf = None
            has_positive_earnings = None
            ttm_fcf = None
            fcf_margin = None
            total_debt = None
            cash = None
            net_debt_to_ebitda = None
            total_revenue_val = None

            if quarterly_metrics:
                q = quarterly_metrics[0]

                # Calculate total_debt from processed data
                long_term_debt = q.get("long_term_debt") or 0
                short_term_debt = q.get("short_term_debt") or 0
                total_debt = (
                    long_term_debt + short_term_debt
                    if (long_term_debt or short_term_debt)
                    else None
                )

                # Get cash
                cash = q.get("cash_and_equivalents")

                # Get EBITDA for net_debt_to_ebitda calculation
                ebitda = q.get("ebitda")
                if (
                    total_debt is not None
                    and cash is not None
                    and ebitda
                    and ebitda > 0
                ):
                    net_debt = total_debt - cash
                    net_debt_to_ebitda = net_debt / ebitda

                # Get total revenue for margin calculation
                total_revenue_val = q.get("total_revenue") or q.get("revenue")

                # Handle SEC filing tool format (nested structure)
                if "income_statement" in quarterly_metrics[0]:
                    sec_data = quarterly_metrics[0]
                    income = sec_data.get("income_statement", {})
                    cash_flow = sec_data.get("cash_flow", {})

                    total_fcf = cash_flow.get("free_cash_flow") or 0
                    total_earnings = (
                        income.get("net_income") or income.get("net_income_loss") or 0
                    )
                    total_revenue = (
                        income.get("total_revenue") or income.get("revenue") or 0
                    )
                    total_revenue_val = total_revenue_val or total_revenue

                    has_positive_fcf = total_fcf > 0 if total_fcf else None
                    has_positive_earnings = (
                        total_earnings > 0 if total_earnings else None
                    )
                    ttm_fcf = total_fcf if total_fcf else None
                    fcf_margin = (
                        total_fcf / total_revenue
                        if total_revenue and total_fcf
                        else None
                    )

                elif len(quarterly_metrics) >= 4:
                    # Sum last 4 quarters for TTM values
                    # Handle both nested format (income_statement/cash_flow) and flat format
                    recent_quarters = quarterly_metrics[:4]

                    # Check if data is in nested format
                    if "income_statement" in recent_quarters[0]:
                        total_fcf = sum(
                            q.get("cash_flow", {}).get("free_cash_flow") or 0
                            for q in recent_quarters
                        )
                        total_earnings = sum(
                            q.get("income_statement", {}).get("net_income") or 0
                            for q in recent_quarters
                        )
                        total_revenue = sum(
                            q.get("income_statement", {}).get("total_revenue") or 0
                            for q in recent_quarters
                        )
                    else:
                        # Flat format
                        total_fcf = sum(
                            q.get("free_cash_flow", 0) or 0 for q in recent_quarters
                        )
                        total_earnings = sum(
                            q.get("net_income", 0) or 0 for q in recent_quarters
                        )
                        total_revenue = sum(
                            q.get("revenue", 0) or q.get("total_revenue", 0) or 0
                            for q in recent_quarters
                        )

                    has_positive_fcf = total_fcf > 0
                    has_positive_earnings = total_earnings > 0
                    ttm_fcf = total_fcf
                    fcf_margin = (
                        total_fcf / total_revenue if total_revenue > 0 else None
                    )
                else:
                    # Single quarter - use as approximation
                    q = quarterly_metrics[0]

                    # Handle nested format
                    if "income_statement" in q:
                        total_fcf = q.get("cash_flow", {}).get("free_cash_flow") or 0
                        total_earnings = (
                            q.get("income_statement", {}).get("net_income") or 0
                        )
                        total_revenue = (
                            q.get("income_statement", {}).get("total_revenue") or 0
                        )
                    else:
                        # Flat format
                        total_fcf = q.get("free_cash_flow", 0) or 0
                        total_earnings = q.get("net_income", 0) or 0
                        total_revenue = (
                            q.get("revenue", 0) or q.get("total_revenue", 0) or 0
                        )

                    has_positive_fcf = total_fcf > 0 if total_fcf else None
                    has_positive_earnings = (
                        total_earnings > 0 if total_earnings else None
                    )
                    ttm_fcf = total_fcf if total_fcf else None
                    fcf_margin = (
                        total_fcf / total_revenue
                        if total_revenue and total_fcf
                        else None
                    )

            # Calculate shares outstanding for EV/EBITDA model
            shares_outstanding_val = None
            revenue_growth_yoy = None
            if quarterly_metrics:
                shares_from_q = quarterly_metrics[0].get("shares_outstanding")
                if shares_from_q:
                    shares_outstanding_val = float(shares_from_q)

                # Calculate revenue growth using shared GrowthCalculator
                from investigator.domain.services.valuation.common import (
                    GrowthCalculator,
                )

                revenue_growth_yoy = GrowthCalculator.calculate_revenue_growth_ttm(
                    quarterly_data=quarterly_metrics,
                    logger=logger,
                )

            return CompanyProfile(
                symbol=symbol,
                sector=sector,
                industry=industry,
                has_positive_fcf=has_positive_fcf,
                has_positive_earnings=has_positive_earnings,
                ttm_fcf=ttm_fcf,
                fcf_margin=fcf_margin,
                total_debt=total_debt,
                cash=cash,
                net_debt_to_ebitda=net_debt_to_ebitda,
                shares_outstanding=shares_outstanding_val,
                revenue=total_revenue_val,
                net_income=q.get("net_income") if quarterly_metrics else None,
                ebitda=q.get("ebitda") if quarterly_metrics else None,
                revenue_growth_yoy=revenue_growth_yoy,
            )

        except ImportError:
            # Return None if CompanyProfile not available
            return None

    def _calculate_ttm_metrics(
        self, quarterly_metrics: List[Dict], shares_outstanding: Optional[float]
    ) -> Dict[str, Optional[float]]:
        """Calculate TTM metrics from quarterly data.

        Handles two formats:
        1. Direct quarterly metrics: [{"net_income": x, "revenue": y, ...}]
        2. SEC filing tool format: [{"income_statement": {...}, "balance_sheet": {...}}]

        Uses shared TTMMetrics from valuation.common for standardized calculations.
        """
        result: Dict[str, Optional[float]] = {
            "ttm_eps": None,
            "ttm_revenue": None,
            "ttm_ebitda": None,
            "book_value": None,
            "revenue_per_share": None,
            "book_value_per_share": None,
        }

        if not quarterly_metrics:
            return result

        # Handle SEC filing tool format (nested structure) - use shared TTMMetrics
        if quarterly_metrics and "income_statement" in quarterly_metrics[0]:
            try:
                from investigator.domain.services.valuation.common import TTMMetrics

                # CRITICAL FIX: Filter out FY (full year) periods to avoid double-counting
                # FY periods contain Q1+Q2+Q3+Q4 data and should not be included in TTM sum
                from investigator.domain.services.valuation_shared.q4_derivation import (
                    filter_quarters_only,
                )

                quarterly_only = filter_quarters_only(quarterly_metrics)

                # Ensure we have at least 4 quarterly periods (not FY)
                if len(quarterly_only) >= 4:
                    result["ttm_eps"] = TTMMetrics.calculate_ttm_eps(
                        quarterly_data=quarterly_only,
                        shares_outstanding=shares_outstanding,
                    )
                    result["ttm_revenue"] = TTMMetrics.calculate_ttm_revenue(
                        quarterly_data=quarterly_only
                    )
                    result["ttm_ebitda"] = TTMMetrics.calculate_ttm_ebitda(
                        quarterly_data=quarterly_only
                    )
                else:
                    # Fallback to all quarters if not enough Q periods
                    result["ttm_eps"] = TTMMetrics.calculate_ttm_eps(
                        quarterly_data=quarterly_metrics,
                        shares_outstanding=shares_outstanding,
                    )
                    result["ttm_revenue"] = TTMMetrics.calculate_ttm_revenue(
                        quarterly_data=quarterly_metrics
                    )
                    result["ttm_ebitda"] = TTMMetrics.calculate_ttm_ebitda(
                        quarterly_data=quarterly_metrics
                    )

                # Book value from balance sheet
                if quarterly_metrics:
                    sec_data = quarterly_metrics[0]
                    balance = sec_data.get("balance_sheet", {})
                    book_value = balance.get("stockholders_equity") or balance.get(
                        "total_equity"
                    )
                    result["book_value"] = book_value

                    if shares_outstanding and shares_outstanding > 0:
                        result["revenue_per_share"] = (
                            result["ttm_revenue"] / shares_outstanding
                            if result["ttm_revenue"]
                            else None
                        )
                        result["book_value_per_share"] = (
                            book_value / shares_outstanding if book_value else None
                        )

                return result

            except Exception as e:
                logger.debug(f"TTMMetrics failed for SEC format, using fallback: {e}")

                # Fallback to direct extraction from nested structure
                sec_data = quarterly_metrics[0]
                income = sec_data.get("income_statement", {})
                balance = sec_data.get("balance_sheet", {})

                ttm_net_income = income.get("net_income") or income.get(
                    "net_income_loss"
                )
                ttm_revenue = income.get("total_revenue") or income.get("revenue")
                ttm_ebitda = income.get("ebitda")
                book_value = balance.get("stockholders_equity") or balance.get(
                    "total_equity"
                )

                result["ttm_revenue"] = ttm_revenue
                result["ttm_ebitda"] = ttm_ebitda
                result["book_value"] = book_value

                if shares_outstanding and shares_outstanding > 0:
                    result["ttm_eps"] = (
                        ttm_net_income / shares_outstanding if ttm_net_income else None
                    )
                    result["revenue_per_share"] = (
                        ttm_revenue / shares_outstanding if ttm_revenue else None
                    )
                    result["book_value_per_share"] = (
                        book_value / shares_outstanding if book_value else None
                    )

                return result

        # Handle direct quarterly metrics format - use shared TTMMetrics
        try:
            from investigator.domain.services.valuation.common import TTMMetrics

            result["ttm_eps"] = TTMMetrics.calculate_ttm_eps(
                quarterly_data=quarterly_metrics,
                shares_outstanding=shares_outstanding,
            )
            result["ttm_revenue"] = TTMMetrics.calculate_ttm_revenue(
                quarterly_data=quarterly_metrics
            )
            result["ttm_ebitda"] = TTMMetrics.calculate_ttm_ebitda(
                quarterly_data=quarterly_metrics
            )

            # Book value and per-share metrics (not in TTMMetrics yet)
            if quarterly_metrics:
                most_recent = quarterly_metrics[0]
                book_value = (
                    most_recent.get("stockholders_equity")
                    or most_recent.get("total_stockholders_equity")
                    or most_recent.get("book_value")
                )
                result["book_value"] = book_value

                if shares_outstanding and shares_outstanding > 0:
                    result["revenue_per_share"] = (
                        result["ttm_revenue"] / shares_outstanding
                        if result["ttm_revenue"]
                        else None
                    )
                    result["book_value_per_share"] = (
                        book_value / shares_outstanding if book_value else None
                    )

            return result

        except Exception as e:
            logger.debug(f"Shared TTMMetrics not available, using fallback: {e}")

        # Fallback to inline calculation for direct quarterly metrics format
        if len(quarterly_metrics) < 4:
            # For single quarter data, use as TTM approximation
            q = quarterly_metrics[0]
            ttm_net_income = q.get("net_income", 0) or 0
            ttm_revenue = q.get("total_revenue") or q.get("revenue", 0) or 0
            ttm_ebitda = q.get("ebitda", 0) or 0
            book_value = (
                q.get("stockholders_equity")
                or q.get("total_stockholders_equity")
                or q.get("book_value")
            )
        else:
            # Sum last 4 quarters for TTM values
            recent_quarters = quarterly_metrics[:4]
            ttm_net_income = sum(q.get("net_income", 0) or 0 for q in recent_quarters)
            ttm_revenue = sum(
                q.get("total_revenue") or q.get("revenue", 0) or 0
                for q in recent_quarters
            )
            ttm_ebitda = sum(q.get("ebitda", 0) or 0 for q in recent_quarters)
            # Book value from most recent quarter
            book_value = recent_quarters[0].get("stockholders_equity")
            if book_value is None:
                book_value = recent_quarters[0].get("total_stockholders_equity")
            if book_value is None:
                book_value = recent_quarters[0].get("book_value")

        result["ttm_revenue"] = ttm_revenue if ttm_revenue else None
        result["ttm_ebitda"] = ttm_ebitda if ttm_ebitda else None
        result["book_value"] = book_value

        if shares_outstanding and shares_outstanding > 0:
            result["ttm_eps"] = (
                ttm_net_income / shares_outstanding if ttm_net_income else None
            )
            result["revenue_per_share"] = (
                ttm_revenue / shares_outstanding if ttm_revenue else None
            )
            result["book_value_per_share"] = (
                book_value / shares_outstanding if book_value else None
            )

        return result

    def _get_sector_multiples(
        self, sector: str, industry: str | None = None
    ) -> Dict[str, float]:
        """Get sector median multiples with industry override.

        Uses normalized sector/industry names and tries historical median lookups first.
        Falls back to config static values if historical data not available.

        Args:
            sector: The company's sector (will be normalized, e.g., "Information Technology" -> "Technology")
            industry: The company's specific industry (e.g., "Semiconductors", "Major Banks")

        Returns:
            Dict with pe, ps, pb, ev_ebitda multiples. If industry is provided and
            has historical data or override defined in config, that value will be used.
        """
        # Normalize sector and industry names
        normalized = SectorIndustryMapper.normalize_metadata(sector, industry)
        standard_sector = normalized["sector"] or "Unknown"
        standard_industry = normalized["industry"]

        # Try historical median lookups first using SectorMultiplesService
        if self._sector_multiples_service:
            try:
                # Try industry-specific historical lookup first
                if standard_industry:
                    industry_pe = self._sector_multiples_service._get_industry_historical_multiple(
                        industry=standard_industry,
                        metric="pe",
                        lookback_years=3,
                    )
                    if industry_pe is not None:
                        # Got industry-specific historical data, use it for all multiples
                        return {
                            "pe": industry_pe,
                            "ps": self._sector_multiples_service.get_ps(
                                standard_sector, standard_industry
                            ),
                            "pb": self._sector_multiples_service.get_pb(
                                standard_sector, standard_industry
                            ),
                            "ev_ebitda": self._sector_multiples_service.get_ev_ebitda(
                                standard_sector, standard_industry
                            ),
                        }

                # Try sector-level historical lookup
                historical_pe = (
                    self._sector_multiples_service.get_historical_median_multiple(
                        sector=standard_sector,
                        metric="pe",
                        lookback_years=3,
                    )
                )
                if historical_pe is not None:
                    # Got historical sector data, use it
                    return {
                        "pe": historical_pe,
                        "ps": self._sector_multiples_service.get_ps(
                            standard_sector, standard_industry
                        ),
                        "pb": self._sector_multiples_service.get_pb(
                            standard_sector, standard_industry
                        ),
                        "ev_ebitda": self._sector_multiples_service.get_ev_ebitda(
                            standard_sector, standard_industry
                        ),
                    }
            except Exception as e:
                logger.debug(
                    f"Historical median lookup failed for {standard_sector}: {e}"
                )

            # Fall back to config static values
            result: dict[str, float] = self._sector_multiples_service.get_multiples(
                standard_sector, standard_industry
            )
            return result

        # Fallback to shared SectorMultiples module if available
        try:
            from investigator.domain.services.valuation.common import SectorMultiples

            return {
                "pe": SectorMultiples.get_multiple_with_override(
                    sector=standard_sector, industry=standard_industry, metric="pe"
                ),
                "ps": SectorMultiples.get_multiple_with_override(
                    sector=standard_sector, industry=standard_industry, metric="ps"
                ),
                "pb": SectorMultiples.get_multiple_with_override(
                    sector=standard_sector, industry=standard_industry, metric="pb"
                ),
                "ev_ebitda": SectorMultiples.get_multiple_with_override(
                    sector=standard_sector,
                    industry=standard_industry,
                    metric="ev_ebitda",
                ),
            }
        except Exception as e:
            logger.debug(f"Shared SectorMultiples not available, using fallback: {e}")

        # Final fallback to hardcoded values
        logger.debug(
            f"Using fallback sector multiples for {standard_sector} (service not available)"
        )
        base = DEFAULT_SECTOR_MULTIPLES.get(
            standard_sector, DEFAULT_SECTOR_MULTIPLES.get("Industrials", {})
        )
        if standard_industry and standard_industry in INDUSTRY_PE_FALLBACKS:
            base = base.copy()
            base["pe"] = INDUSTRY_PE_FALLBACKS[standard_industry]
        return base

    async def _run_all_models(
        self,
        symbol: str,
        quarterly_metrics: List[Dict],
        multi_year_data: List[Dict],
        current_price: Optional[float],
        cost_of_equity: Optional[float],
        terminal_growth_rate: Optional[float],
    ) -> ToolResult:
        """Run all applicable valuation models.

        Args:
            symbol: Stock ticker
            quarterly_metrics: Quarterly financial data
            multi_year_data: Multi-year data
            current_price: Current stock price
            cost_of_equity: Required return rate
            terminal_growth_rate: Terminal growth rate

        Returns:
            ToolResult with all model results
        """
        try:
            results: Dict[str, Any] = {}
            warnings: list[str] = []

            # Run DCF
            dcf_result = await self._run_dcf(
                symbol,
                quarterly_metrics,
                multi_year_data,
                current_price,
                cost_of_equity,
                terminal_growth_rate,
            )
            if dcf_result.success:
                results["dcf"] = dcf_result.output
            else:
                warnings.append(f"DCF: {dcf_result.error}")

            # Run GGM
            ggm_result = await self._run_ggm(
                symbol,
                quarterly_metrics,
                multi_year_data,
                current_price,
                cost_of_equity,
                terminal_growth_rate,
            )
            if ggm_result.success:
                results["ggm"] = ggm_result.output
            else:
                warnings.append(f"GGM: {ggm_result.error}")

            # Run multiple models
            pe_result = await self._run_pe_multiple(
                symbol, quarterly_metrics, current_price
            )
            if pe_result.success:
                results["pe"] = pe_result.output
            else:
                warnings.append(f"P/E: {pe_result.error}")

            ps_result = await self._run_ps_multiple(
                symbol, quarterly_metrics, current_price
            )
            if ps_result.success:
                results["ps"] = ps_result.output
            else:
                warnings.append(f"P/S: {ps_result.error}")

            pb_result = await self._run_pb_multiple(
                symbol, quarterly_metrics, current_price
            )
            if pb_result.success:
                results["pb"] = pb_result.output
            else:
                warnings.append(f"P/B: {pb_result.error}")

            ev_ebitda_result = await self._run_ev_ebitda(
                symbol, quarterly_metrics, current_price
            )
            if ev_ebitda_result.success:
                results["ev_ebitda"] = ev_ebitda_result.output
            else:
                warnings.append(f"EV/EBITDA: {ev_ebitda_result.error}")

            if not results:
                return ToolResult.create_failure(
                    "No valuation models could be applied",
                    metadata={"symbol": symbol, "warnings": warnings},
                )

            # Calculate blended fair value using shared MultiModelValuationOrchestrator
            # This ensures victor-invest produces identical results to investigator CLI
            try:
                import yaml

                from investigator.domain.services.company_metadata_service import (
                    CompanyMetadataService,
                )
                from investigator.domain.services.dynamic_model_weighting import (
                    DynamicModelWeightingService,
                )
                from investigator.domain.services.valuation.orchestrator import (
                    MultiModelValuationOrchestrator,
                )

                # Load valuation config directly from YAML
                with open("config.yaml", "r") as f:
                    config = yaml.safe_load(f)
                valuation_config = config.get("valuation", {})

                # Initialize metadata service for sector/industry lookup
                metadata_service = CompanyMetadataService(
                    sector_normalization=valuation_config.get(
                        "sector_normalization", {}
                    )
                )

                # Get sector/industry from metadata service (database + config lookup)
                sector, industry = metadata_service.get_sector_industry(symbol)
                logger.info(
                    f"{symbol}: Retrieved sector={sector}, industry={industry} from CompanyMetadataService"
                )

                # Build CompanyProfile using existing helper method
                stock_info = await self._get_stock_info(symbol)
                stock_info["sector"] = (
                    sector  # Ensure sector is set from metadata service
                )
                stock_info["industry"] = industry  # Ensure industry is set

                company_profile = self._build_company_profile(
                    symbol, stock_info, quarterly_metrics
                )
                if company_profile is None:
                    raise ValueError("Could not build company profile")

                # Build minimal financials dict for weight calculation
                financials = {
                    "net_income": None,
                    "revenue": None,
                    "shareholders_equity": None,
                    "market_cap": None,
                    "ebitda": None,  # Required for EV/EBITDA model applicability check
                }

                # Try to extract TTM financials from quarterly_metrics
                if quarterly_metrics and len(quarterly_metrics) >= 4:
                    # Get TTM (last 4 quarters)
                    ttm = quarterly_metrics[:4]

                    # Helper function to extract metric from nested or flat format
                    def extract_ttm_metric(keys: List[str]) -> float:
                        """Extract TTM metric from quarterly data, handling both nested and flat formats."""
                        total = 0.0
                        for q in ttm:
                            # Try nested format first (income_statement.total_revenue)
                            if "income_statement" in q:
                                for key in keys:
                                    val = q.get("income_statement", {}).get(key)
                                    if val is not None:
                                        total += val or 0
                                        break
                            # Try flat format
                            else:
                                for key in keys:
                                    val = q.get(key)
                                    if val is not None:
                                        total += val or 0
                                        break
                        return total

                    financials["net_income"] = extract_ttm_metric(
                        ["net_income", "net_income_loss"]
                    )  # type: ignore[assignment]
                    financials["revenue"] = extract_ttm_metric(
                        ["total_revenue", "revenue"]
                    )  # type: ignore[assignment]

                    # Use latest quarter's shareholders_equity
                    latest_q = ttm[0]
                    if "balance_sheet" in latest_q:
                        financials["shareholders_equity"] = latest_q.get(
                            "balance_sheet", {}
                        ).get("stockholders_equity") or latest_q.get(
                            "shareholders_equity", 0
                        )
                    else:
                        financials["shareholders_equity"] = latest_q.get(
                            "stockholders_equity",
                            latest_q.get("shareholders_equity", 0),
                        )

                    # Calculate TTM EBITDA from operating_income and depreciation_amortization
                    ebitda_total = 0.0
                    for q in ttm:
                        if "income_statement" in q:
                            inc_stmt = q.get("income_statement", {})
                            operating_income = inc_stmt.get("operating_income", 0) or 0
                            depr_amort = (
                                inc_stmt.get("depreciation_amortization", 0) or 0
                            )
                            ebitda_total += operating_income + depr_amort
                        else:
                            operating_income = q.get("operating_income", 0) or 0
                            depr_amort = q.get("depreciation_amortization", 0) or 0
                            ebitda_total += operating_income + depr_amort
                    financials["ebitda"] = ebitda_total

                # Calculate market_cap if we have price and shares
                if current_price and quarterly_metrics:
                    shares = quarterly_metrics[0].get("shares_outstanding")
                    if shares:
                        financials["market_cap"] = current_price * shares

                # Build ratios dict for weight calculation
                ratios = {
                    "roe": None,
                    "payout_ratio": None,
                    "revenue_growth_yoy": None,
                    "earnings_growth_yoy": None,
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "dividend_yield": None,
                }

                # Calculate ROE if we have the data
                if (
                    financials.get("net_income")
                    and financials.get("shareholders_equity")
                    and financials["shareholders_equity"] > 0
                ):
                    ratios["roe"] = (
                        financials["net_income"]
                        / financials["shareholders_equity"]
                        * 100
                    )

                # Create weighting service to determine tier weights
                weighting_service = DynamicModelWeightingService(
                    valuation_config=valuation_config
                )

                # Get tier-based weights (these will be passed as fallback_weights to orchestrator)
                weights, tier, audit_trail = weighting_service.determine_weights(
                    symbol=symbol,
                    financials=financials,
                    ratios=ratios,
                    data_quality=None,
                    market_context=None,
                )

                # Convert results dict to model_outputs format for orchestrator
                model_outputs = []
                for model_name, model_result in results.items():
                    if isinstance(model_result, dict) and model_result.get(
                        "fair_value_per_share"
                    ):
                        model_outputs.append(
                            {
                                "model": model_name,
                                "fair_value_per_share": model_result[
                                    "fair_value_per_share"
                                ],
                                "confidence_score": model_result.get(
                                    "confidence_score", 0.7
                                ),
                                "applicable": True,
                            }
                        )

                # Initialize shared orchestrator with same config as investigator CLI
                orchestrator = MultiModelValuationOrchestrator(
                    divergence_threshold=valuation_config.get("agreement", {}).get(
                        "divergence_threshold", 0.35
                    ),
                    agreement_config=valuation_config.get("agreement", {}),
                    bounds_config=valuation_config.get("bounds_validation", {}),
                )

                # Use shared orchestrator for blending (ensures parity with investigator CLI)
                orchestrator_result = orchestrator.combine(
                    company_profile=company_profile,
                    model_outputs=model_outputs,
                    fallback_weights=weights,
                    tier_classification=tier,
                )

                consensus = orchestrator_result["blended_fair_value"]
                overall_confidence = orchestrator_result.get("overall_confidence", 0.7)
                model_agreement_score = orchestrator_result.get("model_agreement_score")
                divergence_flag = orchestrator_result.get("divergence_flag", False)

                # Log orchestrator diagnostics
                consensus_str = f"${consensus:.2f}" if consensus is not None else "N/A"
                logger.info(
                    f"{symbol}: Using MultiModelValuationOrchestrator (tier={tier}) → "
                    f"{consensus_str} | Agreement: {model_agreement_score:.2f} | "
                    f"Divergence: {divergence_flag} | Confidence: {overall_confidence:.2f}"
                )

                # Update model results with weights applied by orchestrator
                for model in orchestrator_result.get("models", []):
                    model_name = model.get("model")
                    if model_name and model_name in results:
                        results[model_name]["weight"] = model.get("weight", 0.0)

            except Exception as e:
                # Fallback to simple average on any error
                logger.warning(
                    f"{symbol}: Could not use MultiModelValuationOrchestrator ({e}), using simple average"
                )
                fair_values = [
                    r.get("fair_value_per_share")
                    for r in results.values()
                    if isinstance(r, dict) and r.get("fair_value_per_share")
                ]
                consensus = sum(fair_values) / len(fair_values) if fair_values else None

            # Build output with orchestrator results if available
            output_dict = {
                "symbol": symbol,
                "current_price": current_price,
                "models": results,
                "models_applied": list(results.keys()),
                "consensus_fair_value": consensus,
                "consensus_upside": (
                    ((consensus / current_price) - 1) * 100
                    if consensus and current_price
                    else None
                ),
            }

            # Add orchestrator-specific outputs if available
            if "orchestrator_result" in locals():
                output_dict.update(
                    {
                        "overall_confidence": orchestrator_result.get(
                            "overall_confidence"
                        ),
                        "model_agreement_score": orchestrator_result.get(
                            "model_agreement_score"
                        ),
                        "divergence_flag": orchestrator_result.get("divergence_flag"),
                        "agreement_level": orchestrator_result.get("agreement_level"),
                        "outlier_models": orchestrator_result.get("outlier_models"),
                        "tier_classification": orchestrator_result.get(
                            "tier_classification"
                        ),
                        "bounds_valid": orchestrator_result.get("bounds_valid"),
                        "dispersion_ratio": orchestrator_result.get("dispersion_ratio"),
                    }
                )
                # Add notes from orchestrator
                if orchestrator_result.get("notes"):
                    warnings.extend(orchestrator_result["notes"])

            return ToolResult.create_success(
                output=output_dict,
                metadata={"model_count": len(results), "warnings": warnings},
            )

        except Exception as e:
            logger.error(f"Error running all models for {symbol}: {e}")
            return ToolResult.create_failure(f"Multi-model valuation failed: {str(e)}")

    async def _run_dcf(
        self,
        symbol: str,
        quarterly_metrics: List[Dict],
        multi_year_data: List[Dict],
        current_price: Optional[float],
        cost_of_equity: Optional[float],
        terminal_growth_rate: Optional[float],
    ) -> ToolResult:
        """Run DCF valuation model."""
        try:
            from investigator.domain.services.valuation import DCFValuation

            loop = asyncio.get_event_loop()

            dcf = DCFValuation(
                symbol=symbol,
                quarterly_metrics=quarterly_metrics,
                multi_year_data=multi_year_data,
                db_manager=self._db_manager,
            )

            # Run DCF calculation (synchronous, run in executor)
            result = await loop.run_in_executor(None, dcf.calculate_dcf_valuation)

            if not result or not result.get("fair_value_per_share"):
                return ToolResult.create_failure(
                    f"DCF not applicable for {symbol}: {result.get('reason', 'Insufficient data')}",
                    metadata={"model": "dcf", "symbol": symbol},
                )

            fair_value = result.get("fair_value_per_share", 0)
            upside = (
                ((fair_value / current_price) - 1) * 100
                if current_price and fair_value
                else None
            )

            return ToolResult.create_success(
                output={
                    "model": "dcf",
                    "fair_value_per_share": fair_value,
                    "current_price": current_price,
                    "upside_percent": upside,
                    "wacc": result.get("wacc"),
                    "terminal_growth_rate": result.get("terminal_growth_rate"),
                    "projection_years": result.get("projection_years"),
                    "enterprise_value": result.get("enterprise_value"),
                    "assumptions": result.get("assumptions", {}),
                },
                metadata={"model": "dcf", "symbol": symbol},
            )

        except Exception as e:
            logger.error(f"DCF error for {symbol}: {e}")
            return ToolResult.create_failure(f"DCF calculation failed: {str(e)}")

    async def _run_ggm(
        self,
        symbol: str,
        quarterly_metrics: List[Dict],
        multi_year_data: List[Dict],
        current_price: Optional[float],
        cost_of_equity: Optional[float],
        terminal_growth_rate: Optional[float],
    ) -> ToolResult:
        """Run Gordon Growth Model valuation."""
        try:
            from investigator.domain.services.valuation import GordonGrowthModel

            loop = asyncio.get_event_loop()

            ggm = GordonGrowthModel(
                symbol=symbol,
                quarterly_metrics=quarterly_metrics,
                multi_year_data=multi_year_data,
                db_manager=self._db_manager,
            )

            # Default cost of equity if not provided (use config-based GGM default)
            if cost_of_equity:
                coe = cost_of_equity
            elif self._valuation_config_service:
                coe = self._valuation_config_service.get_ggm_cost_of_equity()
            else:
                coe = 0.08  # Fallback to 8% if config service not available

            result = await loop.run_in_executor(
                None, ggm.calculate_ggm_valuation, coe, terminal_growth_rate
            )

            if not result or not result.get("applicable", False):
                return ToolResult.create_failure(
                    f"GGM not applicable for {symbol}: {result.get('reason', 'No dividends')}",
                    metadata={"model": "ggm", "symbol": symbol},
                )

            fair_value = result.get("fair_value_per_share", 0)
            upside = (
                ((fair_value / current_price) - 1) * 100
                if current_price and fair_value
                else None
            )

            return ToolResult.create_success(
                output={
                    "model": "ggm",
                    "fair_value_per_share": fair_value,
                    "current_price": current_price,
                    "upside_percent": upside,
                    "cost_of_equity": result.get("cost_of_equity"),
                    "growth_rate": result.get("growth_rate"),
                    "dividend_yield": result.get("dividend_yield"),
                    "latest_dps": result.get("latest_dps"),
                },
                metadata={"model": "ggm", "symbol": symbol},
            )

        except Exception as e:
            logger.error(f"GGM error for {symbol}: {e}")
            return ToolResult.create_failure(f"GGM calculation failed: {str(e)}")

    async def _run_pe_multiple(
        self, symbol: str, quarterly_metrics: List[Dict], current_price: Optional[float]
    ) -> ToolResult:
        """Run P/E Multiple valuation."""
        try:
            from investigator.domain.services.valuation.models import PEMultipleModel
            from investigator.domain.services.valuation.models.base import (
                ModelNotApplicable,
            )

            loop = asyncio.get_event_loop()

            # Get stock info for company profile and shares outstanding
            stock_info = await self._get_stock_info(symbol)
            shares_outstanding = stock_info.get("shares_outstanding")
            sector = stock_info.get("sector", "Unknown")

            # Build company profile
            company_profile = self._build_company_profile(
                symbol, stock_info, quarterly_metrics
            )
            if company_profile is None:
                return ToolResult.create_failure(
                    "Could not build company profile",
                    metadata={"model": "pe", "symbol": symbol},
                )

            # Calculate TTM metrics
            ttm_metrics = self._calculate_ttm_metrics(
                quarterly_metrics, shares_outstanding
            )
            ttm_eps = ttm_metrics.get("ttm_eps")

            # Get sector multiples
            sector_multiples = self._get_sector_multiples(sector)
            sector_median_pe = sector_multiples.get("pe", 15.0)

            # Calculate growth-adjusted P/E using shared GrowthAdjustedMultiples
            growth_adjusted_pe = None
            if company_profile and company_profile.revenue_growth_yoy is not None:
                from investigator.domain.services.valuation.common import (
                    GrowthAdjustedMultiples,
                )

                industry = (
                    company_profile.industry
                    if hasattr(company_profile, "industry")
                    else None
                )
                growth_adjusted_pe = GrowthAdjustedMultiples.calculate_adjusted_pe(
                    sector=sector,
                    industry=industry,
                    revenue_growth=company_profile.revenue_growth_yoy,
                    sector_pe_override=sector_median_pe,
                )

            # Create model with required arguments
            model = PEMultipleModel(
                company_profile=company_profile,
                ttm_eps=ttm_eps,
                current_price=current_price,
                sector_median_pe=sector_median_pe,
                growth_adjusted_pe=growth_adjusted_pe,
            )

            result = await loop.run_in_executor(None, model.calculate)

            if isinstance(result, ModelNotApplicable):
                return ToolResult.create_failure(
                    f"P/E not applicable: {result.reason}",
                    metadata={"model": "pe", "symbol": symbol},
                )

            return ToolResult.create_success(
                output={
                    "model": "pe",
                    "fair_value_per_share": result.fair_value,
                    "current_price": current_price,
                    "upside_percent": result.metadata.get("upside_downside_pct"),
                    "pe_ratio": result.assumptions.get("target_pe"),
                    "eps_ttm": ttm_eps,
                    "sector_pe": sector_median_pe,
                    "confidence": result.confidence_score,
                },
                metadata={"model": "pe", "symbol": symbol},
            )

        except Exception as e:
            logger.error(f"P/E error for {symbol}: {e}")
            return ToolResult.create_failure(f"P/E calculation failed: {str(e)}")

    async def _run_ps_multiple(
        self, symbol: str, quarterly_metrics: List[Dict], current_price: Optional[float]
    ) -> ToolResult:
        """Run P/S Multiple valuation."""
        try:
            from investigator.domain.services.valuation.models import PSMultipleModel
            from investigator.domain.services.valuation.models.base import (
                ModelNotApplicable,
            )

            loop = asyncio.get_event_loop()

            # Get stock info for company profile and shares outstanding
            stock_info = await self._get_stock_info(symbol)
            shares_outstanding = stock_info.get("shares_outstanding")
            sector = stock_info.get("sector", "Unknown")
            industry = stock_info.get("industry")

            # Build company profile
            company_profile = self._build_company_profile(
                symbol, stock_info, quarterly_metrics
            )
            if company_profile is None:
                return ToolResult.create_failure(
                    "Could not build company profile",
                    metadata={"model": "ps", "symbol": symbol},
                )

            # Calculate TTM metrics
            ttm_metrics = self._calculate_ttm_metrics(
                quarterly_metrics, shares_outstanding
            )
            revenue_per_share = ttm_metrics.get("revenue_per_share")

            # Get sector multiples and apply growth adjustment
            sector_multiples = self._get_sector_multiples(sector, industry)
            sector_median_ps = sector_multiples.get("ps", 2.0)

            # Apply growth adjustment using shared module
            try:
                from investigator.domain.services.valuation.common import (
                    GrowthAdjustedMultiples,
                )

                growth_adjusted_ps = GrowthAdjustedMultiples.calculate_adjusted_ps(
                    sector=sector,
                    industry=industry,
                    base_multiple=sector_median_ps,
                    revenue_growth=company_profile.revenue_growth_yoy,
                )
            except Exception as e:
                logger.debug(f"Growth-adjusted P/S not available, using base: {e}")
                growth_adjusted_ps = sector_median_ps

            # Create model with growth-adjusted P/S
            model = PSMultipleModel(
                company_profile=company_profile,
                revenue_per_share=revenue_per_share,
                current_price=current_price,
                sector_median_ps=growth_adjusted_ps,
            )

            result = await loop.run_in_executor(None, model.calculate)

            if isinstance(result, ModelNotApplicable):
                return ToolResult.create_failure(
                    f"P/S not applicable: {result.reason}",
                    metadata={"model": "ps", "symbol": symbol},
                )

            return ToolResult.create_success(
                output={
                    "model": "ps",
                    "fair_value_per_share": result.fair_value,
                    "current_price": current_price,
                    "upside_percent": result.metadata.get("upside_downside_pct"),
                    "ps_ratio": result.assumptions.get("target_ps"),
                    "revenue_per_share": revenue_per_share,
                    "sector_ps": sector_median_ps,
                    "growth_adjusted_ps": growth_adjusted_ps,
                    "confidence": result.confidence_score,
                },
                metadata={"model": "ps", "symbol": symbol},
            )

        except Exception as e:
            logger.error(f"P/S error for {symbol}: {e}")
            return ToolResult.create_failure(f"P/S calculation failed: {str(e)}")

    async def _run_pb_multiple(
        self, symbol: str, quarterly_metrics: List[Dict], current_price: Optional[float]
    ) -> ToolResult:
        """Run P/B Multiple valuation."""
        try:
            from investigator.domain.services.valuation.models import PBMultipleModel
            from investigator.domain.services.valuation.models.base import (
                ModelNotApplicable,
            )

            loop = asyncio.get_event_loop()

            # Get stock info for company profile and shares outstanding
            stock_info = await self._get_stock_info(symbol)
            shares_outstanding = stock_info.get("shares_outstanding")
            sector = stock_info.get("sector", "Unknown")

            # Build company profile
            company_profile = self._build_company_profile(
                symbol, stock_info, quarterly_metrics
            )
            if company_profile is None:
                return ToolResult.create_failure(
                    "Could not build company profile",
                    metadata={"model": "pb", "symbol": symbol},
                )

            # Calculate TTM metrics
            ttm_metrics = self._calculate_ttm_metrics(
                quarterly_metrics, shares_outstanding
            )
            book_value_per_share = ttm_metrics.get("book_value_per_share")

            # Get sector multiples
            sector_multiples = self._get_sector_multiples(sector)
            sector_median_pb = sector_multiples.get("pb", 2.5)

            # Create model with required arguments
            model = PBMultipleModel(
                company_profile=company_profile,
                book_value_per_share=book_value_per_share,
                current_price=current_price,
                sector_median_pb=sector_median_pb,
            )

            result = await loop.run_in_executor(None, model.calculate)

            if isinstance(result, ModelNotApplicable):
                return ToolResult.create_failure(
                    f"P/B not applicable: {result.reason}",
                    metadata={"model": "pb", "symbol": symbol},
                )

            return ToolResult.create_success(
                output={
                    "model": "pb",
                    "fair_value_per_share": result.fair_value,
                    "current_price": current_price,
                    "upside_percent": result.metadata.get("upside_downside_pct"),
                    "pb_ratio": result.assumptions.get("target_pb"),
                    "book_value_per_share": book_value_per_share,
                    "sector_pb": sector_median_pb,
                    "confidence": result.confidence_score,
                },
                metadata={"model": "pb", "symbol": symbol},
            )

        except Exception as e:
            logger.error(f"P/B error for {symbol}: {e}")
            return ToolResult.create_failure(f"P/B calculation failed: {str(e)}")

    async def _run_ev_ebitda(
        self, symbol: str, quarterly_metrics: List[Dict], current_price: Optional[float]
    ) -> ToolResult:
        """Run EV/EBITDA Multiple valuation."""
        try:
            from investigator.domain.services.valuation.models import EVEBITDAModel
            from investigator.domain.services.valuation.models.base import (
                ModelNotApplicable,
            )

            loop = asyncio.get_event_loop()

            # Get stock info for company profile, shares outstanding, and market cap
            stock_info = await self._get_stock_info(symbol)
            shares_outstanding = stock_info.get("shares_outstanding")
            sector = stock_info.get("sector", "Unknown")
            industry = stock_info.get("industry")
            market_cap = stock_info.get("market_cap")

            # Build company profile
            company_profile = self._build_company_profile(
                symbol, stock_info, quarterly_metrics
            )
            if company_profile is None:
                return ToolResult.create_failure(
                    "Could not build company profile",
                    metadata={"model": "ev_ebitda", "symbol": symbol},
                )

            # Calculate TTM metrics
            ttm_metrics = self._calculate_ttm_metrics(
                quarterly_metrics, shares_outstanding
            )
            ttm_ebitda = ttm_metrics.get("ttm_ebitda")

            # Calculate enterprise value: market_cap + total_debt - cash
            enterprise_value = None
            if market_cap:
                # Try to get debt and cash from quarterly metrics
                if quarterly_metrics:
                    latest_q = quarterly_metrics[0]
                    total_debt = (latest_q.get("long_term_debt") or 0) + (
                        latest_q.get("short_term_debt") or 0
                    )
                    cash = latest_q.get("cash_and_equivalents") or 0
                    enterprise_value = market_cap + total_debt - cash
                else:
                    enterprise_value = market_cap  # Approximate

            # Get sector multiples with industry override
            sector_multiples = self._get_sector_multiples(sector, industry)
            sector_median_ev_ebitda = sector_multiples.get("ev_ebitda", 12.0)

            # Create model with required arguments including revenue growth
            model = EVEBITDAModel(
                company_profile=company_profile,
                ttm_ebitda=ttm_ebitda,
                enterprise_value=enterprise_value,
                sector_median_ev_ebitda=sector_median_ev_ebitda,
                revenue_growth=company_profile.revenue_growth_yoy,
            )

            result = await loop.run_in_executor(None, model.calculate)

            if isinstance(result, ModelNotApplicable):
                return ToolResult.create_failure(
                    f"EV/EBITDA not applicable: {result.reason}",
                    metadata={"model": "ev_ebitda", "symbol": symbol},
                )

            return ToolResult.create_success(
                output={
                    "model": "ev_ebitda",
                    "fair_value_per_share": result.fair_value,
                    "current_price": current_price,
                    "upside_percent": result.metadata.get("upside_downside_pct"),
                    "ev_ebitda_ratio": result.assumptions.get("target_multiple"),
                    "enterprise_value": enterprise_value,
                    "ebitda_ttm": ttm_ebitda,
                    "sector_ev_ebitda": sector_median_ev_ebitda,
                    "revenue_growth": company_profile.revenue_growth_yoy,
                    "confidence": result.confidence_score,
                },
                metadata={"model": "ev_ebitda", "symbol": symbol},
            )

        except Exception as e:
            logger.error(f"EV/EBITDA error for {symbol}: {e}")
            return ToolResult.create_failure(f"EV/EBITDA calculation failed: {str(e)}")

    async def _run_sector_routed(
        self,
        symbol: str,
        quarterly_metrics: List[Dict],
        multi_year_data: List[Dict],
        current_price: Optional[float],
    ) -> ToolResult:
        """Run sector-appropriate valuation using SectorValuationRouter."""
        try:
            from investigator.domain.services.valuation import SectorValuationRouter

            loop = asyncio.get_event_loop()

            router = SectorValuationRouter(
                symbol=symbol,
                quarterly_metrics=quarterly_metrics,
                multi_year_data=multi_year_data,
                db_manager=self._db_manager,
            )

            result = await loop.run_in_executor(None, router.get_valuation)

            if not result:
                return ToolResult.create_failure(
                    f"Sector-routed valuation failed for {symbol}",
                    metadata={"model": "sector_routed", "symbol": symbol},
                )

            return ToolResult.create_success(
                output={
                    "model": "sector_routed",
                    "sector": result.get("sector"),
                    "primary_model": result.get("primary_model"),
                    "fair_value_per_share": result.get("fair_value"),
                    "current_price": current_price,
                    "upside_percent": result.get("upside"),
                    "model_weights": result.get("weights", {}),
                    "all_valuations": result.get("valuations", {}),
                },
                metadata={
                    "model": "sector_routed",
                    "symbol": symbol,
                    "sector": result.get("sector"),
                },
            )

        except Exception as e:
            logger.error(f"Sector-routed valuation error for {symbol}: {e}")
            return ToolResult.create_failure(
                f"Sector-routed valuation failed: {str(e)}"
            )

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for Valuation Tool parameters."""
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "model": {
                    "type": "string",
                    "enum": [
                        "dcf",
                        "ggm",
                        "pe",
                        "ps",
                        "pb",
                        "ev_ebitda",
                        "sector_routed",
                        "all",
                    ],
                    "description": "Valuation model to use",
                    "default": "all",
                },
                "current_price": {
                    "type": "number",
                    "description": "Current stock price for upside calculation",
                },
                "cost_of_equity": {
                    "type": "number",
                    "description": "Required rate of return (decimal, e.g., 0.10 for 10%)",
                },
                "terminal_growth_rate": {
                    "type": "number",
                    "description": "Terminal growth rate for DCF (decimal)",
                },
            },
            "required": ["symbol"],
        }

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

"""RL Backtest Tool for Victor Invest.

Provides RL backtesting functionality integrated with shared services:
- Uses shared market data services (SharesService, PriceService, TechnicalAnalysisService)
- Uses shared valuation config services (ValuationConfigService, SectorMultiplesService)
- Records predictions to valuation_outcomes table with JSONB multi-period data
- Consistent with batch_analysis_runner and victor_invest workflows

Multi-period data stored in per_model_rewards JSONB:
{
    "multi_period": {
        "entry_date": "2025-01-02",
        "prices": {"1m": 270.37, "3m": 271.86, "6m": 280.50, "12m": 290.00, ...},
        "exit_dates": {"1m": "2025-02-01", "3m": "2025-04-02", ...},
        "long_rewards": {"1m": 0.577, "3m": 0.214, ...},
        "short_rewards": {"1m": -0.577, "3m": -0.214, ...}
    }
}
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from dateutil.relativedelta import relativedelta

from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Holding periods in days for multi-period reward calculation.
# NOTE: "18m" is 548 days (not 540) to match the valuation_outcomes *_548d columns
# and the ~1.5-year (18 * 30.44) convention used throughout the schema.
HOLDING_PERIODS = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "12m": 365,
    "18m": 548,
    "24m": 730,
    "36m": 1095,
}


class RLBacktestTool(BaseTool):
    """Tool for RL backtesting using shared services.

    This tool provides consistent RL backtest functionality that aligns with
    the victor_invest workflow architecture and uses shared market data and
    valuation services.

    Features:
    - Historical valuation simulation at past dates
    - Multi-period reward calculation (1m, 3m, 6m, 12m, 18m, 24m, 36m)
    - Entry/exit date tracking in JSONB format
    - Dual position recording (LONG and SHORT)
    - Consistent with batch_analysis_runner output

    Actions:
        run_backtest: Run backtest for a symbol at specific lookback periods
        calculate_rewards: Calculate multi-period rewards for a prediction
        record_prediction: Record prediction to database
        get_historical_data: Get historical price and shares data

    Example:
        tool = RLBacktestTool()
        result = await tool.execute(
            action="run_backtest",
            symbol="AAPL",
            lookback_months=[12, 24, 36]
        )
    """

    name = "rl_backtest"
    description = """Run RL backtesting for valuation model training including:
    - Historical valuation simulation using only data available at past dates
    - Multi-period reward calculation (1m, 3m, 6m, 12m, 18m, 24m, 36m)
    - Entry/exit date tracking for position management
    - Dual position recording (LONG and SHORT) for balanced RL training
    - Unified context feature extraction via DataSourceManager"""

    def __init__(self, config: Optional[Any] = None):
        """Initialize the RL backtest tool."""
        super().__init__(config)
        self._shares_service: Optional[Any] = None
        self._price_service: Optional[Any] = None
        self._technical_service: Optional[Any] = None
        self._metadata_service: Optional[Any] = None
        self._valuation_config: Optional[Any] = None
        self._sector_multiples: Optional[Any] = None
        self._outcome_tracker: Optional[Any] = None
        self._reward_calculator: Optional[Any] = None
        self._data_source_manager: Optional[Any] = None
        self._delisting_service: Optional[Any] = None
        self._db: Optional[Any] = None

    async def initialize(self) -> None:
        """Initialize shared services."""
        try:
            # Shared market data services
            # Data source manager for consolidated data access
            from investigator.domain.services.data_sources.manager import (
                DataSourceManager,
            )
            from investigator.domain.services.market_data import (
                PriceService,
                SharesService,
                SymbolMetadataService,
                get_technical_analysis_service,
            )
            from investigator.domain.services.market_data.delisting_service import (
                DelistingService,
            )

            # RL infrastructure
            from investigator.domain.services.rl.outcome_tracker import OutcomeTracker
            from investigator.domain.services.rl.reward_calculator import (
                get_reward_calculator,
            )

            # Shared valuation config services
            from investigator.domain.services.valuation_shared import (
                SectorMultiplesService,
                ValuationConfigService,
            )

            # Database
            from investigator.infrastructure.database.db import get_db_manager

            self._db = get_db_manager()
            # Services use default connection URLs when not specified
            self._shares_service = SharesService()
            self._price_service = PriceService()
            self._metadata_service = SymbolMetadataService()
            self._technical_service = get_technical_analysis_service()
            self._valuation_config = ValuationConfigService()
            self._sector_multiples = SectorMultiplesService()
            self._outcome_tracker = OutcomeTracker()
            self._reward_calculator = get_reward_calculator()
            self._data_source_manager = DataSourceManager()
            self._delisting_service = DelistingService()

            self._initialized = True
            logger.info("RLBacktestTool initialized with shared services and DataSourceManager")
        except ImportError as e:
            logger.error(f"Could not import required services: {e}")
            raise

    async def execute(
        self,
        _exec_ctx: Optional[Dict[str, Any]] = None,
        action: str = "run_backtest",
        symbol: str = "",
        lookback_months: Optional[List[int]] = None,
        analysis_date: Optional[date] = None,
        current_price: float = 0.0,
        fair_value: float = 0.0,
        fair_values: Optional[Dict[str, float]] = None,
        weights: Optional[Dict[str, float]] = None,
        tier_classification: str = "",
        context_features: Optional[Dict] = None,
        **kwargs,
    ) -> ToolResult:
        """Execute RL backtest action.

        Args:
            action: Action to perform:
                - "run_backtest": Run full backtest for symbol at lookback periods
                - "calculate_rewards": Calculate multi-period rewards
                - "record_prediction": Record prediction to database
                - "get_historical_data": Get historical price/shares data
                - "get_context_features": Get RL context features via DataSourceManager
            symbol: Stock symbol
            lookback_months: List of months to look back (e.g., [12, 24, 36])
            analysis_date: Date of analysis (for historical simulation)
            current_price: Price at analysis date
            fair_value: Blended fair value
            fair_values: Dict of model fair values
            weights: Dict of model weights
            tier_classification: Valuation tier classification
            context_features: RL context features dict

        Returns:
            ToolResult with backtest data
        """
        await self.ensure_initialized()

        try:
            if action == "run_backtest":
                return await self._run_backtest(
                    symbol=symbol,
                    lookback_months=lookback_months or [12],
                )
            elif action == "calculate_rewards":
                return await self._calculate_rewards(
                    symbol=symbol,
                    analysis_date=analysis_date or date.today(),
                    current_price=current_price,
                )
            elif action == "record_prediction":
                return await self._record_prediction(
                    symbol=symbol,
                    analysis_date=analysis_date or date.today(),
                    current_price=current_price,
                    fair_value=fair_value,
                    fair_values=fair_values or {},
                    weights=weights or {},
                    tier_classification=tier_classification,
                    context_features=context_features or {},
                    multi_period_data=kwargs.get("multi_period_data"),
                    model_agreement_score=kwargs.get("model_agreement_score"),
                    min_data_quality=kwargs.get("min_data_quality", 0.0),
                    survivorship_flag=kwargs.get("survivorship_flag", True),
                )
            elif action == "get_historical_data":
                return await self._get_historical_data(
                    symbol=symbol,
                    analysis_date=analysis_date or date.today(),
                )
            elif action == "get_context_features":
                return await self._get_context_features(
                    symbol=symbol,
                    analysis_date=analysis_date or date.today(),
                )
            else:
                return ToolResult.create_failure(
                    f"Unknown action: {action}. Valid actions: run_backtest, "
                    "calculate_rewards, record_prediction, get_historical_data, "
                    "get_context_features"
                )
        except Exception as e:
            logger.error(f"Error in RLBacktestTool: {e}")
            return ToolResult.create_failure(str(e))

    async def _run_backtest(
        self,
        symbol: str,
        lookback_months: List[int],
    ) -> ToolResult:
        """Run backtest for a symbol at multiple lookback periods."""
        if self._price_service is None:
            return ToolResult.create_failure("Price service not initialized")

        errors: list[str] = []
        results: Dict[str, Any] = {
            "symbol": symbol,
            "predictions": [],
            "errors": errors,
        }

        today = date.today()
        metadata = await self._get_metadata(symbol)

        for months_back in lookback_months:
            try:
                analysis_date = today - relativedelta(months=months_back)

                # Get historical price
                price = self._price_service.get_price(symbol, analysis_date)
                if not price or price <= 0:
                    results["errors"].append(f"{months_back}m: No price data")
                    continue

                # Get multi-period prices and calculate rewards
                multi_period_data = await self._get_multi_period_data(
                    symbol, analysis_date, price, metadata.get("beta", 1.0)
                )

                results["predictions"].append(
                    {
                        "lookback_months": months_back,
                        "analysis_date": analysis_date.isoformat(),
                        "price_at_prediction": price,
                        "multi_period": multi_period_data,
                    }
                )

            except Exception as e:
                results["errors"].append(f"{months_back}m: {str(e)}")

        return ToolResult.create_success(
            output=results,
            metadata={
                "tool": "rl_backtest",
                "action": "run_backtest",
                "lookback_periods": lookback_months,
            },
        )

    async def _calculate_rewards(
        self,
        symbol: str,
        analysis_date: date,
        current_price: float,
    ) -> ToolResult:
        """Calculate multi-period rewards for a prediction."""
        metadata = await self._get_metadata(symbol)
        beta = metadata.get("beta", 1.0)

        multi_period_data = await self._get_multi_period_data(symbol, analysis_date, current_price, beta)

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "analysis_date": analysis_date.isoformat(),
                "current_price": current_price,
                "beta": beta,
                "multi_period": multi_period_data,
            },
            metadata={
                "tool": "rl_backtest",
                "action": "calculate_rewards",
            },
        )

    async def _record_prediction(
        self,
        symbol: str,
        analysis_date: date,
        current_price: float,
        fair_value: float,
        fair_values: Dict[str, float],
        weights: Dict[str, float],
        tier_classification: str,
        context_features: Dict,
        multi_period_data: Optional[Dict[str, Any]] = None,
        model_agreement_score: Optional[float] = None,
        min_data_quality: float = 0.0,
        survivorship_flag: bool = True,
    ) -> ToolResult:
        """Record prediction to database.

        If context_features is empty, uses DataSourceManager to fetch
        consolidated data and extract RL features automatically. Low-quality
        observations (missing fair value, empty features, or data quality below
        ``min_data_quality``) are skipped so they never become training labels.

        Args:
            multi_period_data: Precomputed multi-period rewards/prices. When None
                it is computed here (kept for backward compatibility); callers that
                already computed it should pass it to avoid recomputation.
            model_agreement_score: Optional cross-model agreement score persisted
                for downstream training-quality filtering.
            min_data_quality: Minimum data-quality score (0-100) required to record.
        """
        if not self._outcome_tracker:
            return ToolResult.create_failure("Outcome tracker not available")

        try:
            metadata = await self._get_metadata(symbol)
            beta = metadata.get("beta", 1.0)
            if multi_period_data is None:
                multi_period_data = await self._get_multi_period_data(symbol, analysis_date, current_price, beta)

            # Capture data-quality provenance; auto-fetch RL features when not provided.
            data_quality_score: Optional[float] = None
            sources_failed: Optional[int] = None
            if not context_features and self._data_source_manager:
                try:
                    consolidated = self._data_source_manager.get_data(symbol=symbol, as_of_date=analysis_date)
                    context_features = consolidated.get_rl_features()
                    data_quality_score = self._quality_to_score(getattr(consolidated, "overall_quality", None))
                    failed = getattr(consolidated, "sources_failed", None)
                    sources_failed = len(failed) if isinstance(failed, (list, tuple, set)) else failed
                    logger.debug(f"Auto-fetched {len(context_features)} RL features for {symbol}")
                except Exception as e:
                    logger.warning(f"Could not fetch RL features via DataSourceManager: {e}")
                    context_features = {}

            # Quality gate: do not record observations that would be noisy/invalid
            # training labels.
            skip_reason = self._quality_gate_reason(
                fair_value=fair_value,
                context_features=context_features,
                data_quality_score=data_quality_score,
                min_data_quality=min_data_quality,
            )
            if skip_reason:
                logger.info(f"Skipping prediction for {symbol} @ {analysis_date}: {skip_reason}")
                return ToolResult.create_success(
                    output={
                        "symbol": symbol,
                        "analysis_date": analysis_date.isoformat(),
                        "record_ids": [],
                        "status": "skipped",
                        "skip_reason": skip_reason,
                        "data_quality_score": data_quality_score,
                    },
                    metadata={"tool": "rl_backtest", "action": "record_prediction"},
                )

            conviction_band = multi_period_data.get("conviction_band")
            predicted_fv_by_position = {
                "LONG": multi_period_data.get("long_predicted_fv"),
                "SHORT": multi_period_data.get("short_predicted_fv"),
            }

            record_ids = []
            for position_type in ["LONG", "SHORT"]:
                rewards_key = "long_rewards" if position_type == "LONG" else "short_rewards"
                rewards = multi_period_data.get(rewards_key, {})
                prices = multi_period_data.get("prices", {})
                exit_dates = multi_period_data.get("exit_dates", {})

                record_id = self._outcome_tracker.record_prediction_with_outcomes(
                    symbol=symbol,
                    analysis_date=analysis_date,
                    blended_fair_value=fair_value,
                    current_price=current_price,
                    model_fair_values=fair_values,
                    model_weights=weights,
                    tier_classification=tier_classification,
                    context_features=context_features,
                    actual_price_30d=prices.get("1m"),
                    actual_price_90d=prices.get("3m"),
                    actual_price_180d=prices.get("6m"),
                    actual_price_365d=prices.get("12m"),
                    actual_price_548d=prices.get("18m"),
                    actual_price_730d=prices.get("24m"),
                    actual_price_1095d=prices.get("36m"),
                    reward_30d=rewards.get("1m"),
                    reward_90d=rewards.get("3m"),
                    reward_180d=rewards.get("6m"),
                    reward_365d=rewards.get("12m"),
                    reward_548d=rewards.get("18m"),
                    reward_730d=rewards.get("24m"),
                    reward_1095d=rewards.get("36m"),
                    multi_period_rewards={position_type.lower(): rewards},
                    per_model_rewards={
                        "multi_period": multi_period_data,
                        "position_type": position_type,
                    },
                    policy_version="backtest_workflow_v1",
                    position_type=position_type,
                    position_predicted_fv=predicted_fv_by_position[position_type],
                    conviction_band=conviction_band,
                    data_quality_score=data_quality_score,
                    model_agreement_score=model_agreement_score,
                    sources_failed=sources_failed,
                    survivorship_flag=survivorship_flag,
                    entry_date=analysis_date,
                    exit_date_30d=self._parse_iso_date(exit_dates.get("1m")),
                    exit_date_90d=self._parse_iso_date(exit_dates.get("3m")),
                    exit_date_180d=self._parse_iso_date(exit_dates.get("6m")),
                    exit_date_365d=self._parse_iso_date(exit_dates.get("12m")),
                    exit_date_548d=self._parse_iso_date(exit_dates.get("18m")),
                    exit_date_730d=self._parse_iso_date(exit_dates.get("24m")),
                    exit_date_1095d=self._parse_iso_date(exit_dates.get("36m")),
                )
                if record_id:
                    record_ids.append(record_id)

            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "analysis_date": analysis_date.isoformat(),
                    "record_ids": record_ids,
                    "position_types": ["LONG", "SHORT"],
                    "context_features_count": len(context_features),
                    "data_quality_score": data_quality_score,
                },
                metadata={
                    "tool": "rl_backtest",
                    "action": "record_prediction",
                },
            )
        except Exception as e:
            return ToolResult.create_failure(f"Failed to record prediction: {e}")

    @staticmethod
    def _quality_to_score(quality: Any) -> Optional[float]:
        """Map a DataQuality enum/value to a 0-100 score, or None when unknown."""
        if quality is None:
            return None
        # Numeric value already on a 0-1 or 0-100 scale.
        value = getattr(quality, "value", None)
        if isinstance(value, (int, float)):
            return float(value) * 100.0 if value <= 1.0 else float(value)
        name = getattr(quality, "name", str(quality)).upper()
        name_scores = {
            "EXCELLENT": 100.0,
            "HIGH": 90.0,
            "GOOD": 80.0,
            "MEDIUM": 60.0,
            "MODERATE": 60.0,
            "FAIR": 50.0,
            "LOW": 30.0,
            "POOR": 20.0,
            "UNKNOWN": None,
            "NONE": 0.0,
        }
        return name_scores.get(name)

    @staticmethod
    def _quality_gate_reason(
        *,
        fair_value: float,
        context_features: Dict,
        data_quality_score: Optional[float],
        min_data_quality: float,
    ) -> Optional[str]:
        """Return a reason string if the observation should be skipped, else None."""
        if not fair_value or fair_value <= 0:
            return "non-positive blended fair value"
        if not context_features:
            return "empty context features"
        if data_quality_score is not None and data_quality_score < min_data_quality:
            return f"data quality {data_quality_score:.0f} < min {min_data_quality:.0f}"
        return None

    @staticmethod
    def _parse_iso_date(value: Any) -> Optional[date]:
        """Parse ISO date strings produced by multi-period reward calculation."""
        if not value:
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    async def _get_historical_data(
        self,
        symbol: str,
        analysis_date: date,
    ) -> ToolResult:
        """Get historical price and shares data."""
        if self._price_service is None or self._shares_service is None:
            return ToolResult.create_failure("Market data services not initialized")
        price = self._price_service.get_price(symbol, analysis_date)
        shares = self._shares_service.get_sec_shares(symbol, analysis_date)
        metadata = await self._get_metadata(symbol)

        return ToolResult.create_success(
            output={
                "symbol": symbol,
                "analysis_date": analysis_date.isoformat(),
                "price": price,
                "shares_outstanding": shares,
                "metadata": metadata,
            },
            metadata={
                "tool": "rl_backtest",
                "action": "get_historical_data",
            },
        )

    async def _get_context_features(
        self,
        symbol: str,
        analysis_date: date,
    ) -> ToolResult:
        """Get RL context features via DataSourceManager.

        Uses the unified DataSourceManager to fetch consolidated data
        and extract normalized features for RL model training.

        Features include:
        - Price returns (1d, 5d, 1m)
        - Technical indicators (RSI, SMA crossovers)
        - Macro indicators (VIX, GDPNow)
        - Sentiment (insider buys/sells, short interest)
        """
        if not self._data_source_manager:
            return ToolResult.create_failure("DataSourceManager not initialized")

        try:
            consolidated = self._data_source_manager.get_data(symbol=symbol, as_of_date=analysis_date)

            features = consolidated.get_rl_features()

            return ToolResult.create_success(
                output={
                    "symbol": symbol,
                    "analysis_date": analysis_date.isoformat(),
                    "features": features,
                    "feature_count": len(features),
                    "sources_succeeded": consolidated.sources_succeeded,
                    "sources_failed": consolidated.sources_failed,
                    "data_quality": consolidated.overall_quality.name,
                },
                metadata={
                    "tool": "rl_backtest",
                    "action": "get_context_features",
                },
            )
        except Exception as e:
            return ToolResult.create_failure(f"Failed to get context features: {e}")

    async def _get_multi_period_data(
        self,
        symbol: str,
        analysis_date: date,
        current_price: float,
        beta: float,
        conviction_band: float = 0.10,
    ) -> Dict[str, Any]:
        """Get multi-period prices, exit dates, and rewards.

        The contrastive LONG/SHORT dataset is generated by assuming a synthetic
        predicted fair value ``conviction_band`` above (LONG) and below (SHORT) the
        entry price. These synthetic fair values are returned as
        ``long_predicted_fv``/``short_predicted_fv`` so callers can persist the exact
        prediction that produced each reward, keeping features and labels coherent.
        """
        long_predicted_fv = round(current_price * (1.0 + conviction_band), 4) if current_price > 0 else None
        short_predicted_fv = round(current_price * (1.0 - conviction_band), 4) if current_price > 0 else None

        # Look up any delisting once so a name that delists mid-horizon resolves to a
        # realized terminal exit (loss-bearing) instead of a dropped None row.
        delisting = self._delisting_service.get_delisting(symbol) if self._delisting_service else None
        # Floor a total-loss (recovery=0) terminal price to a tiny fraction of entry so
        # the shared reward calculator (which neutralizes actual_price<=0) registers a
        # near-total loss rather than a zero reward.
        loss_floor = round(current_price * 1e-4, 6) if current_price > 0 else 0.0

        prices: Dict[str, Any] = {}
        exit_dates: Dict[str, Any] = {}
        long_rewards: Dict[str, Any] = {}
        short_rewards: Dict[str, Any] = {}
        terminal_exits: Dict[str, bool] = {}

        for period, days in HOLDING_PERIODS.items():
            target_date = analysis_date + timedelta(days=days)
            if self._price_service is None:
                continue
            future_price = self._price_service.get_price(symbol, target_date)
            exit_dt = target_date
            is_terminal = False

            # No market price for the horizon: if the symbol delisted on/before the
            # target date, use the terminal exit value (last_price * recovery).
            if (not future_price or future_price <= 0) and delisting is not None and self._delisting_service:
                terminal = self._delisting_service.terminal_exit_price(delisting, target_date)
                if terminal is not None:
                    future_price = terminal if terminal > 0 else loss_floor
                    exit_dt = delisting.delist_date
                    is_terminal = True

            if future_price and future_price > 0:
                prices[period] = round(future_price, 4)
                exit_dates[period] = exit_dt.isoformat()
                terminal_exits[period] = is_terminal

                # RewardCalculator derives LONG/SHORT from predicted_fv vs entry price;
                # we force each direction with the synthetic conviction-band fair values.
                if current_price > 0 and self._reward_calculator is not None:
                    long_result = self._reward_calculator.calculate(
                        predicted_fv=long_predicted_fv,
                        price_at_prediction=current_price,
                        actual_price=future_price,
                        days=days,
                        beta=beta,
                    )
                    short_result = self._reward_calculator.calculate(
                        predicted_fv=short_predicted_fv,
                        price_at_prediction=current_price,
                        actual_price=future_price,
                        days=days,
                        beta=beta,
                    )
                    long_rewards[period] = round(long_result.reward, 4)
                    short_rewards[period] = round(short_result.reward, 4)
            else:
                prices[period] = None
                exit_dates[period] = None
                long_rewards[period] = None
                short_rewards[period] = None
                terminal_exits[period] = False

        return {
            "entry_date": analysis_date.isoformat(),
            "conviction_band": conviction_band,
            "long_predicted_fv": long_predicted_fv,
            "short_predicted_fv": short_predicted_fv,
            "delisted": delisting is not None,
            "delist_date": delisting.delist_date.isoformat() if delisting else None,
            "prices": prices,
            "exit_dates": exit_dates,
            "terminal_exits": terminal_exits,
            "long_rewards": long_rewards,
            "short_rewards": short_rewards,
        }

    async def _get_metadata(self, symbol: str) -> Dict[str, Any]:
        """Get symbol metadata from shared service."""
        if self._metadata_service:
            metadata = self._metadata_service.get_metadata(symbol)
            if metadata:
                # Convert SymbolMetadata dataclass to dict
                return {
                    "symbol": metadata.symbol,
                    "sector": metadata.sector,
                    "industry": metadata.industry,
                    "market_cap": metadata.market_cap,
                    "shares_outstanding": metadata.shares_outstanding,
                    "beta": metadata.beta,
                    "is_sp500": metadata.is_sp500,
                    "is_russell1000": metadata.is_russell1000,
                    "cik": metadata.cik,
                    "size_category": metadata.size_category,
                }
        return {}

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "run_backtest",
                        "calculate_rewards",
                        "record_prediction",
                        "get_historical_data",
                        "get_context_features",
                    ],
                    "description": "Action to perform",
                    "default": "run_backtest",
                },
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g., AAPL)",
                },
                "lookback_months": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of months to look back for backtesting",
                    "default": [12],
                },
                "analysis_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Date of analysis (ISO format)",
                },
                "current_price": {
                    "type": "number",
                    "description": "Price at analysis date",
                },
                "fair_value": {
                    "type": "number",
                    "description": "Blended fair value",
                },
                "fair_values": {
                    "type": "object",
                    "description": "Dict of model fair values",
                },
                "weights": {
                    "type": "object",
                    "description": "Dict of model weights",
                },
                "tier_classification": {
                    "type": "string",
                    "description": "Valuation tier classification",
                },
            },
            "required": ["symbol"],
        }

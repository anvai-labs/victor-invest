# Copyright 2025 Vijaykumar Singh
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

"""
Unified Valuation Executor - Shared Service for Both CLIs

This service provides a unified interface for running multi-model valuations,
ensuring both investigator and victor-invest produce identical results.

Key Features:
- Single entry point for all valuation models
- Uses DynamicModelWeightingService for tier-based weights
- Consistent data fetching and TTM calculations
- Proper model filtering and applicability checks

Usage:
    from investigator.domain.services.unified_valuation_executor import (
        UnifiedValuationExecutor,
    )

    executor = UnifiedValuationExecutor(symbol="AAPL", current_price=150.0)
    result = await executor.run_comprehensive_valuation()
"""

import asyncio
import logging
from typing import Any

from investigator.config import get_config
from investigator.domain.services.company_metadata_service import (
    CompanyMetadataService,
)
from investigator.domain.services.dynamic_model_weighting import (
    DynamicModelWeightingService,
)

logger = logging.getLogger(__name__)


class UnifiedValuationExecutor:
    """
    Unified valuation executor that both CLIs can use.

    Replaces the individual model execution in victor_invest with the
    same approach used by investigator, ensuring consistent results.
    """

    def __init__(
        self,
        symbol: str,
        current_price: float,
        quarterly_metrics: list[dict] | None = None,
        multi_year_data: list[dict] | None = None,
        cost_of_equity: float | None = None,
        terminal_growth_rate: float | None = None,
    ):
        """
        Initialize the unified valuation executor.

        Args:
            symbol: Stock ticker symbol
            current_price: Current stock price
            quarterly_metrics: Quarterly financial data (optional, fetched if needed)
            multi_year_data: Multi-year financial data (optional, fetched if needed)
            cost_of_equity: Required return for DCF (optional, calculated if needed)
            terminal_growth_rate: Terminal growth rate (optional, calculated if needed)
        """
        self.symbol = symbol
        self.current_price = current_price
        self.quarterly_metrics = quarterly_metrics
        self.multi_year_data = multi_year_data
        self.cost_of_equity = cost_of_equity
        self.terminal_growth_rate = terminal_growth_rate

        # Get configuration
        self.config = get_config()
        self.valuation_config = self.config.valuation if hasattr(self.config, "valuation") else {}

        # Initialize services
        self.metadata_service = CompanyMetadataService(
            sector_normalization=self.valuation_config.get("sector_normalization", {})
        )
        self.weighting_service = DynamicModelWeightingService(valuation_config=self.valuation_config)

    async def run_comprehensive_valuation(
        self,
    ) -> dict[str, Any]:
        """
        Run comprehensive multi-model valuation with sector-weighted blending.

        This is the main entry point that both CLIs should use.

        Returns:
            Dictionary with:
            - symbol: Stock symbol
            - current_price: Current price
            - models: Dict of individual model results
            - models_applied: List of model names that succeeded
            - consensus_fair_value: Weighted blended fair value
            - consensus_upside: Percentage upside/downside
            - tier_classification: Tier name used for weighting
            - weights_applied: Final weights used for blending
        """
        # Fetch data if not provided
        if not self.quarterly_metrics:
            self.quarterly_metrics = await self._fetch_quarterly_metrics()

        if not self.multi_year_data:
            self.multi_year_data = await self._fetch_multi_year_data()

        # Get sector/industry
        sector, industry = self.metadata_service.get_sector_industry(self.symbol)
        logger.info(f"{self.symbol}: Retrieved sector={sector}, industry={industry} from CompanyMetadataService")

        # Run all valuation models
        model_results = await self._run_all_models()

        if not model_results:
            return {
                "symbol": self.symbol,
                "current_price": self.current_price,
                "error": "No valuation models could be applied",
                "models": {},
                "models_applied": [],
                "consensus_fair_value": None,
            }

        # Calculate tier-based weights
        financials = self._build_financials_dict()
        ratios = self._build_ratios_dict()

        weights, tier, _audit_trail = self.weighting_service.determine_weights(
            symbol=self.symbol,
            financials=financials,
            ratios=ratios,
            data_quality=None,
            market_context=None,
        )

        logger.info(f"{self.symbol}: Tier={tier} | Sector={sector} | Industry={industry} | Weights: {weights}")

        # Apply weights to calculate blended fair value
        weighted_sum = 0.0
        total_weight = 0.0
        applied_weights = {}

        for model_name, model_result in model_results.items():
            if model_result.get("success") and model_result.get("output"):
                output = model_result["output"]
                fair_value = output.get("fair_value_per_share")

                if fair_value and fair_value > 0:
                    weight = weights.get(model_name, 0.0)
                    # Convert percentage to decimal (e.g., 30 -> 0.30)
                    weight_decimal = weight / 100.0
                    weighted_sum += fair_value * weight_decimal
                    total_weight += weight_decimal
                    applied_weights[model_name] = weight

        # Calculate final blended value
        if total_weight == 0:
            logger.warning(f"{self.symbol}: All models filtered out by tier-based weights, using simple average")
            fair_values = [
                r["output"]["fair_value_per_share"]
                for r in model_results.values()
                if r.get("success") and r.get("output", {}).get("fair_value_per_share")
            ]
            consensus = sum(fair_values) / len(fair_values) if fair_values else None
        else:
            consensus = weighted_sum / total_weight

        if consensus is not None:
            logger.info(
                f"{self.symbol}: Using sector-weighted blend (tier={tier}) → ${consensus:.2f} | "
                f"Applied weights: {applied_weights}"
            )

        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "models": model_results,
            "models_applied": list(model_results.keys()),
            "consensus_fair_value": consensus,
            "consensus_upside": (
                ((consensus / self.current_price) - 1) * 100 if consensus and self.current_price else None
            ),
            "tier_classification": tier,
            "weights_applied": applied_weights,
        }

    async def _run_all_models(self) -> dict[str, Any]:
        """
        Run all applicable valuation models.

        Returns:
            Dict mapping model names to their results
        """
        from investigator.domain.services.valuation import DCFValuation

        # EVEBITDAModel and PBRatioModel are deliberately absent: both models are
        # unavailable (see below), so importing them would only suggest otherwise.
        from investigator.domain.services.valuation.models import (
            GordonGrowthModel,
            PERatioModel,
            PSRatioModel,
        )

        results = {}
        loop = asyncio.get_event_loop()

        # Run DCF
        try:
            dcf = DCFValuation(
                symbol=self.symbol,
                quarterly_metrics=self.quarterly_metrics,
                multi_year_data=self.multi_year_data,
            )
            dcf_result = await loop.run_in_executor(None, dcf.calculate_dcf_valuation)

            if dcf_result and dcf_result.get("fair_value_per_share"):
                results["dcf"] = {
                    "success": True,
                    "output": {
                        "model": "dcf",
                        "fair_value_per_share": dcf_result["fair_value_per_share"],
                    },
                }
        except Exception as e:
            logger.debug(f"{self.symbol}: DCF failed: {e}")
            results["dcf"] = {"success": False, "error": str(e)}

        # Run GGM
        try:
            ggm = GordonGrowthModel(
                symbol=self.symbol,
                quarterly_metrics=self.quarterly_metrics,
                multi_year_data=self.multi_year_data,
            )
            ggm_result = await loop.run_in_executor(None, ggm.calculate)

            if ggm_result and not isinstance(ggm_result, str):
                results["ggm"] = {
                    "success": True,
                    "output": {
                        "model": "ggm",
                        "fair_value_per_share": ggm_result.fair_value,
                    },
                }
        except Exception as e:
            logger.debug(f"{self.symbol}: GGM failed: {e}")
            results["ggm"] = {"success": False, "error": str(e)}

        # Run PE, PS, PB, EV/EBITDA using shared TTMMetrics
        from investigator.domain.services.valuation.common import TTMMetrics

        # Calculate TTM metrics using shared service
        ttm_eps = TTMMetrics.calculate_ttm_eps(
            quarterly_data=self.quarterly_metrics,
            shares_outstanding=None,  # Will be fetched if needed
        )
        ttm_revenue = TTMMetrics.calculate_ttm_revenue(quarterly_data=self.quarterly_metrics)
        # TTM EBITDA fed EV/EBITDA only, which is unavailable; computing it here
        # would be work with nowhere to go.

        # Get sector multiples
        from investigator.domain.services.valuation.common import SectorMultiples

        sector, industry = self.metadata_service.get_sector_industry(self.symbol)
        sector_multiples = SectorMultiples.get_sector_multiples(sector=sector, industry=industry)

        # Run PE
        try:
            if ttm_eps and ttm_eps > 0:
                pe_model = PERatioModel(
                    company_profile=None,  # Will be created if needed
                    ttm_eps=ttm_eps,
                    sector_median_pe=sector_multiples.get("pe", 15.0),
                )
                pe_result = pe_model.calculate()
                if pe_result and not isinstance(pe_result, str):
                    results["pe"] = {
                        "success": True,
                        "output": {
                            "model": "pe",
                            "fair_value_per_share": pe_result.fair_value,
                        },
                    }
        except Exception as e:
            logger.debug(f"{self.symbol}: PE failed: {e}")
            results["pe"] = {"success": False, "error": str(e)}

        # Run PS
        try:
            if ttm_revenue and ttm_revenue > 0:
                ps_model = PSRatioModel(
                    company_profile=None,
                    ttm_revenue=ttm_revenue,
                    sector_median_ps=sector_multiples.get("ps", 3.0),
                )
                ps_result = ps_model.calculate()
                if ps_result and not isinstance(ps_result, str):
                    results["ps"] = {
                        "success": True,
                        "output": {
                            "model": "ps",
                            "fair_value_per_share": ps_result.fair_value,
                        },
                    }
        except Exception as e:
            logger.debug(f"{self.symbol}: PS failed: {e}")
            results["ps"] = {"success": False, "error": str(e)}

        # PB is unavailable, and now says so.
        #
        # This block imported investigator.domain.services.valuation.shared.book_value_service,
        # a module that exists nowhere in the repo. The import raised, a broad
        # handler caught it, and the model reported failure at debug level on every
        # call -- so PB has never once produced a valuation.
        #
        # Reviving it needs a book-value-per-share source. ratio_calculator can
        # compute a PB ratio, but only when handed BVPS; deriving that from
        # quarterly data is the missing piece, and a domain decision rather than a
        # wiring one. Until then the model reports unavailable rather than
        # pretending to have tried.
        results["pb"] = {
            "success": False,
            "error": "PB unavailable: no book-value-per-share source is wired",
        }

        # EV/EBITDA is unavailable for the same reason: the
        # valuation.shared.market_data_service module it imported does not exist,
        # so this model has never run either. Reviving it needs a market-data source
        # supplying the inputs for enterprise value.
        results["ev_ebitda"] = {
            "success": False,
            "error": "EV/EBITDA unavailable: no market-data source is wired",
        }

        return results

    def _build_financials_dict(self) -> dict[str, Any]:
        """Build financials dict for weight calculation."""
        financials: dict[str, Any] = {
            "net_income": None,
            "revenue": None,
            "shareholders_equity": None,
            "market_cap": None,
        }

        # Extract from quarterly_metrics if available
        if self.quarterly_metrics and len(self.quarterly_metrics) >= 4:
            ttm = self.quarterly_metrics[:4]
            financials["net_income"] = sum(self._extract_metric(q, ["net_income"]) or 0 for q in ttm)
            financials["revenue"] = sum(self._extract_metric(q, ["revenue", "total_revenue"]) or 0 for q in ttm)
            financials["shareholders_equity"] = self._extract_metric(
                self.quarterly_metrics[0],
                ["stockholders_equity", "total_stockholders_equity"],
            )

        # Calculate market_cap if we have price
        if self.current_price and self.quarterly_metrics:
            shares = self._extract_metric(
                self.quarterly_metrics[0],
                ["shares_outstanding", "weighted_average_shares_outstanding"],
            )
            if shares:
                financials["market_cap"] = self.current_price * shares

        return financials

    def _build_ratios_dict(self) -> dict[str, Any]:
        """Build ratios dict for weight calculation."""
        ratios = {
            "roe": None,
            "payout_ratio": None,
            "revenue_growth_yoy": None,
            "earnings_growth_yoy": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "dividend_yield": None,
        }

        financials = self._build_financials_dict()

        # Calculate ROE if we have the data
        if financials.get("net_income") and financials.get("shareholders_equity"):
            if financials["shareholders_equity"] and financials["shareholders_equity"] > 0:
                ratios["roe"] = financials["net_income"] / financials["shareholders_equity"] * 100

        return ratios

    def _extract_metric(self, data: dict, keys: list[str]) -> Any:
        """Extract a metric value from data dict, trying multiple keys."""
        for key in keys:
            value = data.get(key)
            if value is not None and value != 0:
                return value
        return None

    async def _fetch_quarterly_metrics(self) -> list[dict]:
        """Fetch quarterly metrics from database."""
        # This would be implemented to fetch from the same source as investigator
        # For now, return empty to use the data passed in __init__
        return []

    async def _fetch_multi_year_data(self) -> list[dict]:
        """Fetch multi-year data from database."""
        # This would be implemented to fetch from the same source as investigator
        # For now, return empty to use the data passed in __init__
        return []

    def _calculate_enterprise_value(self, market_data: dict) -> float | None:
        """Calculate enterprise value from market data."""
        market_cap = market_data.get("market_cap")
        total_debt = market_data.get("total_debt", 0)
        cash = market_data.get("cash_and_equivalents", 0)

        if market_cap:
            return float(market_cap) + float(total_debt or 0) - float(cash or 0)
        return None

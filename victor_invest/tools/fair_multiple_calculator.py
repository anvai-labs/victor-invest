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
Fair Multiple Calculator Tool for Victor Investment Framework.

This tool implements Layer 2 of the robust valuation strategy:
- Combines trend-adjusted sector multiples (Layer 1)
- With company-specific premium history (Layer 2)
- Produces company-specific fair value multiples
- Applies safety margins based on confidence levels

Example:
    from victor_invest.tools import FairMultipleCalculatorTool

    tool = FairMultipleCalculatorTool()
    result = await tool.execute(
        action="calculate",
        symbol="AAPL",
        sector="Technology"
    )
"""

import logging
from typing import Optional

from victor_invest.tools.base import ToolResult

logger = logging.getLogger(__name__)


class FairMultipleCalculatorTool:
    """
    Tool for calculating company-specific fair value multiples.

    Implements Layer 2 of robust valuation strategy combining:
    - Trend-adjusted sector multiples
    - Company historical premium/discount
    - Mean reversion adjustments
    - Safety margins
    """

    name = "fair_multiple_calculator"
    description = (
        "Calculate company-specific fair value multiples using "
        "trend-adjusted sector multiples and company premium history. "
        "Actions: calculate, report"
    )

    def __init__(self, config=None):
        """Initialize tool with optional config."""
        self.config = config

    async def execute(self, _exec_ctx=None, **kwargs) -> ToolResult:
        """
        Execute fair multiple calculation.

        Args:
            action: "calculate" or "report"
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional)
            metric: Metric to calculate - "pe", "ps", "pb", or "all" (default: "all")
            current_price: Current stock price (for report)
            eps: Earnings per share (for report)
            revenue_per_share: Revenue per share (for report)
            book_value_per_share: Book value per share (for report)
            lookback_years: Years of historical data (default: 5)
            conservative: Use conservative adjustments (default: false)

        Returns:
            ToolResult with fair multiple data
        """
        try:
            action = kwargs.get("action", "calculate")

            if action == "calculate":
                return await self._calculate(**kwargs)
            elif action == "report":
                return await self._report(**kwargs)
            else:
                return ToolResult.create_failure(f"Unknown action: {action}. Valid actions: calculate, report")

        except Exception as e:
            logger.exception(f"Error in FairMultipleCalculatorTool.execute: {e}")
            return ToolResult.create_failure(f"Error calculating fair multiples: {str(e)}")

    async def _calculate(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        metric: str = "all",
        lookback_years: int = 5,
        conservative: bool = False,
        **kwargs,
    ) -> ToolResult:
        """
        Calculate fair multiples for a company.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional)
            metric: "pe", "ps", "pb", "ev_ebitda", or "all"
            lookback_years: Years of historical data
            conservative: Use conservative adjustments

        Returns:
            ToolResult with calculated fair multiples
        """
        from investigator.domain.services.company_fair_multiple_calculator import (
            CompanyFairMultipleCalculator,
        )

        # Initialize calculator
        calculator = CompanyFairMultipleCalculator(
            lookback_years=lookback_years,
            conservative=conservative,
        )

        # Calculate for single metric or all
        if metric == "all":
            results = calculator.calculate_all_fair_multiples(symbol=symbol, sector=sector, industry=industry)

            # Format results
            result_data = {
                "action": "calculate",
                "symbol": symbol.upper(),
                "sector": sector,
                "industry": industry,
                "lookback_years": lookback_years,
                "conservative": conservative,
                "multiples": {},
            }

            for metric_name, fair_result in results.items():
                if fair_result is None:
                    result_data["multiples"][metric_name] = {"status": "insufficient_data"}
                    continue

                result_data["multiples"][metric_name] = {
                    "final_fair_multiple": fair_result.final_fair_multiple,
                    "sector_baseline": fair_result.sector_baseline,
                    "historical_premium_pct": fair_result.company_historical_premium,
                    "current_premium_pct": fair_result.current_premium,
                    "premium_z_score": fair_result.premium_z_score,
                    "mean_reversion_signal": fair_result.mean_reversion_signal,
                    "safety_margin_pct": fair_result.safety_margin * 100,
                    "confidence": fair_result.confidence,
                    "upside_downside_pct": fair_result.upside_downside_pct,
                }

        else:
            fair_result = calculator.calculate_fair_multiple(symbol=symbol, sector=sector, metric=metric)

            if fair_result is None:
                return ToolResult.create_failure(
                    f"Could not calculate fair {metric.upper()} multiple for {symbol} (insufficient data)"
                )

            result_data = {
                "action": "calculate",
                "symbol": symbol.upper(),
                "metric": metric,
                "sector": sector,
                "lookback_years": lookback_years,
                "conservative": conservative,
                "multiple": {
                    "final_fair_multiple": fair_result.final_fair_multiple,
                    "sector_baseline": fair_result.sector_baseline,
                    "historical_premium_pct": fair_result.company_historical_premium,
                    "current_premium_pct": fair_result.current_premium,
                    "premium_z_score": fair_result.premium_z_score,
                    "mean_reversion_signal": fair_result.mean_reversion_signal,
                    "safety_margin_pct": fair_result.safety_margin * 100,
                    "confidence": fair_result.confidence,
                    "confidence_factors": fair_result.confidence_factors,
                    "upside_downside_pct": fair_result.upside_downside_pct,
                },
            }

        logger.info(
            f"Fair multiple calculation complete for {symbol}: {len(result_data.get('multiples', {})) or 1} metric(s)"
        )

        return ToolResult.create_success(result_data)

    async def _report(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        current_price: Optional[float] = None,
        eps: Optional[float] = None,
        revenue_per_share: Optional[float] = None,
        book_value_per_share: Optional[float] = None,
        lookback_years: int = 5,
        conservative: bool = False,
        **kwargs,
    ) -> ToolResult:
        """
        Generate comprehensive fair value report.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional)
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share
            lookback_years: Years of historical data
            conservative: Use conservative adjustments

        Returns:
            ToolResult with comprehensive fair value report
        """
        from investigator.domain.services.company_fair_multiple_calculator import (
            CompanyFairMultipleCalculator,
        )

        # Initialize calculator
        calculator = CompanyFairMultipleCalculator(
            lookback_years=lookback_years,
            conservative=conservative,
        )

        # Generate report
        report = calculator.generate_fair_value_report(
            symbol=symbol,
            sector=sector,
            industry=industry,
            current_price=current_price,
            eps=eps,
            revenue_per_share=revenue_per_share,
            book_value_per_share=book_value_per_share,
        )

        logger.info(f"Fair value report generated for {symbol}")

        return ToolResult.create_success(report)

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
Robust Valuation Tool for Victor Investment Framework.

This tool implements the complete 3-layer robust valuation strategy:
- Layer 1: Trend-adjusted sector multiples
- Layer 2: Company-specific premium history
- Layer 3: Cross-sectional peer comparison

Example:
    from victor_invest.tools import RobustValuationTool

    tool = RobustValuationTool()
    result = await tool.execute(
        action="analyze",
        symbol="AAPL",
        sector="Technology",
        current_price=175.0,
        eps=6.05
    )
"""

import logging
from typing import Optional

from victor_invest.tools.base import ToolResult

logger = logging.getLogger(__name__)


class RobustValuationTool:
    """
    Tool for comprehensive robust valuation analysis.

    Combines all 3 layers for robust fair value estimation.
    """

    name = "robust_valuation"
    description = (
        "Comprehensive robust valuation combining trend-adjusted sector multiples, "
        "company premium history, and peer comparison. "
        "Actions: analyze, peer_compare, report"
    )

    def __init__(self, config=None):
        """Initialize tool with optional config."""
        self.config = config

    async def execute(self, _exec_ctx=None, **kwargs) -> ToolResult:
        """
        Execute robust valuation analysis.

        Args:
            action: "analyze" | "peer_compare" | "report"
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional)
            current_price: Current stock price (for report)
            eps: Earnings per share (for report)
            revenue_per_share: Revenue per share (for report)
            book_value_per_share: Book value per share (for report)
            lookback_years: Years of historical data (default: 5)
            conservative: Use conservative adjustments (default: false)

        Returns:
            ToolResult with valuation analysis
        """
        try:
            action = kwargs.get("action", "analyze")

            if action == "analyze":
                return await self._analyze(**kwargs)
            elif action == "peer_compare":
                return await self._peer_compare(**kwargs)
            elif action == "report":
                return await self._report(**kwargs)
            else:
                return ToolResult.create_failure(
                    f"Unknown action: {action}. Valid actions: analyze, peer_compare, report"
                )

        except Exception as e:
            logger.exception(f"Error in RobustValuationTool.execute: {e}")
            return ToolResult.create_failure(f"Error in robust valuation: {str(e)}")

    async def _analyze(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        lookback_years: int = 5,
        conservative: bool = False,
        **kwargs,
    ) -> ToolResult:
        """
        Perform comprehensive robust valuation analysis.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name
            lookback_years: Years of historical data
            conservative: Use conservative adjustments

        Returns:
            ToolResult with comprehensive analysis
        """
        from investigator.domain.services.robust_valuation_service import (
            RobustValuationService,
        )

        service = RobustValuationService(
            lookback_years=lookback_years,
            conservative=conservative,
        )

        result = service.calculate_robust_valuation(
            symbol=symbol,
            sector=sector,
            industry=industry,
        )

        if not result:
            return ToolResult.create_failure(f"Could not calculate robust valuation for {symbol}")

        # Format result
        result_data = {
            "action": "analyze",
            "symbol": result.symbol,
            "sector": result.sector,
            "industry": result.industry,
            "recommendation": result.recommendation,
            "confidence": result.confidence,
            "fair_value_estimate": result.fair_value_estimate,
            "fair_value_range": result.fair_value_range,
            "upside_downside_pct": result.upside_downside_pct,
            "layer1_sector_multiples": result.layer1_sector_multiples,
            "layer2_summary": {
                metric: {
                    "fair_multiple": r.final_fair_multiple,
                    "confidence": r.confidence,
                }
                for metric, r in result.layer2_fair_multiples.items()
            },
            "layer3_summary": {
                metric: {
                    "percentile_rank": r.percentile_rank,
                    "status": r.status,
                }
                for metric, r in result.layer3_peer_comparison.items()
            },
            "signals": result.signals,
            "calculated_at": result.calculated_at,
        }

        logger.info(f"Robust valuation complete for {symbol}: {result.recommendation} ({result.confidence} confidence)")

        return ToolResult.create_success(result_data)

    async def _peer_compare(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        metric: str = "all",
        min_peers: int = 3,
        **kwargs,
    ) -> ToolResult:
        """
        Perform peer comparison analysis.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name
            metric: "pe", "ps", "pb", "ev_ebitda", or "all"
            min_peers: Minimum number of peers required

        Returns:
            ToolResult with peer comparison
        """
        from investigator.domain.services.cross_sectional_valuation import (
            CrossSectionalValuation,
        )

        service = CrossSectionalValuation()

        if metric == "all":
            # Compare all metrics
            comparisons = service.compare_all_metrics(
                symbol=symbol,
                industry=industry,
            )

            result_data = {
                "action": "peer_compare",
                "symbol": symbol.upper(),
                "sector": sector,
                "industry": industry,
                "comparisons": {},
            }

            for metric_name, comparison in comparisons.items():
                if comparison is None:
                    result_data["comparisons"][metric_name] = {"status": "insufficient_data"}
                    continue

                result_data["comparisons"][metric_name] = {
                    "company_multiple": comparison.company_multiple,
                    "peer_median": comparison.peer_median,
                    "peer_mean": comparison.peer_mean,
                    "percentile_rank": comparison.percentile_rank,
                    "status": comparison.status,
                    "premium_to_peers_pct": comparison.premium_to_peers_pct,
                    "peer_count": comparison.peer_count,
                }

        else:
            # Compare single metric
            comparison = service.compare_to_peers(
                symbol=symbol,
                metric=metric,
                industry=industry,
                min_peers=min_peers,
            )

            if not comparison:
                return ToolResult.create_failure(f"Could not compare {symbol} to peers for {metric.upper()}")

            result_data = {
                "action": "peer_compare",
                "symbol": symbol.upper(),
                "metric": metric,
                "sector": sector,
                "industry": comparison.industry,
                "company_multiple": comparison.company_multiple,
                "peer_median": comparison.peer_median,
                "peer_mean": comparison.peer_mean,
                "peer_std": comparison.peer_std,
                "percentile_rank": comparison.percentile_rank,
                "status": comparison.status,
                "premium_to_peers_pct": comparison.premium_to_peers_pct,
                "peer_count": comparison.peer_count,
                "peers": comparison.peers,
            }

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
        Generate comprehensive valuation report.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share
            lookback_years: Years of historical data
            conservative: Use conservative adjustments

        Returns:
            ToolResult with comprehensive report
        """
        from investigator.domain.services.robust_valuation_service import (
            RobustValuationService,
        )

        service = RobustValuationService(
            lookback_years=lookback_years,
            conservative=conservative,
        )

        report = service.generate_comprehensive_report(
            symbol=symbol,
            sector=sector,
            industry=industry,
            current_price=current_price,
            eps=eps,
            revenue_per_share=revenue_per_share,
            book_value_per_share=book_value_per_share,
        )

        if "error" in report:
            return ToolResult.create_failure(report["error"])

        return ToolResult.create_success(report)

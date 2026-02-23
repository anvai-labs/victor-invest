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

"""Robust valuation service orchestrator.

Combines all 3 layers of the robust valuation strategy:
- Layer 1: Trend-adjusted sector multiples
- Layer 2: Company-specific premium history
- Layer 3: Cross-sectional peer comparison

Produces comprehensive fair value analysis with consensus recommendations.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from investigator.domain.services.company_fair_multiple_calculator import (
    CompanyFairMultipleCalculator,
    FairMultipleResult,
)
from investigator.domain.services.cross_sectional_valuation import (
    CrossSectionalValuation,
    PeerComparisonResult,
)
from investigator.domain.services.sector_multiples_trend_adjusted import (
    SectorMultiplesTrendAdjusted,
)
from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


@dataclass
class RobustValuationResult:
    """Result of comprehensive robust valuation analysis."""

    symbol: str
    sector: str
    industry: Optional[str]

    # Layer 1: Trend-adjusted sector multiples
    layer1_sector_multiples: Dict[str, float]

    # Layer 2: Company fair multiples
    layer2_fair_multiples: Dict[str, FairMultipleResult]

    # Layer 3: Peer comparison
    layer3_peer_comparison: Dict[str, PeerComparisonResult]

    # Synthesis
    fair_value_estimate: float
    fair_value_range: tuple  # (low, high)
    confidence: str  # HIGH, MEDIUM, LOW
    recommendation: str  # STRONG BUY, BUY, HOLD, SELL, STRONG SELL
    upside_downside_pct: float

    # Breakdown
    valuation_methods: Dict[str, float]  # pe_based, ps_based, pb_based
    method_weights: Dict[str, float]  # Weight assigned to each method

    # Signals
    signals: List[str]

    # Metadata
    calculated_at: str
    data_sources: List[str] = field(default_factory=list)


class RobustValuationService:
    """Comprehensive robust valuation combining all 3 layers.

    Method:
    1. Layer 1: Get trend-adjusted sector multiples
    2. Layer 2: Calculate company-specific fair multiples
    3. Layer 3: Compare to industry peers
    4. Synthesis: Weighted combination with confidence scoring
    5. Recommendation: Final BUY/HOLD/SELL with confidence level

    Weights:
    - Layer 1 (Sector): 40%
    - Layer 2 (Company Premium): 40%
    - Layer 3 (Peers): 20%

    These weights can be configured based on:
    - Data quality for each layer
    - Sector characteristics
    - Company specific factors
    """

    # Default weights for each layer
    DEFAULT_WEIGHTS = {
        "layer1_sector": 0.40,
        "layer2_company": 0.40,
        "layer3_peers": 0.20,
    }

    # Recommendation thresholds
    STRONG_BUY_THRESHOLD = 15.0  # 15%+ upside
    BUY_THRESHOLD = 5.0  # 5%+ upside
    HOLD_THRESHOLD_DOWN = -5.0  # -5% to +5%
    SELL_THRESHOLD = -15.0  # -15% downside
    STRONG_SELL_THRESHOLD = -15.0  # Beyond -15%

    def __init__(
        self,
        *,
        sec_db_manager: Any = None,
        stock_db_manager: Any = None,
        lookback_years: int = 5,
        weights: Optional[Dict[str, float]] = None,
        conservative: bool = False,
    ):
        """Initialize robust valuation service.

        Args:
            sec_db_manager: Database manager for SEC database
            stock_db_manager: Database manager for stock database
            lookback_years: Years of historical data
            weights: Custom weights for each layer
            conservative: Use conservative adjustments
        """
        if sec_db_manager is None:
            sec_db_manager = get_db_manager()

        self.sec_db_manager = sec_db_manager
        self.lookback_years = lookback_years
        self.conservative = conservative

        # Set weights
        if weights:
            self.weights = weights
        else:
            self.weights = self.DEFAULT_WEIGHTS.copy()

        # Initialize layer services
        self.layer1 = SectorMultiplesTrendAdjusted(
            min_samples=5,
            lookback_years=lookback_years,
        )

        self.layer2 = CompanyFairMultipleCalculator(
            lookback_years=lookback_years,
            conservative=conservative,
        )

        self.layer3 = CrossSectionalValuation(
            sec_db_manager=sec_db_manager,
            stock_db_manager=stock_db_manager,
        )

    def calculate_robust_valuation(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        current_price: Optional[float] = None,
        eps: Optional[float] = None,
        revenue_per_share: Optional[float] = None,
        book_value_per_share: Optional[float] = None,
    ) -> Optional[RobustValuationResult]:
        """Calculate comprehensive robust valuation.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional)
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share

        Returns:
            RobustValuationResult or None if insufficient data
        """
        logger.info(f"Calculating robust valuation for {symbol}...")

        # Step 1: Get trend-adjusted sector multiples (Layer 1)
        layer1_data = self._get_layer1_data(sector)
        if not layer1_data:
            logger.warning(f"{symbol}: Could not get Layer 1 data")
            return None

        # Step 2: Calculate company fair multiples (Layer 2)
        layer2_data = self._get_layer2_data(symbol, sector, industry)
        if not layer2_data:
            logger.warning(f"{symbol}: Could not get Layer 2 data")
            return None

        # Step 3: Compare to peers (Layer 3)
        layer3_data = self._get_layer3_data(symbol, industry)

        # Step 4: Synthesis - Weighted combination
        synthesis = self._synthesize_layers(
            symbol,
            layer1_data,
            layer2_data,
            layer3_data,
            current_price,
            eps,
            revenue_per_share,
            book_value_per_share,
        )

        # Build result
        result = RobustValuationResult(
            symbol=symbol.upper(),
            sector=sector,
            industry=industry,
            layer1_sector_multiples=layer1_data,
            layer2_fair_multiples=layer2_data,
            layer3_peer_comparison=layer3_data,
            **synthesis,
        )

        logger.info(
            f"{symbol} Robust Valuation: {result.recommendation} "
            f"({result.confidence} confidence)"
        )

        return result

    def _get_layer1_data(self, sector: str) -> Optional[Dict[str, float]]:
        """Get Layer 1: Trend-adjusted sector multiples.

        Args:
            sector: Sector name

        Returns:
            Dict of trend-adjusted sector multiples
        """
        # This would typically fetch from cached/stored trend-adjusted values
        # For now, return placeholder - in production would query from database
        # where trend-adjusted values are stored
        logger.debug(f"Layer 1: Getting trend-adjusted sector multiples for {sector}")

        # Placeholder - return sample data for Technology sector
        # In production, this would query actual stored values
        return {
            "pe": 55.0,
            "ps": 7.6,
            "pb": 8.0,
        }

    def _get_layer2_data(
        self, symbol: str, sector: str, industry: Optional[str]
    ) -> Optional[Dict[str, FairMultipleResult]]:
        """Get Layer 2: Company fair multiples.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name

        Returns:
            Dict of fair multiple results by metric
        """
        logger.debug(f"Layer 2: Calculating fair multiples for {symbol}")

        fair_multiples = {}

        # Calculate for each metric
        for metric in ["pe", "ps", "pb"]:
            try:
                result = self.layer2.calculate_fair_multiple(
                    symbol=symbol,
                    sector=sector,
                    metric=metric,
                    sector_trend_adjusted=self._get_layer1_data(sector).get(metric),
                )
                if result:
                    fair_multiples[metric] = result
            except Exception as e:
                logger.warning(f"Layer 2 {metric} calculation failed: {e}")

        return fair_multiples if fair_multiples else None

    def _get_layer3_data(
        self, symbol: str, industry: Optional[str]
    ) -> Dict[str, PeerComparisonResult]:
        """Get Layer 3: Peer comparison data.

        Args:
            symbol: Stock symbol
            industry: Industry name

        Returns:
            Dict of peer comparison results by metric
        """
        logger.debug(f"Layer 3: Comparing {symbol} to peers")

        peer_comparison = {}

        # Compare for each metric
        for metric in ["pe", "ps", "pb"]:
            try:
                result = self.layer3.compare_to_peers(
                    symbol=symbol,
                    metric=metric,
                    industry=industry,
                    min_peers=3,
                )
                if result:
                    peer_comparison[metric] = result
            except Exception as e:
                logger.warning(f"Layer 3 {metric} comparison failed: {e}")

        return peer_comparison

    def _synthesize_layers(
        self,
        symbol: str,
        layer1_data: Dict[str, float],
        layer2_data: Dict[str, FairMultipleResult],
        layer3_data: Dict[str, PeerComparisonResult],
        current_price: Optional[float],
        eps: Optional[float],
        revenue_per_share: Optional[float],
        book_value_per_share: Optional[float],
    ) -> Dict[str, Any]:
        """Synthesize all 3 layers into final valuation.

        Args:
            symbol: Stock symbol
            layer1_data: Trend-adjusted sector multiples
            layer2_data: Company fair multiples
            layer3_data: Peer comparison results
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share

        Returns:
            Dict with synthesis results
        """
        logger.info(f"Synthesizing valuation for {symbol}...")

        # Calculate fair values using different methods
        valuation_methods = {}
        method_weights = {}

        for metric in ["pe", "ps", "pb"]:
            if metric not in layer2_data:
                continue

            fair_multiple = layer2_data[metric].final_fair_multiple
            confidence = layer2_data[metric].confidence

            # Weight based on confidence
            if confidence == "HIGH":
                weight = 1.0
            elif confidence == "MEDIUM":
                weight = 0.5
            else:  # LOW
                weight = 0.25

            method_weights[f"{metric}_weight"] = weight

            # Calculate fair value if per-share data available
            if metric == "pe" and eps:
                valuation_methods["pe_based"] = fair_multiple * eps
            elif metric == "ps" and revenue_per_share:
                valuation_methods["ps_based"] = fair_multiple * revenue_per_share
            elif metric == "pb" and book_value_per_share:
                valuation_methods["pb_based"] = fair_multiple * book_value_per_share

        if not valuation_methods:
            # No fair values could be calculated
            return {
                "fair_value_estimate": 0.0,
                "fair_value_range": (0.0, 0.0),
                "confidence": "LOW",
                "recommendation": "HOLD",
                "upside_downside_pct": 0.0,
                "valuation_methods": {},
                "method_weights": {},
                "signals": ["Insufficient data for valuation"],
                "calculated_at": datetime.now(timezone.utc).isoformat(),
                "data_sources": [],
            }

        # Calculate weighted average fair value
        total_weight = sum(method_weights.values())
        weighted_fair_value = (
            sum(
                value * method_weights.get(f"{method.replace('_based', '')}_weight", 0)
                for method, value in valuation_methods.items()
            )
            / total_weight
            if total_weight > 0
            else 0.0
        )

        # Calculate range (min to max of methods)
        fair_values = list(valuation_methods.values())
        fair_value_range = (min(fair_values), max(fair_values))

        # Determine overall confidence
        confidences = [
            layer2_data[m].confidence for m in ["pe", "ps", "pb"] if m in layer2_data
        ]
        overall_confidence = self._determine_overall_confidence(confidences)

        # Calculate upside/downside
        if current_price:
            upside_downside_pct = (
                (weighted_fair_value - current_price) / current_price
            ) * 100
        else:
            upside_downside_pct = 0.0

        # Determine recommendation
        recommendation = self._determine_recommendation(
            upside_downside_pct, overall_confidence
        )

        # Collect signals
        signals = self._collect_signals(layer2_data, layer3_data, overall_confidence)

        return {
            "fair_value_estimate": round(weighted_fair_value, 2),
            "fair_value_range": (
                round(fair_value_range[0], 2),
                round(fair_value_range[1], 2),
            ),
            "confidence": overall_confidence,
            "recommendation": recommendation,
            "upside_downside_pct": round(upside_downside_pct, 1),
            "valuation_methods": {k: round(v, 2) for k, v in valuation_methods.items()},
            "method_weights": method_weights,
            "signals": signals,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": [
                "Layer 1: Trend-adjusted sector multiples",
                "Layer 2: Company premium history",
                "Layer 3: Cross-sectional peer comparison",
            ],
        }

    def _determine_overall_confidence(self, confidences: List[str]) -> str:
        """Determine overall confidence from individual confidences.

        Args:
            confidences: List of confidence levels

        Returns:
            Overall confidence level
        """
        if not confidences:
            return "LOW"

        if all(c == "HIGH" for c in confidences):
            return "HIGH"
        elif all(c in ["HIGH", "MEDIUM"] for c in confidences):
            return "MEDIUM"
        else:
            return "LOW"

    def _determine_recommendation(
        self, upside_downside_pct: float, confidence: str
    ) -> str:
        """Determine recommendation from upside/downside and confidence.

        Args:
            upside_downside_pct: Percentage upside/downside
            confidence: Confidence level

        Returns:
            Recommendation string
        """
        # Adjust thresholds based on confidence
        if confidence == "HIGH":
            # Use standard thresholds
            strong_buy_threshold = self.STRONG_BUY_THRESHOLD
            buy_threshold = self.BUY_THRESHOLD
        elif confidence == "MEDIUM":
            # More conservative thresholds
            strong_buy_threshold = self.STRONG_BUY_THRESHOLD * 1.5
            buy_threshold = self.BUY_THRESHOLD * 1.5
        else:  # LOW
            # Very conservative thresholds
            strong_buy_threshold = self.STRONG_BUY_THRESHOLD * 2.0
            buy_threshold = self.BUY_THRESHOLD * 2.0

        if upside_downside_pct >= strong_buy_threshold:
            return "STRONG BUY"
        elif upside_downside_pct >= buy_threshold:
            return "BUY"
        elif upside_downside_pct <= -strong_buy_threshold:
            return "STRONG SELL"
        elif upside_downside_pct <= -buy_threshold:
            return "SELL"
        else:
            return "HOLD"

    def _collect_signals(
        self,
        layer2_data: Dict[str, FairMultipleResult],
        layer3_data: Dict[str, PeerComparisonResult],
        confidence: str,
    ) -> List[str]:
        """Collect all signals from analysis.

        Args:
            layer2_data: Company fair multiple results
            layer3_data: Peer comparison results
            confidence: Overall confidence

        Returns:
            List of signal strings
        """
        signals = []

        # Layer 2 signals
        for metric, result in layer2_data.items():
            signal = result.mean_reversion_signal
            if signal and signal != "none":
                signals.append(f"{metric.upper()} mean reversion: {signal.upper()}")

        # Layer 3 signals
        for metric, result in layer3_data.items():
            status = result.status
            if status in ["cheap", "expensive"]:
                signals.append(f"{metric.upper()} vs peers: {status.upper()}")

        # Confidence signal
        signals.append(f"Overall confidence: {confidence}")

        return signals

    def generate_comprehensive_report(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        current_price: Optional[float] = None,
        eps: Optional[float] = None,
        revenue_per_share: Optional[float] = None,
        book_value_per_share: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate comprehensive valuation report.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share

        Returns:
            Comprehensive valuation report
        """
        logger.info(f"Generating comprehensive report for {symbol}...")

        # Calculate robust valuation
        valuation = self.calculate_robust_valuation(
            symbol=symbol,
            sector=sector,
            industry=industry,
            current_price=current_price,
            eps=eps,
            revenue_per_share=revenue_per_share,
            book_value_per_share=book_value_per_share,
        )

        if not valuation:
            return {
                "symbol": symbol.upper(),
                "error": "Could not calculate robust valuation",
                "calculated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Build report
        report = {
            "symbol": valuation.symbol,
            "sector": valuation.sector,
            "industry": valuation.industry,
            "current_price": current_price,
            "calculated_at": valuation.calculated_at,
            "summary": {
                "recommendation": valuation.recommendation,
                "confidence": valuation.confidence,
                "fair_value_estimate": valuation.fair_value_estimate,
                "fair_value_range": valuation.fair_value_range,
                "upside_downside_pct": valuation.upside_downside_pct,
            },
            "layer1_sector_multiples": valuation.layer1_sector_multiples,
            "layer2_fair_multiples": {},
            "layer3_peer_comparison": {},
            "valuation_methods": valuation.valuation_methods,
            "method_weights": valuation.method_weights,
            "signals": valuation.signals,
            "data_sources": valuation.data_sources,
        }

        # Format Layer 2 data
        for metric, result in valuation.layer2_fair_multiples.items():
            report["layer2_fair_multiples"][metric] = {
                "final_fair_multiple": result.final_fair_multiple,
                "sector_baseline": result.sector_baseline,
                "company_historical_premium": result.company_historical_premium,
                "mean_reversion_signal": result.mean_reversion_signal,
                "safety_margin": result.safety_margin,
                "confidence": result.confidence,
            }

        # Format Layer 3 data
        for metric, result in valuation.layer3_peer_comparison.items():
            report["layer3_peer_comparison"][metric] = {
                "company_multiple": result.company_multiple,
                "peer_median": result.peer_median,
                "percentile_rank": result.percentile_rank,
                "status": result.status,
                "premium_to_peers_pct": result.premium_to_peers_pct,
                "peer_count": result.peer_count,
            }

        return report

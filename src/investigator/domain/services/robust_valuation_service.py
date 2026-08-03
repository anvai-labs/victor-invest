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
from investigator.domain.services.sector_name_mapper import SectorIndustryMapper
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
            sector: Sector name (will be normalized)
            industry: Industry name (optional, will be normalized)
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share

        Returns:
            RobustValuationResult or None if insufficient data
        """
        # Normalize sector and industry names
        normalized = SectorIndustryMapper.normalize_metadata(sector, industry)
        sector = normalized["sector"] or "Unknown"
        industry = normalized["industry"]

        logger.info(f"Calculating robust valuation for {symbol} (sector: {sector}, industry: {industry})...")

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

        logger.info(f"{symbol} Robust Valuation: {result.recommendation} ({result.confidence} confidence)")

        return result

    def _get_layer1_data(self, sector: str) -> Optional[Dict[str, float]]:
        """Get Layer 1: Trend-adjusted sector multiples.

        Args:
            sector: Sector name

        Returns:
            Dict of trend-adjusted sector multiples
        """
        logger.debug(f"Layer 1: Getting trend-adjusted sector multiples for {sector}")

        current = self._get_current_sector_multiples(sector)
        if not current:
            return None

        try:
            adjusted = self.layer1.calculate_trend_adjusted_multiples(
                current_multiples={sector: current},
                sectors=[sector],
            )
            sector_adjusted = adjusted.get(sector) if isinstance(adjusted, dict) else None
            if isinstance(sector_adjusted, dict):
                return {
                    metric: float(sector_adjusted[metric])
                    for metric in ("pe", "ps", "pb")
                    if sector_adjusted.get(metric) is not None
                }
        except Exception as exc:
            logger.warning("%s: Trend adjustment failed, using latest stored multiples: %s", sector, exc)

        return {metric: float(current[metric]) for metric in ("pe", "ps", "pb") if current.get(metric) is not None}

    def _get_current_sector_multiples(self, sector: str) -> Optional[Dict[str, Any]]:
        """Fetch the latest stored sector multiples from sector_multiples_history."""
        from sqlalchemy import text

        try:
            with self.sec_db_manager.engine.connect() as conn:
                row = (
                    conn.execute(
                        text("""
                        SELECT pe_multiple, ps_multiple, pb_multiple, sample_size, calculated_at
                        FROM sector_multiples_history
                        WHERE group_name = :sector
                          AND group_type = 'sector'
                        ORDER BY fiscal_year DESC, calculated_at DESC NULLS LAST
                        LIMIT 1
                    """),
                        {"sector": sector},
                    )
                    .mappings()
                    .first()
                )
        except Exception as exc:
            logger.warning("%s: Could not fetch sector multiples: %s", sector, exc)
            return None

        if not row:
            return None

        result = {
            "pe": float(row["pe_multiple"]) if row.get("pe_multiple") is not None else None,
            "ps": float(row["ps_multiple"]) if row.get("ps_multiple") is not None else None,
            "pb": float(row["pb_multiple"]) if row.get("pb_multiple") is not None else None,
            "sample_size": row.get("sample_size"),
            "last_updated": (
                row["calculated_at"].isoformat() if hasattr(row.get("calculated_at"), "isoformat") else None
            ),
        }
        if not any(result.get(metric) is not None for metric in ("pe", "ps", "pb")):
            return None
        return result

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
                    sector_trend_adjusted=(self._get_layer1_data(sector) or {}).get(metric),
                )
                if result:
                    fair_multiples[metric] = result
            except Exception as e:
                logger.warning(f"Layer 2 {metric} calculation failed: {e}")

        return fair_multiples if fair_multiples else None

    def _get_layer3_data(self, symbol: str, industry: Optional[str]) -> Dict[str, PeerComparisonResult]:
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

            # Weight based on confidence. Only add a method weight if that method
            # produced a fair-value estimate from valid per-share inputs.
            if confidence == "HIGH":
                weight = 1.0
            elif confidence == "MEDIUM":
                weight = 0.5
            else:  # LOW
                weight = 0.25

            # Calculate fair value if per-share data available
            if metric == "pe" and eps:
                valuation_methods["pe_based"] = fair_multiple * eps
                method_weights["pe_weight"] = weight
            elif metric == "ps" and revenue_per_share:
                valuation_methods["ps_based"] = fair_multiple * revenue_per_share
                method_weights["ps_weight"] = weight
            elif metric == "pb" and book_value_per_share:
                valuation_methods["pb_based"] = fair_multiple * book_value_per_share
                method_weights["pb_weight"] = weight

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

        # Check for model divergence
        divergence_analysis = self.detect_model_divergence(layer2_data)

        # Calculate weighted average fair value (or use best model if divergent)
        if divergence_analysis["is_divergent"]:
            # Use highest confidence model instead of blended
            recommended_model = divergence_analysis["recommended_model"]
            if recommended_model and recommended_model in layer2_data:
                weighted_fair_value = layer2_data[recommended_model].final_fair_multiple
                # Need to multiply by appropriate per-share metric
                if recommended_model == "pe" and eps:
                    weighted_fair_value *= eps
                elif recommended_model == "ps" and revenue_per_share:
                    weighted_fair_value *= revenue_per_share
                elif recommended_model == "pb" and book_value_per_share:
                    weighted_fair_value *= book_value_per_share
                else:
                    # Fallback to min of methods if can't calculate
                    weighted_fair_value = min(valuation_methods.values())

                logger.info(
                    f"{symbol}: Models divergent, using {recommended_model.upper()}: ${weighted_fair_value:.2f}"
                )
            else:
                # Fallback to min of methods
                weighted_fair_value = min(valuation_methods.values())
        else:
            # Use weighted average as normal
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
        confidences = [layer2_data[m].confidence for m in ["pe", "ps", "pb"] if m in layer2_data]
        overall_confidence = self._determine_overall_confidence(confidences)

        # Calculate upside/downside
        if current_price:
            upside_downside_pct = ((weighted_fair_value - current_price) / current_price) * 100
        else:
            upside_downside_pct = 0.0

        # Determine recommendation
        recommendation = self._determine_recommendation(upside_downside_pct, overall_confidence)

        # Collect signals (include divergence analysis)
        signals = self._collect_signals(layer2_data, layer3_data, overall_confidence, divergence_analysis)

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

    def _determine_recommendation(self, upside_downside_pct: float, confidence: str) -> str:
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
        divergence_analysis: Optional[Dict[str, Any]] = None,
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

        # Divergence warning
        if divergence_analysis and divergence_analysis.get("is_divergent"):
            divergent_models = divergence_analysis.get("divergent_models", [])
            recommended = divergence_analysis.get("recommended_model", "").upper()
            signals.append(f"MODEL DIVERGENCE: {', '.join(divergent_models)}")
            signals.append(f"Using {recommended} model (highest confidence)")

        # Confidence signal
        signals.append(f"Overall confidence: {confidence}")

        return signals

    def detect_stock_split(
        self,
        symbol: str,
        current_price: float,
        fair_value: float,
        model_agreement_score: float = 0.0,
    ) -> Dict[str, Any]:
        """Detect if a stock split has occurred but fair values weren't adjusted.

        Red flags:
        - Fair value > 3x current price
        - High model agreement (>0.7)
        - Large cap company

        Args:
            symbol: Stock symbol
            current_price: Current trading price
            fair_value: Calculated fair value
            model_agreement_score: Model agreement score (0-1)

        Returns:
            Dict with detection results
        """
        result = {
            "symbol": symbol.upper(),
            "is_split_detected": False,
            "implied_split_ratio": None,
            "likely_split": None,
            "confidence": "LOW",
        }

        if current_price <= 0 or fair_value <= 0:
            return result

        ratio = fair_value / current_price

        # High model agreement + high ratio = likely stock split
        if ratio > 3 and model_agreement_score >= 0.7:
            # Check if it's a known common split ratio
            common_splits = {
                2: "2:1",
                3: "3:1",
                4: "4:1",
                5: "5:1",
                7: "7:1",
                10: "10:1",
            }

            for split_ratio, split_name in common_splits.items():
                if abs(ratio - split_ratio) / split_ratio < 0.25:  # Within 25%
                    result["is_split_detected"] = True
                    result["implied_split_ratio"] = round(ratio, 2)
                    result["likely_split"] = split_name
                    result["confidence"] = "HIGH"

                    logger.warning(
                        f"{symbol}: Possible {split_name} stock split detected! "
                        f"Price=${current_price:.2f}, FV=${fair_value:.2f}, ratio={ratio:.2f}x"
                    )
                    return result

            # High ratio but not common split
            if ratio >= 3:
                result["is_split_detected"] = True
                result["implied_split_ratio"] = round(ratio, 2)
                result["likely_split"] = f"{round(ratio)}:1 (unusual)"
                result["confidence"] = "MEDIUM"

                logger.warning(
                    f"{symbol}: Unusual stock split ratio detected! "
                    f"Price=${current_price:.2f}, FV=${fair_value:.2f}, ratio={ratio:.2f}x"
                )

        return result

    def validate_revenue_data(
        self,
        symbol: str,
        revenue_per_share: float,
        mkt_cap: float,
        industry: Optional[str] = None,
        sector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate revenue data before using in models.

        Sanity checks:
        - REITs: mkt_cap / revenue shouldn't be > 500x
        - Mining: revenue should align with production
        - SaaS: revenue should be positive and growing

        Args:
            symbol: Stock symbol
            revenue_per_share: TTM revenue per share
            mkt_cap: Market capitalization
            industry: Industry name
            sector: Sector name

        Returns:
            Dict with validation results
        """
        warnings: List[str] = []
        recommendations: List[str] = []
        result: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "is_valid": True,
            "ps_ratio": None,
            "warnings": warnings,
            "recommendations": recommendations,
        }

        if revenue_per_share <= 0:
            result["is_valid"] = False
            warnings.append("Revenue per share is zero or negative")
            return result

        # Calculate P/S ratio
        ps_ratio = mkt_cap / revenue_per_share if revenue_per_share > 0 else float("inf")
        result["ps_ratio"] = round(ps_ratio, 2)

        # Industry-specific validation
        industry_lower = (industry or "").lower()
        sector_lower = (sector or "").lower()

        # REITs validation
        if "real estate" in industry_lower or "reit" in industry_lower:
            if ps_ratio > 500:
                result["is_valid"] = False
                warnings.append(
                    f"Suspicious P/S ratio {ps_ratio:.1f} for REIT. Revenue data may be dividends instead of revenue."
                )
                recommendations.append("Use AFFO (Adjusted Funds From Operations) instead of revenue for REITs")

        # Mining/Materials validation
        elif "mining" in industry_lower or "materials" in sector_lower:
            if ps_ratio > 100:
                result["is_valid"] = False
                warnings.append(
                    f"Suspicious P/S ratio {ps_ratio:.1f} for miner. Revenue data may be incomplete or timing mismatch."
                )

        # Financials validation
        elif "financial" in sector_lower or "bank" in industry_lower:
            if ps_ratio > 50:
                warnings.append(f"High P/S ratio {ps_ratio:.1f} for financial. Consider using P/B or P/E instead.")

        # General sanity check for all industries
        if ps_ratio > 1000:
            result["is_valid"] = False
            warnings.append(
                f"Extremely high P/S ratio {ps_ratio:.1f}. Revenue data is likely incorrect or scaled wrong."
            )

        if warnings:
            logger.warning(f"{symbol}: Revenue validation issues - {'; '.join(warnings)}")

        return result

    def detect_model_divergence(
        self,
        layer2_data: Dict[str, FairMultipleResult],
    ) -> Dict[str, Any]:
        """Detect when valuation models diverge significantly.

        When models disagree, blended average is unreliable.

        Args:
            layer2_data: Dict of fair multiple results by metric

        Returns:
            Dict with divergence analysis
        """
        divergent_models: List[str] = []
        result: Dict[str, Any] = {
            "is_divergent": False,
            "dispersion_score": None,
            "divergent_models": divergent_models,
            "recommended_model": None,
            "recommendation": "Use blended average",
        }

        if not layer2_data or len(layer2_data) < 2:
            return result

        # Calculate z-scores for each model's fair multiple
        fair_multiples = [m.final_fair_multiple for m in layer2_data.values() if m.final_fair_multiple]

        if len(fair_multiples) < 2:
            return result

        # Calculate dispersion (max - min)
        import statistics

        dispersion = max(fair_multiples) - min(fair_multiples)
        result["dispersion_score"] = round(dispersion, 2)

        mean_multiple = statistics.mean(fair_multiples)
        if len(fair_multiples) > 2:
            try:
                std_dev = statistics.stdev(fair_multiples)
                cv = std_dev / mean_multiple if mean_multiple > 0 else float("inf")
            except statistics.StatisticsError:
                cv = 0.0
        else:
            cv = 0.0

        # Check if dispersion is too high (>2x mean or >50% CV)
        if dispersion > mean_multiple * 2 or cv > 0.5:
            result["is_divergent"] = True
            result["recommendation"] = "Use highest confidence model instead of blended"

            # Find model with highest confidence
            best_metric = None
            best_confidence_score = 0

            confidence_ranks = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

            for metric, fair_multiple_result in layer2_data.items():
                conf_score = confidence_ranks.get(fair_multiple_result.confidence, 0)
                if conf_score > best_confidence_score:
                    best_confidence_score = conf_score
                    best_metric = metric

            result["recommended_model"] = best_metric

            # Find divergent models (>1.5x from mean)
            for metric, fair_multiple_result in layer2_data.items():
                multiple = fair_multiple_result.final_fair_multiple
                if multiple and mean_multiple > 0:
                    ratio = multiple / mean_multiple
                    if ratio > 1.5 or ratio < 0.67:
                        divergent_models.append(f"{metric.upper()} ({ratio:.1f}x)")

            logger.warning(
                f"Model divergence detected! Dispersion: {dispersion:.2f}, CV: {cv:.2f}, Divergent: {divergent_models}"
            )

        return result

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
        layer2_formatted: Dict[str, Any] = {}
        layer3_formatted: Dict[str, Any] = {}
        report: Dict[str, Any] = {
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
            "layer2_fair_multiples": layer2_formatted,
            "layer3_peer_comparison": layer3_formatted,
            "valuation_methods": valuation.valuation_methods,
            "method_weights": valuation.method_weights,
            "signals": valuation.signals,
            "data_sources": valuation.data_sources,
        }

        # Format Layer 2 data
        for metric, result in valuation.layer2_fair_multiples.items():
            layer2_formatted[metric] = {
                "final_fair_multiple": result.final_fair_multiple,
                "sector_baseline": result.sector_baseline,
                "company_historical_premium": result.company_historical_premium,
                "mean_reversion_signal": result.mean_reversion_signal,
                "safety_margin": result.safety_margin,
                "confidence": result.confidence,
            }

        # Format Layer 3 data
        for metric, result in valuation.layer3_peer_comparison.items():
            layer3_formatted[metric] = {
                "company_multiple": result.company_multiple,
                "peer_median": result.peer_median,
                "percentile_rank": result.percentile_rank,
                "status": result.status,
                "premium_to_peers_pct": result.premium_to_peers_pct,
                "peer_count": result.peer_count,
            }

        return report

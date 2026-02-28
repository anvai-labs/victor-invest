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

"""Company fair multiple calculator service.

Combines Layer 1 (trend-adjusted sector multiples) with Layer 2 (company premium history)
to produce company-specific fair value multiples with safety margins.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from investigator.domain.services.company_premium_history import (
    CompanyPremiumHistory,
)
from investigator.domain.services.sector_multiples_trend_adjusted import (
    SectorMultiplesTrendAdjusted,
)
from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


@dataclass
class FairMultipleResult:
    """Result of fair multiple calculation."""

    symbol: str
    metric: str  # pe, ps, pb, ev_ebitda

    # Inputs
    sector_baseline: float  # Layer 1: Trend-adjusted sector multiple
    company_historical_premium: float  # Layer 2: Avg historical premium %
    current_premium: float  # Current premium %
    premium_z_score: float  # Z-score of current premium

    # Calculations
    base_fair_multiple: float  # sector_baseline × (1 + historical_premium)
    mean_reversion_adjustment: float  # Adjustment based on z_score
    safety_margin: float  # Safety margin based on confidence
    final_fair_multiple: float  # After all adjustments

    # Metadata
    confidence: str  # HIGH, MEDIUM, LOW
    confidence_factors: List[str]  # Reasons for confidence level
    mean_reversion_signal: str  # buy, sell, none
    upside_downside_pct: float  # % upside/downside to fair value

    # Timestamp
    calculated_at: str


class CompanyFairMultipleCalculator:
    """Calculate company's fair value multiple using comprehensive framework.

    Method:
    1. Start with trend-adjusted sector multiple (Layer 1)
    2. Apply company's historical average premium (Layer 2)
    3. Adjust for mean reversion signal
    4. Apply safety margins based on confidence
    5. Return final fair multiple with metadata

    Confidence Levels:
    - HIGH: ≥5 years data, low volatility, stable premium, strong fundamentals
    - MEDIUM: 3-5 years data, moderate volatility, adequate fundamentals
    - LOW: <3 years data, high volatility, weak fundamentals
    """

    # Safety margins by confidence level
    SAFETY_MARGINS = {
        "HIGH": 0.05,  # 5% discount for high confidence
        "MEDIUM": 0.10,  # 10% discount for medium confidence
        "LOW": 0.15,  # 15% discount for low confidence
    }

    # Mean reversion adjustments
    MEAN_REVERSION_ADJUSTMENTS = {
        "strong_buy": 1.10,  # 10% upside for strong buy signals
        "buy": 1.05,  # 5% upside for buy signals
        "none": 1.00,  # No adjustment
        "sell": 0.95,  # 5% downside for sell signals
        "strong_sell": 0.90,  # 10% downside for strong sell signals
    }

    # Minimum data requirements
    MIN_DATA_POINTS_HIGH_CONFIDENCE = 16  # 4 years of quarterly data
    MIN_DATA_POINTS_MEDIUM_CONFIDENCE = 8  # 2 years of quarterly data
    MAX_PREMIUM_STD_DEV_HIGH_CONFIDENCE = 5.0  # 5% std dev
    MAX_PREMIUM_STD_DEV_MEDIUM_CONFIDENCE = 10.0  # 10% std dev

    def __init__(
        self,
        *,
        sec_db_manager: Any = None,
        lookback_years: int = 5,
        min_data_points: int = 4,
        conservative: bool = False,
    ):
        """Initialize company fair multiple calculator.

        Args:
            sec_db_manager: Database manager for SEC database
            lookback_years: Years of historical data to analyze
            min_data_points: Minimum data points required
            conservative: If True, use more conservative adjustments
        """
        if sec_db_manager is None:
            sec_db_manager = get_db_manager()

        self.sec_db_manager = sec_db_manager
        self.lookback_years = lookback_years
        self.min_data_points = min_data_points
        self.conservative = conservative

        # Initialize layer services
        self.layer1 = SectorMultiplesTrendAdjusted(
            min_samples=min_data_points,
            lookback_years=lookback_years,
        )
        self.layer2 = CompanyPremiumHistory(sec_db_manager=sec_db_manager)

    def calculate_fair_multiple(
        self,
        symbol: str,
        sector: str,
        metric: str = "pe",
        sector_trend_adjusted: Optional[float] = None,
    ) -> Optional[FairMultipleResult]:
        """Calculate company's fair value multiple for a metric.

        Args:
            symbol: Stock symbol
            sector: Sector name
            metric: Metric to calculate - "pe", "ps", "pb", "ev_ebitda"
            sector_trend_adjusted: Pre-calculated trend-adjusted sector multiple
                (if None, will be calculated)

        Returns:
            FairMultipleResult or None if insufficient data
        """
        logger.info(f"Calculating fair {metric.upper()} multiple for {symbol}...")

        # Step 1: Get trend-adjusted sector multiple (Layer 1)
        if sector_trend_adjusted is None:
            sector_trend_adjusted = self._get_sector_trend_adjusted(sector, metric)

        if not sector_trend_adjusted:
            logger.warning(
                f"{symbol}: Could not get trend-adjusted sector multiple for {sector}"
            )
            return None

        # Step 2: Get company's historical premium (Layer 2)
        premium_data = self.layer2.get_historical_premium(
            symbol=symbol,
            metric=metric,
            lookback_years=self.lookback_years,
            min_data_points=self.min_data_points,
        )

        if not premium_data:
            logger.warning(
                f"{symbol}: Insufficient historical premium data "
                f"(need {self.min_data_points} points)"
            )
            return None

        # Extract premium data
        historical_premium = premium_data["avg_premium_pct"]
        current_premium = premium_data["current_premium_pct"]
        premium_z_score = premium_data.get("z_score", 0.0)
        premium_std_dev = premium_data["std_dev"]
        data_points = premium_data["data_points"]
        premium_trend = premium_data.get("trend", "unknown")

        # Step 3: Calculate base fair multiple
        # Formula: Sector Adjusted × (1 + Historical Premium)
        base_fair_multiple = sector_trend_adjusted * (1 + historical_premium / 100)

        # Step 4: Determine mean reversion signal
        mean_reversion_signal = premium_data.get("mean_reversion_signal", "none")

        # Step 5: Apply mean reversion adjustment
        mean_reversion_factor = self.MEAN_REVERSION_ADJUSTMENTS.get(
            mean_reversion_signal, 1.00
        )

        # Conservative mode: reduce mean reversion adjustments
        if self.conservative and mean_reversion_signal != "none":
            # Use 50% of the adjustment in conservative mode
            mean_reversion_factor = 1.0 + (mean_reversion_factor - 1.0) * 0.5

        after_mean_reversion = base_fair_multiple * mean_reversion_factor

        # Step 6: Determine confidence level
        confidence, confidence_factors = self._determine_confidence(
            data_points=data_points,
            premium_std_dev=premium_std_dev,
            premium_trend=premium_trend,
            premium_z_score=premium_z_score,
        )

        # Step 7: Apply safety margin
        safety_margin_pct = self.SAFETY_MARGINS[confidence]

        # Conservative mode: increase safety margin
        if self.conservative:
            safety_margin_pct *= 1.5

        final_fair_multiple = after_mean_reversion * (1 - safety_margin_pct)

        # Step 8: Calculate upside/downside
        # Need current company multiple for this
        current_company_multiple = self._get_current_company_multiple(symbol, metric)
        if current_company_multiple:
            upside_downside_pct = (
                (final_fair_multiple - current_company_multiple)
                / current_company_multiple
            ) * 100
        else:
            upside_downside_pct = 0.0

        # Create result
        result = FairMultipleResult(
            symbol=symbol.upper(),
            metric=metric,
            sector_baseline=round(sector_trend_adjusted, 2),
            company_historical_premium=round(historical_premium, 2),
            current_premium=round(current_premium, 2),
            premium_z_score=round(premium_z_score, 2),
            base_fair_multiple=round(base_fair_multiple, 2),
            mean_reversion_adjustment=round(mean_reversion_factor, 3),
            safety_margin=round(safety_margin_pct, 3),
            final_fair_multiple=round(final_fair_multiple, 2),
            confidence=confidence,
            confidence_factors=confidence_factors,
            mean_reversion_signal=mean_reversion_signal,
            upside_downside_pct=round(upside_downside_pct, 1),
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"{symbol} {metric.upper()}: "
            f"Base={base_fair_multiple:.2f}x → "
            f"Final={final_fair_multiple:.2f}x "
            f"({confidence} confidence)"
        )

        return result

    def calculate_all_fair_multiples(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
    ) -> Dict[str, Optional[FairMultipleResult]]:
        """Calculate fair multiples for all available metrics.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional, for context)

        Returns:
            Dict mapping metric to FairMultipleResult
        """
        logger.info(f"Calculating all fair multiples for {symbol}...")

        # Get trend-adjusted sector multiples for all metrics
        sector_adjusted = self._get_all_sector_trend_adjusted(sector)

        results = {}

        for metric in ["pe", "ps", "pb", "ev_ebitda"]:
            if metric not in sector_adjusted:
                logger.debug(f"{symbol}: No sector data for {metric}")
                continue

            result = self.calculate_fair_multiple(
                symbol=symbol,
                sector=sector,
                metric=metric,
                sector_trend_adjusted=sector_adjusted[metric],
            )

            results[metric] = result

        return results

    def _get_sector_trend_adjusted(self, sector: str, metric: str) -> Optional[float]:
        """Get trend-adjusted sector multiple for a metric.

        Args:
            sector: Sector name
            metric: Metric name

        Returns:
            Trend-adjusted sector multiple or None
        """
        # This would typically query from stored trend-adjusted values
        # For now, return None to indicate it should be provided by caller
        # In production, this would cache or look up from database
        return None

    def _get_all_sector_trend_adjusted(self, sector: str) -> Dict[str, float]:
        """Get all trend-adjusted sector multiples.

        Args:
            sector: Sector name

        Returns:
            Dict mapping metric to trend-adjusted multiple
        """
        # Placeholder - in production, this would query actual data
        # For now, return empty dict
        return {}

    def _get_current_company_multiple(
        self, symbol: str, metric: str
    ) -> Optional[float]:
        """Get company's current multiple for a metric.

        Args:
            symbol: Stock symbol
            metric: Metric name

        Returns:
            Current multiple or None
        """
        from sqlalchemy import text

        with self.sec_db_manager.engine.connect() as conn:
            # Map metric to database column
            metric_column_map = {
                "pe": "net_income",
                "ps": "total_revenue",
                "pb": "stockholders_equity",
            }

            if metric not in metric_column_map:
                return None

            # Get latest data
            query = text(
                """
                SELECT market_cap, {denominator}
                FROM sec_companyfacts_processed
                WHERE UPPER(symbol) = UPPER(:symbol)
                ORDER BY fiscal_year DESC, fiscal_period DESC
                LIMIT 1
            """.format(denominator=metric_column_map[metric])
            )

            result = conn.execute(query, {"symbol": symbol})
            row = result.fetchone()

            if row and row[0] and row[1]:
                market_cap = float(row[0])
                denominator = float(row[1])

                if denominator > 0:
                    return market_cap / denominator

        return None

    def _determine_confidence(
        self,
        data_points: int,
        premium_std_dev: float,
        premium_trend: str,
        premium_z_score: float,
    ) -> tuple[str, List[str]]:
        """Determine confidence level based on data quality factors.

        Args:
            data_points: Number of historical data points
            premium_std_dev: Standard deviation of premium
            premium_trend: Premium trend (stable/expanding/shrinking)
            premium_z_score: Z-score of current premium

        Returns:
            (confidence_level, list_of_factors)
        """
        factors = []
        confidence_score = 0

        # Factor 1: Data point count
        if data_points >= self.MIN_DATA_POINTS_HIGH_CONFIDENCE:
            confidence_score += 3
            factors.append(f"Excellent data history ({data_points} points)")
        elif data_points >= self.MIN_DATA_POINTS_MEDIUM_CONFIDENCE:
            confidence_score += 2
            factors.append(f"Good data history ({data_points} points)")
        else:
            confidence_score += 1
            factors.append(f"Limited data history ({data_points} points)")

        # Factor 2: Premium stability (std dev)
        if premium_std_dev <= self.MAX_PREMIUM_STD_DEV_HIGH_CONFIDENCE:
            confidence_score += 3
            factors.append(f"Very stable premium (std dev: {premium_std_dev:.1f}%)")
        elif premium_std_dev <= self.MAX_PREMIUM_STD_DEV_MEDIUM_CONFIDENCE:
            confidence_score += 2
            factors.append(
                f"Moderately stable premium (std dev: {premium_std_dev:.1f}%)"
            )
        else:
            confidence_score += 1
            factors.append(f"Volatile premium (std dev: {premium_std_dev:.1f}%)")

        # Factor 3: Trend stability
        if premium_trend == "stable":
            confidence_score += 2
            factors.append("Stable premium trend")
        elif premium_trend in ["expanding", "shrinking"]:
            confidence_score += 1
            factors.append(f"Premium {premium_trend}")
        else:
            factors.append("Unknown premium trend")

        # Factor 4: Current premium deviation (z-score)
        if abs(premium_z_score) <= 0.5:
            confidence_score += 2
            factors.append("Premium near historical average")
        elif abs(premium_z_score) <= 1.0:
            confidence_score += 1
            factors.append("Premium within normal range")
        else:
            factors.append("Premium significantly deviated from norm")

        # Determine confidence level
        if confidence_score >= 10:
            confidence = "HIGH"
        elif confidence_score >= 6:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return confidence, factors

    def generate_fair_value_report(
        self,
        symbol: str,
        sector: str,
        industry: Optional[str] = None,
        current_price: Optional[float] = None,
        eps: Optional[float] = None,
        revenue_per_share: Optional[float] = None,
        book_value_per_share: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate comprehensive fair value report.

        Args:
            symbol: Stock symbol
            sector: Sector name
            industry: Industry name (optional)
            current_price: Current stock price
            eps: Earnings per share
            revenue_per_share: Revenue per share
            book_value_per_share: Book value per share

        Returns:
            Comprehensive fair value report
        """
        logger.info(f"Generating fair value report for {symbol}...")

        # Calculate fair multiples for all metrics
        fair_multiples = self.calculate_all_fair_multiples(
            symbol=symbol, sector=sector, industry=industry
        )

        # Build report
        report = {
            "symbol": symbol.upper(),
            "sector": sector,
            "industry": industry,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "fair_multiples": {},
            "fair_values": {},
            "recommendation": None,
            "overall_confidence": None,
        }

        # Process each metric
        fair_values = []
        confidences = []

        for metric, result in fair_multiples.items():
            if result is None:
                continue

            report["fair_multiples"][metric] = {
                "final_fair_multiple": result.final_fair_multiple,
                "sector_baseline": result.sector_baseline,
                "historical_premium": result.company_historical_premium,
                "mean_reversion_signal": result.mean_reversion_signal,
                "safety_margin": result.safety_margin,
                "confidence": result.confidence,
                "upside_downside_pct": result.upside_downside_pct,
            }

            # Calculate fair value if per-share data provided
            if metric == "pe" and eps:
                fair_value = result.final_fair_multiple * eps
                fair_values.append(fair_value)
                report["fair_values"]["pe_based"] = round(fair_value, 2)

            elif metric == "ps" and revenue_per_share:
                fair_value = result.final_fair_multiple * revenue_per_share
                fair_values.append(fair_value)
                report["fair_values"]["ps_based"] = round(fair_value, 2)

            elif metric == "pb" and book_value_per_share:
                fair_value = result.final_fair_multiple * book_value_per_share
                fair_values.append(fair_value)
                report["fair_values"]["pb_based"] = round(fair_value, 2)

            confidences.append(result.confidence)

        # Calculate overall recommendation
        if fair_values and current_price:
            avg_fair_value = sum(fair_values) / len(fair_values)
            upside_downside = ((avg_fair_value - current_price) / current_price) * 100

            report["average_fair_value"] = round(avg_fair_value, 2)
            report["current_price"] = current_price
            report["upside_downside_pct"] = round(upside_downside, 1)

            # Determine recommendation
            if upside_downside > 15:
                recommendation = "STRONG BUY"
            elif upside_downside > 5:
                recommendation = "BUY"
            elif upside_downside < -15:
                recommendation = "STRONG SELL"
            elif upside_downside < -5:
                recommendation = "SELL"
            else:
                recommendation = "HOLD"

            report["recommendation"] = recommendation

        # Determine overall confidence
        if confidences:
            if all(c == "HIGH" for c in confidences):
                overall_confidence = "HIGH"
            elif all(c in ["HIGH", "MEDIUM"] for c in confidences):
                overall_confidence = "MEDIUM"
            else:
                overall_confidence = "LOW"

            report["overall_confidence"] = overall_confidence

        return report

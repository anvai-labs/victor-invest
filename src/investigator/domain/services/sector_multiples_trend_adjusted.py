# Copyright 2025 Vijaykumar Singh <singhjd@gmail.com>
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

"""Trend-adjusted sector multiples calculation.

Calculates sector/industry valuation multiples that account for:
- Historical trends (expansion/shrinking over time)
- Market regime changes (bull vs bear markets)
- Time-weighted averaging with more weight to recent periods

This provides more robust valuations by adjusting current snapshot multiples
based on historical context and trend momentum.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


class SectorMultiplesTrendAdjusted:
    """Calculate trend-adjusted sector multiples.

    Combines current snapshot data with historical trend analysis to produce
    more robust valuation multiples that account for sector expansion/shrinking.

    Methods:
        calculate_trend_adjusted_multiples: Main calculation method
        _get_historical_trend: Fetch and analyze historical data
        _calculate_trend_metrics: Calculate trend statistics
        _apply_trend_adjustment: Apply adjustments based on trends
        _detect_market_regime: Detect bull/bear market regime
    """

    # Trend thresholds
    SWELLING_THRESHOLD = 0.10  # 10%+ expansion = swelling
    SHRINKING_THRESHOLD = -0.10  # -10%+ contraction = shrinking
    HIGH_VOLATILITY_THRESHOLD = 0.20  # 20%+ std dev = high volatility

    # Adjustment factors
    SWELLING_ADJUSTMENT = 0.85  # Reduce by 15% for swelling sectors
    SHRINKING_ADJUSTMENT = 1.15  # Increase by 15% for shrinking sectors
    HIGH_VOLATILITY_DISCOUNT = 0.90  # 10% discount for high volatility
    BULL_MARKET_PREMIUM = 1.05  # 5% premium in bull markets
    BEAR_MARKET_DISCOUNT = 0.95  # 5% discount in bear markets

    def __init__(
        self,
        *,
        sec_db_manager: Any = None,
        min_samples: int = 5,
        percentile_exclude: Tuple[float, float] = (0.05, 0.95),
        lookback_years: int = 5,
        adjustment_sensitivity: str = "medium",  # low, medium, high
    ):
        """Initialize trend-adjusted sector multiples service.

        Args:
            sec_db_manager: Database manager for SEC database
            min_samples: Minimum number of symbols required
            percentile_exclude: Percentiles for outlier filtering
            lookback_years: Years of historical data to consider
            adjustment_sensitivity: How aggressive to apply adjustments
                - low: Conservative adjustments (50% of factors)
                - medium: Moderate adjustments (100% of factors)
                - high: Aggressive adjustments (150% of factors)
        """
        if sec_db_manager is None:
            sec_db_manager = get_db_manager()

        self.sec_db_manager = sec_db_manager
        self.min_samples = min_samples
        self.percentile_exclude = percentile_exclude
        self.lookback_years = lookback_years

        # Set adjustment sensitivity multiplier
        sensitivity_multipliers = {
            "low": 0.5,
            "medium": 1.0,
            "high": 1.5,
        }
        self.adjustment_multiplier = sensitivity_multipliers.get(adjustment_sensitivity, 1.0)

    def calculate_trend_adjusted_multiples(
        self,
        *,
        current_multiples: Dict[str, Dict[str, Any]],
        sectors: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate trend-adjusted sector multiples.

        Args:
            current_multiples: Current snapshot multiples from refresh service
                Format: {"Technology": {"pe": 28.5, "ps": 6.2, ...}, ...}
            sectors: List of sectors to adjust (None = all)
            industries: List of industries to adjust (None = all)

        Returns:
            Dict with trend-adjusted multiples
            {
                "Technology": {
                    "pe": 26.5,  # Adjusted from current 28.5
                    "pe_raw": 28.5,  # Original current value
                    "ps": 5.9,
                    "ps_raw": 6.2,
                    "trend_analysis": {
                        "pe_trend": "swelling",
                        "pe_change_pct": 12.5,
                        "volatility": "medium",
                        "regime": "bull",
                        "adjustment_factor": 0.93
                    },
                    "sample_size": 150,
                    "last_updated": "2025-02-22T..."
                },
                ...
            }
        """
        logger.info("Calculating trend-adjusted sector multiples...")

        results = {}

        for group_name, current_data in current_multiples.items():
            # Determine if this group should be processed
            if not self._should_process_group(group_name, sectors, industries):
                continue

            logger.info(f"Adjusting multiples for: {group_name}")

            # Get historical trend data
            trend_data = self._get_historical_trend(group_name=group_name, lookback_years=self.lookback_years)

            if not trend_data or len(trend_data) < 2:
                logger.warning(
                    f"{group_name}: Insufficient historical data for trend adjustment, " f"using current multiples"
                )
                results[group_name] = self._create_unadjusted_result(current_data)
                continue

            # Calculate trend metrics
            trend_metrics = self._calculate_trend_metrics(trend_data)

            # Detect market regime
            regime = self._detect_market_regime(trend_data)

            # Apply trend adjustments to each metric
            adjusted_multiples = {}
            for metric in ["pe", "ps", "pb", "ev_ebitda"]:
                current_value = current_data.get(metric)
                if current_value is None:
                    continue

                # Apply adjustment
                adjusted_value, adjustment_info = self._apply_trend_adjustment(
                    current_value=current_value,
                    metric=metric,
                    trend_metrics=trend_metrics,
                    regime=regime,
                )

                adjusted_multiples[f"{metric}_raw"] = current_value
                adjusted_multiples[metric] = round(adjusted_value, 2)

            # Add metadata
            adjusted_multiples["sample_size"] = current_data.get("sample_size")
            adjusted_multiples["last_updated"] = current_data.get(
                "last_updated", datetime.now(timezone.utc).isoformat()
            )
            adjusted_multiples["trend_analysis"] = {
                "regime": regime,
                "lookback_years": self.lookback_years,
                "data_points": len(trend_data),
                "adjustment_sensitivity": self.adjustment_multiplier,
            }

            # Add metric-specific trend analysis
            for metric in ["pe", "ps", "pb"]:
                if metric in trend_metrics:
                    adjusted_multiples["trend_analysis"][f"{metric}_trend"] = trend_metrics[metric]["trend"]
                    adjusted_multiples["trend_analysis"][f"{metric}_change_pct"] = trend_metrics[metric]["change_pct"]
                    adjusted_multiples["trend_analysis"][f"{metric}_volatility"] = trend_metrics[metric]["volatility"]

            results[group_name] = adjusted_multiples

        return results

    def _should_process_group(
        self,
        group_name: str,
        sectors: Optional[List[str]],
        industries: Optional[List[str]],
    ) -> bool:
        """Determine if a group should be processed based on filters."""
        if sectors is None and industries is None:
            return True

        # Check if group name matches any sector
        if sectors and any(s.lower() in group_name.lower() for s in sectors):
            return True

        # Check if group name matches any industry
        if industries and any(i.lower() in group_name.lower() for i in industries):
            return True

        return False

    def _get_historical_trend(self, group_name: str, lookback_years: int) -> List[Dict[str, Any]]:
        """Fetch historical trend data for a group.

        Args:
            group_name: Sector or industry name
            lookback_years: Number of years to look back

        Returns:
            List of historical data points sorted by fiscal_year
        """
        from sqlalchemy import text

        current_year = datetime.now().year
        start_year = current_year - lookback_years

        with self.sec_db_manager.engine.connect() as conn:
            query = text("""
                SELECT fiscal_year, pe_multiple, ps_multiple, pb_multiple, sample_size
                FROM sector_multiples_history
                WHERE group_name = :group_name
                  AND fiscal_year >= :start_year
                  AND fiscal_year < :current_year
                ORDER BY fiscal_year ASC
            """)

            result = conn.execute(
                query,
                {
                    "group_name": group_name,
                    "start_year": start_year,
                    "current_year": current_year,
                },
            )

            trend_data = []
            for row in result:
                trend_data.append(
                    {
                        "fiscal_year": row[0],
                        "pe": float(row[1]) if row[1] else None,
                        "ps": float(row[2]) if row[2] else None,
                        "pb": float(row[3]) if row[3] else None,
                        "sample_size": row[4],
                    }
                )

            return trend_data

    def _calculate_trend_metrics(self, trend_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Calculate trend metrics from historical data.

        Args:
            trend_data: List of historical data points

        Returns:
            Dict with trend metrics for each valuation metric
            {
                "pe": {
                    "trend": "swelling" | "shrinking" | "stable",
                    "change_pct": 12.5,  # Total % change over period
                    "volatility": "high" | "medium" | "low",
                    "std_dev": 5.2,
                    "momentum": 0.8,  # Recent change vs overall trend
                },
                ...
            }
        """
        metrics = {}

        for metric in ["pe", "ps", "pb"]:
            # Extract valid values
            values = [(d["fiscal_year"], d[metric]) for d in trend_data if d.get(metric) is not None]

            if len(values) < 2:
                continue

            metric_values = [v[1] for v in values]

            # Calculate overall change
            first_value = metric_values[0]
            last_value = metric_values[-1]
            total_change_pct = ((last_value - first_value) / first_value) * 100

            # Determine trend direction
            if total_change_pct > self.SWELLING_THRESHOLD * 100:
                trend = "swelling"
            elif total_change_pct < self.SHRINKING_THRESHOLD * 100:
                trend = "shrinking"
            else:
                trend = "stable"

            # Calculate volatility (standard deviation)
            import statistics

            mean_val = statistics.mean(metric_values)
            if len(metric_values) > 1:
                std_dev = statistics.stdev(metric_values)
                cv = (std_dev / mean_val) if mean_val != 0 else 0
            else:
                std_dev = 0
                cv = 0

            # Determine volatility level
            if cv > self.HIGH_VOLATILITY_THRESHOLD:
                volatility = "high"
            elif cv > self.HIGH_VOLATILITY_THRESHOLD / 2:
                volatility = "medium"
            else:
                volatility = "low"

            # Calculate momentum (recent vs overall trend)
            momentum = 0.0
            if len(metric_values) >= 4:
                # Compare last 25% of data to overall trend
                recent_count = max(1, len(metric_values) // 4)
                recent_values = metric_values[-recent_count:]
                early_values = metric_values[:-recent_count]

                if early_values:
                    recent_mean = statistics.mean(recent_values)
                    early_mean = statistics.mean(early_values)
                    momentum = ((recent_mean - early_mean) / early_mean) if early_mean != 0 else 0

            metrics[metric] = {
                "trend": trend,
                "change_pct": round(total_change_pct, 2),
                "volatility": volatility,
                "std_dev": round(std_dev, 2),
                "cv": round(cv, 3),
                "momentum": round(momentum, 3),
                "data_points": len(values),
            }

        return metrics

    def _detect_market_regime(self, trend_data: List[Dict[str, Any]]) -> str:
        """Detect market regime from historical sector multiples.

        Uses average P/E trend across all sectors to detect bull/bear market.
        This is a simplified heuristic - in production would use market-wide indices.

        Args:
            trend_data: Historical trend data for one group

        Returns:
            "bull" | "bear" | "neutral"
        """
        if len(trend_data) < 2:
            return "neutral"

        # Get P/E values
        pe_values = [d.get("pe") for d in trend_data if d.get("pe") is not None]

        if len(pe_values) < 2:
            return "neutral"

        # Calculate trend
        first_pe = pe_values[0]
        last_pe = pe_values[-1]
        change_pct = ((last_pe - first_pe) / first_pe) * 100 if first_pe > 0 else 0

        # Simple regime detection
        if change_pct > 15:  # 15%+ expansion = bull
            return "bull"
        elif change_pct < -15:  # -15%+ contraction = bear
            return "bear"
        else:
            return "neutral"

    def _apply_trend_adjustment(
        self,
        current_value: float,
        metric: str,
        trend_metrics: Dict[str, Dict[str, Any]],
        regime: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """Apply trend adjustment to current multiple.

        Args:
            current_value: Current snapshot multiple value
            metric: Metric name (pe, ps, pb, ev_ebitda)
            trend_metrics: Trend metrics from _calculate_trend_metrics
            regime: Market regime (bull/bear/neutral)

        Returns:
            (adjusted_value, adjustment_info)
        """
        if metric not in trend_metrics:
            # No trend data available, return current value
            return current_value, {"adjustment_factor": 1.0, "adjustments": []}

        metric_trend = trend_metrics[metric]
        adjustments_applied = []
        adjustment_factor = 1.0

        # 1. Apply trend-based adjustment
        trend = metric_trend["trend"]

        if trend == "swelling":
            # Sector is expanding - reduce multiple to account for overvaluation risk
            factor = self.SWELLING_ADJUSTMENT
            # Scale by severity of swelling
            severity_multiplier = min(abs(metric_trend["change_pct"]) / 100, 2.0)  # Cap at 2x
            adjusted_factor = 1.0 - (1.0 - factor) * severity_multiplier
            adjustment_factor *= adjusted_factor
            adjustments_applied.append(f"swelling_adjustment:{adjusted_factor:.3f}")

        elif trend == "shrinking":
            # Sector is contracting - increase multiple for value opportunity
            factor = self.SHRINKING_ADJUSTMENT
            # Scale by severity of shrinking
            severity_multiplier = min(abs(metric_trend["change_pct"]) / 100, 2.0)  # Cap at 2x
            adjusted_factor = 1.0 + (factor - 1.0) * severity_multiplier
            adjustment_factor *= adjusted_factor
            adjustments_applied.append(f"shrinking_adjustment:{adjusted_factor:.3f}")

        # 2. Apply volatility discount
        if metric_trend["volatility"] == "high":
            adjustment_factor *= self.HIGH_VOLATILITY_DISCOUNT
            adjustments_applied.append(f"volatility_discount:{self.HIGH_VOLATILITY_DISCOUNT:.3f}")

        # 3. Apply market regime adjustment
        if regime == "bull":
            adjustment_factor *= self.BULL_MARKET_PREMIUM
            adjustments_applied.append(f"bull_market_premium:{self.BULL_MARKET_PREMIUM:.3f}")
        elif regime == "bear":
            adjustment_factor *= self.BEAR_MARKET_DISCOUNT
            adjustments_applied.append(f"bear_market_discount:{self.BEAR_MARKET_DISCOUNT:.3f}")

        # 4. Apply sensitivity multiplier
        if adjustment_factor != 1.0:
            # Convert factor to adjustment amount, apply sensitivity, convert back
            adjustment_amount = 1.0 - adjustment_factor
            adjusted_amount = adjustment_amount * self.adjustment_multiplier
            final_factor = 1.0 - adjusted_amount
        else:
            final_factor = 1.0

        # Calculate final value
        adjusted_value = current_value * final_factor

        # Sanity check - don't let adjustments go too far
        min_adjustment = 0.5  # Max 50% reduction
        max_adjustment = 1.5  # Max 50% increase

        if final_factor < min_adjustment:
            logger.warning(
                f"{metric}: Adjustment factor {final_factor:.3f} below minimum, " f"capping at {min_adjustment:.3f}"
            )
            final_factor = min_adjustment
            adjusted_value = current_value * final_factor
        elif final_factor > max_adjustment:
            logger.warning(
                f"{metric}: Adjustment factor {final_factor:.3f} above maximum, " f"capping at {max_adjustment:.3f}"
            )
            final_factor = max_adjustment
            adjusted_value = current_value * final_factor

        adjustment_info = {
            "adjustment_factor": round(final_factor, 3),
            "adjustments": adjustments_applied,
            "trend": trend,
            "volatility": metric_trend["volatility"],
        }

        return round(adjusted_value, 2), adjustment_info

    def _create_unadjusted_result(self, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create result object for groups without sufficient historical data."""
        result = {
            "sample_size": current_data.get("sample_size"),
            "last_updated": current_data.get("last_updated", datetime.now(timezone.utc).isoformat()),
            "trend_analysis": {
                "status": "insufficient_historical_data",
                "message": "Current multiples used (no trend adjustment applied)",
            },
        }

        # Copy metrics with _raw suffix (same as adjusted since no adjustment)
        for metric in ["pe", "ps", "pb", "ev_ebitda"]:
            value = current_data.get(metric)
            if value is not None:
                result[metric] = value
                result[f"{metric}_raw"] = value

        return result

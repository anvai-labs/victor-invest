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

"""Revenue growth calculations for valuation models.

Provides TTM-based revenue growth calculation and growth multipliers
for adjusting valuation multiples (P/E, P/S, EV/EBITDA).

TTM (Trailing Twelve Months) is the industry standard for growth-adjusted
valuation multiples because:
1. Smooths seasonality and quarter-to-quarter noise
2. Aligns with annualized valuation multiples
3. Standard practice across equity research
"""

import logging
from typing import Any, List, Optional

from investigator.domain.services.valuation.models.common import clamp

logger = logging.getLogger(__name__)


class GrowthCalculator:
    """Calculate revenue growth rates and growth adjustment factors.

    Methods:
        calculate_revenue_growth_ttm: TTM-based revenue growth (primary)
        calculate_growth_multiplier_pe: P/E growth multiplier (0.8-2.5x cap)
        calculate_growth_multiplier_ps: P/S growth adjustment
        calculate_ev_ebitda_growth_factor: EV/EBITDA growth factor (1.0-1.6x)
    """

    @staticmethod
    def calculate_revenue_growth_ttm(*, quarterly_data: List[Any], logger: Any = logger) -> Optional[float]:
        """Calculate revenue growth using TTM (Trailing Twelve Months) comparison.

        Primary method: TTM Revenue Growth
            - Compares TTM revenue now vs TTM revenue 4 quarters ago
            - Smooths seasonality and quarter-to-quarter noise
            - Industry standard for growth-adjusted valuation multiples

        Fallback method: Same-quarter YoY
            - Compares current quarter to same quarter in prior year
            - More current but can be volatile
            - Used when insufficient quarters for TTM calculation

        Args:
            quarterly_data: List of quarterly entries (dicts or objects with fiscal_period,
                             fiscal_year, and revenue fields)
            logger: Logger instance for logging

        Returns:
            Revenue growth rate as decimal (e.g., 0.368 for 36.8%) or None if unavailable

        Example:
            >>> data = [
            ...     {"fiscal_period": "Q3", "fiscal_year": 2026, "total_revenue": 2074.5},
            ...     {"fiscal_period": "Q2", "fiscal_year": 2026, "total_revenue": 2006.1},
            ...     # ... more quarters
            ... ]
            >>> growth = GrowthCalculator.calculate_revenue_growth_ttm(quarterly_data=data)
            >>> print(f"Revenue growth: {growth * 100:.1f}%")
        """
        if not quarterly_data or len(quarterly_data) < 2:
            return None

        quarter_order = {"Q4": 4, "Q3": 3, "Q2": 2, "Q1": 1}
        quarterly_only = []

        for entry in quarterly_data:
            # Handle both dict and object formats
            if isinstance(entry, dict):
                period = entry.get("fiscal_period")
                fiscal_year = entry.get("fiscal_year", 0)
            else:
                period = getattr(entry, "fiscal_period", None)
                fiscal_year = getattr(entry, "fiscal_year", 0)

            if period and isinstance(period, str) and period.startswith("Q") and period not in ["QFY", "FY"]:
                quarterly_only.append((entry, fiscal_year, period))

        if not quarterly_only:
            return None

        # Sort by fiscal_year, then period (most recent first)
        quarterly_sorted = sorted(
            quarterly_only,
            key=lambda x: (x[1], quarter_order.get(x[2], 0)),
            reverse=True,
        )

        # Extract revenues with metadata
        def _get_revenue(entry: Any) -> float:
            """Extract revenue from dict or object."""
            if isinstance(entry, dict):
                rev = (
                    entry.get("total_revenue")
                    or entry.get("revenue")
                    or entry.get("financial_data", {}).get("revenues", 0)
                    or entry.get("financial_data", {}).get("total_revenue", 0)
                    or 0
                )
            else:
                financial_data = getattr(entry, "financial_data", {}) or {}
                rev = (
                    financial_data.get("revenues", 0)
                    or financial_data.get("total_revenue", 0)
                    or getattr(entry, "total_revenue", 0)
                    or getattr(entry, "revenue", 0)
                    or 0
                )
            return float(rev) if rev else 0

        quarters_with_revenue = []
        for entry, fy, period in quarterly_sorted[:12]:
            quarters_with_revenue.append(
                {
                    "revenue": _get_revenue(entry),
                    "fy": fy,
                    "period": period,
                    "entry": entry,
                }
            )

        # Method 1: TTM Revenue Growth (preferred - industry standard)
        # Need at least 8 quarters: 4 for current TTM, 4 for prior TTM
        if len(quarters_with_revenue) >= 8:
            current_ttm = sum(q["revenue"] for q in quarters_with_revenue[:4])
            prior_ttm = sum(q["revenue"] for q in quarters_with_revenue[4:8])

            if prior_ttm > 0:
                ttm_growth = (current_ttm - prior_ttm) / prior_ttm
                logger.info(
                    "Calculated TTM revenue growth: %.1f%% (TTM: $%.0fM vs $%.0fM)",
                    ttm_growth * 100,
                    current_ttm,
                    prior_ttm,
                )
                return ttm_growth

        # Method 2: Same-quarter YoY (fallback when TTM not available)
        if len(quarters_with_revenue) >= 2:
            current = quarters_with_revenue[0]
            current_period = current["period"]
            current_revenue = current["revenue"]

            # Find same quarter from prior year
            for q in quarters_with_revenue[1:]:
                if q["period"] == current_period and q["fy"] < current["fy"]:
                    prior_revenue = q["revenue"]
                    if prior_revenue > 0:
                        yoy_growth = (current_revenue - prior_revenue) / prior_revenue
                        logger.info(
                            "Calculated same-quarter YoY growth (fallback): %.1f%% (%s %s vs %s %s: $%.0fM vs $%.0fM)",
                            yoy_growth * 100,
                            current["fy"],
                            current_period,
                            q["fy"],
                            q["period"],
                            current_revenue,
                            prior_revenue,
                        )
                        return yoy_growth
                    break

        logger.warning("Could not calculate revenue growth: insufficient data")
        return None

    @staticmethod
    def calculate_growth_multiplier_pe(revenue_growth: Optional[float]) -> float:
        """Calculate P/E growth multiplier based on revenue growth.

        Growth multiplier formula: clamp(1.0 + revenue_growth, 0.8, 2.5)

        Args:
            revenue_growth: Revenue growth rate as decimal (e.g., 0.32 for 32%)

        Returns:
            Growth multiplier to apply to sector P/E multiple (0.8 to 2.5)

        Example:
            >>> GrowthCalculator.calculate_growth_multiplier_pe(0.32)
            1.32  # 32% growth → 1.32x multiplier
            >>> GrowthCalculator.calculate_growth_multiplier_pe(-0.10)
            0.9   # -10% growth → 0.9x multiplier
        """
        if revenue_growth is None:
            return 1.0
        return clamp(1.0 + float(revenue_growth), 0.8, 2.5)

    @staticmethod
    def calculate_growth_multiplier_ps(revenue_growth: Optional[float]) -> float:
        """Calculate P/S growth adjustment based on revenue growth.

        P/S growth adjustment follows the formula:
        - 0-10% growth: +0 to +2x adjustment
        - 10-30% growth: +2 to +6x adjustment
        - 30%+ growth: +6 to +8x adjustment

        Args:
            revenue_growth: Revenue growth rate as decimal (e.g., 0.32 for 32%)

        Returns:
            Growth adjustment to add to base P/S multiple

        Example:
            >>> GrowthCalculator.calculate_growth_multiplier_ps(0.32)
            6.0  # 32% growth → +6.0 adjustment
        """
        if revenue_growth is None or revenue_growth <= 0:
            return 0.0

        growth_pct = float(revenue_growth) * 100  # Convert to percentage

        if growth_pct <= 10:
            return float(clamp(growth_pct * 0.2, 0, 2))
        elif growth_pct <= 30:
            return float(2 + clamp((growth_pct - 10) * 0.2, 0, 4))
        else:
            return float(6 + clamp((growth_pct - 30) * 0.1, 0, 2))

    @staticmethod
    def calculate_ev_ebitda_growth_factor(revenue_growth: Optional[float]) -> float:
        """Calculate EV/EBITDA growth factor based on revenue growth.

        Growth factor scales from 1.0x at 0% revenue growth to 1.6x at 30% revenue growth.
        This accounts for high-growth companies deserving higher EV/EBITDA multiples.

        Formula:
            - 0% growth → 1.0x factor
            - 30% growth → 1.6x factor
            - Linear interpolation between

        Args:
            revenue_growth: Revenue growth rate as decimal (e.g., 0.32 for 32%)

        Returns:
            Growth factor to multiply by sector EV/EBITDA multiple (1.0 to 1.6)

        Example:
            >>> GrowthCalculator.calculate_ev_ebitda_growth_factor(0.30)
            1.6  # 30% growth → 1.6x factor
            >>> GrowthCalculator.calculate_ev_ebitda_growth_factor(0.15)
            1.3  # 15% growth → 1.3x factor
        """
        if revenue_growth is None or revenue_growth <= 0:
            return 1.0

        # Clamp growth at 30% for max factor of 1.6x
        clamped_growth = min(float(revenue_growth), 0.30)

        # Linear interpolation: 1.0x at 0% → 1.6x at 30%
        # factor = 1.0 + (growth / 0.30) * 0.6
        factor = 1.0 + (clamped_growth / 0.30) * 0.6

        return float(min(factor, 1.6))

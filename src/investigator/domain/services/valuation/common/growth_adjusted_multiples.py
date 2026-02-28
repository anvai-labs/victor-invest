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

"""Growth-adjusted valuation multiple calculations.

Provides standardized methods for calculating growth-adjusted valuation multiples:
- Growth-adjusted P/E multiple
- Growth-adjusted P/S multiple
- EV/EBITDA with growth factor

These methods use the GrowthCalculator and SectorMultiples utilities
to provide consistent calculations across both CLIs.
"""

import logging
from typing import Optional

from investigator.domain.services.valuation.common.growth_calculator import (
    GrowthCalculator,
)
from investigator.domain.services.valuation.common.sector_multiples import (
    SectorMultiples,
)

logger = logging.getLogger(__name__)


class GrowthAdjustedMultiples:
    """Calculate growth-adjusted valuation multiples.

    Methods:
        calculate_adjusted_pe: P/E with growth adjustment
        calculate_adjusted_ps: P/S with growth adjustment
        calculate_ev_ebitda_with_growth: EV/EBITDA multiple with growth factor

    Example:
        >>> adjusted_pe = GrowthAdjustedMultiples.calculate_adjusted_pe(
        ...     sector="Technology",
        ...     industry="Software - Application",
        ...     revenue_growth=0.32
        ... )
        >>> print(f"Growth-adjusted P/E: {adjusted_pe}x")
        23.76x
    """

    @staticmethod
    def calculate_adjusted_pe(
        *,
        sector: str,
        industry: Optional[str],
        revenue_growth: Optional[float],
        sector_pe_override: Optional[float] = None,
    ) -> float:
        """Calculate growth-adjusted P/E multiple.

        Formula:
            growth_multiplier = clamp(1.0 + revenue_growth, 0.8, 2.5)
            adjusted_pe = sector_pe * growth_multiplier

        Args:
            sector: Company sector (e.g., "Technology", "Healthcare")
            industry: Company industry for override check (optional)
            revenue_growth: TTM revenue growth rate as decimal (e.g., 0.32 for 32%)
            sector_pe_override: Override sector PE multiple (optional)

        Returns:
            Growth-adjusted P/E multiple

        Example:
            >>> pe = GrowthAdjustedMultiples.calculate_adjusted_pe(
            ...     sector="Technology",
            ...     industry="Internet Content & Information",
            ...     revenue_growth=0.32
            ... )
            >>> print(f"Growth-adjusted P/E: {pe:.2f}x")
            23.76x
        """
        # Get sector P/E multiple
        if sector_pe_override is not None:
            sector_pe = sector_pe_override
        else:
            sector_pe = SectorMultiples.get_multiple_with_override(sector=sector, industry=industry, metric="pe")

        # Calculate growth multiplier
        growth_multiplier = GrowthCalculator.calculate_growth_multiplier_pe(revenue_growth)

        adjusted_pe = sector_pe * growth_multiplier

        logger.debug(
            f"Growth-adjusted P/E: {sector_pe:.2f}x * {growth_multiplier:.2f}x = {adjusted_pe:.2f}x "
            f"(revenue_growth: {revenue_growth * 100:.1f}%)"
        )

        return adjusted_pe

    @staticmethod
    def calculate_adjusted_ps(
        *,
        sector: str,
        industry: Optional[str],
        base_multiple: Optional[float] = None,
        revenue_growth: Optional[float],
    ) -> float:
        """Calculate growth-adjusted P/S multiple.

        Formula:
            base_ps = base_multiple or sector_ps
            growth_adjustment = calculate_growth_multiplier_ps(revenue_growth)
            adjusted_ps = base_ps + growth_adjustment

        Args:
            sector: Company sector (e.g., "Technology", "Healthcare")
            industry: Company industry for override check (optional)
            base_multiple: Base P/S multiple (uses sector default if None)
            revenue_growth: TTM revenue growth rate as decimal

        Returns:
            Growth-adjusted P/S multiple

        Example:
            >>> ps = GrowthAdjustedMultiples.calculate_adjusted_ps(
            ...     sector="Technology",
            ...     revenue_growth=0.32
            ... )
            >>> print(f"Growth-adjusted P/S: {ps:.2f}x")
            11.0x
        """
        # Get sector P/S multiple if no base provided
        if base_multiple is None:
            base_multiple = SectorMultiples.get_multiple_with_override(sector=sector, industry=industry, metric="ps")

        # Calculate growth adjustment
        growth_adjustment = GrowthCalculator.calculate_growth_multiplier_ps(revenue_growth)

        adjusted_ps = base_multiple + growth_adjustment

        logger.debug(
            f"Growth-adjusted P/S: {base_multiple:.2f}x + {growth_adjustment:.2f}x = {adjusted_ps:.2f}x "
            f"(revenue_growth: {revenue_growth * 100:.1f}%)"
        )

        return adjusted_ps

    @staticmethod
    def calculate_ev_ebitda_with_growth(
        *,
        sector: str,
        industry: Optional[str],
        revenue_growth: Optional[float],
        leverage_adjusted_multiple: Optional[float] = None,
        max_multiple: float = 30.0,
    ) -> float:
        """Calculate EV/EBITDA multiple with growth adjustment factor.

        Formula:
            base_multiple = leverage_adjusted_multiple or sector_ev_ebitda
            growth_factor = calculate_ev_ebitda_growth_factor(revenue_growth)
            adjusted_multiple = base_multiple * growth_factor
            final_multiple = min(adjusted_multiple, max_multiple)

        The growth factor scales from 1.0x at 0% revenue growth to 1.6x at 30% revenue growth.

        Args:
            sector: Company sector (e.g., "Technology", "Healthcare")
            industry: Company industry for override check (optional)
            revenue_growth: TTM revenue growth rate as decimal
            leverage_adjusted_multiple: Pre-calculated leverage-adjusted multiple (optional)
            max_multiple: Maximum allowed multiple (default 30.0)

        Returns:
            Growth-adjusted EV/EBITDA multiple

        Example:
            >>> ev_ebitda = GrowthAdjustedMultiples.calculate_ev_ebitda_with_growth(
            ...     sector="Technology",
            ...     industry="Semiconductors",
            ...     revenue_growth=0.30
            ... )
            >>> print(f"EV/EBITDA with growth: {ev_ebitda:.2f}x")
            35.2x  # 22.0 * 1.6
        """
        # Get sector EV/EBITDA multiple if no leverage-adjusted provided
        if leverage_adjusted_multiple is None:
            base_multiple = SectorMultiples.get_multiple_with_override(
                sector=sector, industry=industry, metric="ev_ebitda"
            )
        else:
            base_multiple = leverage_adjusted_multiple

        # Calculate growth factor
        growth_factor = GrowthCalculator.calculate_ev_ebitda_growth_factor(revenue_growth)

        adjusted_multiple = base_multiple * growth_factor
        final_multiple = min(adjusted_multiple, max_multiple)

        logger.debug(
            f"EV/EBITDA with growth: {base_multiple:.2f}x * {growth_factor:.2f}x = {adjusted_multiple:.2f}x "
            f"(clamped to {final_multiple:.2f}x, revenue_growth: {revenue_growth * 100:.1f}%)"
        )

        return final_multiple

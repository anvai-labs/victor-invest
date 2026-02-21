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

"""Common valuation utilities shared between legacy CLI and victor_invest.

This module contains reusable calculation logic for:
- Revenue growth calculations (TTM-based)
- TTM metric calculations (EPS, revenue, EBITDA, FCF)
- Sector multiple lookups from config
- Growth-adjusted valuation multiples

These utilities eliminate code duplication between:
- Legacy CLI: src/investigator/domain/agents/fundamental/
- victor_invest CLI: victor_invest/tools/

Usage:
    from investigator.domain.services.valuation.common import (
        GrowthCalculator,
        TTMMetrics,
        SectorMultiples,
        GrowthAdjustedMultiples,
    )

Example:
    >>> # Calculate revenue growth
    >>> growth = GrowthCalculator.calculate_revenue_growth_ttm(
    ...     quarterly_data=quarterly_data
    ... )
    >>>
    >>> # Calculate TTM metrics
    >>> ttm = TTMMetrics.calculate_all_ttm_metrics(
    ...     quarterly_data=quarterly_data,
    ...     shares_outstanding=shares
    ... )
    >>>
    >>> # Get sector multiples
    >>> pe = SectorMultiples.get_sector_multiple("Technology", "pe")
    >>>
    >>> # Calculate growth-adjusted P/E
    >>> adjusted_pe = GrowthAdjustedMultiples.calculate_adjusted_pe(
    ...     sector="Technology",
    ...     industry="Software",
    ...     revenue_growth=growth
    ... )
"""

from investigator.domain.services.valuation.common.growth_adjusted_multiples import (
    GrowthAdjustedMultiples,
)
from investigator.domain.services.valuation.common.growth_calculator import (
    GrowthCalculator,
)
from investigator.domain.services.valuation.common.sector_multiples import (
    SectorMultiples,
)
from investigator.domain.services.valuation.common.ttm_calculator import (
    TTMMetrics,
)

__all__ = [
    "GrowthCalculator",
    "TTMMetrics",
    "SectorMultiples",
    "GrowthAdjustedMultiples",
]

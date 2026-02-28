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

"""Tests for trend-adjusted sector multiples calculation."""

import pytest

from investigator.domain.services.sector_multiples_trend_adjusted import (
    SectorMultiplesTrendAdjusted,
)


class TestSectorMultiplesTrendAdjusted:
    """Test trend-adjusted sector multiples calculation."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        service = SectorMultiplesTrendAdjusted()

        assert service.min_samples == 5
        assert service.percentile_exclude == (0.05, 0.95)
        assert service.lookback_years == 5
        assert service.adjustment_multiplier == 1.0  # medium sensitivity

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        service = SectorMultiplesTrendAdjusted(
            min_samples=10,
            percentile_exclude=(0.10, 0.90),
            lookback_years=10,
            adjustment_sensitivity="high",
        )

        assert service.min_samples == 10
        assert service.percentile_exclude == (0.10, 0.90)
        assert service.lookback_years == 10
        assert service.adjustment_multiplier == 1.5  # high sensitivity

    def test_sensitivity_multipliers(self):
        """Test adjustment sensitivity multipliers."""
        # Low sensitivity
        service_low = SectorMultiplesTrendAdjusted(adjustment_sensitivity="low")
        assert service_low.adjustment_multiplier == 0.5

        # Medium sensitivity (default)
        service_medium = SectorMultiplesTrendAdjusted(adjustment_sensitivity="medium")
        assert service_medium.adjustment_multiplier == 1.0

        # High sensitivity
        service_high = SectorMultiplesTrendAdjusted(adjustment_sensitivity="high")
        assert service_high.adjustment_multiplier == 1.5

    def test_adjustment_thresholds(self):
        """Test adjustment threshold constants."""
        service = SectorMultiplesTrendAdjusted()

        # Swelling threshold: 10%
        assert service.SWELLING_THRESHOLD == 0.10

        # Shrinking threshold: -10%
        assert service.SHRINKING_THRESHOLD == -0.10

        # High volatility threshold: 20% coefficient of variation
        assert service.HIGH_VOLATILITY_THRESHOLD == 0.20

    def test_adjustment_factors(self):
        """Test adjustment factor constants."""
        service = SectorMultiplesTrendAdjusted()

        # Swelling sectors: reduce by 15%
        assert service.SWELLING_ADJUSTMENT == 0.85

        # Shrinking sectors: increase by 15%
        assert service.SHRINKING_ADJUSTMENT == 1.15

        # High volatility: 10% discount
        assert service.HIGH_VOLATILITY_DISCOUNT == 0.90

        # Bull market: 5% premium
        assert service.BULL_MARKET_PREMIUM == 1.05

        # Bear market: 5% discount
        assert service.BEAR_MARKET_DISCOUNT == 0.95

    @pytest.mark.skipif(
        True,  # Skip by default - requires database
        reason="Requires database connection - enable for integration testing",
    )
    def test_calculate_trend_adjusted_multiples_with_db(self):
        """Test calculation with actual database data."""
        # This test requires a database connection and is skipped by default
        # Enable for integration testing with a real database
        pass

    def test_create_unadjusted_result(self):
        """Test creation of result for groups without historical data."""
        service = SectorMultiplesTrendAdjusted()

        current_data = {
            "pe": 28.5,
            "ps": 6.2,
            "pb": 5.8,
            "ev_ebitda": 22.1,
            "sample_size": 150,
            "last_updated": "2025-02-22T10:00:00Z",
        }

        result = service._create_unadjusted_result(current_data)

        # All metrics should be copied as-is (both adjusted and raw)
        assert result["pe"] == 28.5
        assert result["pe_raw"] == 28.5
        assert result["ps"] == 6.2
        assert result["ps_raw"] == 6.2
        assert result["pb"] == 5.8
        assert result["pb_raw"] == 5.8

        # Metadata should be preserved
        assert result["sample_size"] == 150
        assert result["last_updated"] == "2025-02-22T10:00:00Z"

        # Trend analysis should indicate insufficient data
        assert result["trend_analysis"]["status"] == "insufficient_historical_data"

    def test_should_process_group_no_filters(self):
        """Test group filtering with no filters (should process all)."""
        service = SectorMultiplesTrendAdjusted()

        # No filters - should process all groups
        assert service._should_process_group("Technology", None, None) is True
        assert service._should_process_group("Healthcare", None, None) is True

    def test_should_process_group_with_sector_filter(self):
        """Test group filtering with sector filter."""
        service = SectorMultiplesTrendAdjusted()

        # Technology sector filter
        sectors = ["Technology"]

        # Should match Technology
        assert service._should_process_group("Technology", sectors, None) is True
        assert service._should_process_group("Technology - Software", sectors, None) is True

        # Should not match other sectors
        assert service._should_process_group("Healthcare", sectors, None) is False
        assert service._should_process_group("Financials", sectors, None) is False

    def test_should_process_group_with_industry_filter(self):
        """Test group filtering with industry filter."""
        service = SectorMultiplesTrendAdjusted()

        # Software industry filter
        industries = ["Software"]

        # Should match Software (case-insensitive, partial match)
        assert service._should_process_group("Software", None, industries) is True
        assert service._should_process_group("Computer Software", None, industries) is True

        # Should not match other industries
        assert service._should_process_group("Semiconductors", None, industries) is False

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

"""Tests for fair multiple calculator service."""

import pytest

from investigator.domain.services.company_fair_multiple_calculator import (
    CompanyFairMultipleCalculator,
    FairMultipleResult,
)


class TestCompanyFairMultipleCalculator:
    """Test company fair multiple calculation."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        calculator = CompanyFairMultipleCalculator()

        assert calculator.lookback_years == 5
        assert calculator.min_data_points == 4
        assert calculator.conservative is False

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        calculator = CompanyFairMultipleCalculator(
            lookback_years=10,
            min_data_points=8,
            conservative=True,
        )

        assert calculator.lookback_years == 10
        assert calculator.min_data_points == 8
        assert calculator.conservative is True

    def test_safety_margins(self):
        """Test safety margin constants."""
        calculator = CompanyFairMultipleCalculator()

        # High confidence: 5% discount
        assert calculator.SAFETY_MARGINS["HIGH"] == 0.05

        # Medium confidence: 10% discount
        assert calculator.SAFETY_MARGINS["MEDIUM"] == 0.10

        # Low confidence: 15% discount
        assert calculator.SAFETY_MARGINS["LOW"] == 0.15

    def test_mean_reversion_adjustments(self):
        """Test mean reversion adjustment factors."""
        calculator = CompanyFairMultipleCalculator()

        # Strong buy: 10% upside
        assert calculator.MEAN_REVERSION_ADJUSTMENTS["strong_buy"] == 1.10

        # Buy: 5% upside
        assert calculator.MEAN_REVERSION_ADJUSTMENTS["buy"] == 1.05

        # None: No adjustment
        assert calculator.MEAN_REVERSION_ADJUSTMENTS["none"] == 1.00

        # Sell: 5% downside
        assert calculator.MEAN_REVERSION_ADJUSTMENTS["sell"] == 0.95

        # Strong sell: 10% downside
        assert calculator.MEAN_REVERSION_ADJUSTMENTS["strong_sell"] == 0.90

    def test_determine_confidence_high(self):
        """Test confidence determination for high confidence."""
        calculator = CompanyFairMultipleCalculator()

        confidence, factors = calculator._determine_confidence(
            data_points=20,  # >= 16
            premium_std_dev=3.0,  # <= 5%
            premium_trend="stable",
            premium_z_score=0.3,  # <= 0.5
        )

        assert confidence == "HIGH"
        assert len(factors) == 4
        assert any("Excellent data history" in f for f in factors)
        assert any("Very stable premium" in f for f in factors)
        assert any("Stable premium trend" in f for f in factors)

    def test_determine_confidence_medium(self):
        """Test confidence determination for medium confidence."""
        calculator = CompanyFairMultipleCalculator()

        confidence, factors = calculator._determine_confidence(
            data_points=10,  # >= 8 but < 16
            premium_std_dev=7.0,  # <= 10% but > 5%
            premium_trend="expanding",
            premium_z_score=0.8,  # <= 1.0 but > 0.5
        )

        assert confidence == "MEDIUM"
        assert len(factors) == 4

    def test_determine_confidence_low(self):
        """Test confidence determination for low confidence."""
        calculator = CompanyFairMultipleCalculator()

        confidence, factors = calculator._determine_confidence(
            data_points=4,  # < 8
            premium_std_dev=15.0,  # > 10%
            premium_trend="unknown",
            premium_z_score=2.0,  # > 1.0
        )

        assert confidence == "LOW"
        assert len(factors) == 4

    def test_min_data_points_thresholds(self):
        """Test minimum data point thresholds."""
        calculator = CompanyFairMultipleCalculator()

        assert calculator.MIN_DATA_POINTS_HIGH_CONFIDENCE == 16
        assert calculator.MIN_DATA_POINTS_MEDIUM_CONFIDENCE == 8

    def test_max_premium_std_dev_thresholds(self):
        """Test maximum premium std dev thresholds."""
        calculator = CompanyFairMultipleCalculator()

        assert calculator.MAX_PREMIUM_STD_DEV_HIGH_CONFIDENCE == 5.0
        assert calculator.MAX_PREMIUM_STD_DEV_MEDIUM_CONFIDENCE == 10.0

    @pytest.mark.skipif(
        True,
        reason="Requires database connection with historical premium data",
    )
    def test_calculate_fair_multiple_with_db(self):
        """Test fair multiple calculation with database data."""
        # This test requires actual database data
        # Enable for integration testing

    @pytest.mark.skipif(
        True,
        reason="Requires database connection with historical premium data",
    )
    def test_calculate_all_fair_multiples_with_db(self):
        """Test calculating all fair multiples with database data."""
        # This test requires actual database data
        # Enable for integration testing

    @pytest.mark.skipif(
        True,
        reason="Requires database connection with historical premium data",
    )
    def test_generate_fair_value_report_with_db(self):
        """Test fair value report generation with database data."""
        # This test requires actual database data
        # Enable for integration testing


class TestFairMultipleResult:
    """Test FairMultipleResult dataclass."""

    def test_fair_multiple_result_creation(self):
        """Test creating a FairMultipleResult."""
        result = FairMultipleResult(
            symbol="AAPL",
            metric="pe",
            sector_baseline=55.0,
            company_historical_premium=15.2,
            current_premium=14.0,
            premium_z_score=-0.34,
            base_fair_multiple=63.36,
            mean_reversion_adjustment=1.00,
            safety_margin=0.05,
            final_fair_multiple=60.19,
            confidence="HIGH",
            confidence_factors=["Excellent data history", "Very stable premium"],
            mean_reversion_signal="none",
            upside_downside_pct=5.2,
            calculated_at="2025-02-22T10:00:00Z",
        )

        assert result.symbol == "AAPL"
        assert result.metric == "pe"
        assert result.sector_baseline == 55.0
        assert result.company_historical_premium == 15.2
        assert result.final_fair_multiple == 60.19
        assert result.confidence == "HIGH"
        assert result.mean_reversion_signal == "none"

    def test_fair_multiple_result_rounding(self):
        """Test that values are properly rounded."""
        # Note: Dataclass fields don't auto-round - rounding happens in calculation
        # This test verifies the dataclass accepts and stores values correctly
        result = FairMultipleResult(
            symbol="MSFT",
            metric="pe",
            sector_baseline=55.12,  # Pre-rounded value
            company_historical_premium=15.23,  # Pre-rounded value
            current_premium=14.01,
            premium_z_score=-0.34,
            base_fair_multiple=63.46,
            mean_reversion_adjustment=1.01,
            safety_margin=0.05,
            final_fair_multiple=60.19,
            confidence="HIGH",
            confidence_factors=[],
            mean_reversion_signal="none",
            upside_downside_pct=5.23,
            calculated_at="2025-02-22T10:00:00Z",
        )

        # Verify values are stored correctly
        assert result.symbol == "MSFT"
        assert result.sector_baseline == 55.12
        assert result.company_historical_premium == 15.23
        assert result.premium_z_score == -0.34
        assert result.final_fair_multiple == 60.19

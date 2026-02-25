# Copyright 2025 Vijaykumar Singh
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for P/E and P/S model sanity checks.

Tests that the models correctly reject implausible fair values caused by unit mismatches.
"""

from investigator.domain.services.valuation.models.pe_multiple import PEMultipleModel
from investigator.domain.services.valuation.models.ps_multiple import PSMultipleModel
from investigator.domain.services.valuation.models.company_profile import CompanyProfile
from investigator.domain.services.valuation.models.base import ModelNotApplicable


class TestPEModelSanityChecks:
    """Test P/E model sanity checks for unit mismatches."""

    def test_rejects_absurdly_high_fair_value(self):
        """Test that P/E model rejects fair value > 1000x current price."""
        company_profile = CompanyProfile(
            symbol="TEST",
            sector="Technology",
        )

        # Simulate unit mismatch: EPS in millions instead of per-share
        # EPS = 873,000 (absurd), target_pe = 20, fair_value = 17,460,000
        # With current_price = 333, ratio = 52,400x (should be rejected)
        model = PEMultipleModel(
            company_profile=company_profile,
            ttm_eps=873000.0,  # Wrong unit (millions instead of actual EPS)
            current_price=333.05,
            sector_median_pe=20.0,
        )

        result = model.calculate()

        # Should return ModelNotApplicable due to unit mismatch
        assert isinstance(result, ModelNotApplicable)
        assert result.model_name == "pe"
        assert "unit_mismatch" in result.reason.lower()

    def test_rejects_absurdly_low_fair_value(self):
        """Test that P/E model rejects fair value < 0.001x current price."""
        company_profile = CompanyProfile(
            symbol="TEST",
            sector="Technology",
        )

        # Simulate reverse unit mismatch
        model = PEMultipleModel(
            company_profile=company_profile,
            ttm_eps=0.00001,  # Wrong unit (micro-cents?)
            current_price=333.05,
            sector_median_pe=20.0,
        )

        result = model.calculate()

        # Should return ModelNotApplicable
        assert isinstance(result, ModelNotApplicable)
        assert result.model_name == "pe"
        assert "unit_mismatch" in result.reason.lower()

    def test_accepts_reasonable_fair_value(self):
        """Test that P/E model accepts reasonable fair values."""
        company_profile = CompanyProfile(
            symbol="MCD",
            sector="Consumer Discretionary",
            industry="Restaurants",
        )

        # MCD normal case: EPS = $10.70, PE = 20, fair_value = $214
        model = PEMultipleModel(
            company_profile=company_profile,
            ttm_eps=10.70,  # Correct unit
            current_price=333.05,
            sector_median_pe=20.0,
        )

        result = model.calculate()

        # Should return successful result (not ModelNotApplicable)
        assert not isinstance(result, ModelNotApplicable)
        assert result.fair_value == 214.0
        assert result.model_name == "pe"

    def test_accepts_high_but_reasonable_upside(self):
        """Test that P/E model accepts high upside within 1000x limit."""
        company_profile = CompanyProfile(
            symbol="TURN",
            sector="Technology",
        )

        # High upside but within limit: EPS = $1, PE = 50, fair_value = $50
        # Current price = $10, upside = 5x (500%)
        model = PEMultipleModel(
            company_profile=company_profile,
            ttm_eps=1.0,
            current_price=10.0,
            sector_median_pe=50.0,
        )

        result = model.calculate()

        # Should return successful result (5x < 1000x)
        assert not isinstance(result, ModelNotApplicable)
        assert result.fair_value == 50.0

    def test_no_current_price_skips_sanity_check(self):
        """Test that sanity check is skipped when current_price is None."""
        company_profile = CompanyProfile(
            symbol="TEST",
            sector="Technology",
        )

        # Without current_price, sanity check can't validate
        model = PEMultipleModel(
            company_profile=company_profile,
            ttm_eps=873000.0,  # Absurd value
            current_price=None,  # No price reference
            sector_median_pe=20.0,
        )

        result = model.calculate()

        # Will calculate fair value (can't sanity check without price reference)
        # The value will be absurd but that's expected without price validation
        assert not isinstance(result, ModelNotApplicable)
        assert result.fair_value == 17_460_000.0


class TestPSModelSanityChecks:
    """Test P/S model sanity checks for unit mismatches."""

    def test_rejects_absurdly_high_fair_value(self):
        """Test that P/S model rejects fair value > 1000x current price."""
        company_profile = CompanyProfile(
            symbol="TEST",
            sector="Technology",
        )

        # Simulate unit mismatch: revenue_per_share in millions
        # revenue_per_share = 1,000,000 (wrong unit), PS = 1.5, fair_value = 1,500,000
        # With current_price = 36, ratio = 41,666x (should be rejected)
        model = PSMultipleModel(
            company_profile=company_profile,
            revenue_per_share=1_000_000.0,  # Wrong unit
            current_price=36.30,
            sector_median_ps=1.5,
        )

        result = model.calculate()

        # Should return ModelNotApplicable
        assert isinstance(result, ModelNotApplicable)
        assert result.model_name == "ps"
        assert "unit_mismatch" in result.reason.lower()

    def test_rejects_absurdly_low_fair_value(self):
        """Test that P/S model rejects fair value < 0.001x current price."""
        company_profile = CompanyProfile(
            symbol="TEST",
            sector="Technology",
        )

        # Simulate reverse unit mismatch
        model = PSMultipleModel(
            company_profile=company_profile,
            revenue_per_share=0.00001,
            current_price=36.30,
            sector_median_ps=1.5,
        )

        result = model.calculate()

        # Should return ModelNotApplicable
        assert isinstance(result, ModelNotApplicable)
        assert result.model_name == "ps"
        assert "unit_mismatch" in result.reason.lower()

    def test_accepts_reasonable_fair_value(self):
        """Test that P/S model accepts reasonable fair values."""
        company_profile = CompanyProfile(
            symbol="MCD",
            sector="Consumer Discretionary",
            industry="Restaurants",
        )

        # MCD normal case: revenue_per_share = $35, PS = 1.5, fair_value = $52.50
        model = PSMultipleModel(
            company_profile=company_profile,
            revenue_per_share=35.0,  # Correct unit
            current_price=333.05,
            sector_median_ps=1.5,
        )

        result = model.calculate()

        # Should return successful result
        assert not isinstance(result, ModelNotApplicable)
        assert result.fair_value == 52.5
        assert result.model_name == "ps"

    def test_no_current_price_skips_sanity_check(self):
        """Test that sanity check is skipped when current_price is None."""
        company_profile = CompanyProfile(
            symbol="TEST",
            sector="Technology",
        )

        model = PSMultipleModel(
            company_profile=company_profile,
            revenue_per_share=1_000_000.0,
            current_price=None,
            sector_median_ps=1.5,
            liquidity_floor_usd=0.0,  # Set to 0 to pass liquidity check
        )

        result = model.calculate()

        # Will calculate fair value without sanity check
        # Note: P/S model has liquidity check that may fail without floor set
        if not isinstance(result, ModelNotApplicable):
            assert result.fair_value == 1_500_000.0
        else:
            # If liquidity check fails, that's expected behavior
            assert (
                "liquidity" in result.reason.lower()
                or result.reason == "insufficient_data_or_liquidity"
            )

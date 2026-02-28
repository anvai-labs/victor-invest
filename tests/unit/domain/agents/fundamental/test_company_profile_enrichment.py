"""Unit tests for company profile enrichment helpers."""

from unittest.mock import MagicMock

from investigator.domain.agents.fundamental.company_profile_enrichment import (
    enrich_company_profile,
)
from investigator.domain.services.valuation.models import (
    CompanyArchetype,
    CompanyProfile,
    DataQualityFlag,
)


def test_enrich_company_profile_sets_core_fields_and_high_growth_archetype():
    profile = CompanyProfile(symbol="AAPL", sector="Technology", industry="Software")
    company_data = {
        "ttm_metrics": {},
        "rule_of_40_score": 45.0,
        "quarterly_data": [{} for _ in range(8)],
    }
    ratios = {"revenue_growth": 0.25, "gross_margin": 0.45}
    financials = {
        "free_cash_flow": 100.0,
        "revenues": 500.0,
        "net_income": 80.0,
        "operating_income": 120.0,
        "total_debt": 200.0,
        "cash": 50.0,
    }
    market_data = {"current_price": 100.0, "shares_outstanding": 10.0}
    data_quality = {}

    enrich_company_profile(
        profile=profile,
        symbol="AAPL",
        sector="Technology",
        company_data=company_data,
        ratios=ratios,
        financials=financials,
        market_data=market_data,
        data_quality=data_quality,
        logger=MagicMock(),
    )

    assert profile.has_positive_fcf is True
    assert profile.has_positive_earnings is True
    assert profile.free_cash_flow == 100.0
    assert profile.revenue_growth_yoy == 0.25
    assert profile.primary_archetype == CompanyArchetype.HIGH_GROWTH


def test_enrich_company_profile_calculates_revenue_growth_from_quarters():
    profile = CompanyProfile(symbol="MSFT", sector="Technology", industry="Software")
    company_data = {
        "quarterly_data": [
            {"financial_data": {"revenues": 140.0}},
            {"financial_data": {"revenues": 130.0}},
            {"financial_data": {"revenues": 120.0}},
            {"financial_data": {"revenues": 110.0}},
            {"financial_data": {"revenues": 100.0}},
        ]
    }

    enrich_company_profile(
        profile=profile,
        symbol="MSFT",
        sector="Technology",
        company_data=company_data,
        ratios={},
        financials={},
        market_data={},
        data_quality={},
        logger=MagicMock(),
    )

    assert profile.revenue_growth_yoy == 0.4


def test_enrich_company_profile_sets_quality_flags_and_financial_archetype():
    profile = CompanyProfile(symbol="JPM", sector="Financial Services", industry="Banks")
    company_data = {
        "quarterly_data": [{} for _ in range(4)],
        "rule_of_40_score": 10.0,
    }
    market_data = {"current_price": 100.0, "average_daily_volume": 10_000}
    data_quality = {
        "data_quality_score": 80,
        "consistency_issues": True,
        "stale_data": True,
    }

    enrich_company_profile(
        profile=profile,
        symbol="JPM",
        sector="Financial Services",
        company_data=company_data,
        ratios={},
        financials={},
        market_data=market_data,
        data_quality=data_quality,
        logger=MagicMock(),
    )

    assert profile.primary_archetype == CompanyArchetype.FINANCIAL
    assert profile.has_flag(DataQualityFlag.LOW_LIQUIDITY)
    assert profile.has_flag(DataQualityFlag.MISSING_QUARTERS)
    assert profile.has_flag(DataQualityFlag.OUTLIER_DETECTED)
    assert profile.has_flag(DataQualityFlag.STALE_REFERENCE_DATA)


def test_enrich_company_profile_prioritizes_diluted_shares_for_dual_class_companies():
    """Test that shares_outstanding_diluted is prioritized for dual-class companies like GOOGL.

    This is a regression test for the bug where GOOGL DCF valuation produced $2,291.66
    instead of ~$75 because it used 662M Class A shares instead of 13B total diluted shares.
    """
    profile = CompanyProfile(symbol="GOOGL", sector="Technology", industry="Internet")
    company_data = {
        "quarterly_data": [{} for _ in range(4)],
        "rule_of_40_score": 35.0,
    }

    # Simulate GOOGL's dual-class share structure:
    # - shares_outstanding: 662M (Class A only)
    # - shares_outstanding_diluted: 13B (all classes)
    financials = {
        "shares_outstanding": 662_121_000,  # Class A only (WRONG for valuation)
        "shares_outstanding_diluted": 13_078_000_000,  # Total diluted (CORRECT)
        "revenues": 300_000_000_000,
        "net_income": 80_000_000_000,
    }
    market_data = {"current_price": 150.0, "average_daily_volume": 20_000_000}

    enrich_company_profile(
        profile=profile,
        symbol="GOOGL",
        sector="Technology",
        company_data=company_data,
        ratios={},
        financials=financials,
        market_data=market_data,
        data_quality={},
        logger=MagicMock(),
    )

    # Should use diluted shares, not basic shares
    assert profile.shares_outstanding == 13_078_000_000
    assert profile.shares_outstanding != 662_121_000


def test_enrich_company_profile_falls_back_to_basic_shares_when_diluted_unavailable():
    """Test that basic shares_outstanding is used when diluted is not available."""
    profile = CompanyProfile(symbol="AAPL", sector="Technology", industry="Consumer Electronics")
    company_data = {
        "quarterly_data": [{} for _ in range(4)],
        "rule_of_40_score": 40.0,
    }

    # Single-class company without diluted shares data
    financials = {
        "shares_outstanding": 15_000_000_000,  # Basic shares
        # No shares_outstanding_diluted
        "revenues": 400_000_000_000,
        "net_income": 100_000_000_000,
    }
    market_data = {"current_price": 180.0, "average_daily_volume": 50_000_000}

    enrich_company_profile(
        profile=profile,
        symbol="AAPL",
        sector="Technology",
        company_data=company_data,
        ratios={},
        financials=financials,
        market_data=market_data,
        data_quality={},
        logger=MagicMock(),
    )

    # Should fall back to basic shares when diluted is unavailable
    assert profile.shares_outstanding == 15_000_000_000

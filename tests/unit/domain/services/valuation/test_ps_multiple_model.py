"""Tests for P/S model multiple selection behavior."""

from investigator.domain.services.valuation.models.company_profile import CompanyProfile
from investigator.domain.services.valuation.models.ps_multiple import PSMultipleModel


def test_ps_multiple_prefers_sector_industry_specific_base():
    profile = CompanyProfile(
        symbol="STX",
        sector="Technology",
        industry="Electronic Components",
    )

    model = PSMultipleModel(
        company_profile=profile,
        revenue_per_share=10.0,
        current_price=100.0,
        sector_median_ps=6.0,
    )
    result = model.calculate()

    assert result.assumptions["target_ps"] == 3.0
    assert result.fair_value == 30.0

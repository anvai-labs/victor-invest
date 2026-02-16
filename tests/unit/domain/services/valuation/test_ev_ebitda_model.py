from investigator.domain.services.valuation.models import EVEBITDAModel
from investigator.domain.services.valuation.models.base import (
    ModelNotApplicable,
    ValuationModelResult,
)
from investigator.domain.services.valuation.models.company_profile import CompanyProfile


def test_ev_ebitda_not_applicable_for_financial_sector() -> None:
    profile = CompanyProfile(
        symbol="JPM",
        sector="Financials",
        shares_outstanding=1_000_000_000,
        total_debt=100_000_000_000,
        cash=20_000_000_000,
        current_price=300.0,
    )

    model = EVEBITDAModel(
        company_profile=profile,
        ttm_ebitda=20_000_000_000,
        enterprise_value=500_000_000_000,
        sector_median_ev_ebitda=12.0,
        leverage_adjusted_multiple=10.0,
    )

    result = model.calculate()
    assert isinstance(result, ModelNotApplicable)
    assert result.reason == "unsupported_financial_sector"


def test_ev_ebitda_returns_fair_value_for_supported_sector() -> None:
    profile = CompanyProfile(
        symbol="MSFT",
        sector="Technology",
        shares_outstanding=10_000_000,
        total_debt=100_000_000,
        cash=20_000_000,
        current_price=300.0,
    )

    model = EVEBITDAModel(
        company_profile=profile,
        ttm_ebitda=100_000_000,
        enterprise_value=1_200_000_000,
        sector_median_ev_ebitda=10.0,
        leverage_adjusted_multiple=9.0,
    )

    result = model.calculate()
    assert isinstance(result, ValuationModelResult)
    assert result.fair_value is not None
    assert result.fair_value > 0

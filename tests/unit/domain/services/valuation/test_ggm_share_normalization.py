from types import SimpleNamespace

from investigator.domain.services.valuation.ggm import GordonGrowthModel


def test_get_shares_outstanding_scales_profile_millions_values():
    model = GordonGrowthModel(
        symbol="TEST",
        quarterly_metrics=[],
        multi_year_data=[],
        db_manager=None,
        company_profile=SimpleNamespace(shares_outstanding=715.9),
    )
    assert model._get_shares_outstanding() == 715_900_000.0


def test_get_shares_outstanding_scales_quarterly_millions_values():
    model = GordonGrowthModel(
        symbol="TEST",
        quarterly_metrics=[{"shares_outstanding": 812.4}],
        multi_year_data=[],
        db_manager=None,
        company_profile=None,
    )
    assert model._get_shares_outstanding() == 812_400_000.0

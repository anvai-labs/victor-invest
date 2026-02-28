from investigator.domain.services.valuation.dcf import DCFValuation


def _build_dcf(monkeypatch, quarterly_metrics):
    monkeypatch.setattr(
        DCFValuation, "_load_dcf_config", lambda self: {"wacc_parameters": {}}
    )
    monkeypatch.setattr(
        DCFValuation, "_get_company_sector", lambda self: "Consumer Discretionary"
    )
    monkeypatch.setattr(
        DCFValuation,
        "_get_sector_parameters",
        lambda self: {"terminal_growth_rate": 0.03, "projection_years": 7},
    )
    return DCFValuation(
        symbol="TEST",
        quarterly_metrics=quarterly_metrics,
        multi_year_data=[],
        db_manager=None,
    )


def test_get_shares_outstanding_scales_millions_encoded_values(monkeypatch):
    dcf = _build_dcf(monkeypatch, quarterly_metrics=[{"shares_outstanding": 715.9}])
    assert dcf._get_shares_outstanding() == 715_900_000.0


def test_get_shares_outstanding_keeps_normal_values(monkeypatch):
    dcf = _build_dcf(
        monkeypatch, quarterly_metrics=[{"shares_outstanding": 3_526_000_000}]
    )
    assert dcf._get_shares_outstanding() == 3_526_000_000.0

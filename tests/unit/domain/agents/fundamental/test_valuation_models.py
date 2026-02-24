"""Unit tests for relative valuation model helper."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from investigator.domain.agents.fundamental.valuation_models import (
    calculate_relative_valuation_models,
)


def _profile():
    return SimpleNamespace(
        sector="Technology",
        industry="Software",
        earnings_quality_score=0.8,
        net_debt_to_ebitda=2.5,
        shares_outstanding=100,
        book_value_per_share=20.0,
    )


def _build_model_mock(result):
    model = MagicMock()
    model.calculate.return_value = result
    return model


@patch(
    "investigator.domain.agents.fundamental.valuation_models.normalize_model_output",
    side_effect=lambda payload: payload,
)
@patch("investigator.domain.agents.fundamental.valuation_models.PBMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PSMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.EVEBITDAModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PEMultipleModel")
def test_calculate_relative_valuation_models_returns_all_models(
    pe_cls, ev_cls, ps_cls, pb_cls, _normalize
):
    pe_cls.return_value = _build_model_mock(
        {"model": "pe", "fair_value_per_share": 110}
    )
    ev_cls.return_value = _build_model_mock(
        {"model": "ev_ebitda", "fair_value_per_share": 120}
    )
    ps_cls.return_value = _build_model_mock({"model": "ps", "fair_value_per_share": 90})
    pb_cls.return_value = _build_model_mock({"model": "pb", "fair_value_per_share": 95})

    result = calculate_relative_valuation_models(
        symbol="AAPL",
        company_profile=_profile(),
        company_data={"sector_metrics": {}},
        ratios={"eps": 5.0, "current_price": 100.0},
        financials={"revenues": 10_000, "ebitda": 2_000},
        market_data={"current_price": 100.0, "market_cap": 100_000, "cash": 10_000},
        config=SimpleNamespace(valuation={}),
        sector_specific_result=None,
        lookup_sector_multiple=lambda _sector, multiple: {
            "pe": 20,
            "ev_ebitda": 12,
            "ps": 4,
            "pb": 3,
        }.get(multiple),
        calculate_enterprise_value=lambda _market, _financials: 120_000,
        logger=MagicMock(),
    )

    assert result["pe"]["model"] == "pe"
    assert result["ev_ebitda"]["model"] == "ev_ebitda"
    assert result["ps"]["model"] == "ps"
    assert result["pb"]["model"] == "pb"
    pe_cls.assert_called_once()
    ev_cls.assert_called_once()
    ps_cls.assert_called_once()
    pb_cls.assert_called_once()


@patch(
    "investigator.domain.agents.fundamental.valuation_models.normalize_model_output",
    side_effect=lambda payload: payload,
)
@patch("investigator.domain.agents.fundamental.valuation_models.PBMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PSMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.EVEBITDAModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PEMultipleModel")
def test_calculate_relative_valuation_models_applies_insurance_pb_override(
    pe_cls, ev_cls, ps_cls, pb_cls, _normalize
):
    pe_cls.return_value = _build_model_mock(
        {"model": "pe", "fair_value_per_share": 110}
    )
    ev_cls.return_value = _build_model_mock(
        {"model": "ev_ebitda", "fair_value_per_share": 120}
    )
    ps_cls.return_value = _build_model_mock({"model": "ps", "fair_value_per_share": 90})
    pb_cls.return_value = _build_model_mock({"model": "pb", "fair_value_per_share": 95})

    sector_specific = {
        "method": "Insurance P/BV",
        "fair_value": 130.0,
        "confidence": "high",
        "upside_percent": 0.3,
        "current_price": 100.0,
    }

    result = calculate_relative_valuation_models(
        symbol="AFL",
        company_profile=_profile(),
        company_data={"sector_metrics": {}},
        ratios={"eps": 5.0, "current_price": 100.0},
        financials={"revenues": 10_000, "ebitda": 2_000},
        market_data={"current_price": 100.0, "market_cap": 100_000, "cash": 10_000},
        config=SimpleNamespace(valuation={}),
        sector_specific_result=sector_specific,
        lookup_sector_multiple=lambda _sector, multiple: {
            "pe": 20,
            "ev_ebitda": 12,
            "ps": 4,
            "pb": 3,
        }.get(multiple),
        calculate_enterprise_value=lambda _market, _financials: 120_000,
        logger=MagicMock(),
    )

    assert result["pb"]["fair_value_per_share"] == 130.0
    assert result["pb"]["confidence_score"] == 0.9


@patch(
    "investigator.domain.agents.fundamental.valuation_models.normalize_model_output",
    side_effect=lambda payload: payload,
)
@patch("investigator.domain.agents.fundamental.valuation_models.PBMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PSMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.EVEBITDAModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PEMultipleModel")
def test_calculate_relative_valuation_models_prefers_ttm_ratio_inputs(
    pe_cls, ev_cls, ps_cls, pb_cls, _normalize
):
    pe_cls.return_value = _build_model_mock(
        {"model": "pe", "fair_value_per_share": 110}
    )
    ev_cls.return_value = _build_model_mock(
        {"model": "ev_ebitda", "fair_value_per_share": 120}
    )
    ps_cls.return_value = _build_model_mock({"model": "ps", "fair_value_per_share": 90})
    pb_cls.return_value = _build_model_mock({"model": "pb", "fair_value_per_share": 95})

    calculate_relative_valuation_models(
        symbol="AAPL",
        company_profile=_profile(),
        company_data={"sector_metrics": {}},
        ratios={
            "eps": 5.0,
            "current_price": 100.0,
            "ttm_revenue": 4_000.0,
            "ttm_ebitda": 3_500.0,
            "revenue_per_share": 40.0,
        },
        financials={"revenues": 1_000.0, "ebitda": 2_000.0},
        market_data={"current_price": 100.0, "market_cap": 100_000, "cash": 10_000},
        config=SimpleNamespace(valuation={}),
        sector_specific_result=None,
        lookup_sector_multiple=lambda _sector, multiple: {
            "pe": 20,
            "ev_ebitda": 12,
            "ps": 4,
            "pb": 3,
        }.get(multiple),
        calculate_enterprise_value=lambda _market, _financials: 120_000,
        logger=MagicMock(),
    )

    assert ev_cls.call_args.kwargs["ttm_ebitda"] == 3_500.0
    assert ps_cls.call_args.kwargs["revenue_per_share"] == 40.0


@patch(
    "investigator.domain.agents.fundamental.valuation_models.normalize_model_output",
    side_effect=lambda payload: payload,
)
@patch("investigator.domain.agents.fundamental.valuation_models.PBMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PSMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.EVEBITDAModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PEMultipleModel")
def test_calculate_relative_valuation_models_uses_revenue_growth_for_pe_adjustment(
    pe_cls, ev_cls, ps_cls, pb_cls, _normalize
):
    pe_cls.return_value = _build_model_mock(
        {"model": "pe", "fair_value_per_share": 110}
    )
    ev_cls.return_value = _build_model_mock(
        {"model": "ev_ebitda", "fair_value_per_share": 120}
    )
    ps_cls.return_value = _build_model_mock({"model": "ps", "fair_value_per_share": 90})
    pb_cls.return_value = _build_model_mock({"model": "pb", "fair_value_per_share": 95})

    calculate_relative_valuation_models(
        symbol="AAPL",
        company_profile=_profile(),
        company_data={"sector_metrics": {}},
        ratios={
            "eps": 5.0,
            "current_price": 100.0,
            "peg_ratio": 3.0,
            "revenue_growth_yoy": 0.30,
        },
        financials={"revenues": 1_000.0, "ebitda": 2_000.0},
        market_data={"current_price": 100.0, "market_cap": 100_000, "cash": 10_000},
        config=SimpleNamespace(valuation={}),
        sector_specific_result=None,
        lookup_sector_multiple=lambda _sector, multiple: {
            "pe": 20,
            "ev_ebitda": 12,
            "ps": 4,
            "pb": 3,
        }.get(multiple),
        calculate_enterprise_value=lambda _market, _financials: 120_000,
        logger=MagicMock(),
    )

    assert pe_cls.call_args.kwargs["growth_adjusted_pe"] == 26.0


@patch(
    "investigator.domain.agents.fundamental.valuation_models.normalize_model_output",
    side_effect=lambda payload: payload,
)
@patch("investigator.domain.agents.fundamental.valuation_models.PBMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PSMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.EVEBITDAModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PEMultipleModel")
def test_calculate_relative_valuation_models_forward_1y_scales_denominators(
    pe_cls, ev_cls, ps_cls, pb_cls, _normalize
):
    pe_cls.return_value = _build_model_mock(
        {"model": "pe", "fair_value_per_share": 110}
    )
    ev_cls.return_value = _build_model_mock(
        {"model": "ev_ebitda", "fair_value_per_share": 120}
    )
    ps_cls.return_value = _build_model_mock({"model": "ps", "fair_value_per_share": 90})
    pb_cls.return_value = _build_model_mock({"model": "pb", "fair_value_per_share": 95})

    result = calculate_relative_valuation_models(
        symbol="AAPL",
        company_profile=_profile(),
        company_data={"sector_metrics": {}},
        ratios={
            "eps": 5.0,
            "ttm_ebitda": 300.0,
            "ttm_revenue": 4_000.0,
            "revenue_per_share": 40.0,
            "revenue_growth_yoy": 0.20,
            "earnings_growth_yoy": 0.40,
            "current_price": 100.0,
        },
        financials={"revenues": 1_000.0, "ebitda": 2_000.0},
        market_data={"current_price": 100.0, "market_cap": 100_000, "cash": 10_000},
        config=SimpleNamespace(valuation={}),
        sector_specific_result=None,
        lookup_sector_multiple=lambda _sector, multiple: {
            "pe": 20,
            "ev_ebitda": 12,
            "ps": 4,
            "pb": 3,
        }.get(multiple),
        calculate_enterprise_value=lambda _market, _financials: 120_000,
        logger=MagicMock(),
        valuation_basis="forward",
        forward_horizon="1y",
    )

    assert pe_cls.call_args.kwargs["ttm_eps"] == 7.0
    assert ev_cls.call_args.kwargs["ttm_ebitda"] == 420.0
    assert ps_cls.call_args.kwargs["revenue_per_share"] == pytest.approx(48.0)
    assert result["pe"]["metadata"]["valuation_basis"] == "forward"
    assert result["pe"]["metadata"]["forward_horizon"] == "1y"


@patch(
    "investigator.domain.agents.fundamental.valuation_models.normalize_model_output",
    side_effect=lambda payload: payload,
)
@patch("investigator.domain.agents.fundamental.valuation_models.PBMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PSMultipleModel")
@patch("investigator.domain.agents.fundamental.valuation_models.EVEBITDAModel")
@patch("investigator.domain.agents.fundamental.valuation_models.PEMultipleModel")
def test_calculate_relative_valuation_models_forward_2q_uses_partial_growth_scaling(
    pe_cls, ev_cls, ps_cls, pb_cls, _normalize
):
    pe_cls.return_value = _build_model_mock(
        {"model": "pe", "fair_value_per_share": 110}
    )
    ev_cls.return_value = _build_model_mock(
        {"model": "ev_ebitda", "fair_value_per_share": 120}
    )
    ps_cls.return_value = _build_model_mock({"model": "ps", "fair_value_per_share": 90})
    pb_cls.return_value = _build_model_mock({"model": "pb", "fair_value_per_share": 95})

    calculate_relative_valuation_models(
        symbol="AAPL",
        company_profile=_profile(),
        company_data={"sector_metrics": {}},
        ratios={
            "eps": 5.0,
            "ttm_ebitda": 300.0,
            "ttm_revenue": 4_000.0,
            "revenue_per_share": 40.0,
            "revenue_growth_yoy": 0.20,
            "current_price": 100.0,
        },
        financials={"revenues": 1_000.0, "ebitda": 2_000.0},
        market_data={"current_price": 100.0, "market_cap": 100_000, "cash": 10_000},
        config=SimpleNamespace(valuation={}),
        sector_specific_result=None,
        lookup_sector_multiple=lambda _sector, multiple: {
            "pe": 20,
            "ev_ebitda": 12,
            "ps": 4,
            "pb": 3,
        }.get(multiple),
        calculate_enterprise_value=lambda _market, _financials: 120_000,
        logger=MagicMock(),
        valuation_basis="forward",
        forward_horizon="2q",
    )

    growth_factor = (1.2) ** 0.5
    assert pe_cls.call_args.kwargs["ttm_eps"] == pytest.approx(5.0 * growth_factor)
    assert ev_cls.call_args.kwargs["ttm_ebitda"] == pytest.approx(300.0 * growth_factor)
    assert ps_cls.call_args.kwargs["revenue_per_share"] == pytest.approx(
        40.0 * growth_factor
    )

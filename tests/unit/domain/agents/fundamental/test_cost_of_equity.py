"""Unit tests for CAPM cost-of-equity helper."""

from unittest.mock import MagicMock

import pytest

from investigator.domain.agents.fundamental.cost_of_equity import (
    calculate_cost_of_equity_capm,
)


def test_calculate_cost_of_equity_capm_uses_market_beta_and_fred_rate():
    logger = MagicMock()
    value = calculate_cost_of_equity_capm(
        symbol="AAPL",
        get_stock_info=lambda _symbol: {"beta": 1.2},
        get_latest_indicators=lambda _series: {"DGS10": {"value": 4.0}},
        logger=logger,
    )
    assert value == pytest.approx(0.124)
    logger.info.assert_called_once()


def test_calculate_cost_of_equity_capm_applies_beta_floor_and_default_rf():
    logger = MagicMock()
    value = calculate_cost_of_equity_capm(
        symbol="MSFT",
        get_stock_info=lambda _symbol: {"beta": 0.2},
        get_latest_indicators=lambda _series: {"DGS10": {"value": None}},
        logger=logger,
    )
    assert value == pytest.approx(0.08)


def test_calculate_cost_of_equity_capm_applies_beta_cap():
    value = calculate_cost_of_equity_capm(
        symbol="NVDA",
        get_stock_info=lambda _symbol: {"beta": 3.5},
        get_latest_indicators=lambda _series: {"DGS10": {"value": 5.0}},
        logger=MagicMock(),
    )
    assert value == pytest.approx(0.225)


def test_calculate_cost_of_equity_capm_falls_back_on_errors():
    logger = MagicMock()

    def raise_error(_symbol):
        raise RuntimeError("boom")

    value = calculate_cost_of_equity_capm(
        symbol="TSLA",
        get_stock_info=raise_error,
        get_latest_indicators=lambda _series: {"DGS10": {"value": 4.2}},
        logger=logger,
    )
    assert value == 0.10
    logger.warning.assert_called_once()

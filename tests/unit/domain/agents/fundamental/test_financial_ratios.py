"""Unit tests for financial-ratio helper pipeline."""

from unittest.mock import MagicMock

from investigator.domain.agents.fundamental.financial_ratios import (
    add_market_context_ratios,
    apply_balance_sheet_and_cashflow_ratios,
    apply_valuation_ratios,
    calculate_revenue_growth_yoy,
    resolve_market_inputs,
)


def test_resolve_market_inputs_estimates_shares_and_market_cap():
    ratios = {}
    market_inputs = resolve_market_inputs(
        symbol="AAPL",
        cik="0000320193",
        financials={"stockholders_equity": 500.0},
        market_data={"current_price": 50.0},
        get_shares_outstanding=lambda _s, _c: 0.0,
        get_public_float=lambda _s, _c: 1_000_000.0,
        logger=MagicMock(),
        ratios=ratios,
    )

    assert market_inputs["shares"] == 10.0
    assert market_inputs["market_cap"] == 500.0
    assert ratios["public_float_usd"] == 1_000_000.0
    assert ratios["current_price"] == 50.0


def test_apply_valuation_ratios_populates_core_fields():
    ratios = {}
    apply_valuation_ratios(
        symbol="MSFT",
        financials={
            "net_income": 80.0,
            "stockholders_equity": 400.0,
            "revenues": 1_000.0,
        },
        quarterly_data=[],
        ratios=ratios,
        market_cap=2_000.0,
        shares=100.0,
        calculate_ttm_net_income=lambda _q, _s: 100.0,
        calculate_growth_rate=lambda _f, _metric: 0.1,
        logger=MagicMock(),
    )

    assert ratios["pe_ratio"] == 20.0
    assert ratios["eps"] == 1.0
    assert ratios["price_to_book"] == 5.0
    assert ratios["price_to_sales"] == 2.0
    assert ratios["revenue_per_share"] == 10.0
    assert ratios["peg_ratio"] == 2.0


def test_apply_balance_sheet_and_cashflow_ratios_populates_metrics():
    ratios = {}
    apply_balance_sheet_and_cashflow_ratios(
        financials={
            "current_assets": 300.0,
            "current_liabilities": 100.0,
            "inventory": 20.0,
            "total_debt": 200.0,
            "stockholders_equity": 400.0,
            "total_assets": 900.0,
            "net_income": 90.0,
            "revenues": 600.0,
            "gross_profit": 240.0,
            "operating_income": 120.0,
            "cost_of_revenue": 360.0,
            "operating_cash_flow": 150.0,
            "capital_expenditures": -30.0,
            "dividends_paid": -10.0,
            "preferred_stock_dividends": -5.0,
        },
        ratios=ratios,
        market_cap=1_200.0,
        price=60.0,
    )
    add_market_context_ratios(
        ratios=ratios,
        market_data={"current_price": 60.0},
        financials={"stockholders_equity": 400.0},
        market_cap=1_200.0,
        shares=20.0,
        price=60.0,
    )

    assert ratios["current_ratio"] == 3.0
    assert ratios["quick_ratio"] == 2.8
    assert ratios["debt_to_equity"] == 0.5
    assert ratios["free_cash_flow"] == 120.0
    assert ratios["fcf_yield"] == 0.1
    assert ratios["dividend_yield"] == 0.25
    assert ratios["market_cap"] == 1_200.0
    assert ratios["shares_outstanding"] == 20.0


def test_calculate_revenue_growth_yoy_ignores_fy_rows():
    quarterly_data = [
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q4",
            "financial_data": {"revenues": 140.0},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q3",
            "financial_data": {"revenues": 130.0},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q2",
            "financial_data": {"revenues": 120.0},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q1",
            "financial_data": {"revenues": 110.0},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "financial_data": {"revenues": 500.0},
        },
        {
            "fiscal_year": 2023,
            "fiscal_period": "Q4",
            "financial_data": {"revenues": 100.0},
        },
    ]
    yoy = calculate_revenue_growth_yoy(
        quarterly_data=quarterly_data, logger=MagicMock()
    )
    assert yoy == 0.4

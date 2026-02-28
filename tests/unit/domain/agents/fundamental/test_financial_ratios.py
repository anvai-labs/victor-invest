"""Unit tests for financial-ratio helper pipeline."""

from unittest.mock import MagicMock

from investigator.domain.agents.fundamental.financial_ratios import (
    add_market_context_ratios,
    apply_balance_sheet_and_cashflow_ratios,
    apply_valuation_ratios,
    calculate_revenue_growth_yoy,
    calculate_ttm_metrics,
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
        ttm_metrics={"net_income": 100.0, "revenues": 1_000.0},
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


def test_apply_valuation_ratios_prefers_ttm_revenue_for_ps():
    ratios = {}
    apply_valuation_ratios(
        symbol="MSFT",
        financials={
            "net_income": 80.0,
            "stockholders_equity": 400.0,
            "revenues": 250.0,
        },
        quarterly_data=[],
        ttm_metrics={"net_income": 100.0, "revenues": 1_000.0},
        ratios=ratios,
        market_cap=2_000.0,
        shares=100.0,
        calculate_ttm_net_income=lambda _q, _s: 100.0,
        calculate_growth_rate=lambda _f, _metric: 0.1,
        logger=MagicMock(),
    )

    assert ratios["ttm_revenue"] == 1_000.0
    assert ratios["price_to_sales"] == 2.0
    assert ratios["revenue_per_share"] == 10.0


def test_calculate_ttm_metrics_uses_most_recent_quarters_and_excludes_fy():
    quarterly_data = [
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q1",
            "financial_data": {"net_income": 10, "revenues": 100},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q2",
            "financial_data": {"net_income": 20, "revenues": 120},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q3",
            "financial_data": {"net_income": 30, "revenues": 130},
        },
        {
            "fiscal_year": 2024,
            "fiscal_period": "Q4",
            "financial_data": {"net_income": 40, "revenues": 140},
        },
        {
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "financial_data": {"net_income": 250, "revenues": 1000},
        },
        {
            "fiscal_year": 2025,
            "fiscal_period": "Q1",
            "financial_data": {"net_income": 50, "revenues": 150},
        },
        {
            "fiscal_year": 2025,
            "fiscal_period": "Q2",
            "financial_data": {"net_income": 60, "revenues": 160},
        },
    ]

    ttm = calculate_ttm_metrics(
        quarterly_data=quarterly_data,
        symbol="MSFT",
        logger=MagicMock(),
    )

    # Latest 4 quarters should be: 2025-Q2, 2025-Q1, 2024-Q4, 2024-Q3 (FY excluded)
    assert ttm["net_income"] == 60 + 50 + 40 + 30
    assert ttm["revenues"] == 160 + 150 + 140 + 130
    assert ttm["quarters_used"] == 4.0


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
    assert ratios["dividend_yield"] == 0.0125
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
    yoy = calculate_revenue_growth_yoy(quarterly_data=quarterly_data, logger=MagicMock())
    assert yoy == 0.4

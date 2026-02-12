"""Unit tests for cost-of-capital helper functions."""

from types import SimpleNamespace

from investigator.domain.agents.fundamental.cost_of_capital import (
    apply_cost_of_capital_penalty,
    evaluate_cost_of_capital_inputs,
    hydrate_cost_of_capital_inputs,
)


def test_hydrate_cost_of_capital_inputs_populates_missing_fields():
    profile = SimpleNamespace(beta=None, total_debt=None, interest_coverage=None)
    company_data = {
        "market_data": {"beta": None},
        "financials": {
            "long_term_debt": 70.0,
            "short_term_debt": 30.0,
            "interest_expense": 0,
        },
        "facts": {"interest_expense": 12.0},
        "interest_coverage": 5.5,
    }
    ratios = {"beta": 1.2}

    hydrate_cost_of_capital_inputs(
        profile=profile,
        company_data=company_data,
        ratios=ratios,
        symbol="AAPL",
        get_stock_info=lambda _symbol: {"beta": 1.1},
        require_financials=lambda payload: payload["financials"],
    )

    assert profile.beta == 1.2
    assert profile.total_debt == 100.0
    assert profile.interest_coverage == 5.5
    assert company_data["financials"]["interest_expense"] == 12.0


def test_hydrate_cost_of_capital_inputs_tolerates_stock_info_errors():
    profile = SimpleNamespace(beta=None, total_debt=None, interest_coverage=None)
    company_data = {"financials": {"total_debt": 0, "interest_expense": 1}}

    def raise_error(_symbol):
        raise RuntimeError("network issue")

    hydrate_cost_of_capital_inputs(
        profile=profile,
        company_data=company_data,
        ratios={},
        symbol="MSFT",
        get_stock_info=raise_error,
        require_financials=lambda payload: payload["financials"],
    )

    assert profile.beta is None


def test_evaluate_cost_of_capital_inputs_detects_missing_inputs():
    profile = SimpleNamespace(beta=None, total_debt=200.0, interest_coverage=None)
    company_data = {"financials": {"interest_expense": 0}}
    issues = evaluate_cost_of_capital_inputs(
        profile=profile,
        company_data=company_data,
        require_financials=lambda payload: payload["financials"],
    )

    assert issues == [
        "missing_beta",
        "missing_interest_expense",
        "missing_interest_coverage",
    ]


def test_apply_cost_of_capital_penalty_updates_confidence_and_flags():
    valuation = {
        "applicable": True,
        "confidence_score": 0.8,
        "diagnostics": {"data_quality_score": 90.0, "flags": []},
    }
    result = apply_cost_of_capital_penalty(
        valuation_dict=valuation,
        issues=["missing_beta", "missing_interest_expense"],
    )

    assert result["confidence_score"] == 0.5
    assert result["diagnostics"]["data_quality_score"] == 60.0
    assert "COST_INPUT_MISSING_BETA" in result["diagnostics"]["flags"]
    assert result["metadata"]["cost_of_capital_issues"] == [
        "missing_beta",
        "missing_interest_expense",
    ]


def test_apply_cost_of_capital_penalty_noop_for_non_applicable():
    valuation = {"applicable": False, "confidence_score": 0.9}
    result = apply_cost_of_capital_penalty(
        valuation_dict=valuation,
        issues=["missing_beta"],
    )
    assert result["confidence_score"] == 0.9

"""Unit tests for LLM sanitation helpers."""

from unittest.mock import MagicMock

from investigator.domain.agents.fundamental.llm_sanitization import (
    sanitize_for_llm_inputs,
)


def test_sanitize_for_llm_backfills_market_fields():
    company_data = {
        "market_cap": 0,
        "shares_outstanding": 0,
        "financials": {
            "total_debt": 100.0,
            "stockholders_equity": 200.0,
            "total_assets": 500.0,
        },
        "market_data": {"current_price": 0},
    }
    ratios = {
        "market_cap": 1_000.0,
        "shares_outstanding": 10.0,
        "current_price": 100.0,
        "current_ratio": 2.0,
        "quick_ratio": 1.5,
        "debt_to_equity": 0.9,
        "debt_to_assets": 0.9,
    }
    logger = MagicMock()
    log_issues = MagicMock()

    sanitized_company_data, sanitized_ratios = sanitize_for_llm_inputs(
        company_data=company_data,
        ratios=ratios,
        symbol="AAPL",
        logger=logger,
        log_data_quality_issues=log_issues,
    )

    assert sanitized_company_data["market_cap"] == 1_000.0
    assert sanitized_company_data["shares_outstanding"] == 10.0
    assert sanitized_company_data["market_data"]["current_price"] == 100.0
    assert sanitized_ratios["debt_to_equity"] == 0.5
    assert sanitized_ratios["debt_to_assets"] == 0.2
    log_issues.assert_called_once()


def test_sanitize_for_llm_uses_debt_components_and_bounds_quick_ratio():
    company_data = {
        "financials": {
            "long_term_debt": 70.0,
            "short_term_debt": 30.0,
            "equity": 250.0,
            "assets": 400.0,
        },
    }
    ratios = {"current_ratio": 1.2, "quick_ratio": 1.8}

    _, sanitized_ratios = sanitize_for_llm_inputs(
        company_data=company_data,
        ratios=ratios,
        symbol="MSFT",
        logger=MagicMock(),
        log_data_quality_issues=MagicMock(),
    )

    assert sanitized_ratios["debt_to_equity"] == 0.4
    assert sanitized_ratios["debt_to_assets"] == 0.25
    assert sanitized_ratios["quick_ratio"] == 1.2


def test_sanitize_for_llm_skips_unparseable_financials():
    company_data = {
        "financials": {
            "total_debt": "N/A",
            "stockholders_equity": None,
            "total_assets": "bad",
        }
    }
    ratios = {
        "debt_to_equity": 0.3,
        "debt_to_assets": 0.2,
        "current_ratio": 1.5,
        "quick_ratio": 1.0,
    }

    _, sanitized_ratios = sanitize_for_llm_inputs(
        company_data=company_data,
        ratios=ratios,
        symbol="NVDA",
        logger=MagicMock(),
        log_data_quality_issues=MagicMock(),
    )

    assert sanitized_ratios["debt_to_equity"] == 0.3
    assert sanitized_ratios["debt_to_assets"] == 0.2

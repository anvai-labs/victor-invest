"""Unit tests for model applicability rules."""

from investigator.domain.services.model_applicability import ModelApplicabilityRules


def test_ggm_accepts_percent_style_payout_input():
    rules = ModelApplicabilityRules()
    financials = {
        "net_income": 1_000_000,
        "dividends_paid": 450_000,
        "payout_ratio": 45.0,  # percent format
    }

    is_applicable, reason = rules.is_applicable("ggm", financials)

    assert is_applicable is True
    assert "requirements met" in reason.lower()


def test_ggm_uses_dividend_yield_when_dividend_tag_missing():
    rules = ModelApplicabilityRules()
    financials = {
        "net_income": 1_000_000,
        "dividends_paid": 0,  # missing extract
        "market_cap": 20_000_000,
        "dividend_yield": 2.5,  # percent format
        "payout_ratio": 0.001,  # bad payout source
    }

    is_applicable, reason = rules.is_applicable("ggm", financials)

    assert is_applicable is True
    assert "requirements met" in reason.lower()


def test_ggm_rejects_low_payout_after_normalization():
    rules = ModelApplicabilityRules()
    financials = {
        "net_income": 1_000_000,
        "dividends_paid": 50_000,
        "payout_ratio": 5.0,  # percent format -> 0.05
    }

    is_applicable, reason = rules.is_applicable("ggm", financials)

    assert is_applicable is False
    assert "low payout ratio" in reason.lower()


def test_ggm_rejects_excessive_payout_ratio():
    rules = ModelApplicabilityRules(
        applicability_config={
            "ggm": {
                "min_payout_ratio": 0.40,
                "max_payout_ratio": 0.90,
                "require_positive_earnings": True,
                "require_dividends": True,
            }
        }
    )
    financials = {
        "net_income": 1_000_000,
        "dividends_paid": 1_050_000,
        "payout_ratio": 1.05,
    }

    is_applicable, reason = rules.is_applicable("ggm", financials)

    assert is_applicable is False
    assert "excessive payout ratio" in reason.lower()

from investigator.domain.services.investment_decision_policy import (
    DecisionInputs,
    InvestmentDecisionPolicy,
)


def make_inputs(**overrides):
    values = {
        "symbol": "AAPL",
        "current_price": 100.0,
        "fair_value": 118.0,
        "expected_return_pct": 18.0,
        "technical_score": 70.0,
        "technical_signal": "bullish",
        "model_agreement_score": 0.65,
        "dispersion_ratio": 0.35,
        "data_quality_score": 82.0,
        "applicable_models": 3,
        "valuation_age_hours": 12.0,
    }
    values.update(overrides)
    return DecisionInputs(**values)


def test_positive_fair_value_and_bullish_technical_setup_is_buy():
    result = InvestmentDecisionPolicy().evaluate(make_inputs())

    assert result.action == "BUY"
    assert result.confidence in {"MEDIUM", "HIGH"}
    assert result.expected_return_pct == 18.0
    assert result.guardrails_triggered == ()


def test_large_upside_with_high_quality_and_agreement_is_strong_buy():
    result = InvestmentDecisionPolicy().evaluate(
        make_inputs(
            fair_value=132.0,
            expected_return_pct=32.0,
            technical_score=78.0,
            model_agreement_score=0.82,
            data_quality_score=91.0,
        )
    )

    assert result.action == "STRONG_BUY"
    assert result.confidence == "HIGH"


def test_negative_fair_value_downside_is_sell():
    result = InvestmentDecisionPolicy().evaluate(
        make_inputs(
            fair_value=86.0,
            expected_return_pct=-14.0,
            technical_score=35.0,
            technical_signal="bearish",
        )
    )

    assert result.action == "SELL"


def test_severe_downside_is_strong_sell_when_data_is_clean():
    result = InvestmentDecisionPolicy().evaluate(
        make_inputs(
            fair_value=70.0,
            expected_return_pct=-30.0,
            technical_score=25.0,
            technical_signal="bearish",
            model_agreement_score=0.8,
            data_quality_score=88.0,
        )
    )

    assert result.action == "STRONG_SELL"
    assert result.confidence == "HIGH"


def test_missing_fair_value_returns_review():
    result = InvestmentDecisionPolicy().evaluate(make_inputs(fair_value=None, expected_return_pct=None))

    assert result.action == "REVIEW"
    assert "missing_fair_value" in result.guardrails_triggered


def test_low_data_quality_downgrades_to_review_when_unreliable():
    result = InvestmentDecisionPolicy().evaluate(make_inputs(data_quality_score=32.0))

    assert result.action == "REVIEW"
    assert result.confidence == "LOW"
    assert "low_data_quality" in result.guardrails_triggered


def test_low_model_agreement_triggers_guardrail_and_reduces_confidence():
    result = InvestmentDecisionPolicy().evaluate(make_inputs(model_agreement_score=0.22))

    assert result.action in {"HOLD", "BUY"}
    assert result.confidence == "LOW"
    assert "low_model_agreement" in result.guardrails_triggered


def test_split_suspect_forces_review():
    result = InvestmentDecisionPolicy().evaluate(make_inputs(split_suspect=True))

    assert result.action == "REVIEW"
    assert "split_suspect" in result.guardrails_triggered


def test_llm_contradiction_is_recorded_but_does_not_override_policy():
    result = InvestmentDecisionPolicy().evaluate(make_inputs(llm_recommendation="STRONG SELL"))

    assert result.action == "BUY"
    assert "llm_dissent" in result.guardrails_triggered
    assert result.evidence["llm_recommendation"] == "STRONG_SELL"


def test_positive_fair_value_with_bearish_technical_setup_becomes_hold():
    result = InvestmentDecisionPolicy().evaluate(
        make_inputs(
            expected_return_pct=20.0,
            fair_value=120.0,
            technical_score=25.0,
            technical_signal="bearish",
        )
    )

    assert result.action == "HOLD"
    assert "technical_contradiction" in result.guardrails_triggered

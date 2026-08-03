from investigator.application.decision_input_extractor import (
    from_legacy_analysis_result,
    from_symbol_ranking_row,
    from_ui_cache_summary,
    from_victor_workflow_state,
)


def test_extracts_decision_inputs_from_legacy_analysis_result():
    payload = {
        "symbol": "nvda",
        "agents": {
            "fundamental": {
                "valuation": {"current_price": 220.0},
                "multi_model_summary": {
                    "blended_fair_value": 270.0,
                    "model_agreement_score": 0.42,
                    "applicable_models": 4,
                    "divergence_flag": False,
                },
                "data_quality": {"data_quality_score": 84.0},
            },
            "technical": {
                "trend": {"overall_signal": "bullish"},
                "technical_score": 72.0,
            },
            "synthesis": {"recommendation": {"recommendation": "SELL"}},
        },
    }

    result = from_legacy_analysis_result(payload)

    assert result.symbol == "NVDA"
    assert result.current_price == 220.0
    assert result.fair_value == 270.0
    assert round(result.expected_return_pct or 0, 2) == 22.73
    assert result.technical_signal == "bullish"
    assert result.technical_score == 72.0
    assert result.model_agreement_score == 0.42
    assert result.data_quality_score == 84.0
    assert result.applicable_models == 4
    assert result.llm_recommendation == "SELL"


def test_extracts_decision_inputs_from_victor_workflow_state():
    state = {
        "symbol": "aapl",
        "fundamental_analysis": {
            "valuation_models": {
                "current_price": 100,
                "blended_fair_value": 128,
                "model_agreement_score": 72,  # percent-like input normalized
                "applicable_models": 5,
            },
            "data_quality": {"data_quality_score": 0.9},  # ratio normalized
        },
        "technical_analysis": {
            "trend": {"overall_signal": "bullish"},
            "score": 68,
        },
        "synthesis": {"recommendation": {"action": "BUY"}},
    }

    result = from_victor_workflow_state(state)

    assert result.symbol == "AAPL"
    assert result.current_price == 100.0
    assert result.fair_value == 128.0
    assert result.expected_return_pct == 28.0
    assert result.model_agreement_score == 0.72
    assert result.data_quality_score == 90.0
    assert result.technical_signal == "bullish"
    assert result.technical_score == 68.0
    assert result.llm_recommendation == "BUY"


def test_extracts_decision_inputs_from_symbol_ranking_row():
    row = {
        "symbol": "pypl",
        "current_price": "70.0",
        "target_price": "91.0",
        "expected_return_pct": "30.0",
        "model_agreement_score": "0.55",
        "dispersion_ratio": "0.45",
        "data_quality_score": "76",
        "weighted_model_count": "3",
        "age_hours": "16",
        "action": "BUY",
    }

    result = from_symbol_ranking_row(row)

    assert result.symbol == "PYPL"
    assert result.current_price == 70.0
    assert result.fair_value == 91.0
    assert result.expected_return_pct == 30.0
    assert result.model_agreement_score == 0.55
    assert result.dispersion_ratio == 0.45
    assert result.data_quality_score == 76.0
    assert result.applicable_models == 3
    assert result.valuation_age_hours == 16.0
    assert result.llm_recommendation == "BUY"


def test_extracts_decision_inputs_from_ui_cache_summary():
    summary = {
        "symbol": "adbe",
        "price": {"current": 410.0, "target": 500.0, "expected_return_pct": 21.95},
        "valuation": {
            "blended_fair_value": 500.0,
            "model_agreement_score": 0.61,
            "applicable_models": 4,
        },
        "quality": {"data_quality_score": 88.0},
        "technical": {"overall_signal": "neutral", "technical_score": 54},
        "recommendation": {"action": "HOLD"},
    }

    result = from_ui_cache_summary(summary)

    assert result.symbol == "ADBE"
    assert result.current_price == 410.0
    assert result.fair_value == 500.0
    assert result.expected_return_pct == 21.95
    assert result.data_quality_score == 88.0
    assert result.technical_signal == "neutral"
    assert result.technical_score == 54.0
    assert result.llm_recommendation == "HOLD"


def test_missing_values_are_tolerated_without_exceptions():
    result = from_legacy_analysis_result({"symbol": "MSFT"})

    assert result.symbol == "MSFT"
    assert result.current_price is None
    assert result.fair_value is None
    assert result.expected_return_pct is None

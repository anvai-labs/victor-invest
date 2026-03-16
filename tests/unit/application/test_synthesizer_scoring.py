from unittest.mock import MagicMock

from investigator.application.synthesizer_scoring import (
    assess_data_quality,
    calculate_fundamental_score,
    calculate_technical_score,
    calculate_weighted_score,
    parse_synthesis_response,
)


def test_calculate_fundamental_score_prefers_comprehensive_payload():
    llm_responses = {
        "fundamental": {
            "comprehensive": {"content": {"financial_health_score": 8.2}},
            "Q1_2025": {"content": {"financial_health_score": 6.0}},
        }
    }

    assert calculate_fundamental_score(llm_responses) == 8.2


def test_calculate_technical_score_handles_header_prefixed_json():
    llm_responses = {
        "technical": {
            "content": '=== AI RESPONSE ===\n{"technical_score": {"score": 7.1}}',
        }
    }

    assert calculate_technical_score(llm_responses) == 7.1


def test_calculate_weighted_score_applies_extreme_score_bias():
    result = calculate_weighted_score(10.0, 0.0, fundamental_weight=0.6, technical_weight=0.4)

    assert result > 5.5


def test_assess_data_quality_uses_explicit_comprehensive_score():
    llm_responses = {
        "fundamental": {
            "comprehensive": {
                "content": {"data_quality_score": {"score": 8.5}},
            }
        }
    }

    assert assess_data_quality(llm_responses, {}) == 8.5


def test_parse_synthesis_response_extracts_structured_fields():
    logger = MagicMock()
    response = """**FINAL RECOMMENDATION: [BUY]**
**CONFIDENCE LEVEL: [HIGH]**
**KEY CATALYSTS:**
- Margin expansion
- New market entry

**12-month Target: $210.50**
POSITION SIZING: STARTER
TIME HORIZON: LONG-TERM
"""

    result = parse_synthesis_response(response, logger=logger)

    assert result["recommendation"] == "BUY"
    assert result["confidence"] == "HIGH"
    assert result["key_catalysts"] == ["Margin expansion", "New market entry"]
    assert result["price_targets"]["12_month"] == 210.5
    assert result["position_size"] == "SMALL"
    assert result["time_horizon"] == "LONG-TERM"
    logger.warning.assert_not_called()

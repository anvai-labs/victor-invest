import json

from investigator.application.synthesizer_technicals import (
    assess_trend_strength,
    assess_volume_price_relationship,
    assess_volume_trend,
    calculate_bb_position,
    calculate_ma_position,
    check_ma_cross,
    extract_legacy_technical_indicators,
    extract_momentum_signals,
    extract_technical_indicators,
    extract_technical_signals_from_text,
)


def test_extract_technical_indicators_from_structured_response():
    llm_responses = {
        "technical": {
            "content": {
                "technical_score": {"score": 7.5},
                "trend_analysis": {"primary_trend": "BULLISH", "trend_strength": "STRONG"},
                "support_resistance": {
                    "immediate_support": 150.0,
                    "major_support": 145.0,
                    "immediate_resistance": 160.0,
                    "major_resistance": 165.0,
                },
                "recommendation": {"technical_rating": "BUY", "confidence": "HIGH"},
                "volume_analysis": {"volume_trend": "INCREASING"},
            }
        }
    }

    result = extract_technical_indicators(llm_responses)

    assert result["technical_score"] == 7.5
    assert result["trend_direction"] == "BULLISH"
    assert result["support_levels"] == [150.0, 145.0]
    assert result["resistance_levels"] == [160.0, 165.0]
    assert "volume trend is increasing" in [signal.lower() for signal in result["momentum_signals"]]


def test_extract_technical_indicators_from_json_string_with_prefix():
    payload = {
        "technical_score": 6.0,
        "trend_direction": "BEARISH",
        "support_levels": [100.0, 0.0],
        "resistance_levels": [110.0, 115.0],
        "recommendation": "SELL",
        "confidence": "MEDIUM",
    }
    llm_responses = {"technical": {"content": f"<think>draft</think>\n{json.dumps(payload)}"}}

    result = extract_technical_indicators(llm_responses)

    assert result["technical_score"] == 6.0
    assert result["trend_direction"] == "BEARISH"
    assert result["support_levels"] == [100.0]
    assert result["resistance_levels"] == [110.0, 115.0]


def test_extract_legacy_technical_indicators_handles_plain_text():
    content = 'trend_direction: "bullish" support_levels: [101.5, 99.0] resistance_levels: [110.0, 112.5]'

    result = extract_legacy_technical_indicators(content)

    assert result["trend_direction"] == "BULLISH"
    assert result["support_levels"] == [101.5, 99.0]
    assert result["resistance_levels"] == [110.0, 112.5]


def test_extract_momentum_signals_combines_rsi_macd_and_volume():
    content = {
        "momentum_analysis": {
            "rsi_14": 71.2,
            "rsi_assessment": "OVERBOUGHT",
            "macd": {"signal": "BULLISH_CROSS"},
        },
        "volume_analysis": {"volume_trend": "INCREASING"},
    }

    result = extract_momentum_signals(content)

    assert any("RSI" in signal for signal in result)
    assert any("MACD" in signal for signal in result)
    assert any("Volume trend" in signal for signal in result)


def test_extract_technical_signals_from_text_parses_core_fields():
    text = "RSI: 62.5\nMACD: 1.8\nTrend: bullish\nSupport: $190.0\nResistance: $205.5"

    result = extract_technical_signals_from_text(text)

    assert result == {
        "rsi": 62.5,
        "macd": 1.8,
        "trend": "BULLISH",
        "support": 190.0,
        "resistance": 205.5,
    }


def test_calculate_ma_position_and_cross_helpers():
    assert calculate_ma_position(105.0, 100.0) == "Strong Above"
    assert calculate_ma_position(99.0, 100.0) == "Below"
    assert check_ma_cross(202.0, 100.0) == "Golden Cross"
    assert check_ma_cross(90.0, 100.0) == "Death Cross"


def test_trend_and_bollinger_helpers():
    assert assess_trend_strength({"rsi": 65, "price_change_1m": 8}) == "Strong Bullish"
    assert calculate_bb_position({"current_price": 108, "bollinger_upper": 110, "bollinger_lower": 90}) == "Upper Band"


def test_volume_helpers():
    assert assess_volume_trend({"volume_ratio": 2.1}) == "Very High"
    assert assess_volume_price_relationship({"price_change_1d": 1.5, "volume_ratio": 1.4}) == "Bullish Confirmation"

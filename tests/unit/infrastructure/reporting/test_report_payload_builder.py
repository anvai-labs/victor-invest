"""Unit tests for ReportPayloadBuilder."""

from investigator.infrastructure.reporting.report_payload_builder import ReportPayloadBuilder


def test_build_unwraps_response_json_string():
    """Builder should parse wrapped JSON strings and avoid type errors."""
    builder = ReportPayloadBuilder()
    synthesis_report = {
        "timestamp": "2026-02-12T09:51:54.376094",
        "response": (
            '{"report": {"recommendation": {"final_recommendation": "buy", "confidence_level": 72}, '
            '"valuation": {"current_price": 100.0, "fair_value": 120.0}}}'
        ),
    }

    payload = builder.build(symbol="TEST", synthesis_report=synthesis_report)

    assert payload["symbol"] == "TEST"
    assert payload["timestamp"] == "2026-02-12T09:51:54.376094"
    assert payload["recommendation"] == "buy"
    assert payload["confidence"] == 72
    assert payload["current_price"] == 100.0
    assert payload["fair_value"] == 120.0


def test_build_accepts_plain_json_string_payload():
    """Builder should accept serialized synthesis payloads directly."""
    builder = ReportPayloadBuilder()
    synthesis_report = (
        '{"recommendation": {"final_recommendation": "sell", "confidence": 41}, '
        '"valuation": {"current_price": 50.0, "fair_value": 45.0}}'
    )

    payload = builder.build(symbol="TEST", synthesis_report=synthesis_report)

    assert payload["recommendation"] == "sell"
    assert payload["confidence"] == 41
    assert payload["current_price"] == 50.0
    assert payload["fair_value"] == 45.0


def test_build_uses_recommendation_and_action_plan_fallback():
    """Builder should extract recommendation when only recommendation_and_action_plan exists."""
    builder = ReportPayloadBuilder()
    synthesis_report = {
        "recommendation_and_action_plan": {
            "final_recommendation": "hold",
            "confidence_level": 63,
            "entry_strategy": {
                "entry_timing_considerations": "Scale entries near support.",
            },
        }
    }

    payload = builder.build(symbol="TEST", synthesis_report=synthesis_report)

    assert payload["recommendation"] == "hold"
    assert payload["confidence"] == 63
    assert payload["specific_actions"] == ["Scale entries near support."]

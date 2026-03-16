from unittest.mock import MagicMock

from investigator.application.synthesizer_recommendation import (
    calculate_consistency_bonus,
    calculate_price_target,
    calculate_stop_loss,
    create_fallback_recommendation,
    determine_final_recommendation,
    extract_catalysts,
    extract_position_size,
)


def test_determine_final_recommendation_downgrades_strong_for_low_quality():
    result = determine_final_recommendation(
        overall_score=7.2,
        ai_recommendation={"recommendation": "STRONG BUY", "confidence": "HIGH"},
        data_quality=0.3,
    )
    assert result["recommendation"] == "BUY"
    assert result["confidence"] == "LOW"


def test_calculate_price_target_uses_score_mapping_and_logs_when_price_missing():
    logger = MagicMock()
    recommendation = {"composite_scores": {"overall_score": 8.1}}
    price_target = calculate_price_target("AAPL", recommendation, 0.0, logger)
    assert price_target == 115.0
    logger.warning.assert_called_once()
    logger.info.assert_called_once()


def test_stop_loss_and_position_catalyst_extractors():
    stop = calculate_stop_loss(100.0, {"recommendation": "BUY"}, 3.0)
    assert stop == 95.0

    size = extract_position_size({"investment_recommendation": {"position_sizing": {"recommended_weight": 0.051}}})
    assert size == "LARGE"

    catalysts = extract_catalysts(
        {
            "key_catalysts": [
                {"catalyst": "Margin expansion"},
                "Product cycle",
                {"catalyst": "Buybacks"},
                {"catalyst": "Ignored due to cap"},
            ]
        }
    )
    assert catalysts == ["Margin expansion", "Product cycle", "Buybacks"]


def test_calculate_consistency_bonus_bounds():
    assert calculate_consistency_bonus([7.0]) == 0.0
    assert 0.0 <= calculate_consistency_bonus([7.0, 7.1, 6.9, 7.05]) <= 1.0


def test_create_fallback_recommendation_extracts_partial_signal_fields():
    logger = MagicMock()
    raw_response = """
    FINAL RECOMMENDATION: BUY
    confidence: high
    INVESTMENT THESIS: Durable margins and improving free cash flow support upside over the next year.
    """

    result = create_fallback_recommendation(raw_response, "AAPL", 7.4, logger)

    assert result["overall_score"] == 7.4
    assert result["investment_recommendation"]["recommendation"] == "BUY"
    assert result["investment_recommendation"]["confidence_level"] == "HIGH"
    assert "Durable margins" in result["executive_summary"]["investment_thesis"]
    assert result["_fallback_created"] is True
    assert result["_parsing_error"] is True
    logger.info.assert_called_once()


def test_create_fallback_recommendation_returns_emergency_payload_on_repr_failure():
    logger = MagicMock()

    class BrokenResponse:
        def __str__(self):
            raise RuntimeError("boom")

    result = create_fallback_recommendation(BrokenResponse(), "MSFT", 6.0, logger)

    assert result["overall_score"] == 5.0
    assert result["investment_recommendation"]["recommendation"] == "HOLD"
    assert result["_emergency_fallback"] is True
    logger.error.assert_called_once()

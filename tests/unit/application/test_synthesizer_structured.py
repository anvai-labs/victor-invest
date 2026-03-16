from investigator.application.synthesizer_structured import (
    calculate_data_quality_detailed,
    calculate_quarterly_trends,
    create_recommendation_from_llm_data,
    extract_sec_comprehensive_data,
)


def test_calculate_quarterly_trends_builds_qoq_yoy_and_margin_views():
    quarterly_data = [
        {
            "period_label": "2024-Q1",
            "revenue": 100,
            "net_income": 10,
            "operating_cash_flow": 15,
            "operating_income": 12,
        },
        {
            "period_label": "2024-Q2",
            "revenue": 110,
            "net_income": 12,
            "operating_cash_flow": 17,
            "operating_income": 13,
        },
        {
            "period_label": "2024-Q3",
            "revenue": 120,
            "net_income": 14,
            "operating_cash_flow": 19,
            "operating_income": 14,
        },
        {
            "period_label": "2024-Q4",
            "revenue": 130,
            "net_income": 16,
            "operating_cash_flow": 21,
            "operating_income": 15,
        },
        {
            "period_label": "2025-Q1",
            "revenue": 140,
            "net_income": 18,
            "operating_cash_flow": 23,
            "operating_income": 16,
        },
    ]

    result = calculate_quarterly_trends(quarterly_data)

    assert result["qoq_growth"]["revenue"] == 7.69
    assert result["yoy_growth"]["revenue"][0]["period"] == "2025-Q1"
    assert len(result["margin_trends"]) == 5


def test_extract_sec_comprehensive_data_handles_json_string_payload():
    llm_responses = {
        "fundamental": {
            "comprehensive": {
                "content": (
                    '{"financial_health_score": 8.1, "business_quality_score": 7.8, '
                    '"data_quality_score": {"score": 8.7}, "key_insights": ["Pricing power"]}'
                )
            }
        }
    }

    result = extract_sec_comprehensive_data(llm_responses)

    assert result["financial_health_score"] == 8.1
    assert result["business_quality_score"] == 7.8
    assert result["data_quality_score"] == 8.7
    assert result["key_insights"] == ["Pricing power"]


def test_create_recommendation_from_llm_data_combines_sec_and_technical_signals():
    sec_data = {
        "financial_health_score": 8.4,
        "business_quality_score": 8.2,
        "growth_prospects_score": 7.5,
        "data_quality_score": 8.4,
        "investment_thesis": "Margins are durable.",
        "key_insights": ["Recurring revenue base"],
        "key_risks": ["Competition"],
    }
    tech_indicators = {
        "technical_score": 7.2,
        "trend_direction": "BULLISH",
        "recommendation": "BUY",
        "support_levels": [100.0, 95.0],
        "resistance_levels": [120.0, 125.0],
        "risk_factors": ["Momentum fade"],
        "momentum_signals": ["RSI healthy"],
    }

    result = create_recommendation_from_llm_data("AAPL", sec_data, tech_indicators, 110.0, 8.0)

    assert result["investment_recommendation"]["recommendation"] == "BUY"
    assert result["confidence_level"] == "HIGH"
    assert result["price_target"] == 125.0
    assert result["stop_loss"] == 90.25
    assert result["trend_direction"] == "BULLISH"
    assert result["source"] == "direct_llm_extraction"


def test_calculate_data_quality_detailed_uses_peer_provider_and_assigns_grade():
    result = calculate_data_quality_detailed(
        "AAPL",
        {"fundamental": {}, "technical": {}, "quarterly_summary": {}},
        [1, 2, 3, 4, 5, 6, 7, 8],
        {"current_price": 100.0},
        get_peer_count=lambda _symbol: 12,
    )

    assert result["overall_score"] == 100.0
    assert result["grade"] == "A"
    assert result["components"]["peer_availability"] == 100

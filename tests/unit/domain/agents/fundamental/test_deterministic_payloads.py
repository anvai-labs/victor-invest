from investigator.domain.agents.fundamental.deterministic_payloads import (
    build_deterministic_cache_record,
    build_deterministic_forecast_payload,
    build_deterministic_fundamental_report_payload,
    build_deterministic_response,
    calculate_quality_score,
    coerce_float,
)


def test_build_deterministic_response_contract():
    payload = {"score": 88, "assessment": "Strong"}
    result = build_deterministic_response("agent-x", "financial_health", payload)

    assert result["response"] == payload
    assert result["prompt"] == ""
    assert result["model_info"]["model"] == "deterministic-financial_health"
    assert result["model_info"]["temperature"] == 0.0
    assert result["metadata"]["agent_id"] == "agent-x"
    assert result["metadata"]["cache_type"] == "deterministic_analysis"
    assert result["metadata"]["generated_at"]


def test_build_deterministic_cache_record_with_period():
    key, wrapped = build_deterministic_cache_record(
        symbol="AAPL",
        agent_id="agent-y",
        label="growth_analysis",
        payload={"growth_score": 72},
        period="2025-Q4",
    )

    assert key == {"symbol": "AAPL", "llm_type": "growth_analysis", "period": "2025-Q4"}
    assert wrapped["response"]["growth_score"] == 72
    assert wrapped["metadata"]["agent_id"] == "agent-y"
    assert wrapped["metadata"]["analysis_type"] == "growth_analysis"
    assert wrapped["metadata"]["period"] == "2025-Q4"
    assert wrapped["metadata"]["cached_at"]


def test_build_deterministic_cache_record_without_period():
    key, wrapped = build_deterministic_cache_record(
        symbol="MSFT",
        agent_id="agent-z",
        label="profitability_analysis",
        payload={"profitability_score": 91},
        period=None,
    )

    assert key == {"symbol": "MSFT", "llm_type": "profitability_analysis"}
    assert wrapped["metadata"]["period"] is None


def test_coerce_float_handles_invalid_inputs():
    assert coerce_float("12.5") == 12.5
    assert coerce_float(None, 3.0) == 3.0


def test_build_deterministic_forecast_payload_has_required_sections():
    payload = build_deterministic_forecast_payload(
        financials={
            "revenue": 1_000_000_000,
            "net_income": 100_000_000,
            "free_cash_flow": 120_000_000,
            "shares_outstanding": 100_000_000,
            "gross_margin": 0.42,
            "operating_margin": 0.21,
            "net_margin": 0.10,
        },
        growth_analysis={"revenue_growth_rate": 0.12},
        current_year=2025,
    )

    assert payload["revenue_forecast"][0]["year"] == 2026
    assert len(payload["earnings_forecast"]) == 3
    assert "scenario_analysis" in payload
    assert payload["fallback_used"] is True


def test_build_deterministic_fundamental_report_payload_derives_recommendation():
    buy_payload = build_deterministic_fundamental_report_payload(
        {
            "valuation": {
                "fair_value_estimate": 120.0,
                "valuation_stance": "Undervalued",
            },
            "ratios": {"current_price": 100.0},
            "company_data": {},
        }
    )
    sell_payload = build_deterministic_fundamental_report_payload(
        {
            "valuation": {
                "fair_value_estimate": 80.0,
                "valuation_stance": "Overvalued",
            },
            "ratios": {"current_price": 100.0},
            "company_data": {},
        }
    )

    assert buy_payload["investment_recommendation"] == "buy"
    assert sell_payload["investment_recommendation"] == "sell"
    assert buy_payload["fallback_used"] is True


def test_calculate_quality_score_uses_weighted_average_and_default():
    weighted = calculate_quality_score(
        {"overall_health_score": 80},
        {"growth_score": 70},
        {"profitability_score": 90},
        {"strategic_positioning_score": 60},
    )
    default = calculate_quality_score({}, {}, {}, {})

    assert weighted == 76.0
    assert default == 50.0

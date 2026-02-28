"""Unit tests for robust LLM response parsing in SynthesisAgent."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from investigator.domain.agents import synthesis as synthesis_module
from investigator.domain.agents.synthesis import SynthesisAgent, SynthesisInput


def _build_agent_stub() -> SynthesisAgent:
    """Build a lightweight SynthesisAgent instance for parser unit tests."""
    agent = SynthesisAgent.__new__(SynthesisAgent)
    agent.logger = logging.getLogger("test.synthesis_parser")
    agent.agent_id = "test_synth_agent"
    return agent


def _configure_deterministic(agent: SynthesisAgent) -> SynthesisAgent:
    """Configure deterministic flags for synthesis-path tests."""
    agent.use_deterministic = True
    agent.deterministic_risk_assessment_generation = True
    agent.deterministic_scenario_generation = True
    agent.deterministic_recommendation_generation = True
    agent.deterministic_action_plan_generation = True
    agent.deterministic_report_generation = True
    agent.thresholds = {
        "strong_buy": 80,
        "buy": 65,
        "hold": 50,
        "sell": 35,
        "strong_sell": 20,
    }
    agent.models = {"reasoning": "test", "decision": "test", "synthesis": "test"}
    return agent


def test_parse_llm_response_handles_wrapped_think_and_code_fence():
    agent = _build_agent_stub()

    wrapped = {
        "response": '<think>reasoning</think>\n```json\n{"final_recommendation":"hold","confidence":70}\n```',
        "model_info": {},
        "metadata": {},
    }

    parsed = agent._parse_llm_response(wrapped)

    assert parsed["final_recommendation"] == "hold"
    assert parsed["confidence"] == 70


def test_parse_llm_response_extracts_json_from_mixed_string():
    agent = _build_agent_stub()

    mixed = 'Result below:\n{"bull_case":{},"base_case":{},"bear_case":{}}\nThanks.'
    parsed = agent._parse_llm_response(mixed)

    assert parsed == {"bull_case": {}, "base_case": {}, "bear_case": {}}


def test_parse_llm_response_returns_default_for_invalid_payload():
    agent = _build_agent_stub()
    default = {"fallback": True}

    parsed = agent._parse_llm_response("not-json-at-all", default=default)

    assert parsed == default


def test_parse_llm_response_repairs_malformed_json():
    if synthesis_module.repair_malformed_json is None:
        pytest.skip("json_repair dependency is not available in this test environment")

    agent = _build_agent_stub()

    malformed = '{"final_recommendation":"buy","key_reasons_for_recommendation":' '["line one\nline two"],}'
    wrapped = {"response": malformed, "model_info": {}, "metadata": {}}

    parsed = agent._parse_llm_response(wrapped)

    assert parsed["final_recommendation"] == "buy"
    assert "line one" in parsed["key_reasons_for_recommendation"][0]


def test_normalize_scenarios_response_accepts_alias_case_keys():
    agent = _build_agent_stub()
    raw = {
        "bull": {"price_target": 120},
        "base": {"price_target": 100},
        "bear": {"price_target": 80},
    }

    normalized = agent._normalize_scenarios_response(raw)

    assert normalized["bull_case"]["price_target"] == 120
    assert normalized["base_case"]["price_target"] == 100
    assert normalized["bear_case"]["price_target"] == 80


def test_normalize_recommendation_response_accepts_action_alias():
    agent = _build_agent_stub()
    normalized = agent._normalize_recommendation_response({"action": "strong sell"})

    assert normalized["final_recommendation"] == "strong_sell"


def test_normalize_action_plan_response_accepts_entry_alias():
    agent = _build_agent_stub()
    normalized = agent._normalize_action_plan_response({"entry": "Wait for pullback"})

    assert isinstance(normalized["entry_strategy"], dict)


@pytest.mark.asyncio
async def test_deterministic_scenario_generation_bypasses_llm():
    agent = _configure_deterministic(_build_agent_stub())
    synthesis_input = SynthesisInput(
        symbol="TST",
        fundamental_analysis={"valuation": {"current_price": 100.0, "fair_value": 120.0}},
        technical_analysis={},
    )

    result = await agent._generate_scenarios(
        synthesis_input=synthesis_input,
        composite_scores={"overall_score": 70},
        risk_assessment={"overall_risk": 40},
    )

    assert result["model_info"]["model"] == "deterministic-scenarios"
    assert result["response"]["bull_case"]["price_target"] == 125.0


@pytest.mark.asyncio
async def test_deterministic_risk_assessment_bypasses_llm():
    agent = _configure_deterministic(_build_agent_stub())
    synthesis_input = SynthesisInput(
        symbol="TST",
        fundamental_analysis={"analysis": {"health_score": 40}},
        technical_analysis={"analysis": {"volatility": 0.45}},
    )

    result = await agent._comprehensive_risk_assessment(
        synthesis_input=synthesis_input,
        conflicts=[{"type": "signal_conflict"}],
    )

    assert result["model_info"]["model"] == "deterministic-risk_assessment"
    assert result["response"]["overall_risk"] >= 50


@pytest.mark.asyncio
async def test_risk_assessment_falls_back_when_llm_returns_empty_payload():
    agent = _configure_deterministic(_build_agent_stub())
    agent.use_deterministic = False
    agent.deterministic_risk_assessment_generation = False
    agent.ollama = MagicMock()
    agent.ollama.generate = AsyncMock(return_value="")
    agent._cache_llm_response = AsyncMock()
    synthesis_input = SynthesisInput(
        symbol="TST",
        fundamental_analysis={"analysis": {"health_score": 55}},
        technical_analysis={"analysis": {"volatility": 0.35}},
    )

    result = await agent._comprehensive_risk_assessment(
        synthesis_input=synthesis_input,
        conflicts=[],
    )

    assert bool(result["response"]["fallback_used"]) is True
    agent._cache_llm_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_deterministic_recommendation_normalizes_percent_expected_return():
    agent = _configure_deterministic(_build_agent_stub())

    result = await agent._make_recommendation(
        composite_scores={"overall_score": 72, "confidence": 80},
        risk_assessment={"overall_risk": 30},
        scenarios={"response": {"expected_return": 12.5}},
        symbol="TST",
    )

    assert result["model_info"]["model"] == "deterministic-recommendation"
    assert result["response"]["expected_return"] == pytest.approx(0.125)


@pytest.mark.asyncio
async def test_deterministic_action_plan_generation_uses_technical_levels():
    agent = _configure_deterministic(_build_agent_stub())
    synthesis_input = SynthesisInput(
        symbol="TST",
        technical_analysis={
            "levels": {
                "support_1": 95.0,
                "pivot_point": 100.0,
                "support_2": 90.0,
                "resistance_1": 110.0,
                "resistance_2": 120.0,
            }
        },
    )

    result = await agent._generate_action_plan(
        recommendation={"final_recommendation": "hold"},
        synthesis_input=synthesis_input,
        scenarios={},
    )

    assert result["model_info"]["model"] == "deterministic-action_plan"
    assert result["response"]["entry_strategy"]["ideal_entry_price_range"] == [
        95.0,
        100.0,
    ]


@pytest.mark.asyncio
async def test_deterministic_report_generation_bypasses_llm():
    agent = _configure_deterministic(_build_agent_stub())

    result = await agent._create_synthesis_report({"symbol": "TST", "recommendation": {"final_recommendation": "hold"}})

    assert result["model_info"]["model"] == "deterministic-synthesis_report"
    assert result["response"]["report_mode"] == "deterministic"

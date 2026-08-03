import pytest

from victor_invest.workflows.graphs import run_synthesis


@pytest.mark.asyncio
async def test_run_synthesis_uses_decision_policy_for_final_action(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return {"recommendation": "STRONG SELL", "confidence": "HIGH", "executive_summary": "LLM dissent"}

    monkeypatch.setattr("victor_invest.workflows.graphs._run_llm_synthesis", fake_llm)

    result = await run_synthesis(
        {
            "symbol": "PYPL",
            "mode": "standard",
            "fundamental_analysis": {
                "status": "success",
                "valuation_models": {
                    "current_price": 70.0,
                    "blended_fair_value": 91.0,
                    "model_agreement_score": 0.62,
                    "applicable_models": 3,
                },
                "data_quality": {"data_quality_score": 84.0},
            },
            "technical_analysis": {
                "status": "success",
                "score": 70.0,
                "trend": {"overall_signal": "bullish"},
            },
            "errors": [],
            "completed_steps": [],
        }
    )

    assert result["recommendation"]["action"] == "STRONG_BUY"
    assert result["recommendation"]["confidence"] == "MEDIUM"
    assert result["recommendation"]["llm_recommendation"] == "STRONG SELL"
    assert "llm_dissent" in result["recommendation"]["decision_policy"]["guardrails_triggered"]
    assert result["synthesis"]["decision_policy"]["action"] == "STRONG_BUY"
    assert result["synthesis"]["composite_score"] is not None


@pytest.mark.asyncio
async def test_run_synthesis_returns_review_for_partial_missing_valuation(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return None

    monkeypatch.setattr("victor_invest.workflows.graphs._run_llm_synthesis", fake_llm)

    result = await run_synthesis(
        {
            "symbol": "MSFT",
            "mode": "standard",
            "technical_analysis": {
                "status": "success",
                "score": 76.0,
                "trend": {"overall_signal": "bullish"},
            },
            "errors": [],
            "completed_steps": [],
        }
    )

    assert result["recommendation"]["action"] == "REVIEW"
    assert result["recommendation"]["confidence"] == "LOW"
    assert "missing_fair_value" in result["recommendation"]["decision_policy"]["guardrails_triggered"]

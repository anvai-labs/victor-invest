from unittest.mock import AsyncMock, MagicMock

import pytest

from investigator.domain.agents.market_context import ETFMarketContextAgent


@pytest.mark.asyncio
async def test_market_sentiment_bypasses_llm_when_deterministic_enabled():
    agent = ETFMarketContextAgent.__new__(ETFMarketContextAgent)
    agent.use_deterministic = True
    agent.deterministic_market_sentiment_generation = True
    agent.timeframes = {"leading": 10, "short_term": 21, "medium_term": 63, "long_term": 252}

    result = await agent._generate_market_sentiment_analysis(
        symbol="STX",
        market_context={
            "market_regime": "risk_off",
            "leading": {"broad_market": {"return": -0.01}},
            "short_term": {"broad_market": {"return": -0.02}},
            "medium_term": {"broad_market": {"return": -0.03}},
            "long_term": {"broad_market": {"return": 0.05}},
        },
        sector_context={"sector_strength": "weak"},
        relative_performance={"vs_market": {"medium_term": {"relative_return": 0.04}}},
    )

    assert result["fallback_used"] is True
    assert result["market_regime"] == "risk_off"
    assert result["sentiment"] in {"bearish", "neutral", "bullish"}
    assert "overall_sentiment" in result


@pytest.mark.asyncio
async def test_market_sentiment_uses_fallback_when_llm_returns_empty_payload():
    agent = ETFMarketContextAgent.__new__(ETFMarketContextAgent)
    agent.use_deterministic = False
    agent.deterministic_market_sentiment_generation = False
    agent.market_context_model = "test-model"
    agent.timeframes = {"leading": 10, "short_term": 21, "medium_term": 63, "long_term": 252}
    agent.timeframe_metadata = {
        "leading": {"label": "Leading (10d)", "description": "Leading"},
        "short_term": {"label": "Short-term (21d)", "description": "Short"},
        "medium_term": {"label": "Medium-term (63d)", "description": "Medium"},
        "long_term": {"label": "Long-term (252d)", "description": "Long"},
    }
    agent.ollama = MagicMock()
    agent.ollama.generate = AsyncMock(return_value="")
    agent._cache_llm_response = AsyncMock()
    agent._extract_key_market_metrics = MagicMock(return_value={})
    agent._extract_key_sector_metrics = MagicMock(return_value={})
    agent._summarize_relative_performance = MagicMock(return_value={})
    agent._format_market_data_for_prompt = MagicMock(return_value="{}")

    result = await agent._generate_market_sentiment_analysis(
        symbol="STX",
        market_context={
            "market_regime": "neutral",
            "leading": {"broad_market": {"return": 0.0}},
            "short_term": {"broad_market": {"return": 0.0}},
            "medium_term": {"broad_market": {"return": 0.0}},
            "long_term": {"broad_market": {"return": 0.0}},
        },
        sector_context={},
        relative_performance={},
    )

    assert result["fallback_used"] is True
    agent._cache_llm_response.assert_awaited_once()

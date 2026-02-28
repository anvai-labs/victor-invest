from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from investigator.domain.agents.technical import TechnicalAnalysisAgent


@pytest.mark.asyncio
async def test_generate_signals_bypasses_llm_when_deterministic_enabled():
    agent = MagicMock(spec=TechnicalAnalysisAgent)
    agent.use_deterministic = True
    agent.deterministic_signal_generation = True
    agent.logger = MagicMock()
    agent._build_fallback_signals = MagicMock(
        return_value={"entry_signal": "hold", "fallback_used": True}
    )
    agent._generate_signals = TechnicalAnalysisAgent._generate_signals.__get__(agent)

    price_data = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]})
    result = await agent._generate_signals(
        price_data=price_data,
        indicators={},
        patterns=[],
        momentum={"overall_score": 0},
        symbol="STX",
    )

    assert result["entry_signal"] == "hold"
    agent._build_fallback_signals.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_technical_report_bypasses_llm_when_deterministic_enabled():
    agent = MagicMock(spec=TechnicalAnalysisAgent)
    agent.use_deterministic = True
    agent.deterministic_technical_report_generation = True
    agent.logger = MagicMock()
    agent._build_fallback_technical_report = MagicMock(
        return_value={"executive_summary": "fallback", "fallback_used": True}
    )
    agent._synthesize_technical_report = (
        TechnicalAnalysisAgent._synthesize_technical_report.__get__(agent)
    )

    result = await agent._synthesize_technical_report({"symbol": "STX"})

    assert result["fallback_used"] is True
    agent._build_fallback_technical_report.assert_called_once()


@pytest.mark.asyncio
async def test_detect_patterns_bypasses_llm_when_deterministic_enabled():
    agent = MagicMock(spec=TechnicalAnalysisAgent)
    agent.use_deterministic = True
    agent.deterministic_pattern_recognition = True
    agent.logger = MagicMock()
    agent._build_fallback_patterns = MagicMock(
        return_value=[{"pattern_name": "fallback_pattern", "confidence": 70}]
    )
    agent._detect_patterns = TechnicalAnalysisAgent._detect_patterns.__get__(agent)

    price_data = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1_000_000, 1_100_000, 1_050_000, 1_080_000, 1_120_000],
        }
    )

    result = await agent._detect_patterns(price_data=price_data, symbol="STX")

    assert result[0]["pattern_name"] == "fallback_pattern"
    agent._build_fallback_patterns.assert_called_once()


@pytest.mark.asyncio
async def test_detect_patterns_uses_fallback_when_llm_returns_empty_payload():
    agent = MagicMock(spec=TechnicalAnalysisAgent)
    agent.use_deterministic = False
    agent.deterministic_pattern_recognition = False
    agent.logger = MagicMock()
    agent.models = {"pattern_recognition": "test-model"}
    agent.ollama = MagicMock()
    agent.ollama.generate = AsyncMock(return_value="")
    agent._debug_log_prompt = MagicMock()
    agent._debug_log_response = MagicMock()
    agent._cache_llm_response = AsyncMock()
    agent._parse_llm_response = MagicMock(return_value={})
    agent._build_fallback_patterns = MagicMock(
        return_value=[{"pattern_name": "fallback_pattern", "confidence": 70}]
    )
    agent._detect_patterns = TechnicalAnalysisAgent._detect_patterns.__get__(agent)

    price_data = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1_000_000, 1_100_000, 1_050_000, 1_080_000, 1_120_000],
        }
    )

    result = await agent._detect_patterns(price_data=price_data, symbol="STX")

    assert result[0]["pattern_name"] == "fallback_pattern"
    agent._cache_llm_response.assert_awaited_once()
    agent._build_fallback_patterns.assert_called_once()

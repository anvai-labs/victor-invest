"""Contract tests for FundamentalAnalysisAgent deterministic-analysis delegation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from investigator.domain.agents.fundamental.agent import FundamentalAnalysisAgent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_method", "analyzer_method", "args"),
    [
        (
            "_analyze_financial_health",
            "analyze_financial_health",
            ({"financials": {}}, {"current_ratio": 1.5}, "AAPL"),
        ),
        (
            "_analyze_growth",
            "analyze_growth",
            ({"trend_analysis": {}}, "AAPL"),
        ),
        (
            "_analyze_profitability",
            "analyze_profitability",
            ({"trend_analysis": {}}, {"gross_margin": 0.2}, "AAPL"),
        ),
    ],
)
async def test_deterministic_methods_delegate_to_deterministic_analyzer(
    agent_method, analyzer_method, args
):
    """Each deterministic agent method should forward work to DeterministicAnalyzer."""
    agent = MagicMock(spec=FundamentalAnalysisAgent)
    agent._get_deterministic_analyzer = MagicMock()
    setattr(
        agent,
        agent_method,
        getattr(FundamentalAnalysisAgent, agent_method).__get__(agent),
    )

    expected = {"response": {"source": analyzer_method}}
    analyzer = MagicMock()
    setattr(analyzer, analyzer_method, AsyncMock(return_value=expected))
    agent._get_deterministic_analyzer.return_value = analyzer

    result = await getattr(agent, agent_method)(*args)

    assert result == expected
    agent._get_deterministic_analyzer.assert_called_once_with()
    getattr(analyzer, analyzer_method).assert_awaited_once_with(*args)


def test_get_deterministic_analyzer_caches_per_agent_instance():
    """Analyzer should be created once and cached on the agent instance."""
    agent = MagicMock(spec=FundamentalAnalysisAgent)
    agent.agent_id = "agent-test"
    agent.logger = MagicMock()
    agent._get_deterministic_analyzer = (
        FundamentalAnalysisAgent._get_deterministic_analyzer.__get__(agent)
    )

    analyzer = MagicMock()
    with patch(
        "investigator.domain.agents.fundamental.agent.DeterministicAnalyzer",
        return_value=analyzer,
    ) as cls:
        first = agent._get_deterministic_analyzer()
        second = agent._get_deterministic_analyzer()

    assert first is analyzer
    assert second is analyzer
    cls.assert_called_once_with(agent_id="agent-test", logger=agent.logger)


def test_build_deterministic_forecast_payload_has_required_sections():
    agent = MagicMock(spec=FundamentalAnalysisAgent)
    agent._coerce_float = FundamentalAnalysisAgent._coerce_float
    agent._build_deterministic_forecast_payload = (
        FundamentalAnalysisAgent._build_deterministic_forecast_payload.__get__(agent)
    )

    payload = agent._build_deterministic_forecast_payload(
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
    )

    assert len(payload["revenue_forecast"]) == 3
    assert len(payload["earnings_forecast"]) == 3
    assert len(payload["free_cash_flow_forecast"]) == 3
    assert "scenario_analysis" in payload
    assert payload["fallback_used"] is True


def test_build_deterministic_fundamental_report_payload_derives_recommendation():
    agent = MagicMock(spec=FundamentalAnalysisAgent)
    agent._coerce_float = FundamentalAnalysisAgent._coerce_float
    agent._build_deterministic_fundamental_report_payload = FundamentalAnalysisAgent._build_deterministic_fundamental_report_payload.__get__(
        agent
    )

    buy_payload = agent._build_deterministic_fundamental_report_payload(
        {
            "valuation": {
                "fair_value_estimate": 120.0,
                "valuation_stance": "Undervalued",
            },
            "ratios": {"current_price": 100.0},
            "company_data": {},
        }
    )
    sell_payload = agent._build_deterministic_fundamental_report_payload(
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

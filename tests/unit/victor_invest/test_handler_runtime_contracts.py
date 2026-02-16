import asyncio

from victor_invest.handlers import (
    AnalyzePeersHandler,
    FetchMarketDataHandler,
    RunFundamentalAnalysisHandler,
    RunSynthesisHandler,
    RunTechnicalAnalysisHandler,
)
from victor_invest.tools.base import ToolResult
from victor_invest.workflows.state import AnalysisMode, AnalysisWorkflowState


class _Context:
    def __init__(self, data):
        self._data = dict(data)

    def get(self, key, default=None):
        return self._data.get(key, default)


class _Constraints:
    def __init__(self, llm_allowed=False):
        self.llm_allowed = llm_allowed


class _Node:
    def __init__(self, node_id, output_key=None, llm_allowed=False):
        self.id = node_id
        self.output_key = output_key
        self.constraints = _Constraints(llm_allowed=llm_allowed)


def test_fetch_market_data_uses_supported_action(monkeypatch):
    import victor_invest.tools.market_data as market_data_module

    calls = {}

    class FakeMarketDataTool:
        async def execute(self, _exec_ctx=None, **kwargs):
            calls.update(kwargs)
            return ToolResult.create_success(output={"ok": True})

    monkeypatch.setattr(market_data_module, "MarketDataTool", FakeMarketDataTool)

    handler = FetchMarketDataHandler()
    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("fetch_market_data", "market_data"),
            _Context({"symbol": "AAPL"}),
            None,
        )
    )

    assert calls["action"] == "get_history"
    assert calls["days"] == 365
    assert output["status"] == "success"
    assert tool_calls == 0


def test_run_technical_analysis_uses_supported_action(monkeypatch):
    import victor_invest.tools.technical_indicators as technical_module

    calls = {}

    class FakeTechnicalTool:
        async def execute(self, _exec_ctx=None, **kwargs):
            calls.update(kwargs)
            return ToolResult.create_success(output={"ok": True})

    monkeypatch.setattr(technical_module, "TechnicalIndicatorsTool", FakeTechnicalTool)

    handler = RunTechnicalAnalysisHandler()
    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("run_technical_analysis", "technical_analysis"),
            _Context({"symbol": "AAPL", "market_data": {"status": "success"}}),
            None,
        )
    )

    assert calls["action"] == "calculate_all"
    assert output["status"] == "success"
    assert tool_calls == 0


def test_run_fundamental_analysis_uses_model_all(monkeypatch):
    import victor_invest.tools.valuation as valuation_module

    calls = {}

    class FakeValuationTool:
        async def execute(self, _exec_ctx=None, **kwargs):
            calls.update(kwargs)
            return ToolResult.create_success(output={"ok": True})

    monkeypatch.setattr(valuation_module, "ValuationTool", FakeValuationTool)

    handler = RunFundamentalAnalysisHandler()
    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("run_fundamental_analysis", "fundamental_analysis"),
            _Context({"symbol": "AAPL", "sec_data": {"status": "success"}}),
            None,
        )
    )

    assert calls["model"] == "all"
    assert "action" not in calls
    assert output["status"] == "success"
    assert tool_calls == 0


def test_run_synthesis_skips_llm_when_constraints_disallow(monkeypatch):
    handler = RunSynthesisHandler()
    called = {"value": False}

    async def fake_llm(*args, **kwargs):
        called["value"] = True
        return {"recommendation": "BUY", "confidence": "HIGH"}

    monkeypatch.setattr(handler, "_llm_synthesis", fake_llm)

    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("synthesize", "synthesis", llm_allowed=False),
            _Context(
                {
                    "symbol": "AAPL",
                    "fundamental_analysis": {},
                    "technical_analysis": {},
                    "market_context": {},
                }
            ),
            None,
        )
    )

    assert called["value"] is False
    assert output["status"] == "success"
    assert tool_calls == 0


def test_run_synthesis_uses_llm_when_constraints_allow(monkeypatch):
    handler = RunSynthesisHandler()
    called = {"value": False}

    async def fake_llm(*args, **kwargs):
        called["value"] = True
        return {"recommendation": "BUY", "confidence": "HIGH", "composite_score": 78}

    monkeypatch.setattr(handler, "_llm_synthesis", fake_llm)

    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("synthesize", "synthesis", llm_allowed=True),
            _Context(
                {
                    "symbol": "AAPL",
                    "fundamental_analysis": {"data": {"overall_score": 70}},
                    "technical_analysis": {"data": {"overall_score": 65}},
                    "market_context": {},
                }
            ),
            None,
        )
    )

    assert called["value"] is True
    assert output["synthesis_method"] == "llm"
    assert tool_calls == 1


def test_analyze_peers_uses_yaml_workflow_runner(monkeypatch):
    import victor_invest.workflows as workflows_pkg

    calls = []

    async def fake_run_yaml_analysis(symbol, mode):
        calls.append((symbol, mode))
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            synthesis={"composite_score": 77},
        )

    monkeypatch.setattr(workflows_pkg, "run_yaml_analysis", fake_run_yaml_analysis)

    handler = AnalyzePeersHandler()
    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("analyze_peers", "peer_analyses"),
            _Context({"peer_list": ["MSFT", {"symbol": "NVDA"}]}),
            None,
        )
    )

    assert calls == [
        ("MSFT", AnalysisMode.QUICK),
        ("NVDA", AnalysisMode.QUICK),
    ]
    assert output[0]["status"] == "success"
    assert output[0]["composite_score"] == 77
    assert output[1]["status"] == "success"
    assert output[1]["composite_score"] == 77
    assert tool_calls == 0

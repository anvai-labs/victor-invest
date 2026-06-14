import asyncio

from victor_invest.workflows import AnalysisMode, graphs
from victor_invest.workflows.state import AnalysisWorkflowState


class _FakeNodeResult:
    def __init__(self, error=None, success=True):
        self.error = error
        self.success = success


class _FakeGraphResult:
    """Mimics victor GraphExecutionResult (state dict, success, error)."""

    def __init__(self, *, success, state, error=None):
        self.success = success
        self.state = state
        self.error = error


def test_run_yaml_analysis_uses_provider_execution(monkeypatch):
    import victor_invest.workflows as workflows_pkg

    calls = {}

    class FakeProvider:
        async def run_compiled_workflow(self, workflow_name, context):
            calls["workflow_name"] = workflow_name
            calls["context"] = dict(context)
            return _FakeGraphResult(
                success=True,
                state={
                    "fundamental_analysis": {"status": "success"},
                    "technical_analysis": {"status": "success"},
                    "market_context": {"status": "success"},
                    "synthesis": {"recommendation": "BUY", "confidence": "HIGH"},
                },
            )

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    state = asyncio.run(graphs.run_yaml_analysis("aapl", AnalysisMode.STANDARD))

    assert calls == {"workflow_name": "standard", "context": {"symbol": "AAPL"}}
    assert state.symbol == "AAPL"
    assert state.mode == AnalysisMode.STANDARD
    assert state.synthesis.get("recommendation") == "BUY"
    assert state.recommendation.get("action") == "BUY"
    assert state.errors == []


def test_run_yaml_analysis_collects_top_level_and_node_errors(monkeypatch):
    import victor_invest.workflows as workflows_pkg

    class FakeProvider:
        async def run_compiled_workflow(self, workflow_name, context):
            return _FakeGraphResult(
                success=False,
                state={
                    "synthesis": {},
                    "_node_results": {
                        "run_synthesis": _FakeNodeResult(error="llm timeout", success=False),
                    },
                },
                error="workflow failed",
            )

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    state = asyncio.run(graphs.run_yaml_analysis("msft", AnalysisMode.COMPREHENSIVE))

    assert state.symbol == "MSFT"
    assert "workflow failed" in state.errors
    assert "run_synthesis: llm timeout" in state.errors


def test_run_yaml_analysis_flags_missing_synthesis_as_failure(monkeypatch):
    """On the compiled path a swallowed handler failure shows up as missing synthesis."""
    import victor_invest.workflows as workflows_pkg

    class FakeProvider:
        async def run_compiled_workflow(self, workflow_name, context):
            # success=True but synthesis absent (compiled executor swallows FAILED).
            return _FakeGraphResult(success=True, state={"technical_analysis": {"status": "success"}})

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    state = asyncio.run(graphs.run_yaml_analysis("aapl", AnalysisMode.STANDARD))

    assert state.synthesis == {}
    assert any("no synthesis output" in e for e in state.errors)


def test_run_yaml_analysis_maps_custom_mode_to_comprehensive(monkeypatch):
    import victor_invest.workflows as workflows_pkg

    calls = {}

    class FakeProvider:
        async def run_compiled_workflow(self, workflow_name, context):
            calls["workflow_name"] = workflow_name
            calls["context"] = dict(context)
            return _FakeGraphResult(
                success=True,
                state={"synthesis": {"recommendation": "HOLD"}},
            )

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    state = asyncio.run(graphs.run_yaml_analysis("aapl", AnalysisMode.CUSTOM))

    assert calls == {"workflow_name": "comprehensive", "context": {"symbol": "AAPL"}}
    assert state.mode == AnalysisMode.CUSTOM


def test_run_analysis_prefers_yaml_execution(monkeypatch):
    calls = {"yaml": 0, "stategraph": 0}

    async def fake_yaml(symbol, mode):
        calls["yaml"] += 1
        return AnalysisWorkflowState(symbol=symbol.upper(), mode=mode, synthesis={"status": "success"})

    async def fake_stategraph(symbol, mode):
        calls["stategraph"] += 1
        return AnalysisWorkflowState(symbol=symbol.upper(), mode=mode)

    monkeypatch.setattr(graphs, "run_yaml_analysis", fake_yaml)
    monkeypatch.setattr(graphs, "run_stategraph_analysis", fake_stategraph)

    state = asyncio.run(graphs.run_analysis("aapl", AnalysisMode.STANDARD))

    assert state.symbol == "AAPL"
    assert calls == {"yaml": 1, "stategraph": 0}


def test_run_analysis_falls_back_to_stategraph_on_yaml_failure(monkeypatch):
    calls = {"yaml": 0, "stategraph": 0}

    async def fake_yaml(symbol, mode):
        calls["yaml"] += 1
        raise RuntimeError("yaml failure")

    async def fake_stategraph(symbol, mode):
        calls["stategraph"] += 1
        return AnalysisWorkflowState(symbol=symbol.upper(), mode=mode, errors=["fallback"])

    monkeypatch.setattr(graphs, "run_yaml_analysis", fake_yaml)
    monkeypatch.setattr(graphs, "run_stategraph_analysis", fake_stategraph)

    state = asyncio.run(graphs.run_analysis("msft", AnalysisMode.QUICK))

    assert state.symbol == "MSFT"
    assert state.errors == ["fallback"]
    assert calls == {"yaml": 1, "stategraph": 1}

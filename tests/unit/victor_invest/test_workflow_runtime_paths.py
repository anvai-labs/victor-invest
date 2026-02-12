import asyncio

from victor_invest.workflows import AnalysisMode
from victor_invest.workflows import graphs


class _FakeNodeResult:
    def __init__(self, error=None):
        self.error = error


class _FakeContext(dict):
    def __init__(self, data, node_results=None):
        super().__init__(data)
        self.node_results = node_results or {}

    def to_dict(self):
        return dict(self)


class _FakeWorkflowResult:
    def __init__(self, *, success, context, error=None):
        self.success = success
        self.context = context
        self.error = error


def test_run_yaml_analysis_uses_provider_execution(monkeypatch):
    import victor_invest.workflows as workflows_pkg

    calls = {}

    class FakeProvider:
        async def run_workflow_with_handlers(self, workflow_name, context):
            calls["workflow_name"] = workflow_name
            calls["context"] = dict(context)
            return _FakeWorkflowResult(
                success=True,
                context=_FakeContext(
                    {
                        "fundamental_analysis": {"status": "success"},
                        "technical_analysis": {"status": "success"},
                        "market_context": {"status": "success"},
                        "synthesis": {"recommendation": "BUY", "confidence": "HIGH"},
                    }
                ),
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
        async def run_workflow_with_handlers(self, workflow_name, context):
            return _FakeWorkflowResult(
                success=False,
                context=_FakeContext(
                    {"synthesis": {}},
                    node_results={
                        "run_synthesis": _FakeNodeResult(error="llm timeout"),
                    },
                ),
                error="workflow failed",
            )

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    state = asyncio.run(graphs.run_yaml_analysis("msft", AnalysisMode.COMPREHENSIVE))

    assert state.symbol == "MSFT"
    assert "workflow failed" in state.errors
    assert "run_synthesis: llm timeout" in state.errors

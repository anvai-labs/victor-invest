import asyncio

import victor_invest.workflows as workflows_pkg
from victor_invest.handlers import ProcessBacktestBatchHandler
from victor_invest.workflows import rl_backtest
from victor_invest.workflows.rl_backtest import RLBacktestWorkflowState


class _FakeNodeResult:
    def __init__(self, error=None):
        self.error = error


class _FakeWorkflowResult:
    def __init__(self, *, context, error=None):
        self.success = error is None
        self.context = context
        self.error = error


class _Ctx:
    def __init__(self, data):
        self._data = dict(data)

    def get(self, key, default=None):
        return self._data.get(key, default)


class _Node:
    def __init__(self, node_id, output_key=None):
        self.id = node_id
        self.output_key = output_key


def test_run_rl_backtest_uses_yaml_provider_path(monkeypatch):
    calls = {}

    class FakeProvider:
        async def run_workflow_with_handlers(self, workflow_name, context):
            calls["workflow_name"] = workflow_name
            calls["context"] = dict(context)
            return _FakeWorkflowResult(
                context={
                    "backtest_results": {
                        "predictions": [{"status": "recorded"}],
                        "metadata": {"summary": {"symbol": "AAPL"}},
                    }
                }
            )

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    state = asyncio.run(
        rl_backtest.run_rl_backtest(
            symbol="AAPL",
            lookback_months_list=[12, 24],
            interval="quarterly",
            use_yaml_workflow=True,
        )
    )

    assert calls == {
        "workflow_name": "rl_backtest",
        "context": {
            "symbol": "AAPL",
            "max_lookback_months": 120,
            "interval": "quarterly",
            "lookback_dates": [12, 24],
        },
    }
    assert state.predictions == [{"status": "recorded"}]
    assert state.metadata == {"summary": {"symbol": "AAPL"}}
    assert "yaml_workflow_complete" in state.completed_steps


def test_run_rl_backtest_falls_back_to_stategraph_when_yaml_provider_fails(monkeypatch):
    class FailingProvider:
        async def run_workflow_with_handlers(self, workflow_name, context):
            raise RuntimeError("provider unavailable")

    class _FakeCompiled:
        async def invoke(self, initial_state):
            result = dict(initial_state)
            result["predictions"] = [{"status": "recorded", "source": "stategraph"}]
            result["completed_steps"] = ["finalize_backtest"]
            return result

    class _FakeGraph:
        def compile(self):
            return _FakeCompiled()

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FailingProvider)
    monkeypatch.setattr(rl_backtest, "build_rl_backtest_graph", lambda: _FakeGraph())

    state = asyncio.run(
        rl_backtest.run_rl_backtest(
            symbol="MSFT",
            lookback_months_list=[12],
            interval="quarterly",
            use_yaml_workflow=True,
        )
    )

    assert state.symbol == "MSFT"
    assert state.predictions == [{"status": "recorded", "source": "stategraph"}]
    assert "finalize_backtest" in state.completed_steps


def test_process_backtest_batch_handler_forces_stategraph_execution(monkeypatch):
    import victor_invest.workflows.rl_backtest as rl_backtest_module

    calls = {}

    async def fake_run_rl_backtest(
        symbol,
        lookback_months_list=None,
        max_lookback_months=120,
        interval="quarterly",
        use_yaml_workflow=True,
    ):
        calls["symbol"] = symbol
        calls["lookback_months_list"] = list(lookback_months_list or [])
        calls["interval"] = interval
        calls["use_yaml_workflow"] = use_yaml_workflow
        return RLBacktestWorkflowState(
            symbol=symbol,
            lookback_months_list=list(lookback_months_list or []),
            interval=interval,
            predictions=[{"status": "recorded"}],
        )

    monkeypatch.setattr(rl_backtest_module, "run_rl_backtest", fake_run_rl_backtest)

    handler = ProcessBacktestBatchHandler()
    output, tool_calls = asyncio.run(
        handler.execute(
            _Node("process_dates", "backtest_results"),
            _Ctx(
                {
                    "symbol": "AAPL",
                    "lookback_dates": [12, 24],
                    "interval": "quarterly",
                }
            ),
            None,
        )
    )

    assert calls == {
        "symbol": "AAPL",
        "lookback_months_list": [12, 24],
        "interval": "quarterly",
        "use_yaml_workflow": False,
    }
    assert output["predictions"] == [{"status": "recorded"}]
    assert tool_calls == 0


def test_convert_yaml_result_to_state_collects_top_level_and_node_errors():
    workflow_result = _FakeWorkflowResult(
        context=type(
            "_CtxWithNodeResults",
            (),
            {
                "get": lambda self, key, default=None: default,
                "node_results": {"process_dates": _FakeNodeResult(error="timeout")},
            },
        )(),
        error="workflow failed",
    )

    state = rl_backtest._convert_yaml_result_to_state(  # noqa: SLF001 - test coverage for conversion contract
        symbol="AAPL",
        lookback_months_list=[12],
        interval="quarterly",
        workflow_result=workflow_result,
    )

    assert "workflow failed" in state.errors
    assert "process_dates: timeout" in state.errors

import asyncio

import victor_invest.workflows.rl_backtest as rl_backtest_module
from victor_invest.handlers import ProcessBacktestBatchHandler
from victor_invest.workflows import rl_backtest
from victor_invest.workflows.rl_backtest import RLBacktestWorkflowState


class _Ctx:
    def __init__(self, data):
        self._data = dict(data)

    def get(self, key, default=None):
        return self._data.get(key, default)


class _Node:
    def __init__(self, node_id, output_key=None):
        self.id = node_id
        self.output_key = output_key


class _CopyOnWriteLikeState:
    def __init__(self, data):
        self._data = dict(data)

    def get_state(self):
        return self._data


def test_ensure_state_unwraps_copy_on_write_state():
    state = rl_backtest._ensure_state(  # noqa: SLF001 - compatibility guard for Victor runtime wrapper
        _CopyOnWriteLikeState(
            {
                "symbol": "AAPL",
                "lookback_months_list": [3, 6],
                "interval": "quarterly",
                "predictions": [{"status": "recorded"}],
            }
        )
    )

    assert state.symbol == "AAPL"
    assert state.lookback_months_list == [3, 6]
    assert state.predictions == [{"status": "recorded"}]


def test_extract_valuation_payload_supports_current_valuation_tool_shape():
    fair_values, weights, blended_fair_value, tier = rl_backtest._extract_valuation_payload(  # noqa: SLF001
        {
            "consensus_fair_value": 205.58,
            "tier_classification": "balanced_default",
            "models": {
                "dcf": {"fair_value_per_share": 111.58, "weight": 30.0},
                "pe": {"fair_value_per_share": 339.58, "weight": 25.0},
                "ggm": {"fair_value_per_share": 14.99, "weight": 0.0},
            },
        }
    )

    assert fair_values == {"dcf": 111.58, "pe": 339.58, "ggm": 14.99}
    assert weights == {"dcf": 30.0, "pe": 25.0, "ggm": 0.0}
    assert blended_fair_value == 205.58
    assert tier == "balanced_default"


def test_run_rl_backtest_uses_single_stategraph_path(monkeypatch):
    """run_rl_backtest has a single execution path: the StateGraph."""

    class _FakeCompiled:
        async def invoke(self, initial_state):
            result = dict(initial_state)
            result["predictions"] = [{"status": "recorded", "source": "stategraph"}]
            result["completed_steps"] = ["finalize_backtest"]
            return result

    class _FakeGraph:
        def compile(self):
            return _FakeCompiled()

    monkeypatch.setattr(rl_backtest, "build_rl_backtest_graph", lambda: _FakeGraph())

    state = asyncio.run(
        rl_backtest.run_rl_backtest(
            symbol="MSFT",
            lookback_months_list=[12],
            interval="quarterly",
        )
    )

    assert state.symbol == "MSFT"
    assert state.predictions == [{"status": "recorded", "source": "stategraph"}]
    assert "finalize_backtest" in state.completed_steps


def test_run_rl_backtest_no_longer_accepts_use_yaml_workflow():
    """The dual-path use_yaml_workflow toggle has been removed."""
    import inspect

    params = inspect.signature(rl_backtest.run_rl_backtest).parameters
    assert "use_yaml_workflow" not in params


def test_process_backtest_batch_handler_runs_per_symbol(monkeypatch):
    calls = {}

    async def fake_run_rl_backtest(
        symbol,
        lookback_months_list=None,
        max_lookback_months=120,
        interval="quarterly",
    ):
        calls["symbol"] = symbol
        calls["lookback_months_list"] = list(lookback_months_list or [])
        calls["interval"] = interval
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
    }
    assert output["predictions"] == [{"status": "recorded"}]
    assert tool_calls == 0

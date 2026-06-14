import asyncio
from datetime import date

from victor_invest.tools.rl_backtest import RLBacktestTool


class _FakeOutcomeTracker:
    def __init__(self):
        self.calls = []

    def record_prediction_with_outcomes(self, **kwargs):
        self.calls.append(kwargs)
        return len(self.calls)


def test_record_prediction_uses_multi_horizon_outcome_tracker(monkeypatch):
    tracker = _FakeOutcomeTracker()
    tool = RLBacktestTool()
    tool._outcome_tracker = tracker  # noqa: SLF001 - direct service injection for unit test

    async def fake_get_metadata(symbol):
        return {"beta": 1.2}

    async def fake_get_multi_period_data(symbol, analysis_date, current_price, beta, conviction_band=0.10):
        return {
            "entry_date": analysis_date.isoformat(),
            "conviction_band": conviction_band,
            "long_predicted_fv": round(current_price * (1 + conviction_band), 4),
            "short_predicted_fv": round(current_price * (1 - conviction_band), 4),
            "prices": {
                "1m": 101.0,
                "3m": 103.0,
                "6m": 106.0,
                "12m": 112.0,
                "18m": 118.0,
                "24m": 124.0,
                "36m": 136.0,
            },
            "exit_dates": {
                "1m": "2024-02-01",
                "3m": "2024-04-01",
                "6m": "2024-07-01",
                "12m": "2025-01-01",
                "18m": "2025-07-01",
                "24m": "2026-01-01",
                "36m": "2027-01-01",
            },
            "long_rewards": {
                "1m": 0.1,
                "3m": 0.3,
                "6m": 0.6,
                "12m": 0.9,
                "18m": 0.7,
                "24m": 0.5,
                "36m": 0.2,
            },
            "short_rewards": {
                "1m": -0.1,
                "3m": -0.3,
                "6m": -0.6,
                "12m": -0.9,
                "18m": -0.7,
                "24m": -0.5,
                "36m": -0.2,
            },
        }

    monkeypatch.setattr(tool, "_get_metadata", fake_get_metadata)
    monkeypatch.setattr(tool, "_get_multi_period_data", fake_get_multi_period_data)

    result = asyncio.run(
        tool._record_prediction(  # noqa: SLF001 - unit coverage for DB recording adapter
            symbol="AAPL",
            analysis_date=date(2024, 1, 1),
            current_price=100.0,
            fair_value=120.0,
            fair_values={"dcf": 125.0, "pe": 115.0},
            weights={"dcf": 60.0, "pe": 40.0},
            tier_classification="balanced",
            context_features={"lookback_months": 3},
        )
    )

    assert result.success is True
    assert result.output["record_ids"] == [1, 2]
    assert [call["position_type"] for call in tracker.calls] == ["LONG", "SHORT"]

    long_call = tracker.calls[0]
    assert long_call["model_fair_values"] == {"dcf": 125.0, "pe": 115.0}
    assert long_call["model_weights"] == {"dcf": 60.0, "pe": 40.0}
    assert long_call["actual_price_365d"] == 112.0
    assert long_call["reward_548d"] == 0.7
    assert long_call["exit_date_1095d"] == date(2027, 1, 1)
    # Synthetic FV is recorded per position so features and labels stay coherent.
    assert long_call["position_predicted_fv"] == 110.0
    assert long_call["conviction_band"] == 0.10
    assert long_call["multi_period_rewards"] == {
        "long": {
            "1m": 0.1,
            "3m": 0.3,
            "6m": 0.6,
            "12m": 0.9,
            "18m": 0.7,
            "24m": 0.5,
            "36m": 0.2,
        }
    }

    short_call = tracker.calls[1]
    assert short_call["reward_90d"] == -0.3
    assert short_call["per_model_rewards"]["position_type"] == "SHORT"
    assert short_call["position_predicted_fv"] == 90.0


def test_record_prediction_skips_non_positive_fair_value(monkeypatch):
    tracker = _FakeOutcomeTracker()
    tool = RLBacktestTool()
    tool._outcome_tracker = tracker  # noqa: SLF001 - direct service injection for unit test

    async def fake_get_metadata(symbol):
        return {"beta": 1.0}

    async def fake_get_multi_period_data(symbol, analysis_date, current_price, beta, conviction_band=0.10):
        return {"conviction_band": conviction_band, "prices": {}, "long_rewards": {}, "short_rewards": {}}

    monkeypatch.setattr(tool, "_get_metadata", fake_get_metadata)
    monkeypatch.setattr(tool, "_get_multi_period_data", fake_get_multi_period_data)

    result = asyncio.run(
        tool._record_prediction(  # noqa: SLF001 - unit coverage for quality gate
            symbol="AAPL",
            analysis_date=date(2024, 1, 1),
            current_price=100.0,
            fair_value=0.0,  # non-positive blended FV must be skipped
            fair_values={},
            weights={},
            tier_classification="balanced",
            context_features={"lookback_months": 3},
        )
    )

    assert result.success is True
    assert result.output["status"] == "skipped"
    assert result.output["record_ids"] == []
    assert tracker.calls == []  # nothing persisted

"""A name that delists mid-horizon must be scored, not silently dropped.

Without this, the only observations that ever produce a reward are the ones that
survived to the exit date -- which is survivorship bias reintroduced through the
back door of "no price, no label". A bankruptcy is the most informative outcome a
policy can learn from, and it was the one being discarded.

These tests were adapted from PR #57 rather than taken from it. #57's versions
assert ``long_rewards``/``short_rewards`` -- a mirrored pair derived from a
synthetic fair value, ``current_price * (1 +/- conviction_band)``. That is the
same defect audit finding B removed, parameterised rather than hardcoded: the
reward becomes a function of realised return alone, independent of what the model
predicted. develop emits one reward series scored against the real blended fair
value, and these tests hold that line while adding the terminal-exit behaviour.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from investigator.domain.services.market_data.delisting_service import DelistingRecord, DelistingService
from investigator.domain.services.rl.reward_calculator import get_reward_calculator
from victor_invest.tools.rl_backtest import RLBacktestTool


class _NoPriceService:
    """A delisted name: no future market price at any horizon."""

    def get_price(self, symbol, target_date, search_days=5):
        return None


class _FakeDelistingService:
    def __init__(self, record: DelistingRecord | None):
        self._record = record

    def get_delisting(self, symbol: str) -> DelistingRecord | None:
        return self._record

    terminal_exit_price = staticmethod(DelistingService.terminal_exit_price)


def _tool(record: DelistingRecord | None) -> RLBacktestTool:
    tool = RLBacktestTool()
    tool._price_service = _NoPriceService()
    tool._reward_calculator = get_reward_calculator()
    tool._delisting_service = _FakeDelistingService(record)
    return tool


@pytest.mark.asyncio
async def test_a_bankruptcy_spanning_the_horizon_realises_a_terminal_exit():
    """Held through a bankruptcy, the position exits at the recovery value."""
    analysis = date(2020, 1, 1)
    record = DelistingRecord("ZZZ", analysis + timedelta(days=200), reason="bankruptcy", last_price=5.0)

    data = await _tool(record)._get_multi_period_data(
        "ZZZ", analysis, current_price=100.0, beta=1.0, predicted_fv=130.0
    )

    assert data["delisted"] is True

    # 30 days out, the delisting has not happened yet: no price, no terminal event.
    assert data["prices"]["1m"] is None
    assert data["terminal_exits"]["1m"] is False
    assert data["rewards"]["1m"] is None

    # 365 days out, the position was held through the delisting.
    assert data["terminal_exits"]["12m"] is True
    assert data["exit_dates"]["12m"] == record.delist_date.isoformat()
    assert data["prices"]["12m"] is not None


@pytest.mark.asyncio
async def test_a_bullish_call_into_a_bankruptcy_is_punished():
    """The reward must follow the model's own conviction, not realised return."""
    analysis = date(2020, 1, 1)
    record = DelistingRecord("ZZZ", analysis + timedelta(days=200), reason="bankruptcy", last_price=5.0)

    bullish = await _tool(record)._get_multi_period_data(
        "ZZZ", analysis, current_price=100.0, beta=1.0, predicted_fv=130.0
    )
    bearish = await _tool(record)._get_multi_period_data(
        "ZZZ", analysis, current_price=100.0, beta=1.0, predicted_fv=70.0
    )

    assert bullish["direction"] == "LONG"
    assert bearish["direction"] == "SHORT"
    assert bullish["rewards"]["12m"] < 0, "a LONG into a near-total loss must score negative"
    assert bearish["rewards"]["12m"] > 0, "a SHORT into a near-total loss must score positive"


@pytest.mark.asyncio
async def test_one_reward_series_not_a_mirrored_pair():
    """#57 emitted long_rewards/short_rewards from a synthetic fair value.

    That is audit finding B with a parameter in place of a constant. The contract
    is one series, scored against the fair value the model actually produced.
    """
    analysis = date(2020, 1, 1)
    record = DelistingRecord("ZZZ", analysis + timedelta(days=200), reason="bankruptcy", last_price=5.0)

    data = await _tool(record)._get_multi_period_data(
        "ZZZ", analysis, current_price=100.0, beta=1.0, predicted_fv=130.0
    )

    assert "rewards" in data
    assert "long_rewards" not in data and "short_rewards" not in data
    assert "long_predicted_fv" not in data and "short_predicted_fv" not in data, (
        "synthetic per-direction fair values are back"
    )


@pytest.mark.asyncio
async def test_without_a_delisting_missing_prices_stay_dropped():
    """Terminal exits apply only to real delistings; nothing is invented."""
    data = await _tool(None)._get_multi_period_data(
        "ZZZ", date(2020, 1, 1), current_price=100.0, beta=1.0, predicted_fv=130.0
    )

    assert data["delisted"] is False
    assert all(v is None for v in data["prices"].values())
    assert all(v is False for v in data["terminal_exits"].values())
    assert all(v is None for v in data["rewards"].values())


@pytest.mark.asyncio
async def test_no_prediction_still_scores_nothing_even_with_a_terminal_exit():
    """A terminal exit supplies a price, not a conviction to score it against."""
    analysis = date(2020, 1, 1)
    record = DelistingRecord("ZZZ", analysis + timedelta(days=200), reason="bankruptcy", last_price=5.0)

    data = await _tool(record)._get_multi_period_data("ZZZ", analysis, current_price=100.0, beta=1.0)

    assert data["terminal_exits"]["12m"] is True
    assert data["prices"]["12m"] is not None
    assert data["direction"] is None
    assert all(v is None for v in data["rewards"].values())


@pytest.mark.asyncio
async def test_a_total_loss_is_not_recorded_as_a_neutral_outcome():
    """The exact-zero exit price is a trap, and the floor is what avoids it.

    A zero-recovery bankruptcy prices the exit at 0.0. RewardCalculator treats
    ``actual_price <= 0`` as unusable data and returns reward 0.0 -- so without a
    floor, the single most informative outcome a policy can see would be written
    to the training set as *average*. That is worse than dropping it, because it
    looks like a real observation.
    """
    analysis = date(2020, 1, 1)
    record = DelistingRecord("ZZZ", analysis + timedelta(days=200), reason="bankruptcy", last_price=5.0)

    # Premise: recovery really is zero, so the unfloored price would be 0.0.
    assert DelistingService.terminal_exit_price(record, analysis + timedelta(days=365)) == 0.0

    data = await _tool(record)._get_multi_period_data(
        "ZZZ", analysis, current_price=100.0, beta=1.0, predicted_fv=130.0
    )

    assert data["prices"]["12m"] > 0, "a zero exit price would be scored as neutral"
    assert data["rewards"]["12m"] < -0.5, (
        f"a LONG into a total loss scored {data['rewards']['12m']}; near zero means the guard fired"
    )


@pytest.mark.asyncio
async def test_tool_without_a_delisting_service_behaves_as_before():
    """The service is optional; absence must not raise."""
    tool = RLBacktestTool()
    tool._price_service = _NoPriceService()
    tool._reward_calculator = get_reward_calculator()
    tool._delisting_service = None

    data = await tool._get_multi_period_data("ZZZ", date(2020, 1, 1), current_price=100.0, beta=1.0, predicted_fv=130.0)

    assert data["delisted"] is False
    assert all(v is False for v in data["terminal_exits"].values())

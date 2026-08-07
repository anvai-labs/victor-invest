"""Rewards must follow the model's actual fair value, not a synthetic stand-in.

Audit finding B (CRITICAL): `_get_multi_period_data` computed rewards from
`predicted_fv = current_price * 1.10` for LONG and `* 0.90` for SHORT, and wrote
both per observation with mirrored rewards. The code said so itself:

    # We simulate this by setting fake fair values to force the desired direction

`RewardCalculator.calculate` uses `predicted_fv` for its *sign*, so the reward
became a pure function of realised forward return -- independent of what the model
actually predicted. The persisted fair-value features were therefore noise
relative to the label the policy learns from.

These tests pin the corrected contract: direction comes from the real blended fair
value, and one reward is emitted per observation rather than a mirrored pair.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from victor_invest.tools.rl_backtest import RLBacktestTool


def _tool(future_price: float) -> RLBacktestTool:
    tool = RLBacktestTool()
    price_service = MagicMock()
    price_service.get_price.return_value = future_price
    tool._price_service = price_service

    calc = MagicMock()

    def _calculate(*, predicted_fv, price_at_prediction, actual_price, days, beta):
        # Mirror the real calculator's contract: sign follows predicted_fv vs price.
        direction = 1.0 if predicted_fv > price_at_prediction else -1.0
        realised = (actual_price - price_at_prediction) / price_at_prediction
        return MagicMock(reward=direction * realised)

    calc.calculate.side_effect = _calculate
    tool._reward_calculator = calc
    return tool


@pytest.mark.asyncio
async def test_direction_follows_the_real_fair_value_not_a_synthetic_one():
    """A bullish fair value must produce a LONG-signed reward, and vice versa."""
    tool = _tool(future_price=110.0)

    bullish = await tool._get_multi_period_data("AAPL", date(2025, 1, 1), 100.0, 1.0, predicted_fv=130.0)
    bearish = await tool._get_multi_period_data("AAPL", date(2025, 1, 1), 100.0, 1.0, predicted_fv=70.0)

    called = tool._reward_calculator.calculate.call_args_list
    assert called, "reward calculator was never invoked"
    used = {c.kwargs["predicted_fv"] for c in called}
    assert 130.0 in used and 70.0 in used, (
        f"rewards were computed from {used}, not the supplied fair values. "
        "A synthetic price multiple means the label ignores the model's conviction."
    )
    assert 110.0 not in used and 90.0 not in used, "synthetic +-10% fair values are still in use"

    period = next(iter(bullish["rewards"]))
    assert bullish["rewards"][period] > 0, "price rose and the model was bullish: reward should be positive"
    assert bearish["rewards"][period] < 0, "price rose and the model was bearish: reward should be negative"


@pytest.mark.asyncio
async def test_one_reward_per_observation_not_a_mirrored_pair():
    """Writing both a LONG and a SHORT row per observation doubles and cancels the signal."""
    tool = _tool(future_price=110.0)
    result = await tool._get_multi_period_data("AAPL", date(2025, 1, 1), 100.0, 1.0, predicted_fv=130.0)

    assert "rewards" in result, "expected a single rewards series"
    assert "long_rewards" not in result and "short_rewards" not in result, (
        "mirrored LONG/SHORT reward series are still being emitted"
    )


@pytest.mark.asyncio
async def test_direction_is_recorded_alongside_the_reward():
    """The label is only interpretable if the direction it came from is persisted."""
    tool = _tool(future_price=110.0)
    result = await tool._get_multi_period_data("AAPL", date(2025, 1, 1), 100.0, 1.0, predicted_fv=130.0)
    assert result.get("direction") == "LONG"

    result = await tool._get_multi_period_data("AAPL", date(2025, 1, 1), 100.0, 1.0, predicted_fv=70.0)
    assert result.get("direction") == "SHORT"


@pytest.mark.asyncio
async def test_missing_fair_value_yields_no_reward_rather_than_a_guess():
    """Without a prediction there is no conviction to score, so emit nothing."""
    tool = _tool(future_price=110.0)
    result = await tool._get_multi_period_data("AAPL", date(2025, 1, 1), 100.0, 1.0, predicted_fv=None)

    assert result.get("direction") is None
    assert all(v is None for v in result["rewards"].values()), (
        "a reward was invented despite the model having made no prediction"
    )

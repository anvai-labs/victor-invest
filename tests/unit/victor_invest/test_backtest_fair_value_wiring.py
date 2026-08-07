"""The point-in-time fair value must actually reach the reward calculator.

Audit finding B removed the synthetic ``current_price * 1.10`` fair value, so a
reward is now only scored when a real prediction is supplied. That fix was
correct, but it exposed a wiring gap the old synthetic value had been masking:
nothing in the workflow ever hands a fair value to the scorer.

Two independent breaks, either of which alone zeroes the training signal:

1. ``ValuationTool.execute(model="all")`` emits ``consensus_fair_value`` and a
   ``models`` map. ``record_predictions`` read ``blended_fair_value``,
   ``fair_values`` and ``weights`` -- keys the tool has never emitted -- so it
   got ``0`` and ``{}`` every time. ``_record_prediction`` then computes
   ``predicted_fv = fair_value or None``, and ``0 or None`` is ``None``.

2. The ``calculate_rewards`` action accepts ``fair_value`` on ``execute`` but
   never forwards it to ``_calculate_rewards``.

Net effect before this change: the point-in-time valuation was computed, at
real cost, and then discarded -- every persisted reward was ``None``. The
existing coupling tests pass ``predicted_fv`` directly, which is precisely why
they never caught it. These tests exercise the hand-off instead.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from victor_invest.tools.rl_backtest import RLBacktestTool

# Shaped exactly like ValuationTool._run_all_models output_dict.
VALUATION_TOOL_OUTPUT: dict[str, Any] = {
    "symbol": "AAPL",
    "current_price": 100.0,
    "models": {
        "dcf": {"fair_value_per_share": 130.0, "weight": 0.6},
        "pe": {"fair_value_per_share": 120.0, "weight": 0.4},
    },
    "models_applied": ["dcf", "pe"],
    "consensus_fair_value": 126.0,
    "consensus_upside": 26.0,
    "tier_classification": "growth",
}


def _rl_tool(future_price: float = 110.0) -> RLBacktestTool:
    """An RLBacktestTool with stubbed price and reward services."""
    tool = RLBacktestTool()

    price_service = MagicMock()
    price_service.get_price.return_value = future_price
    tool._price_service = price_service

    metadata_service = MagicMock()
    metadata_service.get_metadata.return_value = None
    tool._metadata_service = metadata_service

    calc = MagicMock()

    def _calculate(*, predicted_fv, price_at_prediction, actual_price, days, beta):
        direction = 1.0 if predicted_fv > price_at_prediction else -1.0
        realised = (actual_price - price_at_prediction) / price_at_prediction
        return MagicMock(reward=direction * realised)

    calc.calculate.side_effect = _calculate
    tool._reward_calculator = calc

    # ensure_initialized() must not try to reach a database.
    tool.ensure_initialized = AsyncMock()
    return tool


@pytest.mark.asyncio
async def test_calculate_rewards_action_scores_the_supplied_fair_value():
    """`execute(action="calculate_rewards", fair_value=...)` must reach the scorer."""
    tool = _rl_tool(future_price=110.0)

    result = await tool.execute(
        action="calculate_rewards",
        symbol="AAPL",
        analysis_date=date(2025, 1, 1),
        current_price=100.0,
        fair_value=126.0,
    )

    assert result.success, result.error
    multi_period = result.output["multi_period"]

    assert multi_period["direction"] == "LONG", (
        "the fair value never reached _get_multi_period_data, so no direction was derived"
    )
    rewards = multi_period["rewards"]
    assert any(v is not None for v in rewards.values()), (
        "every reward is None: calculate_rewards discarded the fair value it was given"
    )

    used = {c.kwargs["predicted_fv"] for c in tool._reward_calculator.calculate.call_args_list}
    assert used == {126.0}, f"scorer saw {used}, not the supplied fair value"


@pytest.mark.asyncio
async def test_calculate_rewards_without_a_fair_value_still_scores_nothing():
    """Omitting the fair value must stay a no-score, not fall back to a guess."""
    tool = _rl_tool(future_price=110.0)

    result = await tool.execute(
        action="calculate_rewards",
        symbol="AAPL",
        analysis_date=date(2025, 1, 1),
        current_price=100.0,
    )

    assert result.success, result.error
    multi_period = result.output["multi_period"]
    assert multi_period["direction"] is None
    assert all(v is None for v in multi_period["rewards"].values())


def test_extractor_reads_the_keys_the_valuation_tool_actually_emits():
    """The recorder must read `consensus_fair_value`/`models`, not invented keys."""
    from victor_invest.workflows.rl_backtest import extract_valuation_fields

    blended, fair_values, weights, tier = extract_valuation_fields(VALUATION_TOOL_OUTPUT)

    assert blended == 126.0, (
        f"blended fair value came back as {blended!r}; reading a key the tool "
        "does not emit yields 0, and `0 or None` disables the reward entirely"
    )
    assert fair_values == {"dcf": 130.0, "pe": 120.0}
    assert weights == {"dcf": 0.6, "pe": 0.4}
    assert tier == "growth"


def test_extractor_is_defensive_about_missing_or_malformed_valuations():
    """A failed valuation must degrade to no-prediction, not to a bogus zero."""
    from victor_invest.workflows.rl_backtest import extract_valuation_fields

    for empty in ({}, None, "not-a-dict", {"models": None}):
        blended, fair_values, weights, tier = extract_valuation_fields(empty)
        assert blended is None, f"{empty!r} should yield no prediction, got {blended!r}"
        assert fair_values == {}
        assert weights == {}
        assert tier == ""


@pytest.mark.asyncio
async def test_workflow_hands_the_valuation_fair_value_to_the_reward_step(monkeypatch):
    """The calculate_rewards node must pass the fair value it already computed."""
    import victor_invest.workflows.rl_backtest as wf

    captured: dict[str, Any] = {}

    async def _fake_execute(**kwargs):
        captured.update(kwargs)
        return MagicMock(success=True, output={"multi_period": {"rewards": {}, "direction": "LONG"}})

    fake_tool = MagicMock()
    fake_tool.execute = _fake_execute
    monkeypatch.setattr(wf, "_get_rl_backtest_tool", AsyncMock(return_value=fake_tool))

    state = wf.RLBacktestWorkflowState(symbol="AAPL")
    state.valuation_results = {
        12: {
            "analysis_date": "2025-01-01",
            "price": 100.0,
            "valuation": VALUATION_TOOL_OUTPUT,
        }
    }

    await wf.calculate_rewards(state)

    assert captured.get("fair_value") == 126.0, (
        f"reward step was called with fair_value={captured.get('fair_value')!r}; "
        "the point-in-time valuation was computed and then dropped"
    )

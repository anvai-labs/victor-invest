"""P3 evaluation-robustness tests: reward frictions + significance utilities."""

import numpy as np

from investigator.domain.services.rl.evaluation import (
    block_bootstrap_ci,
    dedup_mirrored_positions,
    effective_sample_size,
    evaluate_reward_significance,
    newey_west_lags,
    newey_west_tstat,
    quantify_survivorship_bias,
    walk_forward_splits,
)
from investigator.domain.services.rl.reward_calculator import RewardCalculator


# ----------------------------------------------------- reward calculator frictions
def _calc():
    return RewardCalculator()


def test_defaults_are_frictionless_and_backward_compatible():
    c = _calc()
    r = c.calculate(predicted_fv=275.0, price_at_prediction=250.0, actual_price=280.0, days=90)
    assert r.transaction_cost == 0.0
    assert r.borrow_cost == 0.0
    assert r.benchmark_return is None
    assert r.gross_position_return == r.position_return  # no frictions applied


def test_transaction_cost_reduces_return():
    c = _calc()
    base = c.calculate(275.0, 250.0, 280.0, days=90)
    withcost = c.calculate(275.0, 250.0, 280.0, days=90, transaction_cost_bps=50)
    assert abs(withcost.transaction_cost - 0.005) < 1e-9
    assert withcost.position_return < base.position_return
    assert abs((base.position_return - withcost.position_return) - 0.005) < 1e-9


def test_borrow_cost_applies_only_to_shorts():
    c = _calc()
    short = c.calculate(225.0, 250.0, 240.0, days=365, borrow_cost_bps_annual=300)
    longp = c.calculate(275.0, 250.0, 260.0, days=365, borrow_cost_bps_annual=300)
    assert abs(short.borrow_cost - 0.03) < 1e-9  # 300bps * 365/365
    assert longp.borrow_cost == 0.0


def test_borrow_cost_prorated_by_days():
    c = _calc()
    half = c.calculate(225.0, 250.0, 240.0, days=182, borrow_cost_bps_annual=400)
    assert abs(half.borrow_cost - (0.04 * 182 / 365)) < 1e-9


def test_benchmark_relative_nets_market_beta():
    c = _calc()
    # Long that exactly matched the benchmark -> ~zero alpha.
    alpha = c.calculate(275.0, 250.0, 280.0, days=90, benchmark_return=0.12)
    assert abs(alpha.position_return) < 1e-9  # raw 0.12 - 0.12
    assert alpha.benchmark_return == 0.12
    # Short alpha: position profits when stock drops; benchmark up hurts a short's alpha.
    short = c.calculate(225.0, 250.0, 240.0, days=90, benchmark_return=0.05)
    # gross short return = +0.04; alpha = 0.04 - (-1)*0.05 = 0.09
    assert abs(short.position_return - 0.09) < 1e-9


# ----------------------------------------------------- significance utilities
def test_newey_west_lags_rule_of_thumb():
    assert newey_west_lags(1) == 0
    assert newey_west_lags(100) >= 1


def test_newey_west_detects_nonzero_mean():
    rng = np.random.default_rng(0)
    data = 0.05 + rng.normal(0, 0.01, size=200)  # strongly positive mean, low noise
    res = newey_west_tstat(data)
    assert res.n == 200
    assert res.mean > 0
    assert res.p_value < 0.05  # significant


def test_newey_west_zero_mean_not_significant():
    rng = np.random.default_rng(1)
    data = rng.normal(0, 0.05, size=200)  # mean ~0
    res = newey_west_tstat(data)
    assert res.p_value > 0.05


def test_newey_west_handles_tiny_samples():
    assert newey_west_tstat([]).n == 0
    one = newey_west_tstat([0.1])
    assert one.n == 1 and one.mean == 0.1


def test_block_bootstrap_ci_is_deterministic_and_brackets_mean():
    data = list(np.linspace(-0.1, 0.3, 120))
    low1, high1, mean1 = block_bootstrap_ci(data, seed=7)
    low2, high2, mean2 = block_bootstrap_ci(data, seed=7)
    assert (low1, high1, mean1) == (low2, high2, mean2)  # deterministic
    assert low1 <= mean1 <= high1


def test_effective_sample_size_downweights_overlap():
    # 100 quarterly (≈91d) observations of a 365d horizon overlap ~4x.
    ess = effective_sample_size(100, horizon_days=365, sampling_interval_days=91)
    assert ess < 100
    assert abs(ess - 100 / (365 / 91)) < 1e-6
    # No overlap when horizon <= interval.
    assert effective_sample_size(100, horizon_days=30, sampling_interval_days=91) == 100.0


def test_walk_forward_splits_are_ordered_and_embargoed():
    splits = walk_forward_splits(120, n_splits=4, embargo=5)
    assert len(splits) >= 1
    for s in splits:
        # train strictly precedes test, with the embargo gap.
        assert max(s.train_index) < min(s.test_index)
        assert min(s.test_index) - max(s.train_index) > 5


def test_dedup_mirrored_positions_collapses_pairs():
    rows = [
        {"symbol": "AAPL", "analysis_date": "2020-01-01", "position_type": "LONG", "reward_90d": 0.3},
        {"symbol": "AAPL", "analysis_date": "2020-01-01", "position_type": "SHORT", "reward_90d": -0.3},
        {"symbol": "MSFT", "analysis_date": "2020-01-01", "position_type": "LONG", "reward_90d": 0.1},
    ]
    deduped, dropped = dedup_mirrored_positions(rows, keep="LONG")
    assert dropped == 1
    assert len(deduped) == 2
    aapl = next(r for r in deduped if r["symbol"] == "AAPL")
    assert aapl["position_type"] == "LONG"


def test_evaluate_reward_significance_end_to_end():
    rng = np.random.default_rng(3)
    rows = []
    for i in range(150):
        date = f"2020-{(i % 12) + 1:02d}-01-{i}"
        reward = 0.04 + rng.normal(0, 0.01)
        rows.append({"symbol": "AAPL", "analysis_date": date, "position_type": "LONG", "reward_90d": reward})
        # mirror SHORT row that must be dropped
        rows.append({"symbol": "AAPL", "analysis_date": date, "position_type": "SHORT", "reward_90d": -reward})

    summary = evaluate_reward_significance(rows, horizon="90d", sampling_interval_days=91)
    assert summary["n_mirror_rows_dropped"] == 150
    assert summary["n_observations"] == 150
    # 90d horizon at a 91d sampling interval => no overlap => ESS == n.
    assert summary["effective_sample_size"] == 150.0
    assert summary["mean_reward"] > 0
    assert summary["significant_5pct"] is True
    assert summary["bootstrap_ci_95"]["low"] <= summary["mean_reward"] <= summary["bootstrap_ci_95"]["high"]

    # A long horizon at the same interval down-weights ESS.
    long_summary = evaluate_reward_significance(rows, horizon="365d", sampling_interval_days=91)
    # reward_365d is absent -> no observations, but the overlap math is exercised separately
    assert long_summary["n_observations"] == 0


def test_quantify_survivorship_bias_detects_drag_from_delisted():
    rng = np.random.default_rng(11)
    rows = []
    # Survivors: positive rewards.
    for i in range(120):
        rows.append(
            {
                "symbol": f"S{i}",
                "analysis_date": f"2020-01-{(i % 28) + 1:02d}",
                "position_type": "LONG",
                "reward_90d": 0.03 + rng.normal(0, 0.01),
                "delisted": False,
            }
        )
    # Delisted names: strongly negative LONG rewards (terminal losses).
    for i in range(30):
        rows.append(
            {
                "symbol": f"D{i}",
                "analysis_date": f"2020-02-{(i % 28) + 1:02d}",
                "position_type": "LONG",
                "reward_90d": -0.8 + rng.normal(0, 0.02),
                "delisted": True,
            }
        )

    out = quantify_survivorship_bias(rows, horizon="90d")
    assert out["n_delisted_observations"] == 30
    assert out["survivors_only"]["mean_reward"] > 0
    assert out["full_including_delisted"]["mean_reward"] < out["survivors_only"]["mean_reward"]
    assert out["mean_reward_delta"] < 0
    assert out["bias_detected"] is True

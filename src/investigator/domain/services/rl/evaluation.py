"""Statistical-significance utilities for RL/valuation backtest evaluation.

The RL backtest produces heavily overlapping, autocorrelated observations
(multi-year horizons sampled quarterly) and mirrored LONG/SHORT rows. Naively
treating each row as an independent sample massively overstates significance.
This module provides the corrections a defensible evaluation needs:

- ``newey_west_tstat``     : HAC (Newey-West/Bartlett) t-stat robust to overlap.
- ``block_bootstrap_ci``   : circular block-bootstrap CI for the mean reward.
- ``effective_sample_size``: down-weights overlapping windows.
- ``walk_forward_splits``  : expanding-window OOS splits with an embargo gap.
- ``dedup_mirrored_positions``: collapse LONG/SHORT mirror pairs.

Pure functions (numpy only); deterministic given a seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def _clean(values: Sequence[Optional[float]]) -> np.ndarray:
    arr = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return np.asarray(arr, dtype=float)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class SignificanceResult:
    n: int
    mean: float
    std_error: float
    t_stat: float
    p_value: float
    lags: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n": self.n,
            "mean": self.mean,
            "std_error": self.std_error,
            "t_stat": self.t_stat,
            "p_value": self.p_value,
            "lags": self.lags,
            "significant_5pct": self.p_value < 0.05,
        }


def newey_west_lags(n: int) -> int:
    """Rule-of-thumb Bartlett lag length (Newey-West 1994): floor(4*(n/100)^(2/9))."""
    if n < 2:
        return 0
    return max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def newey_west_tstat(returns: Sequence[Optional[float]], lags: Optional[int] = None) -> SignificanceResult:
    """Mean return with a Newey-West HAC standard error and two-sided t-test.

    Robust to the serial correlation induced by overlapping holding-period windows.
    ``lags`` defaults to the Newey-West rule of thumb.
    """
    x = _clean(returns)
    n = int(x.size)
    if n < 2:
        mean = float(x[0]) if n == 1 else 0.0
        return SignificanceResult(
            n=n, mean=mean, std_error=float("nan"), t_stat=float("nan"), p_value=float("nan"), lags=0
        )

    mean = float(x.mean())
    resid = x - mean
    if lags is None:
        lags = newey_west_lags(n)
    lags = max(0, min(lags, n - 1))

    # Long-run variance via Bartlett-weighted autocovariances.
    gamma0 = float(resid @ resid) / n
    lrv = gamma0
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1.0)
        cov = float(resid[lag:] @ resid[:-lag]) / n
        lrv += 2.0 * weight * cov
    lrv = max(lrv, 1e-12)

    se = math.sqrt(lrv / n)
    t_stat = mean / se if se > 0 else float("nan")
    p_value = 2.0 * (1.0 - _norm_cdf(abs(t_stat))) if not math.isnan(t_stat) else float("nan")
    return SignificanceResult(n=n, mean=mean, std_error=se, t_stat=t_stat, p_value=p_value, lags=lags)


def block_bootstrap_ci(
    returns: Sequence[Optional[float]],
    block_size: Optional[int] = None,
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Circular block-bootstrap confidence interval for the mean.

    Resamples contiguous (wrap-around) blocks to preserve autocorrelation, so the
    CI is honest for overlapping samples. Returns (low, high, point_mean).
    Deterministic for a fixed ``seed``.
    """
    x = _clean(returns)
    n = int(x.size)
    if n < 2:
        m = float(x[0]) if n == 1 else 0.0
        return (m, m, m)
    if block_size is None:
        block_size = max(1, int(round(n ** (1.0 / 3.0))))
    block_size = max(1, min(block_size, n))

    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block_size))
    means = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + np.arange(block_size)[None, :]).reshape(-1) % n
        means[i] = float(x[idx][:n].mean())

    alpha = (1.0 - ci) / 2.0
    low = float(np.quantile(means, alpha))
    high = float(np.quantile(means, 1.0 - alpha))
    return (low, high, float(x.mean()))


def effective_sample_size(n: int, horizon_days: float, sampling_interval_days: float) -> float:
    """Effective sample size for overlapping windows.

    With a holding horizon longer than the sampling interval, consecutive
    observations overlap by ``horizon_days / sampling_interval_days`` periods; the
    effective independent count is roughly ``n`` divided by that overlap.
    """
    if n <= 0:
        return 0.0
    overlap = max(1.0, float(horizon_days) / max(1.0, float(sampling_interval_days)))
    return float(n) / overlap


@dataclass
class WalkForwardSplit:
    train_index: List[int] = field(default_factory=list)
    test_index: List[int] = field(default_factory=list)


def walk_forward_splits(n: int, n_splits: int = 5, embargo: int = 0) -> List[WalkForwardSplit]:
    """Expanding-window walk-forward splits with an embargo gap (no leakage).

    The data (assumed time-ordered) is divided into ``n_splits`` sequential test
    folds; each fold trains on everything strictly before it minus an ``embargo``
    gap of observations, so a long-horizon label cannot leak across the boundary.
    """
    if n <= 0 or n_splits < 1:
        return []
    fold = max(1, n // (n_splits + 1))
    splits: List[WalkForwardSplit] = []
    for k in range(1, n_splits + 1):
        train_end = fold * k
        test_start = train_end + embargo
        test_end = min(test_start + fold, n)
        if test_start >= n or train_end <= 0:
            continue
        train_idx = list(range(0, max(0, train_end - embargo)))
        test_idx = list(range(test_start, test_end))
        if train_idx and test_idx:
            splits.append(WalkForwardSplit(train_index=train_idx, test_index=test_idx))
    return splits


def dedup_mirrored_positions(
    rows: Sequence[Dict[str, Any]],
    *,
    symbol_key: str = "symbol",
    date_key: str = "analysis_date",
    position_key: str = "position_type",
    keep: str = "LONG",
) -> Tuple[List[Dict[str, Any]], int]:
    """Collapse mirrored LONG/SHORT rows so they aren't counted as independent.

    For each (symbol, analysis_date) the mirrored pair carries equal-and-opposite
    rewards; counting both double-counts the observation. Keeps the ``keep`` side
    when both are present (otherwise whatever single side exists). Returns
    (deduped_rows, n_dropped).
    """
    by_key: Dict[Tuple[Any, Any], List[Dict[str, Any]]] = {}
    order: List[Tuple[Any, Any]] = []
    for row in rows:
        k = (row.get(symbol_key), row.get(date_key))
        if k not in by_key:
            by_key[k] = []
            order.append(k)
        by_key[k].append(row)

    deduped: List[Dict[str, Any]] = []
    dropped = 0
    for k in order:
        group = by_key[k]
        if len(group) == 1:
            deduped.append(group[0])
            continue
        preferred = [r for r in group if str(r.get(position_key, "")).upper() == keep.upper()]
        chosen = preferred[0] if preferred else group[0]
        deduped.append(chosen)
        dropped += len(group) - 1
    return deduped, dropped


def evaluate_reward_significance(
    rows: Sequence[Dict[str, Any]],
    *,
    horizon: str = "90d",
    sampling_interval_days: float = 91.0,
    dedup_mirrors: bool = True,
    seed: int = 42,
) -> Dict[str, Any]:
    """End-to-end significance summary for a set of recorded outcome rows.

    Dedups mirrored LONG/SHORT pairs, extracts the horizon reward, and reports the
    Newey-West t-test, a block-bootstrap CI, and the overlap-adjusted effective
    sample size — the minimum a defensible backtest report should carry.

    Args:
        rows: outcome rows with ``reward_<n>d`` keys (e.g. ``reward_90d``) and,
            for dedup, ``symbol``/``analysis_date``/``position_type``.
        horizon: which reward horizon to evaluate (e.g. ``"90d"``, ``"365d"``).
        sampling_interval_days: spacing between observations (quarterly ≈ 91).
    """
    n_dropped = 0
    if dedup_mirrors:
        rows, n_dropped = dedup_mirrored_positions(rows)

    reward_key = f"reward_{horizon.rstrip('d')}d"
    horizon_days = float(horizon.rstrip("d"))
    rewards: List[Optional[float]] = [r.get(reward_key) for r in rows]
    clean = _clean(rewards)

    # newey_west_tstat / block_bootstrap_ci re-clean internally; pass the raw list.
    sig = newey_west_tstat(rewards)
    low, high, _ = block_bootstrap_ci(rewards, seed=seed) if clean.size >= 2 else (sig.mean, sig.mean, sig.mean)
    ess = effective_sample_size(int(clean.size), horizon_days, sampling_interval_days)

    return {
        "horizon": horizon,
        "n_observations": int(clean.size),
        "n_mirror_rows_dropped": n_dropped,
        "effective_sample_size": round(ess, 2),
        "mean_reward": round(sig.mean, 6),
        "newey_west": sig.to_dict(),
        "bootstrap_ci_95": {"low": round(low, 6), "high": round(high, 6)},
        "significant_5pct": bool(sig.p_value < 0.05) if not math.isnan(sig.p_value) else False,
    }


def quantify_survivorship_bias(
    rows: Sequence[Dict[str, Any]],
    *,
    horizon: str = "90d",
    delisted_key: str = "delisted",
    long_reward_key: Optional[str] = None,
    sampling_interval_days: float = 91.0,
) -> Dict[str, Any]:
    """Quantify survivorship bias by comparing a survivors-only vs full sample.

    A survivorship-biased backtest omits names that delisted (their terminal,
    usually loss-bearing outcomes never appear). This compares the reward
    distribution of the survivors-only subset (rows where ``delisted`` is falsy)
    against the full set (including delisted/terminal outcomes), reporting the mean
    delta and significance of each via the overlap-robust toolkit.

    A meaningfully negative ``mean_delta`` (full < survivors-only) is the signature
    of removed survivorship bias — the delisted names drag realized returns down.
    """
    survivors = [r for r in rows if not r.get(delisted_key)]
    full = list(rows)
    n_delisted = len(full) - len(survivors)

    survivors_eval = evaluate_reward_significance(
        survivors, horizon=horizon, sampling_interval_days=sampling_interval_days
    )
    full_eval = evaluate_reward_significance(full, horizon=horizon, sampling_interval_days=sampling_interval_days)
    mean_delta = round(full_eval["mean_reward"] - survivors_eval["mean_reward"], 6)

    return {
        "horizon": horizon,
        "n_delisted_observations": n_delisted,
        "survivors_only": survivors_eval,
        "full_including_delisted": full_eval,
        "mean_reward_delta": mean_delta,
        "bias_detected": mean_delta < 0 and n_delisted > 0,
    }

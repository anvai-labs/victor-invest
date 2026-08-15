# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Black-Scholes-Merton option math for the options screener.

Single canonical implementation that replaces the duplicated helpers previously
copy-pasted across the ad-hoc ``tmp_*_put_screen.py`` scripts. Includes a
dividend-yield term and a delta-targeting routine with an explicit tolerance so
callers can reject strikes that don't actually match the requested delta.
"""

from __future__ import annotations

import math

__all__ = ["norm_cdf", "put_delta", "strike_for_delta", "strike_round_step"]


def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def put_delta(
    spot: float,
    strike: float,
    vol: float,
    t_years: float,
    rate: float = 0.0447,
    div_yield: float = 0.0,
) -> float:
    """Black-Scholes-Merton put delta (negative), with continuous dividend yield.

    Returns NaN for non-finite or non-positive inputs so callers can filter.
    """
    if spot <= 0 or strike <= 0 or vol <= 0 or t_years <= 0:
        return float("nan")
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / (vol * math.sqrt(t_years))
    # Put delta with dividend yield: e^{-q t} (N(d1) - 1)
    return math.exp(-div_yield * t_years) * (norm_cdf(d1) - 1.0)


def strike_round_step(spot: float) -> float:
    """Canonical strike-rounding increment by underlying price tier.

    A single tier table (the four ad-hoc scripts each used a different one) so the
    same underlying always yields the same recommended strike.
    """
    if spot >= 250:
        return 5.0
    if spot >= 50:
        return 2.5
    if spot >= 20:
        return 1.0
    return 0.5


def strike_for_delta(
    spot: float,
    vol: float,
    target_abs_delta: float,
    t_years: float,
    rate: float = 0.0447,
    div_yield: float = 0.0,
    tolerance: float | None = 0.10,
) -> float:
    """Find a rounded put strike whose absolute delta is closest to the target.

    Scans candidate strikes from 50% to 105% of spot, picks the closest absolute
    delta, then rounds DOWN to the canonical increment for the price tier. If the
    closest achievable absolute delta deviates from ``target_abs_delta`` by more
    than ``tolerance`` (pass None to disable), returns NaN so the caller drops the
    candidate rather than recommending an off-target strike.
    """
    if not math.isfinite(spot) or spot <= 1.0 or vol <= 0 or t_years <= 0:
        return float("nan")

    step = 0.5
    k = max(1.0, spot * 0.50)
    best_strike = float("nan")
    best_abs_delta = float("nan")
    best_diff = float("inf")
    upper = spot * 1.05
    while k <= upper:
        d = abs(put_delta(spot, k, vol, t_years, rate=rate, div_yield=div_yield))
        if math.isfinite(d):
            diff = abs(d - target_abs_delta)
            if diff < best_diff:
                best_diff = diff
                best_strike = k
                best_abs_delta = d
        k += step

    if not math.isfinite(best_strike):
        return float("nan")
    if tolerance is not None and math.isfinite(best_abs_delta) and abs(best_abs_delta - target_abs_delta) > tolerance:
        return float("nan")

    round_step = strike_round_step(spot)
    return math.floor(best_strike / round_step) * round_step

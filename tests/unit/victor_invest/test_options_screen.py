"""Unit tests for the options-screen math and pure screening core (DB-free)."""

import asyncio
import math
from datetime import date

import pandas as pd

from victor_invest.tools._options_math import norm_cdf, put_delta, strike_for_delta, strike_round_step
from victor_invest.tools.options_screen import OptionsScreenTool


# --------------------------------------------------------------------- BSM math
def test_norm_cdf_known_values():
    assert math.isclose(norm_cdf(0.0), 0.5, abs_tol=1e-9)
    assert 0.84 < norm_cdf(1.0) < 0.842


def test_atm_put_delta_near_minus_half():
    # At-the-money, short-dated put delta sits near -0.5 (slightly above in abs).
    d = put_delta(spot=100.0, strike=100.0, vol=0.30, t_years=0.08, rate=0.0)
    assert -0.55 < d < -0.45


def test_put_delta_invalid_inputs_return_nan():
    assert math.isnan(put_delta(0.0, 100.0, 0.3, 0.1))
    assert math.isnan(put_delta(100.0, 100.0, 0.3, -0.1))


def test_put_delta_monotonic_in_strike():
    # Higher strike -> deeper (more negative) put delta.
    low = put_delta(100.0, 90.0, 0.3, 0.1)
    high = put_delta(100.0, 110.0, 0.3, 0.1)
    assert high < low


def test_strike_round_step_tiers():
    assert strike_round_step(300) == 5.0
    assert strike_round_step(100) == 2.5
    assert strike_round_step(30) == 1.0
    assert strike_round_step(10) == 0.5


def test_strike_for_delta_returns_otm_strike():
    strike = strike_for_delta(spot=100.0, vol=0.30, target_abs_delta=0.35, t_years=0.08)
    assert math.isfinite(strike)
    assert strike < 100.0  # a 0.35-delta put is out-of-the-money
    # rounded down to the tier step (2.5 for $50-250)
    assert math.isclose(strike % 2.5, 0.0, abs_tol=1e-9)


def test_strike_for_delta_tolerance_rejects_unreachable_target():
    # An absurd target delta cannot be matched within tolerance -> NaN.
    strike = strike_for_delta(spot=100.0, vol=0.30, target_abs_delta=0.999, t_years=0.08, tolerance=0.05)
    assert math.isnan(strike)


# ----------------------------------------------------------------- screen core
def _price_history(ticker: str, base: float, n: int = 130) -> pd.DataFrame:
    # Gently rising series so trend filters pass; constant volume for liquidity.
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [base * (1.0 + 0.0008 * i) for i in range(n)]
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": dates,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [5_000_000] * n,
        }
    )


def test_screen_frame_selects_undervalued_liquid_name():
    tool = OptionsScreenTool()
    meta = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "description": "Alpha",
                "stockid": 1,
                "mktcap": 1e11,
                "sec_sector": "Tech",
                "sec_industry": "Software",
                "fair_value_blended": 130.0,  # ~20%+ upside vs ~100 price
                "valuation_updated_at": date(2026, 5, 1),
                "data_quality_score": 90.0,
                "model_agreement_score": 0.8,
            }
        ]
    )
    prices = _price_history("AAA", base=100.0)

    result = tool.screen_frame(
        meta_df=meta,
        prices_df=prices,
        as_of=date(2026, 5, 18),
        expiry=date(2026, 6, 18),
        target_deltas=[0.35, 0.40],
        cash_budget=100_000.0,
    )

    assert result["universe_size"] == 1
    assert len(result["candidates"]) == 1
    cand = result["candidates"][0]
    assert cand["ticker"] == "AAA"
    assert cand["fv_upside_pct"] >= 8.0
    assert "strike_35" in cand and "strike_40" in cand
    # basket respects the cash budget
    assert result["basket_collateral"] <= 100_000.0


def test_screen_frame_drops_overvalued_name():
    tool = OptionsScreenTool()
    meta = pd.DataFrame(
        [
            {
                "ticker": "BBB",
                "description": "Beta",
                "stockid": 2,
                "mktcap": 1e11,
                "sec_sector": "Tech",
                "sec_industry": "Software",
                "fair_value_blended": 95.0,  # below price -> negative upside, filtered
                "valuation_updated_at": date(2026, 5, 1),
                "data_quality_score": 90.0,
                "model_agreement_score": 0.8,
            }
        ]
    )
    prices = _price_history("BBB", base=100.0)
    result = tool.screen_frame(
        meta_df=meta,
        prices_df=prices,
        as_of=date(2026, 5, 18),
        expiry=date(2026, 6, 18),
        target_deltas=[0.35],
    )
    assert result["candidates"] == []


def test_execute_rejects_expiry_before_as_of(monkeypatch):
    tool = OptionsScreenTool()
    tool._initialized = True  # skip DB initialize

    result = asyncio.run(
        tool.execute(
            universe="symbols",
            symbols=["AAA"],
            as_of=date(2026, 6, 18),
            expiry=date(2026, 5, 18),
        )
    )
    assert result.success is False
    assert "expiry" in (result.error or "")

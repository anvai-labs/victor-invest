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

"""Cash-secured put screening tool.

Productizes the four ad-hoc ``tmp_*_put_screen.py`` scripts into a single,
parameterized Victor tool. The universe (top-N by market cap, a sector/industry
filter, or an explicit symbol list) is the only real variable; everything else is
shared. The pure screening core (:meth:`OptionsScreenTool.screen_frame`) operates
on in-memory DataFrames so it is unit-testable without a database.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import date
from typing import Any, cast

import numpy as np
import pandas as pd

from victor_invest.tools._options_math import strike_for_delta
from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_TARGET_DELTAS = [0.35, 0.40]


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).clip(lower=0.0, upper=100.0)


class OptionsScreenTool(BaseTool):
    """Screen a universe for attractive cash-secured put candidates.

    Combines fundamental upside (blended fair value vs price), a trend/momentum
    filter, liquidity gates, and Black-Scholes delta-targeted strikes. Returns a
    ranked candidate list plus a budget-constrained basket. Never raises; returns
    ``ToolResult.create_failure`` on error.
    """

    name = "options_screen"
    description = """Screen an equity universe for cash-secured put candidates using
    blended fair-value upside, trend/momentum filters, liquidity gates, and
    Black-Scholes delta-targeted strikes. Universe can be top-N by market cap, a
    sector/industry filter, or an explicit symbol list."""

    def __init__(self, config: Any | None = None):
        super().__init__(config)
        self._engine: Any | None = None

    def _require_engine(self) -> Any:
        """Return the engine, or say plainly that initialize() was skipped.

        Without this, a tool used before initialize() fails with
        AttributeError on None, which names neither the cause nor the fix.
        """
        if self._engine is None:
            raise RuntimeError("OptionsScreenTool.initialize() must be awaited before querying the database")
        return self._engine

    async def initialize(self) -> None:
        try:
            import investigator.infrastructure.database as db

            self._engine = db.get_database_engine()
            self._initialized = True
        except ImportError as e:  # pragma: no cover - import guard
            logger.error(f"Could not initialize OptionsScreenTool database engine: {e}")
            raise

    async def execute(
        self,
        _exec_ctx: dict[str, Any] | None = None,
        universe: str = "top_n",
        limit: int = 1000,
        symbols: list[str] | None = None,
        sector: str | None = None,
        industry: str | None = None,
        as_of: date | None = None,
        expiry: date | None = None,
        target_deltas: list[float] | None = None,
        cash_budget: float = 100_000.0,
        rate: float = 0.0447,
        min_price: float = 8.0,
        min_fv_upside: float = 8.0,
        min_dollar_volume: float = 20_000_000.0,
        max_per_sector: int = 3,
        **kwargs: Any,
    ) -> ToolResult:
        """Run the put screen.

        Args:
            universe: One of ``"top_n"``, ``"sector"``, ``"industry"``, ``"symbols"``.
            limit: Max universe size for ``top_n``.
            symbols: Explicit symbol list for ``universe="symbols"``.
            sector/industry: Filters for ``universe="sector"``/``"industry"``.
            as_of/expiry: Pricing/expiry dates. Default as_of=today; expiry must be
                supplied (or defaults to ~30 days out) and must be after as_of.
            target_deltas: Absolute put deltas to target (default [0.35, 0.40]).
            cash_budget: Cash available for the basket (collateral cap).
        """
        await self.ensure_initialized()
        try:
            as_of = as_of or date.today()
            if expiry is None:
                from datetime import timedelta

                expiry = as_of + timedelta(days=30)
            if expiry <= as_of:
                return ToolResult.create_failure(f"expiry {expiry} must be after as_of {as_of}")

            deltas = target_deltas or DEFAULT_TARGET_DELTAS
            meta_df = self._fetch_universe(universe, limit, symbols, sector, industry)
            if meta_df.empty:
                return ToolResult.create_success(
                    output={"candidates": [], "basket": [], "universe_size": 0},
                    metadata={"tool": self.name, "universe": universe},
                )
            tickers = meta_df["ticker"].dropna().astype(str).str.upper().tolist()
            prices_df = self._fetch_prices(tickers)

            result = self.screen_frame(
                meta_df=meta_df,
                prices_df=prices_df,
                as_of=as_of,
                expiry=expiry,
                target_deltas=deltas,
                cash_budget=cash_budget,
                rate=rate,
                min_price=min_price,
                min_fv_upside=min_fv_upside,
                min_dollar_volume=min_dollar_volume,
                max_per_sector=max_per_sector,
            )
            return ToolResult.create_success(
                output=result,
                metadata={"tool": self.name, "universe": universe, "as_of": as_of.isoformat()},
            )
        except Exception as e:  # noqa: BLE001 - tools never raise
            logger.error(f"OptionsScreenTool failed: {e}")
            return ToolResult.create_failure(str(e))

    # ------------------------------------------------------------------ data access
    def _fetch_universe(
        self,
        universe: str,
        limit: int,
        symbols: list[str] | None,
        sector: str | None,
        industry: str | None,
    ) -> pd.DataFrame:
        from sqlalchemy import text

        base_cols = """ticker, description, stockid, mktcap, sec_sector, sec_industry,
                   fair_value_blended, valuation_updated_at,
                   data_quality_score, model_agreement_score"""
        where = [
            "COALESCE(islisted, true) = true",
            "COALESCE(isstock, true) = true",
            "COALESCE(isetf, false) = false",
            "stockid IS NOT NULL",
        ]
        params: dict[str, Any] = {}
        if universe == "symbols":
            if not symbols:
                return pd.DataFrame()
            where.append("UPPER(ticker) = ANY(:symbols)")
            params["symbols"] = [s.upper() for s in symbols]
            order, limit_clause = "ticker", ""
        elif universe == "sector":
            where.append("sec_sector = :sector")
            params["sector"] = sector
            order, limit_clause = "mktcap DESC NULLS LAST", "LIMIT :limit"
            params["limit"] = limit
        elif universe == "industry":
            where.append("sec_industry = :industry")
            params["industry"] = industry
            order, limit_clause = "mktcap DESC NULLS LAST", "LIMIT :limit"
            params["limit"] = limit
        else:  # top_n
            order, limit_clause = "mktcap DESC NULLS LAST", "LIMIT :limit"
            params["limit"] = limit

        sql = f"SELECT {base_cols} FROM symbol WHERE {' AND '.join(where)} ORDER BY {order} {limit_clause}"
        with self._require_engine().connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def _fetch_prices(self, tickers: list[str]) -> pd.DataFrame:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            return pd.read_sql(
                text(
                    """
                    SELECT ticker, date, open, high, low, close, volume
                    FROM tickerdata
                    WHERE ticker = ANY(:symbols)
                      AND date >= CURRENT_DATE - INTERVAL '260 days'
                    ORDER BY ticker, date
                    """
                ),
                conn,
                params=cast("Mapping[str, Any]", {"symbols": tickers}),
            )

    # ------------------------------------------------------------------ pure core
    def screen_frame(
        self,
        *,
        meta_df: pd.DataFrame,
        prices_df: pd.DataFrame,
        as_of: date,
        expiry: date,
        target_deltas: list[float],
        cash_budget: float = 100_000.0,
        rate: float = 0.0447,
        min_price: float = 8.0,
        min_fv_upside: float = 8.0,
        min_dollar_volume: float = 20_000_000.0,
        max_per_sector: int = 3,
    ) -> dict[str, Any]:
        """Pure screening logic over in-memory frames (DB-free; unit-testable)."""
        t_years = (expiry - as_of).days / 365.0
        primary_delta = target_deltas[0]
        meta_by_ticker = {str(t).upper(): row for t, row in zip(meta_df["ticker"], meta_df.to_dict("records"))}

        rows: list[dict[str, Any]] = []
        for ticker, df in prices_df.groupby("ticker"):
            df = df.sort_values("date").copy()
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            if len(df) < 90:
                continue

            close = df["close"]
            price = float(close.iloc[-1])
            if not math.isfinite(price) or price < min_price:
                continue

            m = meta_by_ticker.get(str(ticker).upper())
            if m is None:
                continue
            raw_fv = m.get("fair_value_blended")
            fv = float(raw_fv) if raw_fv is not None and pd.notna(raw_fv) else float("nan")
            if not math.isfinite(fv) or fv <= 0:
                continue
            fv_upside = (fv / price - 1.0) * 100.0
            if fv_upside < min_fv_upside:
                continue

            returns = close.pct_change().dropna()
            vol30 = returns.tail(30).std() * math.sqrt(252)
            vol60 = returns.tail(60).std() * math.sqrt(252)
            vol = max(float(np.nanmean([vol30, vol60])), 0.15)

            avg_vol20 = float(df["volume"].tail(20).mean())
            dollar_vol20 = avg_vol20 * price
            if dollar_vol20 < min_dollar_volume:
                continue

            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]
            sma200 = close.rolling(200).mean().iloc[-1] if len(df) >= 200 else np.nan
            rsi14 = float(_rsi(close).iloc[-1])
            ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
            ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
            macd = ema12 - ema26
            macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()

            trend_score = 0
            trend_score += 1 if price > sma20 else 0
            trend_score += 1 if price > sma50 else 0
            trend_score += 1 if pd.notna(sma200) and price > sma200 else 0
            trend_score += (
                1
                if bool(pd.notna(macd.iloc[-1]))
                and bool(pd.notna(macd_signal.iloc[-1]))
                and macd.iloc[-1] > macd_signal.iloc[-1]
                else 0
            )
            trend_score += 1 if 35 <= rsi14 <= 65 else 0
            if trend_score < 1 or rsi14 > 72:
                continue

            strikes = {
                f"strike_{int(d * 100)}": strike_for_delta(price, vol, d, t_years, rate=rate) for d in target_deltas
            }
            primary_strike = strikes.get(f"strike_{int(primary_delta * 100)}")
            if primary_strike is None or not math.isfinite(primary_strike) or primary_strike <= 0:
                continue
            collateral = primary_strike * 100.0
            if collateral > cash_budget:
                continue

            raw_agreement = m.get("model_agreement_score")
            agreement = float(raw_agreement) if raw_agreement is not None and pd.notna(raw_agreement) else float("nan")
            score = (
                min(fv_upside, 100.0) * 0.42
                + trend_score * 8.0
                + min(dollar_vol20 / 50_000_000, 10.0) * 2.0
                + (0.0 if math.isnan(agreement) else agreement * 10.0)
                - max(0.0, vol - 0.55) * 25.0
                - (10.0 if rsi14 > 68 else 0.0)
            )

            rows.append(
                {
                    "ticker": str(ticker).upper(),
                    "sector": m.get("sec_sector"),
                    "industry": m.get("sec_industry"),
                    "price": round(price, 2),
                    "fair_value": round(fv, 2),
                    "fv_upside_pct": round(fv_upside, 1),
                    "rsi14": round(rsi14, 1),
                    "trend_score": trend_score,
                    "dollar_vol20": round(dollar_vol20, 0),
                    "hist_vol": round(vol, 4),
                    **{k: (round(v, 2) if math.isfinite(v) else None) for k, v in strikes.items()},
                    "primary_collateral": round(collateral, 0),
                    "score": round(score, 1),
                }
            )

        candidates = sorted(rows, key=lambda r: (r["score"], r["fv_upside_pct"]), reverse=True)

        basket: list[dict[str, Any]] = []
        remaining = cash_budget
        sector_counts: dict[str, int] = {}
        for row in candidates:
            collateral = float(row["primary_collateral"])
            sec = str(row["sector"])
            if collateral > remaining or sector_counts.get(sec, 0) >= max_per_sector:
                continue
            basket.append(row)
            remaining -= collateral
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            if remaining < 2_000 or len(basket) >= 10:
                break

        return {
            "candidates": candidates,
            "basket": basket,
            "universe_size": len(meta_df),
            "basket_collateral": round(cash_budget - remaining, 0),
            "remaining_cash": round(remaining, 0),
        }

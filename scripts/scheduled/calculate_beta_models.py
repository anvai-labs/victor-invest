#!/usr/bin/env python3
# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
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

"""Calculate market, FF6, fundamental, and blended betas for symbols.

Schedule recommendation:
- Weekend refresh (Saturday/Sunday morning) for stable valuation inputs
- Optional ad-hoc refresh for symbols after major earnings events

Models:
- market: CAPM beta from stock vs benchmark returns (SPY by default)
- ff6: MKT loading from FF6 regression (Mkt-RF, SMB, HML, RMW, CMA, UMD)
- fundamental: industry unlevered beta relevered with D/E (Hamada)
- blended: quality-weighted blend of market + ff6 + fundamental

Outputs:
1. Upserts detailed model rows into `symbol_beta_models`
2. Updates legacy `symbol` beta columns (b_12_month/r2_12_month, etc.) for compatibility

Usage:
    python scripts/scheduled/calculate_beta_models.py
    python scripts/scheduled/calculate_beta_models.py --symbols STX,MSFT --models market,ff6,blended
    python scripts/scheduled/calculate_beta_models.py --universe russell1000 --windows 12,24,36,60 --frequency weekly
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from investigator.domain.services.valuation.cost_of_capital import (  # noqa: E402
    IndustryCostOfCapital,
)
from scripts.scheduled.base import (  # noqa: E402
    BaseCollector,
    CollectionMetrics,
    get_russell1000_symbols,
    get_sp500_symbols,
)

VALID_MODELS = {"market", "ff6", "fundamental", "blended"}


@dataclass
class BetaEstimate:
    symbol: str
    as_of_date: date
    lookback_months: int
    model: str
    beta: float
    alpha: Optional[float] = None
    r_squared: Optional[float] = None
    observations: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BetaModelCollector(BaseCollector):
    """Collect and persist beta model estimates."""

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        universe: str = "sp500",
        models: Optional[Set[str]] = None,
        benchmark: str = "SPY",
        windows: Optional[List[int]] = None,
        frequency: str = "daily",
        min_obs: int = 126,
        winsorize_pct: float = 0.01,
        max_abs_beta: float = 20.0,
        use_fred_rf: bool = True,
        dry_run: bool = False,
    ):
        super().__init__("calculate_beta_models")
        self.symbols = [s.strip().upper() for s in symbols] if symbols else None
        self.universe = universe
        self.models = models or {"market", "ff6", "fundamental", "blended"}
        self.benchmark = benchmark.upper()
        self.windows = sorted(set(windows or [12, 24, 36, 60]))
        self.frequency = frequency
        self.min_obs = min_obs
        self.winsorize_pct = winsorize_pct
        self.max_abs_beta = max_abs_beta
        self.use_fred_rf = use_fred_rf
        self.dry_run = dry_run
        self.cost_of_capital = IndustryCostOfCapital()

    def collect(self) -> CollectionMetrics:
        conn = self._get_stock_database_connection()
        cursor = conn.cursor()

        try:
            self._ensure_beta_models_table(cursor)
            # Persist DDL immediately so later recoverable query failures (e.g., FF DB fallback)
            # cannot roll back table creation in the same transaction.
            conn.commit()
            symbol_columns = self._get_symbol_columns(cursor)
            symbols = self._resolve_symbols(cursor)
            if not symbols:
                self.metrics.warnings.append("No symbols resolved for beta refresh")
                return self.metrics

            as_of_date = self._get_latest_trading_date(cursor, self.benchmark)
            if not as_of_date:
                self.metrics.errors.append("Could not determine latest trading date")
                return self.metrics

            start_date = as_of_date - relativedelta(months=max(self.windows) + 3)
            all_tickers = sorted(set(symbols + [self.benchmark]))

            returns = self._load_price_returns(
                conn=conn,
                tickers=all_tickers,
                start_date=start_date,
                end_date=as_of_date,
                frequency=self.frequency,
                winsorize_pct=self.winsorize_pct,
            )
            if returns.empty or self.benchmark not in returns.columns:
                self.metrics.errors.append(f"Benchmark returns unavailable for {self.benchmark}")
                return self.metrics

            ff_factors = self._load_ff_factors(
                conn=conn,
                start_date=start_date,
                end_date=as_of_date,
                winsorize_pct=self.winsorize_pct,
            )
            fred_rf = None
            if self.use_fred_rf:
                fred_rf = self._load_fred_rf_series(
                    conn=conn,
                    start_date=start_date,
                    end_date=as_of_date,
                )

            symbol_fundamentals = self._load_symbol_fundamentals(conn=conn, symbols=symbols)
            benchmark_returns = returns[self.benchmark]

            estimates: List[BetaEstimate] = []
            symbol_updates: Dict[str, Dict[str, Any]] = {}

            for symbol in symbols:
                if symbol == self.benchmark:
                    continue
                if symbol not in returns.columns:
                    self.metrics.records_skipped += 1
                    continue

                stock_returns = returns[symbol]
                fundamental_estimate = None
                if "fundamental" in self.models or "blended" in self.models:
                    fundamental_estimate = self._estimate_fundamental_beta(
                        symbol=symbol,
                        as_of_date=as_of_date,
                        windows=self.windows,
                        row=symbol_fundamentals.get(symbol, {}),
                    )

                for lookback in self.windows:
                    market_estimate = None
                    ff6_estimate = None
                    blend_estimate = None

                    if "market" in self.models:
                        market_estimate = self._estimate_market_beta(
                            symbol=symbol,
                            as_of_date=as_of_date,
                            lookback_months=lookback,
                            stock_returns=stock_returns,
                            benchmark_returns=benchmark_returns,
                            fred_rf=fred_rf,
                        )
                        if market_estimate is not None:
                            estimates.append(market_estimate)
                            self._collect_symbol_column_updates(
                                symbol_updates=symbol_updates,
                                symbol_columns=symbol_columns,
                                estimate=market_estimate,
                            )

                    if "ff6" in self.models:
                        ff6_estimate = self._estimate_ff6_beta(
                            symbol=symbol,
                            as_of_date=as_of_date,
                            lookback_months=lookback,
                            stock_returns=stock_returns,
                            ff_factors=ff_factors,
                            fred_rf=fred_rf,
                        )
                        if ff6_estimate is not None:
                            estimates.append(ff6_estimate)
                            self._collect_symbol_column_updates(
                                symbol_updates=symbol_updates,
                                symbol_columns=symbol_columns,
                                estimate=ff6_estimate,
                            )

                    if "fundamental" in self.models and fundamental_estimate:
                        fundamental_for_window = fundamental_estimate.get(lookback)
                        if fundamental_for_window:
                            estimates.append(fundamental_for_window)
                            self._collect_symbol_column_updates(
                                symbol_updates=symbol_updates,
                                symbol_columns=symbol_columns,
                                estimate=fundamental_for_window,
                            )

                    if "blended" in self.models:
                        blend_estimate = self._estimate_blended_beta(
                            symbol=symbol,
                            as_of_date=as_of_date,
                            lookback_months=lookback,
                            market_estimate=market_estimate,
                            ff6_estimate=ff6_estimate,
                            fundamental_estimate=(fundamental_estimate.get(lookback) if fundamental_estimate else None),
                        )
                        if blend_estimate is not None:
                            estimates.append(blend_estimate)
                            self._collect_symbol_column_updates(
                                symbol_updates=symbol_updates,
                                symbol_columns=symbol_columns,
                                estimate=blend_estimate,
                            )

                self.metrics.records_processed += 1

            if self.dry_run:
                self.logger.info(
                    "Dry run: computed %d beta estimates for %d symbols",
                    len(estimates),
                    self.metrics.records_processed,
                )
                self.metrics.records_skipped += len(estimates)
                conn.rollback()
                return self.metrics

            if estimates:
                self._upsert_beta_models(cursor, estimates)
                self.metrics.records_updated += len(estimates)
            if symbol_updates:
                updated_rows = self._apply_symbol_updates(cursor, symbol_updates)
                self.metrics.records_inserted += updated_rows

            conn.commit()
            self.logger.info(
                "Beta models refreshed: symbols=%d, estimates=%d, symbol_updates=%d",
                self.metrics.records_processed,
                len(estimates),
                len(symbol_updates),
            )
            return self.metrics
        except Exception as exc:
            conn.rollback()
            self.metrics.errors.append(str(exc))
            raise
        finally:
            cursor.close()
            conn.close()

    def _resolve_symbols(self, cursor) -> List[str]:
        if self.symbols:
            return sorted(set(self.symbols))

        if self.universe == "sp500":
            return sorted(set(get_sp500_symbols()))
        if self.universe == "russell1000":
            return sorted(set(get_russell1000_symbols()))

        try:
            cursor.execute(
                """
                SELECT ticker
                FROM symbol
                WHERE COALESCE(islisted, TRUE) = TRUE
                  AND COALESCE(isetf, FALSE) = FALSE
                ORDER BY ticker
                """
            )
            rows = cursor.fetchall()
            return [str(r[0]).upper() for r in rows if r and r[0]]
        except Exception:
            cursor.execute("SELECT ticker FROM symbol ORDER BY ticker")
            rows = cursor.fetchall()
            return [str(r[0]).upper() for r in rows if r and r[0]]

    @staticmethod
    def _get_stock_database_connection():
        import psycopg2

        from investigator.infrastructure.credentials import get_database_credentials

        creds = get_database_credentials("stock")
        return psycopg2.connect(
            host=creds.host,
            port=creds.port,
            dbname=creds.database,
            user=creds.username,
            password=creds.password,
        )

    def _get_latest_trading_date(self, cursor, benchmark: str) -> Optional[date]:
        cursor.execute("SELECT MAX(date) FROM tickerdata WHERE ticker = %s", (benchmark,))
        row = cursor.fetchone()
        latest = row[0] if row else None
        if latest:
            return latest
        cursor.execute("SELECT MAX(date) FROM tickerdata")
        row = cursor.fetchone()
        return row[0] if row else None

    def _load_price_returns(
        self,
        conn,
        tickers: Sequence[str],
        start_date: date,
        end_date: date,
        frequency: str,
        winsorize_pct: float,
    ) -> pd.DataFrame:
        query = """
            SELECT ticker, date, COALESCE(adjclose, close) AS close
            FROM tickerdata
            WHERE ticker = ANY(%(tickers)s)
              AND date BETWEEN %(start_date)s AND %(end_date)s
            ORDER BY date ASC
        """
        df = pd.read_sql_query(
            query,
            conn,
            params={
                "tickers": list(tickers),
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        if df.empty:
            return pd.DataFrame()

        df["date"] = pd.to_datetime(df["date"])
        prices = df.pivot(index="date", columns="ticker", values="close").sort_index()
        if frequency == "weekly":
            prices = prices.resample("W-FRI").last()

        returns = prices.pct_change(fill_method=None).dropna(how="all")
        if winsorize_pct > 0:
            for col in returns.columns:
                returns[col] = self._winsorize_series(returns[col], winsorize_pct)
        return returns.dropna(how="all")

    def _load_ff_factors(
        self,
        conn,
        start_date: date,
        end_date: date,
        winsorize_pct: float,
    ) -> pd.DataFrame:
        query = """
            SELECT date, mkt_rf, smb, hml, rmw, cma, umd, rf
            FROM fama_french_factors
            WHERE date BETWEEN %(start_date)s AND %(end_date)s
            ORDER BY date ASC
        """
        try:
            df = pd.read_sql_query(
                query,
                conn,
                params={"start_date": start_date, "end_date": end_date},
            )
        except Exception as exc:
            self.logger.warning("FF factors unavailable in DB: %s", exc)
            return self._load_ff_factors_from_csv(start_date, end_date, winsorize_pct)

        if df.empty:
            return self._load_ff_factors_from_csv(start_date, end_date, winsorize_pct)

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        for col in ["mkt_rf", "smb", "hml", "rmw", "cma", "umd", "rf"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            median_abs = float(df[col].abs().median() or 0)
            if median_abs > 1:
                df[col] = df[col] / 100.0
            if winsorize_pct > 0 and col != "rf":
                df[col] = self._winsorize_series(df[col], winsorize_pct)
        return df.dropna(how="all")

    def _load_ff_factors_from_csv(self, start_date: date, end_date: date, winsorize_pct: float) -> pd.DataFrame:
        candidate_paths = [
            PROJECT_ROOT / "data" / "factors" / "ff6.csv",
            PROJECT_ROOT.parent / "ibkrtrading" / "data" / "factors" / "ff6.csv",
        ]
        source_path = next((p for p in candidate_paths if p.exists()), None)
        if source_path is None:
            self.logger.warning("FF factors fallback file not found")
            return pd.DataFrame()

        try:
            raw = pd.read_csv(source_path)
        except Exception as exc:
            self.logger.warning("Failed reading FF factors CSV fallback %s: %s", source_path, exc)
            return pd.DataFrame()

        if raw.empty:
            return pd.DataFrame()

        rename_map = {
            "Date": "date",
            "DATE": "date",
            "MKT-RF": "mkt_rf",
            "Mkt-RF": "mkt_rf",
            "SMB": "smb",
            "HML": "hml",
            "RMW": "rmw",
            "CMA": "cma",
            "MOM": "umd",
            "UMD": "umd",
            "RF": "rf",
        }
        raw = raw.rename(columns=rename_map)
        required = {"date", "mkt_rf", "smb", "hml", "rmw", "cma", "umd", "rf"}
        if not required.issubset(set(raw.columns)):
            self.logger.warning("FF factors CSV fallback missing required columns")
            return pd.DataFrame()

        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        raw = raw[(raw["date"] >= pd.Timestamp(start_date)) & (raw["date"] <= pd.Timestamp(end_date))]
        raw = raw.dropna(subset=["date"]).set_index("date").sort_index()
        for col in ["mkt_rf", "smb", "hml", "rmw", "cma", "umd", "rf"]:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
            median_abs = float(raw[col].abs().median() or 0)
            if median_abs > 1:
                raw[col] = raw[col] / 100.0
            if winsorize_pct > 0 and col != "rf":
                raw[col] = self._winsorize_series(raw[col], winsorize_pct)
        self.logger.info("Loaded FF factors from CSV fallback: %s", source_path)
        return raw.dropna(how="all")

    def _load_fred_rf_series(
        self,
        conn,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.Series]:
        query_join = """
            SELECT mv.date, mv.value
            FROM macro_indicator_values mv
            JOIN macro_indicators mi ON mi.id = mv.indicator_id
            WHERE mi.series_id = 'DFF'
              AND mv.date BETWEEN %(start_date)s AND %(end_date)s
            ORDER BY mv.date ASC
        """
        query_direct = """
            SELECT date, value
            FROM macro_indicator_values
            WHERE indicator_id = 'DFF'
              AND date BETWEEN %(start_date)s AND %(end_date)s
            ORDER BY date ASC
        """
        try:
            df = pd.read_sql_query(
                query_join,
                conn,
                params={"start_date": start_date, "end_date": end_date},
            )
        except Exception:
            try:
                df = pd.read_sql_query(
                    query_direct,
                    conn,
                    params={"start_date": start_date, "end_date": end_date},
                )
            except Exception as exc:
                self.logger.warning("FRED DFF unavailable for beta fallback: %s", exc)
                return None

        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        rf = pd.to_numeric(df["value"], errors="coerce")
        if float(rf.abs().median() or 0) > 1:
            rf = rf / 100.0
        rf = rf / 360.0
        series = pd.Series(rf.values, index=df["date"]).sort_index()
        return series

    def _load_symbol_fundamentals(self, conn, symbols: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        query = """
            SELECT *
            FROM symbol
            WHERE ticker = ANY(%(symbols)s)
        """
        df = pd.read_sql_query(query, conn, params={"symbols": list(symbols)})
        if df.empty:
            return {}
        records: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).upper()
            if not ticker:
                continue
            records[ticker] = row.to_dict()
        return records

    def _estimate_market_beta(
        self,
        symbol: str,
        as_of_date: date,
        lookback_months: int,
        stock_returns: pd.Series,
        benchmark_returns: pd.Series,
        fred_rf: Optional[pd.Series],
    ) -> Optional[BetaEstimate]:
        window_start = pd.Timestamp(as_of_date - relativedelta(months=lookback_months))
        df = pd.DataFrame(
            {
                "stock": stock_returns,
                "benchmark": benchmark_returns,
            }
        )
        df = df[df.index >= window_start].dropna()
        if df.empty or len(df) < self.min_obs:
            return None

        if fred_rf is not None:
            rf = fred_rf.reindex(df.index).ffill().fillna(0.0)
            y = df["stock"] - rf
            x = df["benchmark"] - rf
        else:
            y = df["stock"]
            x = df["benchmark"]

        alpha, beta, r2 = self._ols_single_factor(x.values, y.values)
        if not np.isfinite(beta) or abs(beta) > self.max_abs_beta:
            return None

        return BetaEstimate(
            symbol=symbol,
            as_of_date=as_of_date,
            lookback_months=lookback_months,
            model="market",
            beta=float(beta),
            alpha=float(alpha),
            r_squared=float(r2),
            observations=int(len(df)),
            metadata={"benchmark": self.benchmark},
        )

    def _estimate_ff6_beta(
        self,
        symbol: str,
        as_of_date: date,
        lookback_months: int,
        stock_returns: pd.Series,
        ff_factors: pd.DataFrame,
        fred_rf: Optional[pd.Series],
    ) -> Optional[BetaEstimate]:
        if ff_factors.empty:
            return None

        window_start = pd.Timestamp(as_of_date - relativedelta(months=lookback_months))
        factors = ff_factors[ff_factors.index >= window_start].copy()
        if factors.empty:
            return None

        df = pd.DataFrame({"stock": stock_returns})
        df = df.join(factors, how="inner").dropna()
        if df.empty or len(df) < self.min_obs:
            return None

        rf = df["rf"].copy()
        if rf.isna().all() and fred_rf is not None:
            rf = fred_rf.reindex(df.index).ffill().fillna(0.0)
        else:
            rf = rf.fillna(0.0)

        y = (df["stock"] - rf).values
        x = df[["mkt_rf", "smb", "hml", "rmw", "cma", "umd"]].values

        alpha, betas, r2 = self._ols_multi_factor(x, y)
        beta_mkt = float(betas[0])
        if not np.isfinite(beta_mkt) or abs(beta_mkt) > self.max_abs_beta:
            return None

        return BetaEstimate(
            symbol=symbol,
            as_of_date=as_of_date,
            lookback_months=lookback_months,
            model="ff6",
            beta=beta_mkt,
            alpha=float(alpha),
            r_squared=float(r2),
            observations=int(len(df)),
            metadata={
                "beta_mkt": beta_mkt,
                "beta_smb": float(betas[1]),
                "beta_hml": float(betas[2]),
                "beta_rmw": float(betas[3]),
                "beta_cma": float(betas[4]),
                "beta_umd": float(betas[5]),
            },
        )

    def _estimate_fundamental_beta(
        self,
        symbol: str,
        as_of_date: date,
        windows: Sequence[int],
        row: Dict[str, Any],
    ) -> Dict[int, BetaEstimate]:
        industry = self._first_nonempty(
            row,
            ["sec_industry", "industry", "Industry", "gics_industry"],
        )
        sector = self._first_nonempty(
            row,
            ["sec_sector", "sector", "Sector", "gics_sector"],
        )
        beta_lookup_key = industry or sector or "Default"
        unlevered_beta, exact_match = self.cost_of_capital.get_unlevered_beta(str(beta_lookup_key))
        debt_to_equity = self._extract_debt_to_equity(row)
        tax_rate = self._extract_tax_rate(row)
        levered_beta = self.cost_of_capital.calculate_levered_beta(
            unlevered_beta=unlevered_beta,
            debt_to_equity=debt_to_equity,
            tax_rate=tax_rate,
        )
        if not np.isfinite(levered_beta):
            levered_beta = unlevered_beta
        levered_beta = float(np.clip(levered_beta, -self.max_abs_beta, self.max_abs_beta))

        out: Dict[int, BetaEstimate] = {}
        for lookback in windows:
            out[lookback] = BetaEstimate(
                symbol=symbol,
                as_of_date=as_of_date,
                lookback_months=lookback,
                model="fundamental",
                beta=levered_beta,
                alpha=None,
                r_squared=None,
                observations=0,
                metadata={
                    "industry": industry,
                    "sector": sector,
                    "unlevered_beta": unlevered_beta,
                    "debt_to_equity": debt_to_equity,
                    "tax_rate": tax_rate,
                    "exact_industry_match": exact_match,
                },
            )
        return out

    def _estimate_blended_beta(
        self,
        symbol: str,
        as_of_date: date,
        lookback_months: int,
        market_estimate: Optional[BetaEstimate],
        ff6_estimate: Optional[BetaEstimate],
        fundamental_estimate: Optional[BetaEstimate],
    ) -> Optional[BetaEstimate]:
        components: List[Tuple[str, float, float, Optional[float], int]] = []

        if market_estimate is not None:
            w_market = max(0.05, float(market_estimate.r_squared or 0.0))
            components.append(
                (
                    "market",
                    market_estimate.beta,
                    w_market,
                    market_estimate.alpha,
                    market_estimate.observations,
                )
            )
        if ff6_estimate is not None:
            w_ff6 = max(0.05, float(ff6_estimate.r_squared or 0.0))
            components.append(
                (
                    "ff6",
                    ff6_estimate.beta,
                    w_ff6,
                    ff6_estimate.alpha,
                    ff6_estimate.observations,
                )
            )
        if fundamental_estimate is not None:
            components.append(
                (
                    "fundamental",
                    fundamental_estimate.beta,
                    0.20,
                    fundamental_estimate.alpha,
                    fundamental_estimate.observations,
                )
            )

        if not components:
            return None

        total_weight = sum(weight for _, _, weight, _, _ in components)
        if total_weight <= 0:
            return None

        beta = sum(beta_val * weight for _, beta_val, weight, _, _ in components) / total_weight
        alpha_vals = [
            (alpha_val, weight)
            for _, _, weight, alpha_val, _ in components
            if alpha_val is not None and np.isfinite(alpha_val)
        ]
        alpha = (
            sum(alpha_val * weight for alpha_val, weight in alpha_vals) / sum(weight for _, weight in alpha_vals)
            if alpha_vals
            else None
        )
        r2_vals = [
            (float(model.r_squared), max(0.05, float(model.r_squared)))
            for model in (market_estimate, ff6_estimate)
            if model is not None and model.r_squared is not None
        ]
        r2 = sum(v * w for v, w in r2_vals) / sum(w for _, w in r2_vals) if r2_vals else None
        obs = max((obs for _, _, _, _, obs in components), default=0)

        return BetaEstimate(
            symbol=symbol,
            as_of_date=as_of_date,
            lookback_months=lookback_months,
            model="blended",
            beta=float(beta),
            alpha=float(alpha) if alpha is not None else None,
            r_squared=float(r2) if r2 is not None else None,
            observations=int(obs),
            metadata={
                "components": [
                    {
                        "model": model_name,
                        "beta": beta_val,
                        "weight": weight,
                    }
                    for model_name, beta_val, weight, _, _ in components
                ]
            },
        )

    def _ensure_beta_models_table(self, cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_beta_models (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(16) NOT NULL,
                as_of_date DATE NOT NULL,
                lookback_months INTEGER NOT NULL,
                model VARCHAR(32) NOT NULL,
                beta_value DOUBLE PRECISION NOT NULL,
                alpha_value DOUBLE PRECISION NULL,
                r_squared DOUBLE PRECISION NULL,
                observations INTEGER NOT NULL DEFAULT 0,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, as_of_date, lookback_months, model)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_symbol_beta_models_symbol_model
                ON symbol_beta_models(symbol, model, lookback_months, as_of_date DESC)
            """
        )

    def _upsert_beta_models(self, cursor, estimates: Sequence[BetaEstimate]) -> None:
        rows = []
        for est in estimates:
            rows.append(
                (
                    est.symbol,
                    est.as_of_date,
                    est.lookback_months,
                    est.model,
                    float(est.beta),
                    float(est.alpha) if est.alpha is not None else None,
                    float(est.r_squared) if est.r_squared is not None else None,
                    int(est.observations),
                    json.dumps(est.metadata or {}),
                )
            )

        cursor.executemany(
            """
            INSERT INTO symbol_beta_models (
                symbol, as_of_date, lookback_months, model,
                beta_value, alpha_value, r_squared, observations, metadata_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (symbol, as_of_date, lookback_months, model)
            DO UPDATE SET
                beta_value = EXCLUDED.beta_value,
                alpha_value = EXCLUDED.alpha_value,
                r_squared = EXCLUDED.r_squared,
                observations = EXCLUDED.observations,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
            """,
            rows,
        )

    def _get_symbol_columns(self, cursor) -> Set[str]:
        cursor.execute(
            """
            SELECT LOWER(column_name)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'symbol'
            """
        )
        return {str(row[0]).lower() for row in cursor.fetchall() if row and row[0]}

    def _collect_symbol_column_updates(
        self,
        symbol_updates: Dict[str, Dict[str, Any]],
        symbol_columns: Set[str],
        estimate: BetaEstimate,
    ) -> None:
        symbol = estimate.symbol
        lookback = estimate.lookback_months
        updates = symbol_updates.setdefault(symbol, {})
        if "beta_model_updated_at" in symbol_columns:
            updates["beta_model_updated_at"] = datetime.now(timezone.utc)

        if estimate.model == "market":
            beta_col = f"b_{lookback}_month"
            r2_col = f"r2_{lookback}_month"
            if beta_col in symbol_columns:
                updates[beta_col] = estimate.beta
            if r2_col in symbol_columns and estimate.r_squared is not None:
                updates[r2_col] = estimate.r_squared
            return

        if estimate.model == "ff6":
            beta_candidates = [
                f"beta_ff6_{lookback}m",
                f"beta_ff6_{lookback}_month",
                f"b_ff6_{lookback}_month",
            ]
            r2_candidates = [
                f"r2_ff6_{lookback}m",
                f"r2_ff6_{lookback}_month",
            ]
            self._set_first_existing(updates, symbol_columns, beta_candidates, estimate.beta)
            if estimate.r_squared is not None:
                self._set_first_existing(updates, symbol_columns, r2_candidates, estimate.r_squared)
            return

        if estimate.model == "fundamental":
            # Keep 12m as the canonical summary value and avoid overwriting it
            # with longer-window runs when multiple horizons are calculated.
            if lookback == 12:
                beta_candidates = [
                    "beta_fundamental_12m",
                    "beta_fundamental_12_month",
                    "beta_fundamental",
                ]
                # Mirror 12m into legacy generic column when present.
                if "beta_fundamental" in symbol_columns:
                    updates["beta_fundamental"] = estimate.beta
            else:
                beta_candidates = [
                    f"beta_fundamental_{lookback}m",
                    f"beta_fundamental_{lookback}_month",
                ]
            self._set_first_existing(updates, symbol_columns, beta_candidates, estimate.beta)
            return

        if estimate.model == "blended":
            beta_candidates = [
                f"beta_blended_{lookback}m",
                f"beta_blended_{lookback}_month",
                f"beta_blend_{lookback}m",
                f"b_blend_{lookback}_month",
            ]
            r2_candidates = [
                f"r2_blended_{lookback}m",
                f"r2_blended_{lookback}_month",
                f"r2_blend_{lookback}m",
            ]
            self._set_first_existing(updates, symbol_columns, beta_candidates, estimate.beta)
            if estimate.r_squared is not None:
                self._set_first_existing(updates, symbol_columns, r2_candidates, estimate.r_squared)

    def _apply_symbol_updates(self, cursor, symbol_updates: Dict[str, Dict[str, Any]]) -> int:
        updated_rows = 0
        for symbol, values in symbol_updates.items():
            if not values:
                continue
            columns = sorted(values.keys())
            params = [values[col] for col in columns]
            set_clause = ", ".join(f"{col} = %s" for col in columns)
            query = f"""
                UPDATE symbol
                SET {set_clause}, lastupdts = CURRENT_TIMESTAMP
                WHERE ticker = %s
            """
            cursor.execute(query, params + [symbol])
            updated_rows += cursor.rowcount
        return updated_rows

    @staticmethod
    def _set_first_existing(
        updates: Dict[str, float],
        symbol_columns: Set[str],
        candidates: Iterable[str],
        value: float,
    ) -> None:
        for col in candidates:
            if col in symbol_columns:
                updates[col] = value
                return

    @staticmethod
    def _winsorize_series(series: pd.Series, pct: float) -> pd.Series:
        if pct <= 0 or pct >= 0.5:
            return series
        clean = series.dropna()
        if len(clean) < 20:
            return series
        lower = clean.quantile(pct)
        upper = clean.quantile(1 - pct)
        return series.clip(lower=lower, upper=upper)

    @staticmethod
    def _ols_single_factor(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x = x[mask]
        y = y[mask]
        if len(x) < 3:
            return 0.0, math.nan, 0.0

        X = np.column_stack([np.ones(len(x)), x])
        coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        y_hat = X @ coef
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 0.0 if ss_tot <= 0 else max(0.0, 1.0 - (ss_res / ss_tot))
        alpha = float(coef[0])
        beta = float(coef[1])
        return alpha, beta, r2

    @staticmethod
    def _ols_multi_factor(x: np.ndarray, y: np.ndarray) -> Tuple[float, np.ndarray, float]:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = np.isfinite(y)
        if x.ndim != 2:
            return 0.0, np.full(6, np.nan), 0.0
        for i in range(x.shape[1]):
            mask &= np.isfinite(x[:, i])
        x = x[mask]
        y = y[mask]
        if len(y) < 10:
            return 0.0, np.full(6, np.nan), 0.0

        X = np.column_stack([np.ones(len(y)), x])
        coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        y_hat = X @ coef
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 0.0 if ss_tot <= 0 else max(0.0, 1.0 - (ss_res / ss_tot))
        alpha = float(coef[0])
        betas = np.asarray(coef[1:], dtype=float)
        return alpha, betas, r2

    @staticmethod
    def _first_nonempty(row: Dict[str, Any], keys: Sequence[str]) -> Optional[Any]:
        for key in keys:
            val = row.get(key)
            if val is not None and str(val).strip() != "":
                return val
        return None

    def _extract_debt_to_equity(self, row: Dict[str, Any]) -> float:
        candidates = [
            row.get("debt_to_equity"),
            row.get("debttoequity"),
            row.get("DebtToEquity"),
        ]
        for value in candidates:
            parsed = self._safe_float(value)
            if parsed is not None and np.isfinite(parsed):
                return float(np.clip(parsed, 0.0, 10.0))

        total_debt = self._safe_float(row.get("total_debt")) or self._safe_float(row.get("totaldebt"))
        market_cap = self._safe_float(row.get("mktcap")) or self._safe_float(row.get("market_cap"))
        if total_debt is not None and market_cap and market_cap > 0:
            return float(np.clip(total_debt / market_cap, 0.0, 10.0))

        return 0.0

    def _extract_tax_rate(self, row: Dict[str, Any]) -> float:
        tax_candidates = [
            row.get("tax_rate"),
            row.get("taxrate"),
            row.get("effective_tax_rate"),
        ]
        for value in tax_candidates:
            parsed = self._safe_float(value)
            if parsed is None:
                continue
            if parsed > 1:
                parsed = parsed / 100.0
            if 0 <= parsed <= 0.6:
                return parsed
        return 0.21

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            result = float(value)
            if not np.isfinite(result):
                return None
            return result
        except (TypeError, ValueError):
            return None


def _parse_windows(value: str) -> List[int]:
    out = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            number = int(part)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid window '{part}'") from exc
        if number <= 0:
            raise argparse.ArgumentTypeError("Window months must be positive")
        out.append(number)
    if not out:
        raise argparse.ArgumentTypeError("At least one lookback window is required")
    return sorted(set(out))


def _parse_models(value: str) -> Set[str]:
    raw = {x.strip().lower() for x in str(value or "").split(",") if x.strip()}
    if not raw:
        raise argparse.ArgumentTypeError("At least one model is required")
    if "all" in raw:
        return set(VALID_MODELS)
    invalid = sorted(raw - VALID_MODELS)
    if invalid:
        raise argparse.ArgumentTypeError(f"Invalid model(s): {', '.join(invalid)}")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate market/FF6/fundamental beta models")
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated symbols (overrides universe)",
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="sp500",
        choices=["sp500", "russell1000", "all_listed"],
        help="Symbol universe when --symbols is not provided",
    )
    parser.add_argument(
        "--models",
        type=_parse_models,
        default=set(VALID_MODELS),
        help="Comma-separated beta models: market,ff6,fundamental,blended or all",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="SPY",
        help="Benchmark ticker for market beta (default: SPY)",
    )
    parser.add_argument(
        "--windows",
        type=_parse_windows,
        default=[12, 24, 36, 60],
        help="Comma-separated lookback windows in months",
    )
    parser.add_argument(
        "--frequency",
        type=str,
        choices=["daily", "weekly"],
        default="daily",
        help="Return frequency for market beta",
    )
    parser.add_argument(
        "--min-obs",
        type=int,
        default=126,
        help="Minimum observations required for regression models",
    )
    parser.add_argument(
        "--winsorize-pct",
        type=float,
        default=0.01,
        help="Tail winsorization percent for returns/factors (0 to disable)",
    )
    parser.add_argument(
        "--max-abs-beta",
        type=float,
        default=20.0,
        help="Reject estimates where |beta| exceeds this threshold",
    )
    parser.add_argument(
        "--no-fred-rf",
        action="store_true",
        help="Disable FRED DFF fallback for risk-free series",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write")
    args = parser.parse_args()

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    collector = BetaModelCollector(
        symbols=symbols,
        universe=args.universe,
        models=args.models if isinstance(args.models, set) else _parse_models(args.models),
        benchmark=args.benchmark,
        windows=args.windows if isinstance(args.windows, list) else _parse_windows(args.windows),
        frequency=args.frequency,
        min_obs=max(20, int(args.min_obs)),
        winsorize_pct=max(0.0, min(float(args.winsorize_pct), 0.49)),
        max_abs_beta=max(1.0, float(args.max_abs_beta)),
        use_fred_rf=not args.no_fred_rf,
        dry_run=args.dry_run,
    )
    sys.exit(collector.run())


if __name__ == "__main__":
    main()

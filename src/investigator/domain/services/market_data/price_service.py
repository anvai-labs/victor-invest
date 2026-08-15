# Copyright 2025 Vijaykumar Singh
# SPDX-License-Identifier: Apache-2.0
"""
Price Service - Handles historical stock price lookup.

This service provides:
- Historical price lookup from stock database
- Current price fetching
- Price range queries for technical analysis

Note: Prices in the database are typically split-adjusted, meaning historical
prices are retroactively adjusted for splits. When using historical prices
with shares data, use SharesService.get_shares_history() which normalizes
shares to match split-adjusted prices.

Example:
    service = PriceService()

    # Get price on a specific date
    price = service.get_price("AAPL", date(2024, 6, 15))

    # Get current price
    current = service.get_current_price("AAPL")

    # Get price history for a range
    history = service.get_price_history("AAPL", start_date, end_date)
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


@dataclass
class PriceData:
    """Container for price data."""

    symbol: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int | None


class PriceService:
    """
    Service for stock price data.

    Connects to stock database for historical and current prices.
    All prices are split-adjusted.
    """

    def __init__(
        self,
        stock_db_url: str | None = None,
    ):
        """
        Initialize PriceService with database connection.

        Args:
            stock_db_url: Connection string for stock database.
                         If None, builds from environment variables.
        """
        from investigator.domain.services.market_data import get_stock_db_url

        if stock_db_url is None:
            stock_db_url = get_stock_db_url()

        self.stock_engine = create_engine(
            stock_db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self.StockSession = sessionmaker(bind=self.stock_engine)

    def get_price(
        self,
        symbol: str,
        target_date: date,
        search_days: int = 5,
    ) -> float | None:
        """
        Get stock closing price on or near target date.

        Searches backwards from target_date up to search_days to handle
        weekends and holidays. The backward search is bounded by search_days so a
        stale price from far before target_date (e.g. near a data gap or a
        delisting) is never silently returned; in that case None is returned and
        the caller should drop the observation.

        Args:
            symbol: Stock ticker
            target_date: Date to get price for
            search_days: Max calendar days to search backward (default: 5)

        Returns:
            Closing price or None if no trading day exists within search_days
        """
        min_date = target_date - timedelta(days=search_days)
        with self.stock_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT close
                    FROM tickerdata
                    WHERE ticker = :symbol
                      AND date <= :target_date
                      AND date >= :min_date
                    ORDER BY date DESC
                    LIMIT 1
                """),
                {"symbol": symbol, "target_date": target_date, "min_date": min_date},
            ).fetchone()

            if result:
                return float(result[0])
            return None

    def get_current_price(self, symbol: str) -> float | None:
        """
        Get most recent closing price.

        Args:
            symbol: Stock ticker

        Returns:
            Most recent closing price or None
        """
        return self.get_price(symbol, date.today())

    def get_last_close(self, symbol: str) -> tuple[date, float] | None:
        """Get the most recent (date, close) with NO staleness bound.

        Unlike ``get_price``/``get_current_price`` (which cap the backward search so
        stale prices are not returned for live names), this returns the final
        available ``tickerdata`` row regardless of age. For a delisted/merged name
        — whose ``tickerdata`` rows simply stop at delisting — this is the last
        traded price and the de-facto last-trade date, the natural source for a
        delisting event's ``last_price``.
        """
        with self.stock_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT date, close
                    FROM tickerdata
                    WHERE ticker = :symbol
                    ORDER BY date DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol},
            ).fetchone()
            if result and result[1] is not None:
                return (result[0], float(result[1]))
            return None

    def get_price_data(
        self,
        symbol: str,
        target_date: date,
    ) -> PriceData | None:
        """
        Get full OHLCV data for a date.

        Args:
            symbol: Stock ticker
            target_date: Date to get data for

        Returns:
            PriceData with OHLCV or None
        """
        with self.stock_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT date, open, high, low, close, volume
                    FROM tickerdata
                    WHERE ticker = :symbol
                      AND date <= :target_date
                    ORDER BY date DESC
                    LIMIT 1
                """),
                {"symbol": symbol, "target_date": target_date},
            ).fetchone()

            if result:
                return PriceData(
                    symbol=symbol,
                    date=result[0],
                    open=float(result[1]) if result[1] else None,
                    high=float(result[2]) if result[2] else None,
                    low=float(result[3]) if result[3] else None,
                    close=float(result[4]),
                    volume=int(result[5]) if result[5] else None,
                )
            return None

    def get_price_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """
        Get price history for a date range.

        Args:
            symbol: Stock ticker
            start_date: Start date (inclusive)
            end_date: End date (inclusive, default: today)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        if end_date is None:
            end_date = date.today()

        with self.stock_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT date, open, high, low, close, volume
                    FROM tickerdata
                    WHERE ticker = :symbol
                      AND date >= :start_date
                      AND date <= :end_date
                    ORDER BY date ASC
                """),
                {"symbol": symbol, "start_date": start_date, "end_date": end_date},
            ).fetchall()

            if result:
                df = pd.DataFrame(result, columns=["date", "open", "high", "low", "close", "volume"])
                return df
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    def get_price_at_lookback(
        self,
        symbol: str,
        months_back: int,
        reference_date: date | None = None,
    ) -> float | None:
        """
        Get price at a specific lookback period.

        Convenience method for backtesting scenarios.

        Args:
            symbol: Stock ticker
            months_back: Number of months back from reference_date
            reference_date: Reference date (default: today)

        Returns:
            Closing price or None
        """
        from dateutil.relativedelta import relativedelta

        if reference_date is None:
            reference_date = date.today()

        target_date = reference_date - relativedelta(months=months_back)
        return self.get_price(symbol, target_date)

    def get_prices_for_lookbacks(
        self,
        symbol: str,
        lookback_months: list[int],
        reference_date: date | None = None,
    ) -> dict[int, float | None]:
        """
        Get prices for multiple lookback periods.

        Args:
            symbol: Stock ticker
            lookback_months: List of months back (e.g., [36, 24, 12, 6, 3])
            reference_date: Reference date (default: today)

        Returns:
            Dict mapping months_back -> price
        """
        from dateutil.relativedelta import relativedelta

        if reference_date is None:
            reference_date = date.today()

        result = {}
        for months in lookback_months:
            target_date = reference_date - relativedelta(months=months)
            result[months] = self.get_price(symbol, target_date)

        return result

    def calculate_return(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> float | None:
        """
        Calculate price return between two dates.

        Args:
            symbol: Stock ticker
            start_date: Start date
            end_date: End date

        Returns:
            Return as decimal (e.g., 0.15 for 15% return) or None
        """
        start_price = self.get_price(symbol, start_date)
        end_price = self.get_price(symbol, end_date)

        if start_price and end_price and start_price > 0:
            return (end_price - start_price) / start_price

        return None

    def get_volatility(
        self,
        symbol: str,
        days: int = 30,
        end_date: date | None = None,
    ) -> float | None:
        """
        Calculate historical volatility (annualized standard deviation of returns).

        Args:
            symbol: Stock ticker
            days: Number of trading days to use
            end_date: End date (default: today)

        Returns:
            Annualized volatility or None
        """
        import numpy as np

        if end_date is None:
            end_date = date.today()

        start_date = end_date - timedelta(days=days * 2)  # Get extra days for weekends
        df = self.get_price_history(symbol, start_date, end_date)

        if len(df) < 10:
            return None

        # Take last N days
        df = df.tail(days + 1)

        # Calculate daily returns
        df["return"] = df["close"].pct_change()

        # Annualize (252 trading days)
        daily_vol = df["return"].std()
        return daily_vol * np.sqrt(252) if daily_vol else None

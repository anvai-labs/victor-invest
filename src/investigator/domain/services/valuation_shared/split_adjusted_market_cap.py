#!/usr/bin/env python3
"""
Split-Adjusted Market Cap Calculator

Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

This module provides utilities for calculating market cap correctly when
dealing with stock splits.

The Problem:
- tickerdata prices are split-adjusted by exchanges
- SEC shares_outstanding are actual (not split-adjusted)
- Simply multiplying: market_cap = price × shares gives WRONG results after splits

The Solution:
- For current data: Use split-adjusted price with split-adjusted shares (from tickerdata)
- For historical data: De-adjust price using cumulative split ratio, then multiply by SEC shares
- Best: Use enterprise-level P/E = market_cap / net_income (shares cancel out)

Usage:
    from investigator.domain.services.valuation_shared.split_adjusted_market_cap import (
        calculate_market_cap,
        calculate_market_cap_from_sec_data,
        get_split_adjusted_price,
    )
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from investigator.infrastructure.database.db import get_database_engine

logger = logging.getLogger(__name__)


def get_split_adjusted_price(
    symbol: str,
    split_adjusted_price: float,
    price_date: date,
    engine: Optional[Engine] = None,
) -> float:
    """
    Convert split-adjusted price to actual price for a specific date.

    Exchanges retroactively split-adjust prices. To calculate market cap
    correctly with SEC shares (which are actual, not split-adjusted), we
    need to de-adjust the price.

    Args:
        symbol: Stock ticker
        split_adjusted_price: Current price from tickerdata (split-adjusted)
        price_date: Date of the price (for determining which splits to apply)
        engine: Database engine (optional, uses default if None)

    Returns:
        Actual (non-split-adjusted) price as of price_date

    Example:
        GOOGL on 2020-12-31 with 20:1 split in 2022:
        - Split-adjusted price: $140
        - Splits since 2020: 20:1
        - Actual price: $140 × 20 = $2,800
    """
    if engine is None:
        engine = get_database_engine()

    try:
        with engine.connect() as conn:
            # Get cumulative split ratio from price_date to now
            result = conn.execute(
                text("""
                    SELECT COALESCE(EXP(SUM(LN(split_ratio))), 1.0) as cumulative_ratio
                    FROM stock_splits
                    WHERE symbol = :symbol
                        AND split_date > :price_date
                        AND split_date <= CURRENT_DATE
                """),
                {"symbol": symbol.upper(), "price_date": price_date},
            )

            row = result.fetchone()
            if row:
                cumulative_ratio = float(row[0])
                actual_price = split_adjusted_price * cumulative_ratio
                logger.debug(
                    f"{symbol} {price_date}: De-adjusted price from ${split_adjusted_price:.2f} "
                    f"to ${actual_price:.2f} (ratio: {cumulative_ratio:.2f}x)"
                )
                return actual_price
            else:
                # No splits since price_date, return as-is
                return split_adjusted_price

    except Exception as e:
        logger.error(f"Error getting split adjustment for {symbol}: {e}")
        # Fallback: return original price
        return split_adjusted_price


def calculate_market_cap(
    symbol: str,
    price: float,
    shares: float,
    price_date: Optional[date] = None,
    shares_source: str = "sec",
    engine: Optional[Engine] = None,
) -> Optional[float]:
    """
    Calculate market cap accounting for stock splits.

    IMPORTANT: The behavior depends on where shares came from:

    If shares from tickerdata (split-adjusted):
        - Use price directly: market_cap = price × shares
        - Both are on same split-adjusted basis

    If shares from SEC (actual, not split-adjusted):
        - Must de-adjust price: actual_price = split_adjusted_price × split_ratio
        - Then: market_cap = actual_price × actual_shares

    Args:
        symbol: Stock ticker
        price: Price from tickerdata (split-adjusted)
        shares: Shares outstanding
        price_date: Date of the price (required if shares from SEC)
        shares_source: "tickerdata" (split-adjusted) or "sec" (actual)
        engine: Database engine

    Returns:
        Market cap in dollars, or None if calculation fails

    Example:
        GOOGL 2020 with SEC shares:
        - price = $140 (split-adjusted), shares = 675M (actual)
        - price_date = 2020-12-31
        - actual_price = $140 × 20 = $2,800
        - market_cap = $2,800 × 675M = $1.89T ✓

        GOOGL 2024 with SEC shares (post-split):
        - price = $140, shares = 13,200M
        - No adjustment needed (already at current split basis)
        - market_cap = $140 × 13,200M = $1.85T ≈ $1.89T ✓
    """
    if not price or not shares:
        return None

    if shares_source == "tickerdata":
        # Both price and shares are split-adjusted - multiply directly
        return price * shares

    elif shares_source == "sec":
        # Shares are actual (not split-adjusted), need to de-adjust price
        if price_date is None:
            logger.warning(
                f"{symbol}: price_date required when shares_source='sec', "
                "defaulting to current date (may be incorrect for historical data)"
            )
            price_date = datetime.now().date()

        # For current date, no adjustment needed
        if price_date >= datetime.now().date() - timedelta(days=7):
            return price * shares

        # For historical dates, de-adjust price
        actual_price = get_split_adjusted_price(symbol, price, price_date, engine)
        return actual_price * shares

    else:
        logger.error(f"Unknown shares_source: {shares_source}")
        return None


def calculate_market_cap_from_sec_data(
    symbol: str,
    split_adjusted_price: float,
    sec_shares: float,
    sec_fiscal_year: int,
    engine: Optional[Engine] = None,
) -> Optional[float]:
    """
    Calculate market cap using SEC shares and split-adjusted price.

    This is specifically for the case where we have:
    - Current/historical price from tickerdata (split-adjusted)
    - Actual shares from SEC company facts (not split-adjusted)

    Args:
        symbol: Stock ticker
        split_adjusted_price: Price from tickerdata
        sec_shares: Actual shares outstanding from SEC
        sec_fiscal_year: Fiscal year (for determining split adjustment)
        engine: Database engine

    Returns:
        Correct market cap, or None if data unavailable
    """
    if not split_adjusted_price or not sec_shares:
        return None

    if engine is None:
        engine = get_database_engine()

    try:
        with engine.connect() as conn:
            # Get fiscal period end date
            result = conn.execute(
                text("""
                    SELECT period_end_date
                    FROM sec_companyfacts_processed
                    WHERE symbol = :symbol
                        AND fiscal_year = :fiscal_year
                        AND fiscal_period = 'FY'
                    LIMIT 1
                """),
                {"symbol": symbol.upper(), "fiscal_year": sec_fiscal_year},
            )

            row = result.fetchone()
            if not row:
                logger.warning(f"Could not find period_end_date for {symbol} FY{sec_fiscal_year}")
                return None

            period_end_date = row[0]

            # Calculate market cap with split adjustment
            mcap = calculate_market_cap(
                symbol=symbol,
                price=split_adjusted_price,
                shares=sec_shares,
                price_date=period_end_date,
                shares_source="sec",
                engine=engine,
            )

            return mcap

    except Exception as e:
        logger.error(f"Error calculating market cap for {symbol}: {e}")
        return None


def calculate_enterprise_pe(
    symbol: str,
    market_cap: Optional[float],
    net_income: Optional[float],
) -> Optional[float]:
    """
    Calculate P/E ratio using enterprise-level valuation (split-independent).

    P/E = Market Cap / Net Income

    This is split-independent because shares cancel out:
    - Market Cap = Shares × Price (both adjusted same way by split)
    - Net Income = EPS × Shares (both adjusted same way by split)
    - P/E = (Shares × Price) / (EPS × Shares) = Price / EPS

    But the KEY INSIGHT: if we use market_cap / net_income directly,
    we don't need to worry about split adjustment at all!

    Args:
        symbol: Stock ticker
        market_cap: Market capitalization
        net_income: Net income from SEC

    Returns:
        P/E ratio, or None if data unavailable
    """
    if not market_cap or not net_income or net_income <= 0:
        return None

    return market_cap / net_income


# Convenience function for common use case
def get_market_cap_with_split_adjustment(
    symbol: str,
    current_price: float,
    sec_shares: float,
    fiscal_year: int,
    engine: Optional[Engine] = None,
) -> dict:
    """
    Get market cap and related metrics with proper split adjustment.

    Args:
        symbol: Stock ticker
        current_price: Current price from tickerdata (split-adjusted)
        sec_shares: Actual shares from SEC
        fiscal_year: Fiscal year of the SEC data
        engine: Database engine

    Returns:
        Dict with market_cap, notes about split adjustment
    """
    mcap = calculate_market_cap_from_sec_data(symbol, current_price, sec_shares, fiscal_year, engine)

    return {
        "symbol": symbol,
        "market_cap": mcap,
        "current_price": current_price,
        "sec_shares": sec_shares,
        "fiscal_year": fiscal_year,
        "split_adjusted": True,
    }

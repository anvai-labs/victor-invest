#!/usr/bin/env python3
"""
Stock Split Adjuster Service

Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

This service provides split-adjusted EPS calculations to enable accurate
comparisons of earnings per share across stock split events.

Key Concepts:
- Stock splits change shares outstanding proportionally
- SEC data reports actual shares at fiscal year-end (NOT split-adjusted)
- EPS = Net Income / Shares Outstanding uses actual shares
- Pre-split and post-split EPS are NOT directly comparable
- This service adjusts EPS to a common split basis for comparison

Example:
    GOOGL had a 20:1 split in July 2022
    - 2020 EPS: $59.64 (pre-split, ~675M shares)
    - 2024 EPS: $8.13 (post-split, ~12.3B shares)
    - Split-adjusted 2020 EPS: $59.64 / 20 = $2.98
    - Real growth: $2.98 → $8.13 = +173% ✅

Usage:
    from investigator.domain.services.stock_split_adjuster import StockSplitAdjuster

    adjuster = StockSplitAdjuster()
    adjusted_eps = adjuster.get_split_adjusted_eps('GOOGL', 2020, 'FY', 59.64, target_year=2024)
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from investigator.infrastructure.database.db import get_database_engine

logger = logging.getLogger(__name__)


@dataclass
class StockSplit:
    """Represents a stock split event"""

    symbol: str
    split_date: date
    split_ratio: float  # e.g., 20.0 for 20:1 split, 0.5 for 1:2 reverse split
    description: Optional[str] = None

    def __post_init__(self):
        """Validate split ratio"""
        if self.split_ratio <= 0:
            raise ValueError(f"Split ratio must be positive, got {self.split_ratio}")


@dataclass
class SplitAdjustedEPS:
    """Result of split-adjusted EPS calculation"""

    symbol: str
    fiscal_year: int
    fiscal_period: str
    raw_eps: float
    split_adjusted_eps: float
    adjustment_factor: float
    splits_applied: List[StockSplit]
    target_year: Optional[int] = None

    def __str__(self) -> str:
        """Human-readable representation"""
        splits_str = (
            ", ".join(f"{s.split_date.strftime('%Y-%m-%d')} ({s.split_ratio}x)" for s in self.splits_applied)
            if self.splits_applied
            else "None"
        )

        return (
            f"{self.symbol} {self.fiscal_year} {self.fiscal_period}: "
            f"${self.raw_eps:.2f} → ${self.split_adjusted_eps:.2f} "
            f"(adjusted by {self.adjustment_factor:.2f}x, splits: {splits_str})"
        )


class StockSplitAdjuster:
    """
    Service for calculating split-adjusted EPS values.

    This service tracks stock splits and provides methods to adjust EPS
    to a common basis for accurate comparisons across time.
    """

    def __init__(self, engine: Optional[Engine] = None):
        """
        Initialize the stock split adjuster.

        Args:
            engine: SQLAlchemy database engine. If None, uses default engine.
        """
        self.engine = engine or get_database_engine()

    def get_splits_for_symbol(self, symbol: str) -> List[StockSplit]:
        """
        Get all stock splits for a symbol, ordered by date.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of StockSplit objects ordered by split_date (oldest first)
        """
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT symbol, split_date, split_ratio, description
                    FROM stock_splits
                    WHERE symbol = :symbol
                        AND split_date IS NOT NULL
                    ORDER BY split_date ASC
                """)

                result = conn.execute(query, {"symbol": symbol})

                splits = [
                    StockSplit(
                        symbol=row[0],
                        split_date=row[1],
                        split_ratio=float(row[2]),
                        description=row[3],
                    )
                    for row in result
                ]

                logger.debug(f"Found {len(splits)} splits for {symbol}")
                return splits

        except Exception as e:
            logger.error(f"Error fetching splits for {symbol}: {e}")
            return []

    def get_splits_between_years(self, symbol: str, from_year: int, to_year: int) -> List[StockSplit]:
        """
        Get all splits that occurred between two fiscal years.

        Args:
            symbol: Stock ticker symbol
            from_year: Starting fiscal year
            to_year: Ending fiscal year

        Returns:
            List of StockSplit objects that occurred in the period
        """
        splits = self.get_splits_for_symbol(symbol)

        # Filter splits that occurred between the years
        # Note: This is a simplified check - fiscal years don't perfectly align with calendar dates
        return [s for s in splits if from_year <= s.split_date.year <= to_year]

    def calculate_cumulative_split_ratio(
        self, symbol: str, before_date: date, after_date: Optional[date] = None
    ) -> float:
        """
        Calculate the cumulative split ratio for a period.

        Args:
            symbol: Stock ticker symbol
            before_date: Only consider splits before this date
            after_date: Only consider splits after this date (exclusive)

        Returns:
            Cumulative split ratio (product of all split ratios in the period)
        """
        splits = self.get_splits_for_symbol(symbol)

        # Filter splits by date range
        if after_date:
            splits = [s for s in splits if after_date < s.split_date < before_date]
        else:
            splits = [s for s in splits if s.split_date < before_date]

        # Calculate cumulative product
        cumulative_ratio = 1.0
        for split in splits:
            cumulative_ratio *= split.split_ratio

        return cumulative_ratio

    def get_split_adjusted_eps(
        self,
        symbol: str,
        fiscal_year: int,
        fiscal_period: str,
        raw_eps: float,
        target_year: Optional[int] = None,
        fiscal_year_end: Optional[date] = None,
    ) -> SplitAdjustedEPS:
        """
        Calculate split-adjusted EPS for a given period.

        Args:
            symbol: Stock ticker symbol
            fiscal_year: Fiscal year of the EPS value
            fiscal_period: Fiscal period ('FY', 'Q1', 'Q2', 'Q3', 'Q4')
            raw_eps: Unadjusted EPS value
            target_year: Target fiscal year for adjustment (default: most recent)
            fiscal_year_end: Date of fiscal year end (defaults to Dec 31)

        Returns:
            SplitAdjustedEPS object with adjustment details
        """
        if fiscal_year_end is None:
            # Assume calendar year end if not specified
            fiscal_year_end = date(fiscal_year, 12, 31)

        if target_year is None:
            # Default to adjusting to the most recent data
            target_year = datetime.now().year

        # Get all splits for the symbol
        all_splits = self.get_splits_for_symbol(symbol)

        # Determine which splits occurred between the EPS year and target year
        # A split affects EPS if it occurred AFTER the fiscal year end
        # of the source year and BEFORE or DURING the target year

        splits_applied = []
        adjustment_factor = 1.0

        for split in all_splits:
            # Split affects adjustment if it's after the source fiscal year end
            # and we're adjusting to a period after the split
            if split.split_date > fiscal_year_end:
                # Check if we should apply this split
                if target_year > split.split_date.year or (
                    target_year == split.split_date.year and fiscal_year < target_year
                ):
                    splits_applied.append(split)
                    adjustment_factor *= split.split_ratio

        # Calculate split-adjusted EPS
        # If adjusting forward (pre-split to post-split): divide by ratio
        # If adjusting backward (post-split to pre-split): multiply by ratio
        split_adjusted_eps = raw_eps / adjustment_factor

        result = SplitAdjustedEPS(
            symbol=symbol,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            raw_eps=raw_eps,
            split_adjusted_eps=split_adjusted_eps,
            adjustment_factor=adjustment_factor,
            splits_applied=splits_applied,
            target_year=target_year,
        )

        logger.debug(str(result))
        return result

    def get_historical_eps_adjusted(
        self,
        symbol: str,
        start_year: int,
        end_year: Optional[int] = None,
        fiscal_period: str = "FY",
    ) -> Dict[int, SplitAdjustedEPS]:
        """
        Get historical EPS values all adjusted to the same (most recent) basis.

        Args:
            symbol: Stock ticker symbol
            start_year: Starting fiscal year
            end_year: Ending fiscal year (default: current year)
            fiscal_period: Fiscal period to query ('FY', 'Q1', etc.)

        Returns:
            Dictionary mapping year -> SplitAdjustedEPS object
        """
        if end_year is None:
            end_year = datetime.now().year

        # Fetch raw EPS data from sec_companyfacts_processed
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT
                        fiscal_year,
                        fiscal_period,
                        ROUND((net_income / NULLIF(shares_outstanding, 0))::numeric, 2) as eps
                    FROM sec_companyfacts_processed
                    WHERE symbol = :symbol
                        AND fiscal_year BETWEEN :start_year AND :end_year
                        AND fiscal_period = :fiscal_period
                        AND shares_outstanding IS NOT NULL
                        AND shares_outstanding > 0
                        AND net_income IS NOT NULL
                    ORDER BY fiscal_year ASC
                """)

                result = conn.execute(
                    query,
                    {
                        "symbol": symbol,
                        "start_year": start_year,
                        "end_year": end_year,
                        "fiscal_period": fiscal_period,
                    },
                )

                adjusted_data = {}
                for row in result:
                    year, period, eps = row
                    if eps:
                        # Adjust each year's EPS to the end_year basis
                        adjusted = self.get_split_adjusted_eps(
                            symbol=symbol,
                            fiscal_year=year,
                            fiscal_period=period,
                            raw_eps=float(eps),
                            target_year=end_year,
                        )
                        adjusted_data[year] = adjusted

                return adjusted_data

        except Exception as e:
            logger.error(f"Error fetching historical EPS for {symbol}: {e}")
            return {}

    def calculate_eps_growth_rate(
        self,
        symbol: str,
        start_year: int,
        end_year: int,
        fiscal_period: str = "FY",
        use_split_adjusted: bool = True,
    ) -> Optional[float]:
        """
        Calculate EPS growth rate between two years.

        Args:
            symbol: Stock ticker symbol
            start_year: Starting fiscal year
            end_year: Ending fiscal year
            fiscal_period: Fiscal period ('FY', 'Q1', etc.)
            use_split_adjusted: If True, use split-adjusted EPS

        Returns:
            Growth rate as percentage (e.g., 15.5 for 15.5% growth), or None if data unavailable
        """
        if use_split_adjusted:
            adjusted_data = self.get_historical_eps_adjusted(symbol, start_year, end_year, fiscal_period)

            if start_year not in adjusted_data or end_year not in adjusted_data:
                logger.warning(f"Missing EPS data for {symbol} between {start_year} and {end_year}")
                return None

            start_eps = adjusted_data[start_year].split_adjusted_eps
            end_eps = adjusted_data[end_year].split_adjusted_eps
        else:
            # Fetch raw EPS without split adjustment
            try:
                with self.engine.connect() as conn:
                    query = text("""
                        SELECT
                            fiscal_year,
                            ROUND((net_income / NULLIF(shares_outstanding, 0))::numeric, 2) as eps
                        FROM sec_companyfacts_processed
                        WHERE symbol = :symbol
                            AND fiscal_year IN (:start_year, :end_year)
                            AND fiscal_period = :fiscal_period
                            AND shares_outstanding IS NOT NULL
                            AND shares_outstanding > 0
                            AND net_income IS NOT NULL
                        ORDER BY fiscal_year
                    """)

                    result = conn.execute(
                        query,
                        {
                            "symbol": symbol,
                            "start_year": start_year,
                            "end_year": end_year,
                            "fiscal_period": fiscal_period,
                        },
                    )

                    eps_data = {row[0]: float(row[1]) for row in result}

                    if start_year not in eps_data or end_year not in eps_data:
                        return None

                    start_eps = eps_data[start_year]
                    end_eps = eps_data[end_year]

            except Exception as e:
                logger.error(f"Error calculating EPS growth for {symbol}: {e}")
                return None

        # Calculate growth rate
        if start_eps <= 0:
            logger.warning(f"Invalid start EPS for {symbol} {start_year}: {start_eps}")
            return None

        growth_rate = ((end_eps / start_eps) - 1) * 100

        logger.info(
            f"{symbol} EPS growth ({start_year}→{end_year}): "
            f"${start_eps:.2f} → ${end_eps:.2f} = {growth_rate:.1f}% "
            f"{'(split-adjusted)' if use_split_adjusted else '(raw)'}"
        )

        return growth_rate

    def add_split(
        self,
        symbol: str,
        split_date: date,
        split_ratio: float,
        description: Optional[str] = None,
    ) -> bool:
        """
        Add a new stock split to the database.

        Args:
            symbol: Stock ticker symbol
            split_date: Date of the split
            split_ratio: Split ratio (e.g., 20.0 for 20:1, 0.5 for 1:2 reverse)
            description: Optional description

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                query = text("""
                    INSERT INTO stock_splits (symbol, split_date, split_ratio, description)
                    VALUES (:symbol, :split_date, :split_ratio, :description)
                    ON CONFLICT (symbol, split_date) DO UPDATE SET
                        split_ratio = EXCLUDED.split_ratio,
                        description = EXCLUDED.description,
                        updated_at = NOW()
                """)

                conn.execute(
                    query,
                    {
                        "symbol": symbol.upper(),
                        "split_date": split_date,
                        "split_ratio": split_ratio,
                        "description": description,
                    },
                )
                conn.commit()

                logger.info(f"Added stock split: {symbol} {split_date} {split_ratio}x")
                return True

        except Exception as e:
            logger.error(f"Error adding stock split: {e}")
            return False

    def get_actual_price_for_date(self, symbol: str, split_adjusted_price: float, price_date: date) -> float:
        """
        Convert split-adjusted price to actual price as of a specific date.

        Exchanges retroactively split-adjust historical prices. To calculate
        market cap correctly for a historical date, we need to reverse this.

        Example GOOGL 20:1 split on 2022-07-18:
        - Price in 2020 tickerdata: $140 (split-adjusted)
        - Splits between 2020 and now: 20:1
        - Actual price in 2020: $140 × 20 = $2,800
        - Market cap: 675M shares × $2,800 = $1.89T ✓

        Args:
            symbol: Stock ticker symbol
            split_adjusted_price: Price from tickerdata (split-adjusted)
            price_date: The date as of which we want the actual price

        Returns:
            Actual (non-split-adjusted) price as of price_date
        """
        # Get cumulative split ratio from price_date to today
        # These are splits that happened AFTER price_date
        cumulative_ratio = self.calculate_cumulative_split_ratio(
            symbol=symbol, before_date=date.today(), after_date=price_date
        )

        # De-adjust: multiply to reverse split adjustments that happened since
        actual_price = split_adjusted_price * cumulative_ratio
        return actual_price

    def calculate_market_cap(
        self,
        symbol: str,
        price: float,
        shares: float,
        price_date: Optional[date] = None,
    ) -> float:
        """
        Calculate market cap correctly accounting for stock splits.

        IMPORTANT: The price parameter should be the split-adjusted price from
        tickerdata. The shares parameter should be actual shares from SEC.

        We de-adjust the price to match the actual shares, then calculate market cap.

        Args:
            symbol: Stock ticker symbol
            price: Split-adjusted price from tickerdata
            shares: Actual shares outstanding from SEC
            price_date: Date of the price (required for historical data)

        Returns:
            Correct market cap

        Example:
            GOOGL 2020: price=$140 (split-adjusted), shares=675M
            → Actual price = $140 × 20 = $2,800
            → Market cap = 675M × $2,800 = $1.89T ✓

            GOOGL 2024: price=$140, shares=13,200M (post-split)
            → No adjustment needed (already at current split basis)
            → Market cap = 13,200M × $140 = $1.85T ≈ $1.89T ✓
        """
        if price_date is None:
            # Current price - no split adjustment needed
            return price * shares

        # Historical price - need to de-adjust
        actual_price = self.get_actual_price_for_date(symbol, price, price_date)
        return actual_price * shares

    def explain_split_impact(self, symbol: str) -> str:
        """
        Generate a human-readable explanation of split impact on EPS comparisons.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Formatted explanation string
        """
        splits = self.get_splits_for_symbol(symbol)

        if not splits:
            return f"{symbol}: No stock splits recorded."

        lines = [f"{symbol} Stock Split History:", "-" * 60]

        for split in splits:
            lines.append(f"  {split.split_date.strftime('%Y-%m-%d')}: {split.split_ratio}x split")
            if split.description:
                lines.append(f"    ({split.description})")

        lines.append("-" * 60)
        lines.append("Impact on EPS Comparisons:")
        lines.append("  - EPS values before splits are NOT directly comparable to after")
        lines.append("  - Use split_adjusted_eps for accurate growth calculations")
        lines.append("  - Example: Pre-split $50 EPS + 20:1 split → Adjusted $2.50 EPS")

        return "\n".join(lines)


# Singleton instance
_split_adjuster_instance = None


def get_stock_split_adjuster() -> StockSplitAdjuster:
    """Get the global StockSplitAdjuster instance"""
    global _split_adjuster_instance
    if _split_adjuster_instance is None:
        _split_adjuster_instance = StockSplitAdjuster()
    return _split_adjuster_instance


if __name__ == "__main__":
    # Example usage and testing
    import sys

    logging.basicConfig(level=logging.INFO)

    adjuster = get_stock_split_adjuster()

    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
    else:
        symbol = "GOOGL"

    print(f"\n{'=' * 70}")
    print(f"Stock Split Analysis for {symbol}")
    print(f"{'=' * 70}\n")

    # Show split history
    print(adjuster.explain_split_impact(symbol))
    print()

    # Get historical split-adjusted EPS
    print("Split-Adjusted EPS History:")
    print("-" * 70)
    adjusted_data = adjuster.get_historical_eps_adjusted(symbol, 2016, 2024)

    for year in sorted(adjusted_data.keys()):
        adj = adjusted_data[year]
        print(
            f"  {year}: ${adj.raw_eps:.2f} → ${adj.split_adjusted_eps:.2f} (adjustment: {adj.adjustment_factor:.2f}x)"
        )

    print()

    # Calculate growth rate
    growth = adjuster.calculate_eps_growth_rate(symbol, 2016, 2024, use_split_adjusted=True)
    if growth is not None:
        print(f"Split-Adjusted EPS Growth (2016-2024): {growth:.1f}%")

    growth_raw = adjuster.calculate_eps_growth_rate(symbol, 2016, 2024, use_split_adjusted=False)
    if growth_raw is not None:
        print(f"Raw EPS Growth (2016-2024): {growth_raw:.1f}%")
        print("  ⚠️  Raw growth is misleading due to splits!")

    print()

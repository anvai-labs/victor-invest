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

"""Company premium/discount history service.

Analyzes how individual companies trade relative to their sector/industry
to identify mean reversion opportunities and consistent premium/discount patterns.
"""

import logging
import statistics
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, text

from investigator.config import get_config
from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


class CompanyPremiumHistory:
    """Analyze company's historical premium/discount to sector.

    Methods:
        calculate_premium_for_period: Calculate premium for a specific period
        get_historical_premium: Get historical premium statistics
        detect_mean_reversion: Detect mean reversion opportunities
        backfill_premium_history: Backfill historical premium data
        store_premium_record: Store premium record in database
    """

    def __init__(
        self,
        *,
        sec_db_manager: Any = None,
        stock_db_manager: Any = None,
    ):
        """Initialize company premium history service.

        Args:
            sec_db_manager: Database manager for SEC database
            stock_db_manager: Database manager for stock database
        """
        if sec_db_manager is None:
            sec_db_manager = get_db_manager()

        self.sec_db_manager = sec_db_manager

        # Create stock database manager for symbol classification
        if stock_db_manager is None:
            config = get_config()
            stock_db_url = config.database.url.replace("/sec_database", "/stock")
            from investigator.infrastructure.database.db import DatabaseManager

            stock_db_manager = DatabaseManager(config)
            stock_db_manager.engine = create_engine(stock_db_url)
            from sqlalchemy.orm import sessionmaker

            stock_db_manager.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=stock_db_manager.engine
            )

        self.stock_db_manager = stock_db_manager

    def get_historical_premium(
        self,
        symbol: str,
        metric: str = "pe",
        lookback_years: int = 5,
        min_data_points: int = 4,
    ) -> Optional[Dict[str, Any]]:
        """Get historical premium/discount statistics for a company.

        Args:
            symbol: Stock symbol
            metric: Metric to analyze - "pe", "ps", "pb", or "ev_ebitda"
            lookback_years: Years of historical data to analyze
            min_data_points: Minimum data points required

        Returns:
            Dict with historical premium statistics or None if insufficient data
            {
                "symbol": "AAPL",
                "metric": "pe",
                "lookback_years": 5,
                "data_points": 20,
                "avg_premium_pct": 15.2,
                "median_premium_pct": 14.8,
                "std_dev": 3.5,
                "min_premium_pct": 8.2,
                "max_premium_pct": 22.5,
                "current_premium_pct": 14.0,
                "z_score": -0.34,
                "percentile_rank": 45,
                "trend": "stable",
                "mean_reversion_signal": "none",
                "premium_history": [
                    {"fiscal_year": 2020, "fiscal_period": "FY", "premium_pct": 12.5},
                    ...
                ]
            }
        """

        # Validate metric
        valid_metrics = ["pe", "ps", "pb", "ev_ebitda"]
        if metric not in valid_metrics:
            logger.error(f"Invalid metric: {metric}. Must be one of {valid_metrics}")
            return None

        # Map metric to column names
        premium_col = f"{metric}_premium_pct"
        multiple_col = f"{metric}_multiple"

        with self.sec_db_manager.engine.connect() as conn:
            # Get historical premium data
            current_year = datetime.now().year
            start_year = current_year - lookback_years

            query = text(f"""
                SELECT
                    fiscal_year,
                    fiscal_period,
                    {multiple_col} as company_multiple,
                    sector_{metric}_multiple as sector_multiple,
                    {premium_col} as premium_pct,
                    {metric}_z_score as z_score,
                    snapshot_date
                FROM company_sector_premium_history
                WHERE UPPER(symbol) = UPPER(:symbol)
                  AND fiscal_year >= :start_year
                  AND {premium_col} IS NOT NULL
                ORDER BY fiscal_year, fiscal_period
            """)

            result = conn.execute(query, {"symbol": symbol, "start_year": start_year})

            premium_history = []
            for row in result:
                premium_history.append(
                    {
                        "fiscal_year": row[0],
                        "fiscal_period": row[1],
                        "company_multiple": float(row[2]) if row[2] else None,
                        "sector_multiple": float(row[3]) if row[3] else None,
                        "premium_pct": float(row[4]) if row[4] else None,
                        "z_score": float(row[5]) if row[5] else None,
                        "snapshot_date": row[6].isoformat() if row[6] else None,
                    }
                )

        if len(premium_history) < min_data_points:
            logger.warning(
                f"{symbol}: Insufficient historical data "
                f"({len(premium_history)} points, min required: {min_data_points})"
            )
            return None

        # Calculate statistics
        premiums = [p["premium_pct"] for p in premium_history if p["premium_pct"] is not None]

        if not premiums:
            logger.warning(f"{symbol}: No valid premium data found")
            return None

        avg_premium = statistics.mean(premiums)
        median_premium = statistics.median(premiums)
        std_dev = statistics.stdev(premiums) if len(premiums) > 1 else 0.0
        min_premium = min(premiums)
        max_premium = max(premiums)

        # Current premium (most recent)
        current_premium = premium_history[-1]["premium_pct"]

        # Z-score of current premium
        if std_dev > 0:
            z_score = (current_premium - avg_premium) / std_dev
        else:
            z_score = 0.0

        # Percentile rank
        percentile_rank = sum(1 for p in premiums if p <= current_premium) / len(premiums) * 100

        # Trend detection
        if len(premiums) >= 4:
            # Compare first half to second half
            mid = len(premiums) // 2
            early_avg = statistics.mean(premiums[:mid])
            recent_avg = statistics.mean(premiums[mid:])

            change = recent_avg - early_avg
            if change > 2.0:  # 2%+ increase
                trend = "expanding"
            elif change < -2.0:  # -2%+ decrease
                trend = "shrinking"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Mean reversion signal
        mean_reversion_signal = self._detect_mean_reversion_signal(z_score=z_score, trend=trend)

        return {
            "symbol": symbol.upper(),
            "metric": metric,
            "lookback_years": lookback_years,
            "data_points": len(premiums),
            "avg_premium_pct": round(avg_premium, 2),
            "median_premium_pct": round(median_premium, 2),
            "std_dev": round(std_dev, 2),
            "min_premium_pct": round(min_premium, 2),
            "max_premium_pct": round(max_premium, 2),
            "current_premium_pct": round(current_premium, 2),
            "z_score": round(z_score, 2),
            "percentile_rank": round(percentile_rank, 1),
            "trend": trend,
            "mean_reversion_signal": mean_reversion_signal,
            "premium_history": premium_history,
        }

    def detect_mean_reversion(
        self,
        symbol: str,
        metric: str = "pe",
        z_threshold: float = 1.5,
        lookback_years: int = 5,
    ) -> Optional[str]:
        """Detect mean reversion opportunity.

        Args:
            symbol: Stock symbol
            metric: Metric to analyze
            z_threshold: Z-score threshold for signal
            lookback_years: Years of historical data

        Returns:
            "buy" | "sell" | "none" or None if insufficient data
        """
        premium_data = self.get_historical_premium(
            symbol=symbol,
            metric=metric,
            lookback_years=lookback_years,
        )

        if not premium_data:
            return None

        z_score = premium_data.get("z_score", 0)

        if z_score < -z_threshold:
            return "buy"
        elif z_score > z_threshold:
            return "sell"
        else:
            return "none"

    def _detect_mean_reversion_signal(self, z_score: float, trend: str) -> str:
        """Detect mean reversion signal from z-score and trend.

        Args:
            z_score: Current z-score
            trend: Premium trend (expanding/shrinking/stable)

        Returns:
            "strong_buy" | "buy" | "sell" | "strong_sell" | "none"
        """
        if z_score < -2.0:
            # Trading at significant discount
            if trend == "shrinking":
                return "strong_buy"  # Discount likely to revert
            else:
                return "buy"
        elif z_score < -1.0:
            return "buy"
        elif z_score > 2.0:
            # Trading at significant premium
            if trend == "expanding":
                return "strong_sell"  # Premium likely to contract
            else:
                return "sell"
        elif z_score > 1.0:
            return "sell"
        else:
            return "none"

    def calculate_premium_for_period(
        self,
        symbol: str,
        fiscal_year: int,
        fiscal_period: str = "FY",
    ) -> Optional[Dict[str, Any]]:
        """Calculate company's premium/discount for a specific period.

        Args:
            symbol: Stock symbol
            fiscal_year: Fiscal year
            fiscal_period: Fiscal period (Q1, Q2, Q3, Q4, FY)

        Returns:
            Dict with premium data or None if insufficient data
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "sector": "Technology",
                "industry": "Technology Hardware",
                "pe_multiple": 28.5,
                "sector_pe_multiple": 25.0,
                "pe_premium_pct": 14.0,
                "ps_multiple": 8.2,
                "sector_ps_multiple": 7.5,
                "ps_premium_pct": 9.3,
                ...
            }
        """
        # Get company's sector classification
        sector_info = self._get_sector_classification(symbol)
        if not sector_info:
            logger.warning(f"{symbol}: Could not determine sector classification")
            return None

        sector = sector_info["sector"]
        industry = sector_info.get("industry")

        # Get company's multiples for the period
        company_multiples = self._get_company_multiples(symbol, fiscal_year, fiscal_period)
        if not company_multiples:
            logger.warning(f"{symbol}: Could not get multiples for {fiscal_year} {fiscal_period}")
            return None

        # Get sector's multiples for the period
        sector_multiples = self._get_sector_multiples(sector, fiscal_year, fiscal_period)
        if not sector_multiples:
            logger.warning(f"{sector}: Could not get sector multiples for {fiscal_year} {fiscal_period}")
            return None

        # Calculate premiums for all metrics
        result = {
            "symbol": symbol.upper(),
            "fiscal_year": fiscal_year,
            "fiscal_period": fiscal_period,
            "sector": sector,
            "industry": industry,
            "snapshot_date": company_multiples.get("snapshot_date"),
        }

        for metric in ["pe", "ps", "pb", "ev_ebitda"]:
            company_multiple = company_multiples.get(metric)
            sector_multiple = sector_multiples.get(metric)

            if company_multiple and sector_multiple and sector_multiple > 0:
                # Calculate premium percentage
                premium_pct = ((company_multiple - sector_multiple) / sector_multiple) * 100

                result[f"{metric}_multiple"] = round(company_multiple, 2)
                result[f"sector_{metric}_multiple"] = round(sector_multiple, 2)
                result[f"{metric}_premium_pct"] = round(premium_pct, 2)

        return result

    def _get_sector_classification(self, symbol: str) -> Optional[Dict[str, Optional[str]]]:
        """Get company's sector/industry classification.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with sector and industry or None
        """

        with self.stock_db_manager.get_session() as session:
            query = text("""
                SELECT "Sector", "Industry"
                FROM symbol
                WHERE UPPER(ticker) = UPPER(:symbol)
                  AND islisted = true
            """)

            result = session.execute(query, {"symbol": symbol})
            row = result.fetchone()

            if row:
                return {"sector": row[0], "industry": row[1]}

        return None

    def _get_company_multiples(self, symbol: str, fiscal_year: int, fiscal_period: str) -> Optional[Dict[str, Any]]:
        """Get company's valuation multiples for a period.

        Args:
            symbol: Stock symbol
            fiscal_year: Fiscal year
            fiscal_period: Fiscal period

        Returns:
            Dict with multiples or None
        """

        with self.sec_db_manager.engine.connect() as conn:
            query = text("""
                SELECT
                    market_cap,
                    total_revenue,
                    net_income,
                    stockholders_equity,
                    operating_income,
                    operating_cash_flow,
                    capital_expenditures,
                    period_end_date,
                    filed_date
                FROM sec_companyfacts_processed
                WHERE UPPER(symbol) = UPPER(:symbol)
                  AND fiscal_year = :fiscal_year
                  AND fiscal_period = :fiscal_period
            """)

            result = conn.execute(
                query,
                {
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": fiscal_period,
                },
            )
            row = result.fetchone()

            if not row:
                return None

            market_cap = float(row[0]) if row[0] else None
            revenue = float(row[1]) if row[1] else None
            net_income = float(row[2]) if row[2] else None
            equity = float(row[3]) if row[3] else None
            operating_income = float(row[4]) if row[4] else None
            operating_cash_flow = float(row[5]) if row[5] else None
            period_end = row[7]
            filed_date = row[8]

            if not market_cap:
                return None

            multiples = {"snapshot_date": period_end or filed_date}

            # P/E
            if net_income and net_income > 0:
                multiples["pe"] = market_cap / net_income

            # P/S
            if revenue and revenue > 0:
                multiples["ps"] = market_cap / revenue

            # P/B
            if equity and equity > 0:
                multiples["pb"] = market_cap / equity

            # EBITDA approximation: Operating Income + (Operating Cash Flow - Net Income)
            # This is a rough approximation - EBITDA ≈ Operating Income + D&A
            # And D&A ≈ (Operating Cash Flow - Net Income)
            if operating_income and operating_cash_flow and net_income:
                ebitda = operating_income + (operating_cash_flow - net_income)
                if ebitda > 0:
                    # EV ≈ Market Cap (simplified, should include debt - cash)
                    multiples["ev_ebitda"] = market_cap / ebitda

            return multiples if len(multiples) > 1 else None

    def _get_sector_multiples(self, sector: str, fiscal_year: int, fiscal_period: str) -> Optional[Dict[str, float]]:
        """Get sector's median multiples for a period.

        Args:
            sector: Sector name
            fiscal_year: Fiscal year
            fiscal_period: Fiscal period

        Returns:
            Dict with sector multiples or None
        """
        # Try sector_multiples_history table first (for FY data)
        if fiscal_period == "FY":
            return self._get_sector_multiples_from_history(sector, fiscal_year)

        # For quarterly data, calculate on-the-fly
        return self._calculate_sector_multiples_period(sector, fiscal_year, fiscal_period)

    def _get_sector_multiples_from_history(self, sector: str, fiscal_year: int) -> Optional[Dict[str, float]]:
        """Get sector multiples from sector_multiples_history table.

        Args:
            sector: Sector name
            fiscal_year: Fiscal year

        Returns:
            Dict with sector multiples or None
        """

        with self.sec_db_manager.engine.connect() as conn:
            query = text("""
                SELECT
                    pe_multiple,
                    ps_multiple,
                    pb_multiple
                FROM sector_multiples_history
                WHERE group_name = :sector
                  AND group_type = 'sector'
                  AND fiscal_year = :fiscal_year
            """)

            result = conn.execute(query, {"sector": sector, "fiscal_year": fiscal_year})
            row = result.fetchone()

            if row:
                multiples = {}
                if row[0]:
                    multiples["pe"] = float(row[0])
                if row[1]:
                    multiples["ps"] = float(row[1])
                if row[2]:
                    multiples["pb"] = float(row[2])
                return multiples if multiples else None

        return None

    def _calculate_sector_multiples_period(
        self, sector: str, fiscal_year: int, fiscal_period: str
    ) -> Optional[Dict[str, float]]:
        """Calculate sector multiples for a specific period on-the-fly.

        Args:
            sector: Sector name
            fiscal_year: Fiscal year
            fiscal_period: Fiscal period

        Returns:
            Dict with sector multiples or None
        """
        # This would calculate sector multiples from sec_companyfacts_processed
        # For now, return None to indicate not available
        # In production, this would aggregate all companies in the sector
        logger.warning(
            f"On-the-fly sector multiple calculation not yet implemented: " f"{sector} {fiscal_year} {fiscal_period}"
        )
        return None

    def store_premium_record(self, premium_data: Dict[str, Any], update_existing: bool = True) -> bool:
        """Store premium record in database.

        Args:
            premium_data: Dict from calculate_premium_for_period()
            update_existing: Whether to update existing records

        Returns:
            True if successful, False otherwise
        """
        from investigator.infrastructure.database.migrations.versions.create_company_sector_premium_history import (
            CompanySectorPremiumHistory,
        )

        try:
            with self.sec_db_manager.get_session() as session:
                # Check if record exists
                existing = (
                    session.query(CompanySectorPremiumHistory)
                    .filter_by(
                        symbol=premium_data["symbol"],
                        fiscal_year=premium_data["fiscal_year"],
                        fiscal_period=premium_data["fiscal_period"],
                    )
                    .first()
                )

                if existing and update_existing:
                    # Update existing record
                    for key, value in premium_data.items():
                        if key in [
                            "pe_multiple",
                            "ps_multiple",
                            "pb_multiple",
                            "ev_ebitda_multiple",
                            "sector_pe_multiple",
                            "sector_ps_multiple",
                            "sector_pb_multiple",
                            "sector_ev_ebitda_multiple",
                            "pe_premium_pct",
                            "ps_premium_pct",
                            "pb_premium_pct",
                            "ev_ebitda_premium_pct",
                        ]:
                            setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                    logger.debug(
                        f"Updated premium record: {premium_data['symbol']} "
                        f"{premium_data['fiscal_year']} {premium_data['fiscal_period']}"
                    )
                elif not existing:
                    # Create new record
                    record = CompanySectorPremiumHistory(
                        symbol=premium_data["symbol"],
                        sector=premium_data["sector"],
                        industry=premium_data.get("industry"),
                        fiscal_year=premium_data["fiscal_year"],
                        fiscal_period=premium_data["fiscal_period"],
                        snapshot_date=(
                            datetime.fromisoformat(premium_data["snapshot_date"])
                            if premium_data.get("snapshot_date")
                            else datetime.utcnow()
                        ),
                    )

                    # Set all premium fields
                    for key, value in premium_data.items():
                        if key in [
                            "pe_multiple",
                            "ps_multiple",
                            "pb_multiple",
                            "ev_ebitda_multiple",
                            "sector_pe_multiple",
                            "sector_ps_multiple",
                            "sector_pb_multiple",
                            "sector_ev_ebitda_multiple",
                            "pe_premium_pct",
                            "ps_premium_pct",
                            "pb_premium_pct",
                            "ev_ebitda_premium_pct",
                        ]:
                            setattr(record, key, value)

                    session.add(record)
                    logger.debug(
                        f"Created premium record: {premium_data['symbol']} "
                        f"{premium_data['fiscal_year']} {premium_data['fiscal_period']}"
                    )

                session.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to store premium record: {e}")
            return False

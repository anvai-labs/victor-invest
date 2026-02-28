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

"""Historical sector multiples tracking from SEC database.

Calculates and stores historical sector/industry valuation multiples over time
using fiscal year (FY) data from sec_num_data/sec_tag_data tables.

This enables tracking:
- Swelling (multiples expanding over time)
- Shrinking (multiples contracting over time)
- Trends across sectors/industries
- Historical context for current valuations
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from investigator.config import get_config
from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

logger = logging.getLogger(__name__)


class SectorMultiplesHistory:
    """Calculate and store historical sector multiples from SEC data.

    Methods:
        calculate_historical_multiples: Calculate multiples for specific fiscal year
        store_history: Save to database
        get_trend_data: Retrieve historical trend data
        export_to_file: Export to JSON/CSV for analysis
    """

    # Key SEC tags for valuation metrics
    TAGS = {
        "total_revenue": ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"],
        "net_income": ["us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"],
        "ebitda": [],  # Calculated from operating income + D&A
        "operating_income": ["us-gaap:OperatingIncomeLoss"],
        "stockholders_equity": ["us-gaap:StockholdersEquity"],
        "shares_outstanding": ["us-gaap:CommonStockSharesOutstanding"],
    }

    # Quarter end dates (approximate) for announcement proxy (+1 month)
    QUARTER_ENDS = {
        "Q1": (3, 31),  # March 31 -> April 30 announcement
        "Q2": (6, 30),  # June 30 -> July 31 announcement
        "Q3": (9, 30),  # Sept 30 -> Oct 31 announcement
        "Q4": (12, 31),  # Dec 31 -> Jan 31 announcement
        "FY": (12, 31),  # FY uses Dec 31 -> Jan 31
    }

    def __init__(
        self,
        *,
        stock_db_manager: Any = None,
        sec_db_manager: Any = None,
        min_samples: int = 5,
        percentile_exclude: Tuple[float, float] = (0.05, 0.95),
    ):
        """Initialize sector multiples history service.

        Args:
            stock_db_manager: Database manager for stock database
            sec_db_manager: Database manager for SEC database
            min_samples: Minimum number of symbols required
            percentile_exclude: Percentiles for outlier filtering
        """
        # Create stock database manager if not provided
        if stock_db_manager is None:
            import os

            # Use stock database credentials from environment
            stock_user = os.environ.get("STOCK_DB_USER", "stockuser")
            stock_password = os.environ.get("STOCK_DB_PASSWORD", "Am1nt0r")
            stock_host = os.environ.get("STOCK_DB_HOST", "dataserver1.singh.local")
            stock_port = os.environ.get("STOCK_DB_PORT", "5432")
            stock_db_name = os.environ.get("STOCK_DB_NAME", "stock")
            stock_db_url = f"postgresql://{stock_user}:{stock_password}@{stock_host}:{stock_port}/{stock_db_name}"

            from investigator.infrastructure.database.db import DatabaseManager

            config = get_config()
            stock_db_manager = DatabaseManager(config)
            stock_db_manager.engine = create_engine(stock_db_url)
            from sqlalchemy.orm import sessionmaker

            stock_db_manager.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=stock_db_manager.engine
            )

        self.stock_db_manager = stock_db_manager
        # Create sec_db_manager with correct connection to dataserver1
        if sec_db_manager is None:
            import os

            # Use SEC database credentials from environment
            sec_user = os.environ.get("SEC_DB_USER", "investigator")
            sec_password = os.environ.get("SEC_DB_PASSWORD", "investigator")
            sec_host = os.environ.get("SEC_DB_HOST", "dataserver1.singh.local")
            sec_port = os.environ.get("SEC_DB_PORT", "5432")
            sec_db_name = os.environ.get("SEC_DB_NAME", "sec_database")
            sec_db_url = f"postgresql://{sec_user}:{sec_password}@{sec_host}:{sec_port}/{sec_db_name}"

            from investigator.infrastructure.database.db import DatabaseManager

            config = get_config()
            sec_db_manager = DatabaseManager(config)
            # Override engine to connect to dataserver1 with credentials
            sec_db_manager.engine = create_engine(sec_db_url)
            from sqlalchemy.orm import sessionmaker

            sec_db_manager.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sec_db_manager.engine)
        else:
            sec_db_manager = sec_db_manager

        self.sec_db_manager = sec_db_manager
        self.min_samples = min_samples
        self.percentile_exclude = percentile_exclude

    def calculate_historical_multiples(
        self,
        *,
        fiscal_year: int,
        sectors: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        use_config_overrides: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate sector/industry multiples for a specific fiscal year.

        Uses SEC num/tag data for FY values and market data for prices.
        Snapshot date is end of FY quarter + 1 month (announcement proxy).

        Args:
            fiscal_year: Fiscal year to calculate (e.g., 2023, 2024)
            sectors: List of sectors to calculate (None = all)
            industries: List of industries to calculate (None = all)
            use_config_overrides: Apply config.yaml sector overrides

        Returns:
            Dict with calculated multiples for fiscal year
            {
                "Technology": {"pe": 28.5, "ps": 6.2, "fiscal_year": 2024, "sample_size": 150},
                ...
            }
        """
        logger.info(f"Calculating historical multiples for FY{fiscal_year}...")

        # Load config overrides if needed
        config_overrides = {}
        if use_config_overrides:
            config_overrides = self._load_config_overrides()

        # Get symbols in target sectors/industries
        symbol_classification = self._get_symbols_by_sector_industry(
            sectors=sectors, industries=industries, config_overrides=config_overrides
        )

        results = {}

        # Group by sector first (standardizing names)
        sector_groups: Dict[str, List[str]] = {}
        # Track industries with their parent sector: {(industry, sector): [symbols]}
        industry_groups: Dict[Tuple[str, str], List[str]] = {}

        for symbol, sector, industry in symbol_classification:
            # Standardize sector name
            standard_sector = self._standardize_sector_name(sector)
            if standard_sector not in sector_groups:
                sector_groups[standard_sector] = []
            sector_groups[standard_sector].append(symbol)

            if industry:
                # Track industry with its parent sector
                industry_key = (industry, standard_sector)
                if industry_key not in industry_groups:
                    industry_groups[industry_key] = []
                industry_groups[industry_key].append(symbol)

        # Calculate sector-level multiples
        for sector, symbols in sector_groups.items():
            logger.info(f"Calculating for sector: {sector} ({len(symbols)} symbols)")
            multiples = self._calculate_historical_multiples_for_symbols(symbols, f"sector:{sector}", fiscal_year)
            if multiples:
                results[sector] = multiples

        # Calculate industry-level multiples (with sector tracking)
        for (industry, sector), symbols in industry_groups.items():
            logger.info(f"Calculating for industry: {industry} in sector: {sector} ({len(symbols)} symbols)")
            multiples = self._calculate_historical_multiples_for_symbols(symbols, f"industry:{industry}", fiscal_year)
            if multiples:
                # Add sector information to multiples dict for hierarchical storage
                multiples["sector"] = sector
                results[industry] = multiples

        return results

    def _calculate_historical_multiples_for_symbols(
        self, symbols: List[str], group_name: str, fiscal_year: int
    ) -> Optional[Dict[str, Any]]:
        """Calculate valuation multiples for a group of symbols for specific FY.

        Uses SEC tag data for FY values and historical market data for prices.
        Snapshot date is approx. 1 month after FY end (announcement proxy).

        Args:
            symbols: List of stock symbols
            group_name: Name of group (for logging)
            fiscal_year: Fiscal year to calculate

        Returns:
            Dict with calculated multiples or None if insufficient data
        """
        # Get FY metrics from SEC tag data
        fy_metrics = self._get_fy_metrics(symbols, fiscal_year)

        if len(fy_metrics) < self.min_samples:
            logger.warning(
                f"{group_name} FY{fiscal_year}: Insufficient data "
                f"({len(fy_metrics)} symbols, min required: {self.min_samples})"
            )
            return None

        # Calculate multiples for each metric
        pe_multiples = []
        ps_multiples = []
        pb_multiples = []

        skipped_no_mc = 0
        skipped_no_price = 0
        skipped_no_revenue = 0
        skipped_no_eps = 0
        skipped_pb_asset_light = 0

        for symbol, metrics in fy_metrics.items():
            # Skip if no market cap or price
            mc = metrics.get("market_cap")
            price = metrics.get("price")

            if not mc or mc == 0:
                skipped_no_mc += 1
                continue
            if not price:
                skipped_no_price += 1
                continue

            # P/E = Price / EPS
            # EPS = Net Income / Shares
            ni = metrics.get("net_income")
            shares = metrics.get("shares_outstanding")
            if ni and shares and shares > 0:
                eps = ni / shares
                if eps > 0:
                    pe = price / eps
                    if pe > 0 and pe < 1000:  # Sanity check
                        pe_multiples.append(pe)
                else:
                    skipped_no_eps += 1

            # P/S = Market Cap / Revenue
            rev = metrics.get("total_revenue")
            if rev and rev > 0:
                ps = mc / rev
                if ps > 0 and ps < 100:  # Sanity check
                    ps_multiples.append(ps)
            else:
                skipped_no_revenue += 1

            # P/B = Price / Book Value per Share
            # Book Value per Share = Shareholders Equity / Shares
            # Skip asset-light companies where P/B is not meaningful
            equity = metrics.get("stockholders_equity")
            if equity and shares and shares > 0:
                bvps = equity / shares
                if bvps > 0:
                    pb = price / bvps

                    # Detect asset-light companies (payment networks, platforms)
                    # For these, book value is minimal, making P/B artificially high
                    # Threshold: if bvps < 10% of price, it's asset-light (P/B would be > 10x)
                    is_asset_light = bvps < (price * 0.10) if price > 0 else False

                    if is_asset_light:
                        # Skip P/B for asset-light companies - not meaningful
                        logger.debug(
                            f"{symbol}: Excluding from P/B calculation - asset-light model "
                            f"(price=${price:.2f}, bvps=${bvps:.2f}, implied P/B={pb:.1f}x)"
                        )
                        skipped_pb_asset_light += 1
                    elif pb > 0 and pb < 50:  # Sanity check
                        pb_multiples.append(pb)

        # Apply percentile filtering
        pe_median = self._filtered_median(pe_multiples, f"{group_name}_PE")
        ps_median = self._filtered_median(ps_multiples, f"{group_name}_PS")
        pb_median = self._filtered_median(pb_multiples, f"{group_name}_PB")

        # Log data quality metrics
        total_symbols = len(fy_metrics)
        valid_pe = len(pe_multiples)
        valid_ps = len(ps_multiples)
        valid_pb = len(pb_multiples)

        logger.info(
            f"{group_name} FY{fiscal_year}: Data quality - "
            f"Total: {total_symbols}, P/E: {valid_pe}/{total_symbols}, "
            f"P/S: {valid_ps}/{total_symbols}, P/B: {valid_pb}/{total_symbols}, "
            f"Skipped: no_mc={skipped_no_mc}, no_price={skipped_no_price}, "
            f"no_rev={skipped_no_revenue}, no_eps={skipped_no_eps}, "
            f"pb_asset_light={skipped_pb_asset_light}"
        )

        if pe_median is None and ps_median is None:
            logger.warning(f"{group_name} FY{fiscal_year}: No valid multiples calculated")
            return None

        # Calculate snapshot date (FY end + 1 month)
        snapshot_date = datetime(fiscal_year, 12, 31) + timedelta(days=31)

        return {
            "pe": round(pe_median, 2) if pe_median is not None else None,
            "ps": round(ps_median, 2) if ps_median is not None else None,
            "pb": round(pb_median, 2) if pb_median is not None else None,
            "fiscal_year": fiscal_year,
            "snapshot_date": snapshot_date.isoformat(),
            "sample_size": len(fy_metrics),
            "percentile_low": self.percentile_exclude[0],
            "percentile_high": self.percentile_exclude[1],
        }

    def _get_fy_metrics(self, symbols: List[str], fiscal_year: int) -> Dict[str, Dict[str, float]]:
        """Get FY metrics from sec_companyfacts_processed table.

        This table has cleaned, validated FY data with market data.
        Includes fallback logic for missing market_cap or shares_outstanding.

        Args:
            symbols: List of stock symbols
            fiscal_year: Fiscal year to fetch

        Returns:
            Dict mapping symbol to FY metrics
        """
        with self.sec_db_manager.get_session() as sec_session:
            # Use sec_companyfacts_processed for FY metrics (already extracted)
            # All required fields are now available including shares_outstanding, market_cap, EPS
            query = text("""
                SELECT
                    p.symbol,
                    p.total_revenue,
                    p.net_income,
                    p.operating_income,
                    p.stockholders_equity,
                    p.shares_outstanding,
                    p.weighted_average_diluted_shares_outstanding,
                    p.market_cap,
                    p.period_end_date,
                    p.filed_date,
                    p.earnings_per_share,
                    p.earnings_per_share_diluted
                FROM sec_companyfacts_processed p
                WHERE UPPER(p.symbol) IN :symbols
                    AND p.fiscal_year = :fiscal_year
                    AND p.fiscal_period = 'FY'
            """)

            try:
                result = sec_session.execute(
                    query,
                    {
                        "symbols": tuple(s.upper() for s in list(symbols)),
                        "fiscal_year": fiscal_year,
                    },
                )
            except Exception as e:
                logger.warning(f"sec_companyfacts_processed query failed: {e}")
                return {}

            # Process results into metrics with fallback logic
            fy_metrics: Dict[str, Dict[str, float]] = {}

            for row in result:
                symbol = row[0]
                total_revenue = float(row[1]) if row[1] else None
                net_income = float(row[2]) if row[2] else None
                operating_income = float(row[3]) if row[3] else None
                equity = float(row[4]) if row[4] else None
                shares = float(row[5]) if row[5] else None
                shares_wa_diluted = float(row[6]) if row[6] else None  # Weighted average diluted
                market_cap = float(row[7]) if row[7] else None
                period_end = row[8]
                filed_date = row[9]
                eps = float(row[10]) if row[10] else None
                eps_diluted = float(row[11]) if row[11] else None

                if symbol not in fy_metrics:
                    fy_metrics[symbol] = {}

                # Map columns to metrics
                if total_revenue:
                    fy_metrics[symbol]["total_revenue"] = total_revenue
                if net_income:
                    fy_metrics[symbol]["net_income"] = net_income
                if operating_income:
                    fy_metrics[symbol]["operating_income"] = operating_income
                if equity:
                    fy_metrics[symbol]["stockholders_equity"] = equity

                # Shares outstanding fallback chain:
                # 1. Use weighted_average_diluted_shares_outstanding (most accurate for dilution)
                # 2. Use shares_outstanding (basic shares)
                if shares_wa_diluted and shares_wa_diluted > 0:
                    fy_metrics[symbol]["shares_outstanding"] = shares_wa_diluted
                elif shares and shares > 0:
                    fy_metrics[symbol]["shares_outstanding"] = shares

                # Market cap: Use stored value, will calculate fallback if needed
                if market_cap and market_cap > 0:
                    fy_metrics[symbol]["market_cap"] = market_cap

                # EPS for fallback
                if eps and eps > 0:
                    fy_metrics[symbol]["eps"] = eps
                elif eps_diluted and eps_diluted > 0:
                    fy_metrics[symbol]["eps"] = eps_diluted

                if period_end:
                    fy_metrics[symbol]["period_end_date"] = period_end

                if filed_date:
                    fy_metrics[symbol]["filed_date"] = filed_date

            # Apply robust fallback logic for missing market_cap and price
            # Fallback priority:
            # 1. Use stored market_cap if available and > 0
            # 2. Calculate from tickerdata (with split adjustment for SEC shares)
            # 3. Validate consistency
            for symbol, metrics in fy_metrics.items():
                # Skip if we already have both market_cap AND price
                # (Note: market_cap alone isn't enough - we need price for P/E and P/B)
                if metrics.get("market_cap") and metrics.get("market_cap", 0) > 0 and metrics.get("price"):
                    continue

                # Fallback 1: Try to get price from tickerdata around period_end + buffer
                # This uses tickerdata which has historical prices (split-adjusted)
                # We need price even if we have market_cap (for P/E and P/B calculations)
                if "filed_date" in metrics and not metrics.get("price"):
                    from datetime import date, datetime, timedelta

                    # Use period_end as base for price anchor (more stable than filed_date)
                    # Add 90-day buffer to next quarter when market has digested FY results
                    # This reduces vulnerability to splits between period_end and filing
                    period_end = metrics.get("period_end_date")
                    if period_end:
                        # Convert period_end to datetime regardless of input type
                        if isinstance(period_end, str):
                            period_end = datetime.fromisoformat(period_end)
                        elif isinstance(period_end, date):
                            period_end = datetime.combine(period_end, datetime.min.time())
                        # If already datetime, use as-is

                        # Use period_end + 90 days (next quarter) as price anchor
                        # This allows time for 10-K filing and market digestion
                        # Any splits between period_end and period_end+90 will be handled
                        # by the split adjustment logic in calculate_market_cap()
                        price_anchor_date = period_end + timedelta(days=90)
                    else:
                        # Fallback to filed_date if period_end not available
                        filed_date = metrics["filed_date"]
                        if isinstance(filed_date, str):
                            filed_date = datetime.fromisoformat(filed_date)
                        elif isinstance(filed_date, date):
                            filed_date = datetime.combine(filed_date, datetime.min.time())
                        price_anchor_date = filed_date + timedelta(days=30)
                    price_data = self._get_historical_price(sec_session, symbol, price_anchor_date)

                    # Check for splits between period_end and price_anchor_date
                    # This helps identify potentially unreliable data points
                    period_end_for_check = metrics.get("period_end_date")
                    if period_end_for_check:
                        if isinstance(period_end_for_check, str):
                            period_end_for_check = datetime.fromisoformat(period_end_for_check)
                        elif isinstance(period_end_for_check, date):
                            period_end_for_check = datetime.combine(period_end_for_check, datetime.min.time())

                        splits = self._detect_splits_between_dates(symbol, period_end_for_check, price_anchor_date)
                        if splits:
                            logger.info(
                                f"{symbol} FY{fiscal_year}: {len(splits)} split(s) detected "
                                f"between period_end and price_anchor_date"
                            )
                            for split in splits:
                                logger.info(f"  Split on {split['split_date']}: {split['split_ratio']}-for-1 ratio")
                            # Store split info for context (don't skip, just log)
                            metrics["splits_in_window"] = len(splits)

                    if price_data:
                        metrics["price"] = price_data
                        # Recalculate market_cap if missing or zero with split adjustment
                        shares = metrics.get("shares_outstanding")
                        period_end = metrics.get("period_end_date")
                        if (
                            (not metrics.get("market_cap") or metrics.get("market_cap", 0) == 0)
                            and shares
                            and shares > 0
                        ):
                            # Use split-adjusted market cap calculation
                            # Shares are from SEC (actual), price is split-adjusted
                            from investigator.domain.services.valuation_shared.split_adjusted_market_cap import (
                                calculate_market_cap,
                            )

                            # Convert period_end to date if needed
                            if isinstance(period_end, str):
                                from datetime import datetime

                                period_end = datetime.fromisoformat(period_end).date()
                            elif isinstance(period_end, datetime):
                                period_end = period_end.date()

                            mcap = calculate_market_cap(
                                symbol=symbol,
                                price=price_data,
                                shares=shares,
                                price_date=period_end,
                                shares_source="sec",  # SEC shares are actual
                            )
                            if mcap:
                                metrics["market_cap"] = mcap
                            else:
                                # Skip this symbol if split adjustment fails
                                # Better to have no data than wrong data that distorts sector medians
                                logger.warning(
                                    f"{symbol} FY{fiscal_year}: Split adjustment failed, "
                                    f"excluding from multiples calculation"
                                )
                                # Remove from metrics so it will be skipped in calculation
                                if symbol in fy_metrics:
                                    del fy_metrics[symbol]
                        continue

                # Fallback 2: If we have shares but no price, we can't calculate P/E or P/B
                # But we can still calculate P/S using stored market_cap (if we had it in the original row)
                # This case is handled in the calculation function itself

            # Validate market cap consistency for all symbols
            # This catches split adjustment issues
            validated_metrics = {}
            for symbol, metrics in fy_metrics.items():
                if self._validate_market_cap_consistency(symbol, metrics):
                    validated_metrics[symbol] = metrics
                else:
                    # Skip symbols with inconsistent market cap
                    logger.warning(
                        f"{symbol}: Excluding from FY{fiscal_year} multiples due to "
                        f"market cap inconsistency (likely split adjustment issue)"
                    )

            return validated_metrics

    def _get_historical_price(self, session: Session, symbol: str, target_date: datetime) -> Optional[float]:
        """Get historical price around target date from tickerdata table.

        Uses price closest to target date (within ±7 days).

        Args:
            session: Stock database session
            symbol: Stock symbol
            target_date: Target date for price

        Returns:
            Price or None
        """
        # Query for price closest to target date (within ±14 days)
        query = text("""
            SELECT date, close
            FROM tickerdata
            WHERE ticker = :symbol
                AND date BETWEEN :start_date AND :end_date
            ORDER BY ABS(date - CAST(:target_date AS date)) ASC
            LIMIT 1
        """)

        # Get date range (target ± 14 days for wider search)
        from datetime import timedelta

        start_date = target_date - timedelta(days=14)
        end_date = target_date + timedelta(days=14)

        result = session.execute(
            query,
            {
                "symbol": symbol.upper(),
                "start_date": start_date,
                "end_date": end_date,
                "target_date": target_date,
            },
        )

        row = result.fetchone()
        if row and row[1]:
            return float(row[1])

        return None

    def _detect_splits_between_dates(self, symbol: str, start_date, end_date) -> List[Dict[str, any]]:
        """Detect if any stock splits occurred between two dates.

        This is used to identify periods where split adjustment may be unreliable.
        If splits occurred between period_end and the price anchor date,
        the price from tickerdata may be on a different split basis than
        the shares from SEC data.

        Args:
            symbol: Stock symbol
            start_date: Start date (period_end_date)
            end_date: End date (price_anchor_date)

        Returns:
            List of split events with date and ratio
        """
        query = text("""
            SELECT split_date, split_ratio
            FROM stock_splits
            WHERE UPPER(symbol) = UPPER(:symbol)
              AND split_date BETWEEN :start_date AND :end_date
            ORDER BY split_date
        """)

        try:
            # Use sec_db_manager for stock_splits table (it's in sec_database)
            with self.sec_db_manager.get_session() as session:
                result = session.execute(
                    query,
                    {
                        "symbol": symbol,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                )
                splits = [{"split_date": str(row[0]), "split_ratio": float(row[1])} for row in result]
                return splits
        except Exception as e:
            logger.debug(f"Error detecting splits for {symbol}: {e}")
            return []

    def _validate_market_cap_consistency(self, symbol: str, metrics: Dict[str, any]) -> bool:
        """Validate that market_cap is consistent with price × shares.

        This catches split adjustment issues where:
        - Price is split-adjusted (tickerdata)
        - Shares are actual (SEC)
        - Market cap calculation didn't account for the mismatch

        Args:
            symbol: Stock symbol
            metrics: Dict with market_cap, price, shares_outstanding

        Returns:
            True if consistent (within 20% tolerance), False otherwise
        """
        market_cap = metrics.get("market_cap")
        price = metrics.get("price")
        shares = metrics.get("shares_outstanding")

        if not all([market_cap, price, shares]):
            return True  # Can't validate, assume OK

        if market_cap <= 0 or price <= 0 or shares <= 0:
            return True  # Invalid values, can't validate

        calculated_mc = price * shares
        diff_pct = abs(market_cap - calculated_mc) / market_cap

        if diff_pct > 0.20:  # More than 20% difference
            logger.warning(
                f"{symbol}: Market cap inconsistency detected - "
                f"Stored: ${market_cap:,.0f}, "
                f"Calculated (price × shares): ${calculated_mc:,.0f}, "
                f"Difference: {diff_pct * 100:.1f}% - "
                f"Possible split adjustment issue"
            )
            return False

        return True

    # Note: Sector name mapping is now centralized in SectorIndustryMapper
    # Use SectorIndustryMapper.to_standard() for normalization
    # and SectorIndustryMapper.to_database_variants() for expansion

    def _normalize_sector_names(self, sectors: List[str]) -> List[str]:
        """Expand sector names to include all database variants."""
        return SectorIndustryMapper.expand_sectors_for_query(sectors)

    def _standardize_sector_name(self, sector_name: str) -> str:
        """Convert database sector name to standard name."""
        return SectorIndustryMapper.to_standard(sector_name)

    def _get_symbols_by_sector_industry(
        self,
        *,
        sectors: Optional[List[str]],
        industries: Optional[List[str]],
        config_overrides: Dict[str, str],
    ) -> List[Tuple[str, str, Optional[str]]]:
        """Get symbols grouped by sector/industry from stock.symbol table."""
        with self.stock_db_manager.get_session() as session:
            filters = ["islisted = true"]
            params: Dict[str, Any] = {}

            if sectors:
                override_symbols = [s.upper() for s, sec in config_overrides.items() if sec in sectors]
                if override_symbols:
                    filters.append("ticker = ANY(:override_symbols)")
                    params["override_symbols"] = override_symbols

                # Expand sector names to include database variants
                sector_list = self._normalize_sector_names(sectors)
                filters.append("COALESCE(NULLIF(\"Sector\", ''), '') = ANY(:sectors) OR \"Sector\" = ANY(:sectors)")
                params["sectors"] = sector_list

            if industries:
                filters.append(
                    "COALESCE(NULLIF(\"Industry\", ''), '') = ANY(:industries) OR \"Industry\" = ANY(:industries)"
                )
                params["industries"] = [i.title() for i in industries]

            where_clause = " AND ".join(filters)

            query = text(f"""
                SELECT ticker, "Sector", "Industry"
                FROM symbol
                WHERE {where_clause}
                ORDER BY ticker
            """)

            result = session.execute(query, params)
            return [(row[0], row[1], row[2]) for row in result]

    def _filtered_median(self, values: List[float], name: str) -> Optional[float]:
        """Calculate median after excluding outliers by percentile."""
        if not values:
            return None

        if len(values) < 3:
            return float(sum(values) / len(values)) if values else None

        sorted_values = sorted(values)
        low_idx = int(len(sorted_values) * self.percentile_exclude[0])
        high_idx = int(len(sorted_values) * self.percentile_exclude[1])
        filtered = sorted_values[low_idx:high_idx]

        if not filtered:
            logger.warning(f"{name}: No values after outlier filtering")
            return None

        return float(sum(filtered) / len(filtered))

    def _load_config_overrides(self) -> Dict[str, str]:
        """Load sector overrides from config.yaml."""
        from pathlib import Path

        # From: src/investigator/domain/services/sector_multiples_history.py
        # To: repo_root/config.yaml
        # Go up: services(1) -> domain(2) -> investigator(3) -> src(4) -> repo_root(5)
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config.yaml"

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return {}

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        overrides = {}

        dcf_valuation = config.get("dcf_valuation", {})
        if dcf_valuation:
            sector_override = dcf_valuation.get("sector_override", {})
            overrides.update({k.upper(): v for k, v in sector_override.items()})

        company_metadata = config.get("company_metadata", {})
        if company_metadata:
            sector_overrides = company_metadata.get("sector_override", {})
            overrides.update(sector_overrides)

        logger.debug(f"Loaded {len(overrides)} sector overrides from config")
        return overrides

    def store_history(
        self,
        calculated_multiples: Dict[str, Dict[str, Any]],
        group_type: str = "sector",
    ) -> bool:
        """Store calculated historical multiples to database.

        Args:
            calculated_multiples: Dict from calculate_historical_multiples()
                             For industry-level, should include 'sector' key in each multiples dict
            group_type: 'sector' or 'industry'

        Returns:
            True if successful, False otherwise
        """
        try:
            from investigator.infrastructure.database.migrations.versions.create_sector_multiples_history import (
                SectorMultiplesHistory,
            )

            with self.sec_db_manager.get_session() as session:
                for name, multiples in calculated_multiples.items():
                    # Determine hierarchical values
                    if group_type == "sector":
                        sector_name = name
                        industry_name = None
                    else:  # industry
                        sector_name = multiples.get("sector")  # Should be set by calculate_historical_multiples
                        industry_name = name

                    # Check if record exists (use new unique constraint)
                    existing = (
                        session.query(SectorMultiplesHistory)
                        .filter_by(
                            sector_name=sector_name,
                            industry_name=industry_name,
                            fiscal_year=multiples["fiscal_year"],
                        )
                        .first()
                    )

                    if existing:
                        # Update existing record
                        existing.pe_multiple = multiples.get("pe")
                        existing.ps_multiple = multiples.get("ps")
                        existing.pb_multiple = multiples.get("pb")
                        existing.ev_ebitda_multiple = multiples.get("ev_ebitda")
                        existing.sample_size = multiples["sample_size"]
                        existing.snapshot_date = datetime.fromisoformat(multiples["snapshot_date"])
                        existing.percentile_low = multiples.get("percentile_low", 0.05)
                        existing.percentile_high = multiples.get("percentile_high", 0.95)
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new record with hierarchical columns
                        record = SectorMultiplesHistory(
                            sector_name=sector_name,
                            industry_name=industry_name,
                            # Legacy columns (for backward compatibility)
                            group_name=name,
                            group_type=group_type,
                            fiscal_year=multiples["fiscal_year"],
                            snapshot_date=datetime.fromisoformat(multiples["snapshot_date"]),
                            pe_multiple=multiples.get("pe"),
                            ps_multiple=multiples.get("ps"),
                            pb_multiple=multiples.get("pb"),
                            ev_ebitda_multiple=multiples.get("ev_ebitda"),
                            sample_size=multiples["sample_size"],
                            percentile_low=multiples.get("percentile_low", 0.05),
                            percentile_high=multiples.get("percentile_high", 0.95),
                        )
                        session.add(record)

                session.commit()
                logger.info(f"Stored {len(calculated_multiples)} historical records (group_type={group_type})")
                return True

        except Exception as e:
            logger.error(f"Failed to store history: {e}")
            return False

    def get_trend_data(
        self,
        group_name: str,
        group_type: str = "sector",
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical trend data for a sector/industry.

        Args:
            group_name: Sector or industry name
            group_type: 'sector' or 'industry'
            start_year: Start fiscal year (inclusive)
            end_year: End fiscal year (inclusive)

        Returns:
            List of historical multiples sorted by fiscal year
        """
        from investigator.infrastructure.database.migrations.versions.create_sector_multiples_history import (
            SectorMultiplesHistory,
        )

        with self.sec_db_manager.get_session() as session:
            query = session.query(SectorMultiplesHistory).filter_by(group_name=group_name, group_type=group_type)

            if start_year:
                query = query.filter(SectorMultiplesHistory.fiscal_year >= start_year)
            if end_year:
                query = query.filter(SectorMultiplesHistory.fiscal_year <= end_year)

            results = query.order_by(SectorMultiplesHistory.fiscal_year).all()

            return [
                {
                    "fiscal_year": r.fiscal_year,
                    "snapshot_date": r.snapshot_date.isoformat(),
                    "pe": r.pe_multiple,
                    "ps": r.ps_multiple,
                    "pb": r.pb_multiple,
                    "sample_size": r.sample_size,
                }
                for r in results
            ]

    def export_to_file(
        self,
        output_path: str,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        format: str = "json",
    ) -> bool:
        """Export historical multiples to file for analysis.

        Args:
            output_path: Output file path
            start_year: Start fiscal year
            end_year: End fiscal year
            format: 'json' or 'csv'

        Returns:
            True if successful, False otherwise
        """
        try:
            from investigator.infrastructure.database.migrations.versions.create_sector_multiples_history import (
                SectorMultiplesHistory,
            )

            with self.sec_db_manager.get_session() as session:
                query = session.query(SectorMultiplesHistory)

                if start_year:
                    query = query.filter(SectorMultiplesHistory.fiscal_year >= start_year)
                if end_year:
                    query = query.filter(SectorMultiplesHistory.fiscal_year <= end_year)

                results = query.all()

            if format == "json":
                import json

                data = [
                    {
                        "group_name": r.group_name,
                        "group_type": r.group_type,
                        "fiscal_year": r.fiscal_year,
                        "snapshot_date": r.snapshot_date.isoformat(),
                        "pe": r.pe_multiple,
                        "ps": r.ps_multiple,
                        "pb": r.pb_multiple,
                        "sample_size": r.sample_size,
                    }
                    for r in results
                ]

                with open(output_path, "w") as f:
                    json.dump(data, f, indent=2)

            elif format == "csv":
                import csv

                with open(output_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "Group",
                            "Type",
                            "FY",
                            "Snapshot",
                            "P/E",
                            "P/S",
                            "P/B",
                            "Sample",
                        ]
                    )

                    for r in results:
                        writer.writerow(
                            [
                                r.group_name,
                                r.group_type,
                                r.fiscal_year,
                                r.snapshot_date.isoformat(),
                                r.pe_multiple or "",
                                r.ps_multiple or "",
                                r.pb_multiple or "",
                                r.sample_size,
                            ]
                        )

            logger.info(f"Exported {len(results)} records to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export: {e}")
            return False

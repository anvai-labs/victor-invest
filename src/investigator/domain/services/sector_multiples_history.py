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
from investigator.infrastructure.database.db import get_db_manager

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
        "total_revenue": [
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
        ],
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
        self.sec_db_manager = sec_db_manager or get_db_manager()
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

        # Group by sector first
        sector_groups: Dict[str, List[str]] = {}
        industry_groups: Dict[str, List[str]] = {}

        for symbol, sector, industry in symbol_classification:
            if sector not in sector_groups:
                sector_groups[sector] = []
            sector_groups[sector].append(symbol)

            if industry:
                if industry not in industry_groups:
                    industry_groups[industry] = []
                industry_groups[industry].append(symbol)

        # Calculate sector-level multiples
        for sector, symbols in sector_groups.items():
            logger.info(f"Calculating for sector: {sector} ({len(symbols)} symbols)")
            multiples = self._calculate_historical_multiples_for_symbols(
                symbols, f"sector:{sector}", fiscal_year
            )
            if multiples:
                results[sector] = multiples

        # Calculate industry-level multiples
        for industry, symbols in industry_groups.items():
            logger.info(
                f"Calculating for industry: {industry} ({len(symbols)} symbols)"
            )
            multiples = self._calculate_historical_multiples_for_symbols(
                symbols, f"industry:{industry}", fiscal_year
            )
            if multiples:
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

        for symbol, metrics in fy_metrics.items():
            # Skip if no market cap or price
            mc = metrics.get("market_cap")
            price = metrics.get("price")
            if not mc or not price:
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

            # P/S = Market Cap / Revenue
            rev = metrics.get("total_revenue")
            if rev and rev > 0:
                ps = mc / rev
                if ps > 0 and ps < 100:  # Sanity check
                    ps_multiples.append(ps)

            # P/B = Price / Book Value per Share
            # Book Value per Share = Shareholders Equity / Shares
            equity = metrics.get("stockholders_equity")
            if equity and shares and shares > 0:
                bvps = equity / shares
                if bvps > 0:
                    pb = price / bvps
                    if pb > 0 and pb < 50:  # Sanity check
                        pb_multiples.append(pb)

        # Apply percentile filtering
        pe_median = self._filtered_median(pe_multiples, f"{group_name}_PE")
        ps_median = self._filtered_median(ps_multiples, f"{group_name}_PS")
        pb_median = self._filtered_median(pb_multiples, f"{group_name}_PB")

        if pe_median is None:
            logger.warning(
                f"{group_name} FY{fiscal_year}: No valid multiples calculated"
            )
            return None

        # Calculate snapshot date (FY end + 1 month)
        snapshot_date = datetime(fiscal_year, 12, 31) + timedelta(days=31)

        return {
            "pe": round(pe_median, 2),
            "ps": round(ps_median, 2) if ps_median else None,
            "pb": round(pb_median, 2) if pb_median else None,
            "fiscal_year": fiscal_year,
            "snapshot_date": snapshot_date.isoformat(),
            "sample_size": len(fy_metrics),
            "percentile_low": self.percentile_exclude[0],
            "percentile_high": self.percentile_exclude[1],
        }

    def _get_fy_metrics(
        self, symbols: List[str], fiscal_year: int
    ) -> Dict[str, Dict[str, float]]:
        """Get FY metrics from SEC num/tag data for a fiscal year.

        Queries sec_num_data for tag values and joins with stock.symbol for prices.

        Args:
            symbols: List of stock symbols
            fiscal_year: Fiscal year to fetch

        Returns:
            Dict mapping symbol to FY metrics
        """
        with self.sec_db_manager.get_session() as sec_session:
            with self.stock_db_manager.get_session() as stock_session:
                # Get CIKs for symbols
                symbol_cik_map = self._get_symbol_cik_map(stock_session, symbols)

                if not symbol_cik_map:
                    logger.warning("No symbols found in stock.symbol table")
                    return {}

                # Query SEC tag data for FY values
                # Using sec_num_data table with fy filter
                query = text("""
                    SELECT
                        s.adsh,
                        s.tag,
                        s.ddate AS filing_date,
                        s.value,
                        s.uom,
                        c.ticker AS symbol
                    FROM sec_num_data s
                    JOIN submissions sub ON s.adsh = sub.adsh
                    JOIN company_facts c ON sub.cik = c.cik
                    WHERE sub.cik = ANY(:ciks)
                        AND sub.fy = :fiscal_year
                        AND s.tag IN (
                            'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                            'us-gaap:NetIncomeLoss',
                            'us-gaap:OperatingIncomeLoss',
                            'us-gaap:StockholdersEquity',
                            'us-gaap:CommonStockSharesOutstanding'
                        )
                        AND s.qtrs = 4  -- FY data (4 quarters)
                """)

                try:
                    result = sec_session.execute(
                        query,
                        {
                            "ciks": list(symbol_cik_map.values()),
                            "fiscal_year": fiscal_year,
                        },
                    )
                except Exception as e:
                    logger.warning(f"SEC num_data query failed: {e}")
                    # Fallback: try simpler query
                    return {}

                # Process results into metrics
                fy_metrics: Dict[str, Dict[str, float]] = {}

                for row in result:
                    symbol = row[5]
                    tag = row[1]
                    value = float(row[3]) if row[3] else None

                    if symbol not in fy_metrics:
                        fy_metrics[symbol] = {}

                    # Map tags to metrics
                    if "Revenue" in tag:
                        fy_metrics[symbol]["total_revenue"] = value
                    elif "NetIncomeLoss" in tag or "ProfitLoss" in tag:
                        fy_metrics[symbol]["net_income"] = value
                    elif "OperatingIncomeLoss" in tag:
                        fy_metrics[symbol]["operating_income"] = value
                    elif "StockholdersEquity" in tag:
                        fy_metrics[symbol]["stockholders_equity"] = value
                    elif "SharesOutstanding" in tag:
                        fy_metrics[symbol]["shares_outstanding"] = value

                # Add market data from stock database
                # Use end of FY + 1 month as proxy price
                snapshot_date = datetime(fiscal_year, 12, 31) + timedelta(days=31)
                for symbol in fy_metrics.keys():
                    price_data = self._get_historical_price(
                        stock_session, symbol, snapshot_date
                    )
                    if price_data:
                        fy_metrics[symbol]["price"] = price_data["price"]
                        fy_metrics[symbol]["market_cap"] = price_data["market_cap"]

                return fy_metrics

    def _get_symbol_cik_map(
        self, session: Session, symbols: List[str]
    ) -> Dict[str, int]:
        """Get CIK mapping for symbols from stock.symbol."""
        query = text("""
            SELECT ticker, cik
            FROM symbol
            WHERE UPPER(ticker) = ANY(:symbols)
                AND islisted = true
        """)

        result = session.execute(query, {"symbols": [s.upper() for s in symbols]})
        return {row[0]: int(row[1]) for row in result}

    def _get_historical_price(
        self, session: Session, symbol: str, target_date: datetime
    ) -> Optional[Dict[str, float]]:
        """Get historical price around target date (end of FY + 1 month proxy).

        Uses end of month price closest to target date.

        Args:
            session: Stock database session
            symbol: Stock symbol
            target_date: Target date for price

        Returns:
            Dict with price and market_cap or None
        """
        # Query for price closest to target date (within same month)
        query = text("""
            SELECT date, close, volume, market_cap
            FROM stock_data
            WHERE ticker = :symbol
                AND date <= :end_date
                AND date >= :start_date
            ORDER BY date DESC
            LIMIT 1
        """)

        # Get date range for the month
        start_date = target_date.replace(day=1)
        end_date = start_date.replace(
            month=start_date.month % 12 + 1, day=1
        ) - timedelta(days=1)

        result = session.execute(
            query,
            {"symbol": symbol.upper(), "start_date": start_date, "end_date": end_date},
        )

        row = result.fetchone()
        if row:
            return {
                "price": float(row[1]) if row[1] else None,
                "market_cap": float(row[3]) if row[3] else None,
            }

        return None

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
                override_symbols = [
                    s.upper() for s, sec in config_overrides.items() if sec in sectors
                ]
                if override_symbols:
                    filters.append("ticker = ANY(:override_symbols)")
                    params["override_symbols"] = override_symbols

                sector_list = [s.title() for s in sectors]
                filters.append(
                    "COALESCE(NULLIF(\"Sector\", ''), '') = ANY(:sectors) OR \"Sector\" = ANY(:sectors)"
                )
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

        config_path = (
            Path(__file__).parent.parent.parent.parent.parent.parent / "config.yaml"
        )

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
                    # Check if record exists
                    existing = (
                        session.query(SectorMultiplesHistory)
                        .filter_by(
                            group_name=name,
                            group_type=group_type,
                            fiscal_year=multiples["fiscal_year"],
                        )
                        .first()
                    )

                    if existing:
                        # Update existing record
                        existing.pe_multiple = multiples.get("pe")
                        existing.ps_multiple = multiples.get("ps")
                        existing.pb_multiple = multiples.get("pb")
                        existing.sample_size = multiples["sample_size"]
                        existing.snapshot_date = datetime.fromisoformat(
                            multiples["snapshot_date"]
                        )
                        existing.percentile_low = multiples.get("percentile_low", 0.05)
                        existing.percentile_high = multiples.get(
                            "percentile_high", 0.95
                        )
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new record
                        record = SectorMultiplesHistory(
                            group_name=name,
                            group_type=group_type,
                            fiscal_year=multiples["fiscal_year"],
                            snapshot_date=datetime.fromisoformat(
                                multiples["snapshot_date"]
                            ),
                            pe_multiple=multiples.get("pe"),
                            ps_multiple=multiples.get("ps"),
                            pb_multiple=multiples.get("pb"),
                            sample_size=multiples["sample_size"],
                            percentile_low=multiples.get("percentile_low", 0.05),
                            percentile_high=multiples.get("percentile_high", 0.95),
                        )
                        session.add(record)

                session.commit()
                logger.info(f"Stored {len(calculated_multiples)} historical records")
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
            query = session.query(SectorMultiplesHistory).filter_by(
                group_name=group_name, group_type=group_type
            )

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
                    query = query.filter(
                        SectorMultiplesHistory.fiscal_year >= start_year
                    )
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

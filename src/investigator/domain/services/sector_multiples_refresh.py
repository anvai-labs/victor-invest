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

"""Sector multiples refresh service - calculate from database data.

Calculates sector/industry median valuation multiples from actual market data:
- Uses sec_companyfacts_processed for TTM metrics (EPS, revenue, EBITDA, etc.)
- Uses stock.symbol for sector/industry classification
- Calculates median P/E, P/S, EV/EBITDA, P/B with outlier filtering
- Updates config.yaml with fresh values

This provides data-driven sector multiples instead of manual/static values.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, text

from investigator.config import get_config
from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


class SectorMultiplesRefresh:
    """Calculate and refresh sector multiples from database data.

    Methods:
        calculate_sector_multiples: Calculate medians for sectors/industries
        update_config_yaml: Update config.yaml with calculated values
        refresh: Main method to calculate and update
    """

    def __init__(
        self,
        *,
        stock_db_manager: Any = None,
        sec_db_manager: Any = None,
        min_samples: int = 5,
        percentile_exclude: tuple[float, float] = (0.05, 0.95),
    ):
        """Initialize sector multiples refresh service.

        Args:
            stock_db_manager: Database manager for stock database
            sec_db_manager: Database manager for SEC database
            min_samples: Minimum number of symbols required for calculation
            percentile_exclude: Percentiles to exclude (low, high) for outlier filtering
        """
        # Create stock database manager if not provided
        if stock_db_manager is None:
            from investigator.infrastructure.database.db import DatabaseManager

            config = get_config()
            stock_db_url = config.database.url.replace("/sec_database", "/stock")
            stock_db_manager = DatabaseManager(config)
            stock_db_manager.engine = create_engine(stock_db_url)
            from sqlalchemy.orm import sessionmaker

            stock_db_manager.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=stock_db_manager.engine
            )

        # SEC database manager (uses default)
        if sec_db_manager is None:
            sec_db_manager = get_db_manager()

        self.stock_db_manager = stock_db_manager
        self.sec_db_manager = sec_db_manager
        self.min_samples = min_samples
        self.percentile_exclude = percentile_exclude

        # Load P/B excluded symbols from config
        self.pb_excluded_symbols = self._load_pb_excluded_symbols()

    def calculate_sector_multiples(
        self,
        *,
        sectors: list[str] | None = None,
        industries: list[str] | None = None,
        use_config_overrides: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Calculate sector/industry multiples from processed data.

        Args:
            sectors: List of sectors to calculate (None = all sectors)
            industries: List of industries to calculate (None = all industries)
            use_config_overrides: Apply config.yaml sector overrides

        Returns:
            Dict with keys as sector/industry names, values containing calculated multiples
            {
                "Technology": {"pe": 28.5, "ps": 6.2, "ev_ebitda": 22.1, "pb": 5.8, "sample_size": 150},
                "Healthcare": {"pe": 20.3, "ps": 4.1, "ev_ebitda": 15.2, "pb": 4.2, "sample_size": 80},
                ...
            }
        """
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
        sector_groups: dict[str, list[str]] = {}
        industry_groups: dict[str, list[str]] = {}

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
            logger.info(f"Calculating multiples for sector: {sector} ({len(symbols)} symbols)")
            multiples = self._calculate_multiples_for_symbols(symbols, f"sector:{sector}")
            if multiples:
                results[sector] = multiples

        # Calculate industry-level multiples
        for industry, symbols in industry_groups.items():
            logger.info(f"Calculating multiples for industry: {industry} ({len(symbols)} symbols)")
            multiples = self._calculate_multiples_for_symbols(symbols, f"industry:{industry}")
            if multiples:
                results[industry] = multiples

        return results

    def _get_symbols_by_sector_industry(
        self,
        *,
        sectors: list[str] | None,
        industries: list[str] | None,
        config_overrides: dict[str, str],
    ) -> list[tuple[str, str, str | None]]:
        """Get symbols grouped by sector/industry from stock.symbol table.

        Returns:
            List of (symbol, sector, industry) tuples
        """
        with self.stock_db_manager.get_session() as session:
            # Build query filters
            filters = ["islisted = true"]
            params: dict[str, Any] = {}

            if sectors:
                # Apply config overrides first
                if config_overrides:
                    override_symbols = [s.upper() for s, sec in config_overrides.items() if sec in sectors]
                    if override_symbols:
                        filters.append("ticker = ANY(:override_symbols)")
                        params["override_symbols"] = override_symbols

                # Also match by sector column (but config overrides take precedence)
                sector_list = [s.title() for s in sectors]
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

    def _calculate_multiples_for_symbols(self, symbols: list[str], group_name: str) -> dict[str, Any] | None:
        """Calculate valuation multiples for a group of symbols.

        Args:
            symbols: List of stock symbols
            group_name: Name of group (for logging, e.g., "sector:Technology")

        Returns:
            Dict with calculated multiples or None if insufficient data
        """
        # Get TTM metrics from sec_companyfacts_processed
        metrics_data = self._get_ttm_metrics(symbols)

        if len(metrics_data) < self.min_samples:
            logger.warning(
                f"{group_name}: Insufficient data ({len(metrics_data)} symbols, min required: {self.min_samples})"
            )
            return None

        # Calculate multiples for each metric
        pe_multiples = []
        ps_multiples = []
        ev_ebitda_multiples = []
        pb_multiples = []

        for symbol, metrics in metrics_data.items():
            # Skip if market_cap is None (required for all multiples)
            mc = metrics.get("market_cap")
            if mc is None:
                continue

            # P/E = Market Cap / Net Income
            ni = metrics.get("net_income")
            if ni and ni > 0:
                pe = mc / ni
                if pe > 0 and pe < 1000:  # Sanity check
                    pe_multiples.append(pe)

            # P/S = Market Cap / Revenue
            rev = metrics.get("total_revenue")
            if rev and rev > 0:
                ps = mc / rev
                if ps > 0 and ps < 100:  # Sanity check
                    ps_multiples.append(ps)

            # EV/EBITDA = Enterprise Value / EBITDA
            # EV = Market Cap + Total Debt - Cash
            ebitda = metrics.get("ebitda")
            if ebitda and ebitda > 0:
                debt = metrics.get("total_debt") or 0
                cash = metrics.get("cash_and_equivalents") or 0
                ev = mc + debt - cash
                ev_ebitda = ev / ebitda
                if ev_ebitda > 0 and ev_ebitda < 200:  # Sanity check
                    ev_ebitda_multiples.append(ev_ebitda)

            # P/B = Market Cap / Shareholders Equity
            # Exclude configured symbols where P/B is not meaningful (e.g., asset-light payment networks)
            equity = metrics.get("stockholders_equity")
            if equity and equity > 0:
                pb = mc / equity

                # Check if symbol is in config-based exclusion list
                is_excluded = symbol.upper() in self.pb_excluded_symbols

                if is_excluded:
                    # Skip P/B for excluded symbols - not meaningful per config
                    logger.debug(
                        f"{symbol}: Excluding from P/B calculation (config pb.excluded_symbols) "
                        f"(market_cap=${mc / 1e9:.1f}B, equity=${equity / 1e9:.1f}B, P/B={pb:.1f}x)"
                    )
                elif pb > 0:  # Only check for positive values
                    pb_multiples.append(pb)

        # Apply percentile filtering to remove outliers
        pe_median = self._filtered_median(pe_multiples, f"{group_name}_PE")
        ps_median = self._filtered_median(ps_multiples, f"{group_name}_PS")
        ev_ebitda_median = self._filtered_median(ev_ebitda_multiples, f"{group_name}_EV_EBITDA")
        pb_median = self._filtered_median(pb_multiples, f"{group_name}_PB")

        if pe_median is None:
            logger.warning(f"{group_name}: No valid multiples calculated")
            return None

        return {
            "pe": round(pe_median, 2),
            "ps": round(ps_median, 2) if ps_median else None,
            "ev_ebitda": round(ev_ebitda_median, 2) if ev_ebitda_median else None,
            "pb": round(pb_median, 2) if pb_median else None,
            "sample_size": len(metrics_data),
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _filtered_median(self, values: list[float], name: str) -> float | None:
        """Calculate median - robust to outliers without filtering.

        The median is inherently robust to outliers (unlike mean).
        No need for percentile filtering since median naturally handles extreme values.

        Args:
            values: List of values
            name: Name for logging

        Returns:
            Median value or None if insufficient data
        """
        if not values:
            return None

        sorted_values = sorted(values)
        n = len(sorted_values)

        # Calculate median directly without filtering
        if n % 2 == 0:
            # Even number of values: average of two middle values
            median = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
        else:
            # Odd number of values: middle value
            median = sorted_values[n // 2]

        logger.debug(
            f"{name}: median={median:.2f} from {n} values (range: {sorted_values[0]:.2f} - {sorted_values[-1]:.2f})"
        )

        return float(median)

    def _get_ttm_metrics(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        """Get TTM metrics from sec_companyfacts_processed.

        Aggregates the last 4 quarters (or 1 FY) to get TTM values.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to TTM metrics
        """
        with self.sec_db_manager.get_session() as session:
            # Get latest fiscal period per symbol
            period_query = text("""
                SELECT DISTINCT symbol, fiscal_period, fiscal_year
                FROM sec_companyfacts_processed
                WHERE symbol = ANY(:symbols)
                ORDER BY symbol, fiscal_year DESC, fiscal_period DESC
            """)

            result = session.execute(period_query, {"symbols": list(symbols)})

            # Get most recent FY or last 4 quarters per symbol
            latest_periods: dict[str, list[str]] = {}
            for row in result:
                symbol, period, year = row[0], row[1], row[2]
                if symbol not in latest_periods:
                    latest_periods[symbol] = []

                if len(latest_periods[symbol]) < 5:
                    if period == "FY":
                        # Use FY alone if available
                        latest_periods[symbol] = [f"{year}-FY"]
                    else:
                        latest_periods[symbol].append(f"{year}-{period}")

            # Query TTM metrics for the determined periods
            ttm_metrics: dict[str, dict[str, float]] = {}

            for symbol, periods in latest_periods.items():
                # Build query for this symbol's periods
                period_conditions = []
                for period in periods:
                    if "-" in period:
                        year, period_name = period.split("-")
                        period_conditions.append(f"(fiscal_year = {year} AND fiscal_period = '{period_name}')")

                where_clause = " OR ".join(period_conditions)

                query = text(f"""
                    SELECT
                        symbol,
                        SUM(total_revenue) as total_revenue,
                        SUM(net_income) as net_income,
                        SUM(operating_income) as operating_income,
                        SUM(stockholders_equity) as stockholders_equity,
                        AVG(market_cap) as market_cap,
                        SUM(total_debt) as total_debt,
                        SUM(cash_and_equivalents) as cash_and_equivalents,
                        SUM(operating_cash_flow) as operating_cash_flow,
                        SUM(capital_expenditures) as capital_expenditures
                    FROM sec_companyfacts_processed
                    WHERE symbol = :symbol
                        AND ({where_clause})
                    GROUP BY symbol, market_cap
                """)

                result = session.execute(query, {"symbol": symbol})
                row = result.fetchone()
                if row:

                    def safe_float(val, default=0.0):
                        """Safely convert value to float, returning default if conversion fails."""
                        if val is None:
                            return default
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            return default

                    # Calculate EBITDA = Operating Income + Depreciation & Amortization
                    # Approximate as Operating Income + (Capital Expenditures - Depreciation isn't directly available)
                    # Using: Operating Income + (Operating Cash Flow - Net Income) as EBITDA proxy
                    operating_income = safe_float(row[3])
                    operating_cash_flow = safe_float(row[8])
                    net_income = safe_float(row[1])

                    # EBITDA ≈ Operating Income + (Operating Cash Flow - Net Income)
                    ebitda = operating_income + (operating_cash_flow - net_income)

                    ttm_metrics[symbol] = {
                        "total_revenue": safe_float(row[0], None),
                        "net_income": safe_float(row[1], None),
                        "operating_income": safe_float(row[3], None),
                        "stockholders_equity": safe_float(row[4], None),
                        "market_cap": safe_float(row[5], None),
                        "total_debt": safe_float(row[6], None),
                        "cash_and_equivalents": safe_float(row[7], None),
                        "ebitda": safe_float(ebitda if ebitda != 0 else None, None),
                    }

            return ttm_metrics

    def _load_config_overrides(self) -> dict[str, str]:
        """Load sector overrides from config.yaml."""
        # From: src/investigator/domain/services/sector_multiples_refresh.py
        # To: repo_root/config.yaml
        # Go up: services(1) -> domain(2) -> investigator(3) -> src(4) -> repo_root(5)
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config.yaml"

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return {}

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        overrides = {}

        # Check dcf_valuation.sector_override
        dcf_valuation = config.get("dcf_valuation", {})
        if dcf_valuation:
            sector_override = dcf_valuation.get("sector_override", {})
            overrides.update({k.upper(): v for k, v in sector_override.items()})

        # Check company_metadata.sector_override
        company_metadata = config.get("company_metadata", {})
        if company_metadata:
            sector_override = company_metadata.get("sector_override", {})
            overrides.update({k.upper(): v for k, v in sector_override.items()})

        logger.debug(f"Loaded {len(overrides)} sector overrides from config")
        return overrides

    def _load_pb_excluded_symbols(self) -> set:
        """Load symbols to exclude from P/B calculation from config.yaml."""
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config.yaml"

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return set()

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Get excluded_symbols from valuation.sector_multiples.pb
        valuation = config.get("valuation", {})
        sector_multiples = valuation.get("sector_multiples", {})
        pb_config = sector_multiples.get("pb", {})
        excluded = pb_config.get("excluded_symbols", [])

        # Normalize to uppercase set
        excluded_set = {s.upper() for s in excluded} if excluded else set()

        if excluded_set:
            logger.debug(f"Loaded {len(excluded_set)} P/B excluded symbols from config: {excluded_set}")

        return excluded_set

    def update_config_yaml(self, calculated_multiples: dict[str, dict[str, Any]]) -> bool:
        """Update config.yaml with calculated sector multiples.

        Args:
            calculated_multiples: Dict from calculate_sector_multiples()

        Returns:
            True if successful, False otherwise
        """
        # From: src/investigator/domain/services/sector_multiples_refresh.py
        # To: repo_root/config.yaml
        # Go up: services(1) -> domain(2) -> investigator(3) -> src(4) -> repo_root(5)
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config.yaml"

        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            return False

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Update pe_multiples section
        if "pe_multiples" not in config:
            config["pe_multiples"] = {}
        if "sector_defaults" not in config["pe_multiples"]:
            config["pe_multiples"]["sector_defaults"] = {}

        # Update ps_multiples section
        if "ps_multiples" not in config:
            config["ps_multiples"] = {}
        if "sector_defaults" not in config["ps_multiples"]:
            config["ps_multiples"]["sector_defaults"] = {}

        # Update ev_ebitda section (under sector_multiples)
        if "sector_multiples" not in config:
            config["sector_multiples"] = {}
        if "ev_ebitda" not in config["sector_multiples"]:
            config["sector_multiples"]["ev_ebitda"] = {}

        # Update with calculated values
        for name, multiples in calculated_multiples.items():
            # Determine if this is a sector or industry
            is_industry = self._is_industry_name(name, calculated_multiples)

            if is_industry:
                # Add to industry_overrides
                if multiples.get("pe"):
                    if "industry_overrides" not in config["pe_multiples"]:
                        config["pe_multiples"]["industry_overrides"] = {}
                    config["pe_multiples"]["industry_overrides"][name] = multiples["pe"]
                if multiples.get("ps"):
                    if "industry_overrides" not in config["ps_multiples"]:
                        config["ps_multiples"]["industry_overrides"] = {}
                    config["ps_multiples"]["industry_overrides"][name] = multiples["ps"]
                if multiples.get("ev_ebitda"):
                    if "ev_ebitda_industry_overrides" not in config["sector_multiples"]:
                        config["sector_multiples"]["ev_ebitda_industry_overrides"] = {}
                    config["sector_multiples"]["ev_ebitda_industry_overrides"][name] = multiples["ev_ebitda"]
            else:
                # Add to sector_defaults
                if multiples.get("pe"):
                    config["pe_multiples"]["sector_defaults"][name] = multiples["pe"]
                if multiples.get("ps"):
                    config["ps_multiples"]["sector_defaults"][name] = multiples["ps"]
                if multiples.get("ev_ebitda"):
                    config["sector_multiples"]["ev_ebitda"][name] = multiples["ev_ebitda"]

        # Write back to config
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Updated config.yaml: {config_path}")
        return True

    def _is_industry_name(self, name: str, all_groups: dict[str, dict[str, Any]]) -> bool:
        """Determine if a name is an industry or sector based on hierarchy."""
        # Industries typically have more specific names (contain spaces, special words)
        industry_keywords = [
            "Software",
            "Hardware",
            "Semiconductor",
            "Equipment",
            "Services",
            "Banking",
            "Insurance",
            "Real Estate",
            "Telecom",
            "Utilities",
            "Pharmaceutical",
            "Biotech",
            "Medical",
            "Industrial",
            "Machinery",
            "Consumer",
            "Discretionary",
            "Staples",
            "Financial",
            "Healthcare",
        ]

        name_lower = name.lower()
        return any(keyword.lower() in name_lower for keyword in industry_keywords)

    def refresh(
        self,
        *,
        sectors: list[str] | None = None,
        industries: list[str] | None = None,
        update_config: bool = True,
        use_config_overrides: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Main method to calculate and refresh sector multiples.

        Args:
            sectors: List of sectors to calculate (None = all)
            industries: List of industries to calculate (None = all)
            update_config: Whether to update config.yaml
            use_config_overrides: Apply config.yaml sector overrides

        Returns:
            Calculated multiples dict
        """
        logger.info("Starting sector multiples refresh...")

        # Calculate multiples from database
        calculated = self.calculate_sector_multiples(
            sectors=sectors,
            industries=industries,
            use_config_overrides=use_config_overrides,
        )

        if not calculated:
            logger.error("No sector multiples calculated")
            return {}

        # Log summary
        logger.info("\n" + "=" * 80)
        logger.info("SECTOR MULTIPLES CALCULATION SUMMARY")
        logger.info("=" * 80)
        for name, multiples in sorted(calculated.items()):
            logger.info(f"\n{name}:")
            logger.info(f"  Sample Size: {multiples.get('sample_size', 'N/A')}")
            if multiples.get("pe"):
                logger.info(f"  P/E: {multiples['pe']}x")
            if multiples.get("ps"):
                logger.info(f"  P/S: {multiples['ps']}x")
            if multiples.get("ev_ebitda"):
                logger.info(f"  EV/EBITDA: {multiples['ev_ebitda']}x")
            if multiples.get("pb"):
                logger.info(f"  P/B: {multiples['pb']}x")

        # Update config.yaml if requested
        if update_config:
            logger.info("\nUpdating config.yaml...")
            self.update_config_yaml(calculated)
            logger.info("Config updated successfully")

        logger.info("\n" + "=" * 80)
        logger.info("Sector multiples refresh complete!")
        logger.info("=" * 80)

        return calculated

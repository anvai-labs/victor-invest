# Copyright 2025 Vijaykumar Singh
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

"""
Sector Multiples Tool for Victor Investment Framework.

This tool wraps the investigator sector multiples functionality to provide:
- Current sector multiples calculation (refresh)
- Historical sector multiples calculation
- Timeline visualization
- Trend analysis

Example:
    from victor_invest.tools import SectorMultiplesTool

    tool = SectorMultiplesTool()
    result = await tool.execute(
        action="refresh",
        sectors=["Technology", "Healthcare"],
        min_samples=10
    )
"""

import logging
from typing import Any, List, Optional

from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SectorMultiplesTool(BaseTool):
    """
    Tool for calculating and managing sector/industry valuation multiples.

    Wraps investigator domain services for sector multiples calculation.
    """

    name = "sector_multiples"
    description = (
        "Calculate sector/industry valuation multiples from database. "
        "Actions: refresh (current), historical (fiscal year), timeline, trend, "
        "trend_adjusted (robust valuations with trend analysis)"
    )

    def __init__(self, config=None):
        super().__init__(config)

    async def execute(self, _exec_ctx=None, **kwargs) -> ToolResult:
        """
        Execute sector multiples operation.

        Args:
            action: Operation to perform - "refresh", "historical", "timeline", "trend", "trend_adjusted"
            sectors: Comma-separated list of sectors (for refresh, historical, timeline, trend_adjusted)
            industries: Comma-separated list of industries
            fiscal_year: Fiscal year for historical calculation
            min_samples: Minimum sample size per sector (default: 10 for refresh, 5 for historical)
            exclude_outliers: Whether to exclude outliers (default: True)
            update_config: Whether to update config.yaml (default: True)
            dry_run: Calculate without updating config (default: False)
            store: Store in database for historical (default: True)
            export: Export file path for historical/timeline
            years: Years range for timeline (default: "5")
            metric: Metric for timeline - "pe", "ps", "pb", or "all" (default: "all")
            start_year: Start year for trend
            end_year: End year for trend
            group_type: Group type for trend - "sector" or "industry" (default: "sector")
            group_name: Group name for trend
            lookback_years: Years of historical data for trend_adjusted (default: 5)
            adjustment_sensitivity: Sensitivity for trend adjustments - "low", "medium", "high" (default: "medium")
            update_trend_config: Update config.yaml with trend-adjusted multiples (default: False)

        Returns:
            ToolResult with calculated sector multiples or error message
        """
        try:
            action = kwargs.get("action", "refresh")

            if action == "refresh":
                return await self._refresh(**kwargs)
            elif action == "historical":
                return await self._historical(**kwargs)
            elif action == "timeline":
                return await self._timeline(**kwargs)
            elif action == "trend":
                return await self._trend(**kwargs)
            elif action == "trend_adjusted":
                return await self._trend_adjusted(**kwargs)
            else:
                return ToolResult.create_failure(
                    f"Unknown action: {action}. Valid actions: refresh, historical, timeline, trend, trend_adjusted"
                )

        except Exception as e:
            logger.exception(f"Error in SectorMultiplesTool.execute: {e}")
            return ToolResult.create_failure(f"Error executing sector multiples: {str(e)}")

    async def _refresh(
        self,
        sectors: Optional[str] = None,
        industries: Optional[str] = None,
        min_samples: int = 10,
        exclude_outliers: bool = True,
        update_config: bool = True,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """
        Refresh current sector multiples from database data.

        Calculates median valuation multiples (P/E, P/S, EV/EBITDA, P/B) from
        actual market data in sec_companyfacts_processed.
        """
        from investigator.domain.services.sector_multiples_refresh import (
            SectorMultiplesRefresh,
        )

        # Parse sector/industry lists
        sector_list: Optional[List[str]] = None
        industry_list: Optional[List[str]] = None

        if sectors:
            sector_list = [s.strip() for s in sectors.split(",")]
            logger.info(f"Refreshing sectors: {', '.join(sector_list)}")

        if industries:
            industry_list = [i.strip() for i in industries.split(",")]
            logger.info(f"Refreshing industries: {', '.join(industry_list)}")

        # Configure outlier filtering
        percentile_exclude = (0.05, 0.95) if exclude_outliers else (0.0, 1.0)

        # Initialize refresh service
        refresh_service = SectorMultiplesRefresh(
            min_samples=min_samples,
            percentile_exclude=percentile_exclude,
        )

        # Calculate multiples
        logger.info("Calculating sector/industry multiples from database...")
        calculated = refresh_service.calculate_sector_multiples(
            sectors=sector_list,
            industries=industry_list,
            use_config_overrides=True,
        )

        if not calculated:
            return ToolResult.create_failure("No sector multiples calculated (insufficient data)")

        # Format results
        result_data = {
            "action": "refresh",
            "dry_run": dry_run,
            "config_updated": False,
            "multiples": {},
        }

        for name, multiples in sorted(calculated.items()):
            result_data["multiples"][name] = {
                "sample_size": multiples.get("sample_size"),
                "pe": multiples.get("pe"),
                "ps": multiples.get("ps"),
                "ev_ebitda": multiples.get("ev_ebitda"),
                "pb": multiples.get("pb"),
            }

        # Update config if requested (not in dry run)
        if update_config and not dry_run:
            logger.info("Updating config.yaml...")
            success = refresh_service.update_config_yaml(calculated)
            if success:
                result_data["config_updated"] = True
                logger.info("Config updated successfully")
            else:
                logger.warning("Failed to update config.yaml")
        elif dry_run:
            logger.info("Dry run mode - config.yaml not updated")

        logger.info(f"Refresh complete: {len(calculated)} sector/industry multiples calculated")

        return ToolResult.create_success(result_data)

    async def _historical(
        self,
        fiscal_year: int,
        sectors: Optional[str] = None,
        industries: Optional[str] = None,
        min_samples: int = 5,
        exclude_outliers: bool = True,
        store: bool = True,
        export: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Calculate historical sector multiples for a specific fiscal year.

        Uses SEC FY data from sec_num_data/sec_tag_data tables.
        """
        from investigator.domain.services.sector_multiples_history import (
            SectorMultiplesHistory,
        )

        # Parse sector/industry lists
        sector_list: Optional[List[str]] = None
        industry_list: Optional[List[str]] = None

        if sectors:
            sector_list = [s.strip() for s in sectors.split(",")]
            logger.info(f"Historical calculation for sectors: {', '.join(sector_list)}")

        if industries:
            industry_list = [i.strip() for i in industries.split(",")]
            logger.info(f"Historical calculation for industries: {', '.join(industry_list)}")

        # Configure outlier filtering
        percentile_exclude = (0.05, 0.95) if exclude_outliers else (0.0, 1.0)

        # Initialize history service
        history_service = SectorMultiplesHistory(
            min_samples=min_samples,
            percentile_exclude=percentile_exclude,
        )

        # Calculate historical multiples
        logger.info(f"Calculating historical multiples for FY{fiscal_year}...")
        calculated = history_service.calculate_historical_multiples(
            fiscal_year=fiscal_year,
            sectors=sector_list,
            industries=industry_list,
            use_config_overrides=True,
        )

        if not calculated:
            return ToolResult.create_failure(f"No historical multiples calculated for FY{fiscal_year}")

        # Format results
        result_data = {
            "action": "historical",
            "fiscal_year": fiscal_year,
            "stored": False,
            "export_file": export,
            "multiples": {},
        }

        for name, multiples in sorted(calculated.items()):
            result_data["multiples"][name] = {
                "snapshot_date": multiples.get("snapshot_date"),
                "sample_size": multiples.get("sample_size"),
                "pe": multiples.get("pe"),
                "ps": multiples.get("ps"),
                "pb": multiples.get("pb"),
            }

        # Store in database if requested
        if store:
            logger.info("Storing in database...")
            # Store sectors
            sector_data = {k: v for k, v in calculated.items() if not self._is_industry(k)}
            if sector_data:
                history_service.store_history(sector_data, group_type="sector")

            # Store industries
            industry_data = {k: v for k, v in calculated.items() if self._is_industry(k)}
            if industry_data:
                history_service.store_history(industry_data, group_type="industry")

            result_data["stored"] = True
            logger.info("Data stored successfully in sector_multiples_history table")

        # Export to file if requested
        if export:
            logger.info(f"Exporting to {export}...")
            fmt = "json" if export.endswith(".json") else "csv"
            success = history_service.export_to_file(
                export,
                start_year=fiscal_year,
                end_year=fiscal_year,
                format=fmt,
            )
            if success:
                logger.info(f"Exported to {export}")
            else:
                logger.warning(f"Failed to export to {export}")

        logger.info(f"Historical calculation complete: {len(calculated)} sector/industry multiples")

        return ToolResult.create_success(result_data)

    async def _timeline(
        self,
        sectors: str = "Technology",
        industries: Optional[str] = None,
        years: str = "5",
        metric: str = "all",
        **kwargs,
    ) -> ToolResult:
        """
        Display sector/industry multiples timeline table.

        Shows matrix view with sectors/industries as rows and years as columns.
        """
        from sqlalchemy import text

        from investigator.infrastructure.database.db import get_db_manager

        # Parse years
        year_list = self._parse_years(years)

        # Parse sector/industry lists
        sector_list = [s.strip() for s in sectors.split(",")] if sectors else ["Technology"]
        industry_list = [i.strip() for i in industries.split(",")] if industries else []

        db_manager = get_db_manager()
        engine = db_manager.engine

        # Fetch data
        with engine.connect() as conn:
            params = {}
            year_placeholders = ",".join([f":year_{i}" for i in range(len(year_list))])
            for i, y in enumerate(year_list):
                params[f"year_{i}"] = y

            group_filters = []
            if sector_list:
                sector_placeholders = ",".join([f":sector_{i}" for i in range(len(sector_list))])
                for i, s in enumerate(sector_list):
                    params[f"sector_{i}"] = s
                group_filters.append(f"(group_type = 'sector' AND group_name IN ({sector_placeholders}))")

            if industry_list:
                industry_placeholders = ",".join([f":industry_{i}" for i in range(len(industry_list))])
                for i, ind in enumerate(industry_list):
                    params[f"industry_{i}"] = ind
                group_filters.append(f"(group_type = 'industry' AND group_name IN ({industry_placeholders}))")

            where_clause = " OR ".join(group_filters) if group_filters else "1=1"

            query = text(f"""
                SELECT group_type, group_name, fiscal_year,
                       pe_multiple, ps_multiple, pb_multiple, sample_size
                FROM sector_multiples_history
                WHERE fiscal_year IN ({year_placeholders})
                  AND ({where_clause})
                ORDER BY group_type, group_name, fiscal_year
            """)

            result = conn.execute(query, params)

            # Organize data
            data: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
            for row in result:
                group_type, group_name = row[0], row[1]
                year = row[2]
                pe, ps, pb, sample = row[3], row[4], row[5], row[6]

                key = (group_type, group_name)
                if key not in data:
                    data[key] = {}
                data[key][year] = {"pe": pe, "ps": ps, "pb": pb, "sample": sample}

        if not data:
            return ToolResult.create_failure(
                "No historical data found. Run historical action first to populate database."
            )

        # Format results
        result_data = {
            "action": "timeline",
            "years": year_list,
            "metric": metric,
            "sectors": sector_list,
            "industries": industry_list,
            "data": {},
        }

        for (group_type, group_name), year_data in data.items():
            prefix = "sector:" if group_type == "sector" else "industry:"
            key = f"{prefix} {group_name}"
            result_data["data"][key] = {}

            for year in year_list:
                if year in year_data:
                    result_data["data"][key][year] = year_data[year]

        # Calculate trend summary
        result_data["trends"] = {}
        if len(year_list) >= 2:
            for (group_type, group_name), year_data in data.items():
                if year_list[0] in year_data and year_list[-1] in year_data:
                    for m in ["pe", "ps", "pb"]:
                        start_val = year_data[year_list[0]].get(m)
                        end_val = year_data[year_list[-1]].get(m)

                        if start_val and end_val:
                            change_pct = ((end_val - start_val) / start_val) * 100
                            prefix = "sector:" if group_type == "sector" else "industry:"
                            key = f"{prefix} {group_name}"
                            if key not in result_data["trends"]:
                                result_data["trends"][key] = {}
                            result_data["trends"][key][m] = {
                                "start": start_val,
                                "end": end_val,
                                "change_pct": change_pct,
                                "status": (
                                    "SWELLING" if change_pct > 5 else "SHRINKING" if change_pct < -5 else "STABLE"
                                ),
                            }

        logger.info(f"Timeline generated: {len(data)} sector/industry groups over {len(year_list)} years")

        return ToolResult.create_success(result_data)

    async def _trend(
        self,
        group_name: str,
        group_type: str = "sector",
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        export: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """
        View historical trend for a sector or industry.

        Displays historical valuation multiples over time to identify
        swelling (expansion) and shrinking (contraction) trends.
        """
        from investigator.domain.services.sector_multiples_history import (
            SectorMultiplesHistory,
        )

        history_service = SectorMultiplesHistory()

        logger.info(f"Fetching trend data for {group_type}: {group_name}...")

        trend_data = history_service.get_trend_data(
            group_name=group_name,
            group_type=group_type,
            start_year=start_year,
            end_year=end_year,
        )

        if not trend_data:
            return ToolResult.create_failure(
                f"No trend data found for {group_type}: {group_name}. Run historical action first to populate database."
            )

        # Format results
        result_data: dict[str, Any] = {
            "action": "trend",
            "group_name": group_name,
            "group_type": group_type,
            "start_year": start_year,
            "end_year": end_year,
            "data": [],
            "trend_analysis": {},
        }

        for row in trend_data:
            result_data["data"].append(
                {
                    "fiscal_year": row["fiscal_year"],
                    "snapshot_date": row.get("snapshot_date"),
                    "pe": row.get("pe"),
                    "ps": row.get("ps"),
                    "pb": row.get("pb"),
                    "sample_size": row.get("sample_size"),
                }
            )

        # Calculate trend analysis
        if len(trend_data) > 1:
            first_pe = trend_data[0].get("pe")
            last_pe = trend_data[-1].get("pe")

            if first_pe and last_pe:
                if last_pe > first_pe:
                    pct_change = ((last_pe - first_pe) / first_pe) * 100
                    result_data["trend_analysis"]["pe"] = {
                        "status": "SWELLING",
                        "first": first_pe,
                        "last": last_pe,
                        "change_pct": pct_change,
                    }
                else:
                    pct_change = ((first_pe - last_pe) / first_pe) * 100
                    result_data["trend_analysis"]["pe"] = {
                        "status": "SHRINKING",
                        "first": first_pe,
                        "last": last_pe,
                        "change_pct": pct_change,
                    }

        logger.info(f"Trend data retrieved: {len(trend_data)} years for {group_name}")

        return ToolResult.create_success(result_data)

    async def _trend_adjusted(
        self,
        sectors: Optional[str] = None,
        industries: Optional[str] = None,
        min_samples: int = 10,
        exclude_outliers: bool = True,
        lookback_years: int = 5,
        adjustment_sensitivity: str = "medium",
        update_trend_config: bool = False,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """
        Calculate trend-adjusted sector multiples for robust valuations.

        Combines current snapshot data with historical trend analysis to adjust
        for sector expansion/shrinking, market regime changes, and volatility.

        Args:
            sectors: Comma-separated list of sectors
            industries: Comma-separated list of industries
            min_samples: Minimum sample size per sector (default: 10)
            exclude_outliers: Whether to exclude outliers (default: True)
            lookback_years: Years of historical data to analyze (default: 5)
            adjustment_sensitivity: Sensitivity - "low", "medium", "high" (default: "medium")
            update_trend_config: Update config.yaml with trend-adjusted multiples (default: False)
            dry_run: Calculate without updating config (default: False)

        Returns:
            ToolResult with trend-adjusted sector multiples
        """
        from investigator.domain.services.sector_multiples_refresh import (
            SectorMultiplesRefresh,
        )
        from investigator.domain.services.sector_multiples_trend_adjusted import (
            SectorMultiplesTrendAdjusted,
        )

        # Parse sector/industry lists
        sector_list: Optional[List[str]] = None
        industry_list: Optional[List[str]] = None

        if sectors:
            sector_list = [s.strip() for s in sectors.split(",")]
            logger.info(f"Calculating trend-adjusted multiples for sectors: {', '.join(sector_list)}")

        if industries:
            industry_list = [i.strip() for i in industries.split(",")]
            logger.info(f"Calculating trend-adjusted multiples for industries: {', '.join(industry_list)}")

        # Configure outlier filtering
        percentile_exclude = (0.05, 0.95) if exclude_outliers else (0.0, 1.0)

        # Step 1: Get current snapshot multiples
        logger.info("Step 1: Calculating current snapshot multiples...")
        refresh_service = SectorMultiplesRefresh(
            min_samples=min_samples,
            percentile_exclude=percentile_exclude,
        )

        current_multiples = refresh_service.calculate_sector_multiples(
            sectors=sector_list,
            industries=industry_list,
            use_config_overrides=True,
        )

        if not current_multiples:
            return ToolResult.create_failure("No sector multiples calculated (insufficient data)")

        logger.info(f"Current multiples calculated for {len(current_multiples)} groups")

        # Step 2: Apply trend adjustments
        logger.info(
            f"Step 2: Applying trend adjustments (lookback: {lookback_years} years, "
            f"sensitivity: {adjustment_sensitivity})..."
        )

        trend_service = SectorMultiplesTrendAdjusted(
            min_samples=min_samples,
            percentile_exclude=percentile_exclude,
            lookback_years=lookback_years,
            adjustment_sensitivity=adjustment_sensitivity,
        )

        adjusted_multiples = trend_service.calculate_trend_adjusted_multiples(
            current_multiples=current_multiples,
            sectors=sector_list,
            industries=industry_list,
        )

        if not adjusted_multiples:
            return ToolResult.create_failure("Failed to calculate trend-adjusted multiples")

        # Step 3: Update config if requested
        config_updated = False
        if update_trend_config and not dry_run:
            logger.info("Step 3: Updating config.yaml with trend-adjusted multiples...")
            success = refresh_service.update_config_yaml(adjusted_multiples)
            if success:
                config_updated = True
                logger.info("Config updated successfully with trend-adjusted multiples")
            else:
                logger.warning("Failed to update config.yaml")
        elif dry_run:
            logger.info("Dry run mode - config.yaml not updated")

        # Format results
        result_data = {
            "action": "trend_adjusted",
            "dry_run": dry_run,
            "config_updated": config_updated,
            "lookback_years": lookback_years,
            "adjustment_sensitivity": adjustment_sensitivity,
            "multiples": {},
        }

        for name, multiples in sorted(adjusted_multiples.items()):
            result_data["multiples"][name] = {
                "sample_size": multiples.get("sample_size"),
                "trend_analysis": multiples.get("trend_analysis", {}),
            }

            # Add both raw and adjusted values
            for metric in ["pe", "ps", "pb", "ev_ebitda"]:
                if f"{metric}_raw" in multiples:
                    result_data["multiples"][name][f"{metric}_raw"] = multiples.get(f"{metric}_raw")
                if metric in multiples:
                    result_data["multiples"][name][metric] = multiples.get(metric)

        logger.info(f"Trend-adjusted calculation complete: {len(adjusted_multiples)} sector/industry multiples")

        return ToolResult.create_success(result_data)

    def _is_industry(self, name: str) -> bool:
        """Determine if a name is likely an industry vs sector."""
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
            "Electrical",
            "Metal",
            "Chemical",
            "Food",
            "Retail",
            "Energy",
            "Transportation",
        ]
        name_lower = name.lower()
        return any(keyword.lower() in name_lower for keyword in industry_keywords)

    @staticmethod
    def _parse_years(years_str: str) -> list:
        """Parse years string into list of years.

        Examples:
            "5" -> [2024, 2023, 2022, 2021, 2020]
            "2018-2024" -> [2018, 2019, 2020, 2021, 2022, 2023, 2024]
        """
        from datetime import datetime

        current_year = datetime.now().year

        if "-" in years_str:
            # Range like 2018-2024
            start, end = years_str.split("-")
            return list(range(int(start), int(end) + 1))
        else:
            # Number of years back from current
            try:
                count = int(years_str)
                return list(range(current_year - count + 1, current_year + 1))
            except ValueError:
                return [current_year]

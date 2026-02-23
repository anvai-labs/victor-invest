# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
# SPDX-License-Identifier: Apache-2.0

"""FastAPI router for sector analysis endpoints.

Provides endpoints for sector multiples, historical trends, and
representative stock data for the sector analysis dashboard.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from investigator.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui/api/sectors", tags=["sectors"])


def _get_engine() -> Engine:
    """Get database engine for sector queries."""
    config = get_config()
    db_url = (
        f"postgresql://{config.database.username}:{config.database.password}@"
        f"{config.database.host}:{config.database.port}/{config.database.database}"
    )
    return create_engine(db_url)


@router.get("/multiples")
async def get_sector_multiples(
    fiscal_year: Optional[int] = Query(None, description="Filter by fiscal year"),
    sector: Optional[str] = Query(None, description="Filter by sector name"),
) -> Dict[str, Any]:
    """Get sector multiples data.

    Args:
        fiscal_year: Optional fiscal year filter
        sector: Optional sector name filter

    Returns:
        Dictionary with sector multiples data
    """
    engine = _get_engine()

    where_clauses = ["group_type = 'sector'"]
    params_list = []

    if fiscal_year:
        where_clauses.append("fiscal_year = %s")
        params_list.append(fiscal_year)

    if sector:
        where_clauses.append("group_name = %s")
        params_list.append(sector)

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT
            group_name as sector,
            fiscal_year,
            pe_multiple as pe,
            ps_multiple as ps,
            pb_multiple as pb,
            ev_ebitda_multiple as ev_ebitda,
            sample_size,
            percentile_low,
            percentile_high,
            snapshot_date,
            updated_at
        FROM sector_multiples_history
        WHERE {where_sql}
        ORDER BY sector, fiscal_year DESC
    """

    with engine.connect() as conn:
        import pandas as pd

        df = pd.read_sql(query, conn, params=tuple(params_list))

        if df.empty:
            return {"data": [], "total": 0}

        # Convert to list of dicts for JSON response
        data = df.to_dict(orient="records")

        return {
            "data": data,
            "total": len(data),
            "fiscal_years": sorted(df["fiscal_year"].unique().tolist(), reverse=True),
            "sectors": sorted(df["sector"].unique().tolist()),
        }


@router.get("/history")
async def get_sector_history(
    sector: str = Query(..., description="Sector name"),
    start_year: int = Query(2016, description="Start year (inclusive)"),
    end_year: int = Query(2024, description="End year (inclusive)"),
) -> Dict[str, Any]:
    """Get historical multiples data for a specific sector.

    Args:
        sector: Sector name
        start_year: Start year
        end_year: End year

    Returns:
        Historical data for the sector
    """
    engine = _get_engine()

    query = """
        SELECT
            fiscal_year,
            pe_multiple as pe,
            ps_multiple as ps,
            pb_multiple as pb,
            ev_ebitda_multiple as ev_ebitda,
            sample_size
        FROM sector_multiples_history
        WHERE group_type = 'sector'
            AND group_name = %s
            AND fiscal_year BETWEEN %s AND %s
        ORDER BY fiscal_year
    """

    with engine.connect() as conn:
        import pandas as pd

        df = pd.read_sql(
            query,
            conn,
            params=(sector, start_year, end_year),
        )

        if df.empty:
            return {"sector": sector, "data": [], "years": []}

        return {
            "sector": sector,
            "data": df.to_dict(orient="records"),
            "years": df["fiscal_year"].tolist(),
        }


@router.get("/timeline")
async def get_sector_timeline(
    start_year: int = Query(2016, description="Start year"),
    end_year: int = Query(2024, description="End year"),
    sectors: Optional[str] = Query(None, description="Comma-separated sector list"),
) -> Dict[str, Any]:
    """Get sector multiples timeline data for multiple sectors.

    Args:
        start_year: Start year
        end_year: End year
        sectors: Comma-separated list of sectors (empty = all sectors)

    Returns:
        Timeline data for all requested sectors
    """
    engine = _get_engine()

    where_clauses = [
        "group_type = 'sector'",
        f"fiscal_year BETWEEN {start_year} AND {end_year}",
    ]

    if sectors:
        sector_list = [s.strip() for s in sectors.split(",")]
        formatted_sectors = ", ".join([f"'{s}'" for s in sector_list])
        where_clauses.append(f"group_name IN ({formatted_sectors})")

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT
            group_name as sector,
            fiscal_year,
            pe_multiple as pe,
            ps_multiple as ps,
            pb_multiple as pb,
            ev_ebitda_multiple as ev_ebitda,
            sample_size
        FROM sector_multiples_history
        WHERE {where_sql}
        ORDER BY sector, fiscal_year
    """

    with engine.connect() as conn:
        import pandas as pd

        df = pd.read_sql(query, conn)

        if df.empty:
            return {
                "data": [],
                "sectors": [],
                "years": list(range(start_year, end_year + 1)),
            }

        # Group by sector for easier consumption
        sector_data = {}
        for sector in df["sector"].unique():
            sector_df = df[df["sector"] == sector]
            sector_data[sector] = {
                "data": sector_df.to_dict(orient="records"),
                "years": sector_df["fiscal_year"].tolist(),
            }

        return {
            "data": sector_data,
            "sectors": sorted(df["sector"].unique().tolist()),
            "years": sorted(df["fiscal_year"].unique().tolist()),
        }


@router.get("/stocks/representative")
async def get_representative_stocks(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    fiscal_year: int = Query(2024, description="Fiscal year for stock selection"),
    limit: int = Query(10, ge=1, le=50, description="Max stocks per sector"),
) -> Dict[str, Any]:
    """Get representative stocks for sector(s).

    Args:
        sector: Optional sector filter
        fiscal_year: Year to select stocks from
        limit: Max stocks per sector

    Returns:
        Representative stocks data
    """
    engine = _get_engine()

    where_clauses = [f"scp.fiscal_year = {fiscal_year}"]

    if sector:
        where_clauses.append(f"s.\"Sector\" = '{sector}'")

    where_sql = " AND ".join(where_clauses)

    query = f"""
        WITH ranked_stocks AS (
            SELECT
                s.ticker as symbol,
                s.\"Sector\" as sector,
                s.mktcap as market_cap,
                s.pe_ratio,
                s.ps_ratio,
                s.pb_ratio,
                ROW_NUMBER() OVER (PARTITION BY s.\"Sector\" ORDER BY s.mktcap DESC NULLS LAST) as rank_in_sector
            FROM symbol s
            INNER JOIN sec_companyfacts_processed scp ON s.ticker = scp.symbol
            WHERE {where_sql}
                AND s.mktcap > 0
                AND s.\"Sector\" IS NOT NULL
        )
        SELECT
            symbol,
            sector,
            market_cap,
            pe_ratio,
            ps_ratio,
            pb_ratio,
            rank_in_sector
        FROM ranked_stocks
        WHERE rank_in_sector <= {limit}
            AND (pe_ratio > 0 OR ps_ratio > 0 OR pb_ratio > 0)
        ORDER BY sector, rank_in_sector
    """

    with engine.connect() as conn:
        import pandas as pd

        df = pd.read_sql(query, conn)

        if df.empty:
            return {"data": [], "sectors": [], "total": 0}

        # Group by sector
        sector_data = {}
        for s in df["sector"].unique():
            sector_df = df[df["sector"] == s]
            sector_data[s] = {
                "stocks": sector_df.to_dict(orient="records"),
                "count": len(sector_df),
            }

        return {
            "data": sector_data,
            "sectors": sorted(df["sector"].unique().tolist()),
            "total": len(df),
        }


@router.get("/overview")
async def get_sector_overview() -> Dict[str, Any]:
    """Get overview of all available sectors and their latest multiples.

    Returns:
        Sector overview with latest data
    """
    engine = _get_engine()

    query = """
        WITH latest_data AS (
            SELECT DISTINCT ON (group_name)
                group_name as sector,
                fiscal_year,
                pe_multiple as pe,
                ps_multiple as ps,
                pb_multiple as pb,
                ev_ebitda_multiple as ev_ebitda,
                sample_size,
                updated_at
            FROM sector_multiples_history
            WHERE group_type = 'sector'
                AND pe_multiple IS NOT NULL
            ORDER BY group_name, fiscal_year DESC
        )
        SELECT
            sector,
            fiscal_year,
            pe,
            ps,
            pb,
            ev_ebitda,
            sample_size,
            updated_at
        FROM latest_data
        ORDER BY sector
    """

    with engine.connect() as conn:
        import pandas as pd

        df = pd.read_sql(query, conn)

        if df.empty:
            return {"sectors": [], "total_sectors": 0, "latest_year": None}

        return {
            "sectors": df.to_dict(orient="records"),
            "total_sectors": len(df),
            "latest_year": int(df["fiscal_year"].max()),
            "fiscal_years": sorted(df["fiscal_year"].unique().tolist(), reverse=True),
        }


@router.get("/comparison")
async def compare_sectors(
    sectors: str = Query(..., description="Comma-separated sector list to compare"),
    metric: str = Query("pe", description="Metric to compare (pe, ps, pb, ev_ebitda)"),
) -> Dict[str, Any]:
    """Compare multiples across specified sectors.

    Args:
        sectors: Comma-separated list of sectors
        metric: Metric to compare

    Returns:
        Comparison data for the sectors
    """
    engine = _get_engine()

    sector_list = [s.strip() for s in sectors.split(",")]
    metric_column = f"{metric}_multiple"

    placeholders = ", ".join(["%s"] * len(sector_list))

    query = f"""
        SELECT
            group_name as sector,
            fiscal_year,
            {metric_column} as value,
            sample_size
        FROM sector_multiples_history
        WHERE group_type = 'sector'
            AND group_name IN ({placeholders})
            AND {metric_column} IS NOT NULL
        ORDER BY sector, fiscal_year
    """

    with engine.connect() as conn:
        import pandas as pd

        df = pd.read_sql(query, conn, params=tuple(sector_list))

        if df.empty:
            return {"metric": metric, "sectors": sector_list, "data": {}}

        # Pivot to have years as index, sectors as columns
        pivot_df = df.pivot(index="fiscal_year", columns="sector", values="value")

        return {
            "metric": metric,
            "sectors": sector_list,
            "data": pivot_df.to_dict(orient="index"),
            "years": sorted(df["fiscal_year"].unique().tolist()),
        }

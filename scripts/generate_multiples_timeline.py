#!/usr/bin/env python3
"""Generate sector/industry multiples timeline table.

Creates a matrix view with sectors/industries as rows and years as columns.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from investigator.infrastructure.database.db import get_db_manager
from sqlalchemy import text
from typing import Dict, List, Tuple
import psycopg2.extras


def get_timeline_data(
    sectors: List[str], industries: List[str], years: List[int]
) -> Dict[Tuple[str, str], Dict[int, dict]]:
    """Fetch historical multiples data for specified groups and years.

    Args:
        sectors: List of sector names
        industries: List of industry names
        years: List of fiscal years

    Returns:
        Dict mapping (group_type, group_name) -> {year: {pe, ps, pb, sample_size}}
    """
    db_manager = get_db_manager()
    engine = db_manager.engine

    data: Dict[Tuple[str, str], Dict[int, dict]] = {}

    with engine.connect() as conn:
        # Build year filter using IN clause
        year_placeholders = ",".join([f":year_{i}" for i in range(len(years))])
        params = {}
        for i, y in enumerate(years):
            params[f"year_{i}"] = y

        # Build sector/industry filter
        group_filters = []
        if sectors:
            sector_placeholders = ",".join([f":sector_{i}" for i in range(len(sectors))])
            for i, s in enumerate(sectors):
                params[f"sector_{i}"] = s
            group_filters.append(f"(group_type = 'sector' AND group_name IN ({sector_placeholders}))")

        if industries:
            industry_placeholders = ",".join([f":industry_{i}" for i in range(len(industries))])
            for i, ind in enumerate(industries):
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

        for row in result:
            group_type = row[0]
            group_name = row[1]
            year = row[2]
            pe = row[3]
            ps = row[4]
            pb = row[5]
            sample_size = row[6]

            key = (group_type, group_name)
            if key not in data:
                data[key] = {}

            data[key][year] = {
                "pe": pe,
                "ps": ps,
                "pb": pb,
                "sample_size": sample_size,
            }

    return data


def format_value(val: float, baseline: float = None) -> str:
    """Format a value with color coding for trends."""
    if val is None:
        return "—"

    formatted = f"{val:.1f}x"

    # Add trend indicator if baseline provided
    if baseline is not None and baseline > 0:
        change = ((val - baseline) / baseline) * 100
        if change > 10:
            return f"{formatted} ↑"  # Swelling
        elif change < -10:
            return f"{formatted} ↓"  # Shrinking
        elif change > 0:
            return f"{formatted} ↗"
        elif change < 0:
            return f"{formatted} ↘"

    return formatted


def print_timeline_table(
    data: Dict[Tuple[str, str], Dict[int, dict]],
    years: List[int],
    metric: str = "pe",
    show_trends: bool = True,
):
    """Print timeline table as ASCII matrix.

    Args:
        data: Historical multiples data
        years: List of years (columns)
        metric: Which metric to display ('pe', 'ps', or 'pb')
        show_trends: Whether to show trend arrows vs earliest year
    """
    if not data:
        print("No data available")
        return

    # Sort groups: sectors first, then industries
    sorted_groups = sorted(data.keys(), key=lambda x: (x[0], x[1]))

    # Get baseline year for trend calculation
    baseline_year = min(years) if show_trends else None

    # Print header
    metric_name = {"pe": "P/E", "ps": "P/S", "pb": "P/B"}[metric].upper()
    print(f"\n{'SECTOR/INDUSTRY':<50} │", end="")
    for year in years:
        print(f" {year:>6} │", end="")
    print("\n" + "─" * (50 + 8 * len(years)))

    # Print rows
    for group_type, group_name in sorted_groups:
        year_data = data[(group_type, group_name)]

        # Format group name
        prefix = "🏢 " if group_type == "sector" else "🏭 "
        name = f"{prefix}{group_name}"
        print(f"{name:<50} │", end="")

        baseline = year_data.get(baseline_year, {}).get(metric) if baseline_year else None

        for year in years:
            if year in year_data and year_data[year].get(metric):
                val = year_data[year][metric]
                print(f" {format_value(val, baseline if show_trends else None):>6} │", end="")
            else:
                print(f" {'—':>6} │", end="")

        print()

    print("\nLegend: ↑↗ = swelling (expansion), ↓↘ = shrinking (contraction), — = no data")


def print_trend_summary(
    data: Dict[Tuple[str, str], Dict[int, dict]], years: List[int], metric: str = "pe"
):
    """Print summary of trends for each group."""
    if len(years) < 2:
        return

    print(f"\n{metric.upper()} TREND SUMMARY ({years[0]} → {years[-1]}):")
    print("=" * 80)

    sorted_groups = sorted(data.keys(), key=lambda x: (x[0], x[1]))

    for group_type, group_name in sorted_groups:
        year_data = data[(group_type, group_name)]

        if years[0] in year_data and years[-1] in year_data:
            start_val = year_data[years[0]].get(metric)
            end_val = year_data[years[-1]].get(metric)

            if start_val and end_val:
                change_pct = ((end_val - start_val) / start_val) * 100

                prefix = "🏢" if group_type == "sector" else "🏭"
                status = "SWELLING" if change_pct > 5 else "SHRINKING" if change_pct < -5 else "STABLE"

                print(
                    f"{prefix} {group_name:<40} │ {start_val:>6.1f}x → {end_val:>6.1f}x │ "
                    f"{change_pct:+6.1f}% │ {status}"
                )


def main():
    """Main entry point."""
    # Define sectors and industries to track
    sectors = [
        "Technology",
        "Healthcare",
        "Financials",
        "Consumer Cyclical",
        "Consumer Defensive",
        "Industrials",
        "Energy",
        "Real Estate",
        "Communication Services",
        "Utilities",
    ]

    industries = [
        "Semiconductors",
        "Computer Software: Prepackaged Software",
        "EDP Services",
        "Retail: Computer Software & Peripheral Equipment",
        "Electronic Components",
    ]

    years = [2020, 2021, 2022, 2023, 2024]

    print("Fetching historical multiples data...")
    data = get_timeline_data(sectors, industries, years)

    # Print P/E timeline
    print("\n" + "=" * 80)
    print("P/E MULTIPLE TIMELINE")
    print("=" * 80)
    print_timeline_table(data, years, metric="pe", show_trends=True)
    print_trend_summary(data, years, metric="pe")

    # Print P/S timeline
    print("\n" + "=" * 80)
    print("P/S MULTIPLE TIMELINE")
    print("=" * 80)
    print_timeline_table(data, years, metric="ps", show_trends=True)
    print_trend_summary(data, years, metric="ps")

    # Print P/B timeline
    print("\n" + "=" * 80)
    print("P/B MULTIPLE TIMELINE")
    print("=" * 80)
    print_timeline_table(data, years, metric="pb", show_trends=True)
    print_trend_summary(data, years, metric="pb")


if __name__ == "__main__":
    main()

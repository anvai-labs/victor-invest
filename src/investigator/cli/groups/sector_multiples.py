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

"""Sector multiples management commands for InvestiGator CLI."""

import logging
from typing import List, Optional

import click

logger = logging.getLogger(__name__)


@click.group()
@click.pass_context
def sector_multiples(ctx):
    """Sector/industry valuation multiples management

    Calculate and refresh sector/industry valuation multiples from actual
    market data stored in the database. Updates config.yaml with fresh values.

    Examples:
        investigator sector-multiples refresh --sectors "Technology"
        investigator sector-multiples refresh --dry-run
        investigator sector-multiples refresh --min-samples 20
    """
    pass


@sector_multiples.command("refresh")
@click.option(
    "--sectors",
    "-s",
    help="Comma-separated list of sectors to calculate (default: all)",
)
@click.option(
    "--industries",
    "-i",
    help="Comma-separated list of industries to calculate (default: all)",
)
@click.option(
    "--min-samples",
    "-n",
    default=10,
    type=int,
    help="Minimum number of symbols required per sector/industry (default: 10)",
)
@click.option(
    "--exclude-outliers/--no-exclude-outliers",
    default=True,
    help="Exclude outliers using percentile filtering (default: True)",
)
@click.option(
    "--update-config/--no-update-config",
    default=True,
    help="Update config.yaml with calculated values (default: True)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Calculate without updating config.yaml",
)
@click.pass_context
def refresh(ctx, sectors, industries, min_samples, exclude_outliers, update_config, dry_run):
    """Refresh sector/industry multiples from database data

    Calculates median valuation multiples (P/E, P/S, EV/EBITDA, P/B) from
    actual market data in the database. Uses sec_companyfacts_processed for
    TTM metrics and stock.symbol for sector/industry classification.

    \b
    Calculation Process:
      1. Get all symbols in target sectors/industries
      2. Fetch TTM metrics (revenue, net income, EBITDA, market cap, etc.)
      3. Calculate multiples: P/E, P/S, EV/EBITDA, P/B
      4. Apply outlier filtering (5th-95th percentile)
      5. Compute median multiples per sector/industry
      6. Update config.yaml with calculated values

    \b
    Data Sources:
      - stock.symbol: Sector/industry classification
      - sec_companyfacts_processed: TTM financial metrics
      - config.yaml: For sector overrides and storing results

    \b
    Examples:
        # Refresh all sectors (dry run)
        investigator sector-multiples refresh --dry-run

        # Refresh Technology sector only
        investigator sector-multiples refresh --sectors "Technology"

        # Refresh with higher minimum sample size
        investigator sector-multiples refresh --min-samples 20

        # Calculate but don't update config
        investigator sector-multiples refresh --no-update-config
    """
    from investigator.domain.services.sector_multiples_refresh import (
        SectorMultiplesRefresh,
    )

    # Parse sector/industry lists
    sector_list: Optional[List[str]] = None
    industry_list: Optional[List[str]] = None

    if sectors:
        sector_list = [s.strip() for s in sectors.split(",")]
        click.echo(f"Target sectors: {', '.join(sector_list)}")

    if industries:
        industry_list = [i.strip() for i in industries.split(",")]
        click.echo(f"Target industries: {', '.join(industry_list)}")

    # Configure outlier filtering
    percentile_exclude = (0.05, 0.95) if exclude_outliers else (0.0, 1.0)

    click.echo("\nConfiguration:")
    click.echo(f"  Minimum samples: {min_samples}")
    click.echo(f"  Exclude outliers: {exclude_outliers}")
    click.echo(f"  Update config: {update_config}")
    if dry_run:
        click.echo("  Dry run: YES (config will not be updated)")
    click.echo()

    # Initialize refresh service
    refresh_service = SectorMultiplesRefresh(
        min_samples=min_samples,
        percentile_exclude=percentile_exclude,
    )

    # Calculate multiples
    click.echo("Calculating sector/industry multiples from database...")
    calculated = refresh_service.calculate_sector_multiples(
        sectors=sector_list,
        industries=industry_list,
        use_config_overrides=True,
    )

    if not calculated:
        click.echo("No sector multiples calculated (insufficient data)")
        return

    # Display results
    click.echo("\n" + "=" * 80)
    click.echo("CALCULATED SECTOR/INDUSTRY MULTIPLES")
    click.echo("=" * 80)

    for name, multiples in sorted(calculated.items()):
        click.echo(f"\n{name}:")
        click.echo(f"  Sample Size: {multiples.get('sample_size', 'N/A')}")
        if multiples.get("pe"):
            click.echo(f"  P/E: {multiples['pe']}x")
        if multiples.get("ps"):
            click.echo(f"  P/S: {multiples['ps']}x")
        if multiples.get("ev_ebitda"):
            click.echo(f"  EV/EBITDA: {multiples['ev_ebitda']}x")
        if multiples.get("pb"):
            click.echo(f"  P/B: {multiples['pb']}x")

    # Update config if requested
    if update_config and not dry_run:
        click.echo("\nUpdating config.yaml...")
        success = refresh_service.update_config_yaml(calculated)
        if success:
            click.echo("Config updated successfully")
        else:
            click.echo("Failed to update config.yaml", err=True)
    elif dry_run:
        click.echo("\nDry run mode - config.yaml not updated")

    click.echo("\n" + "=" * 80)
    click.echo("Sector multiples refresh complete!")
    click.echo("=" * 80)


@sector_multiples.command("historical")
@click.option(
    "--fiscal-year",
    "-y",
    required=True,
    type=int,
    help="Fiscal year to calculate (e.g., 2023, 2024)",
)
@click.option(
    "--sectors",
    "-s",
    help="Comma-separated list of sectors to calculate (default: all)",
)
@click.option(
    "--industries",
    "-i",
    help="Comma-separated list of industries to calculate (default: all)",
)
@click.option(
    "--min-samples",
    "-n",
    default=5,
    type=int,
    help="Minimum number of symbols required per sector/industry (default: 5)",
)
@click.option(
    "--exclude-outliers/--no-exclude-outliers",
    default=True,
    help="Exclude outliers using percentile filtering (default: True)",
)
@click.option(
    "--store/--no-store",
    default=True,
    help="Store results in database (default: True)",
)
@click.option(
    "--export",
    type=click.Path(),
    help="Export results to file (JSON or CSV format inferred from extension)",
)
@click.pass_context
def historical(
    ctx,
    fiscal_year,
    sectors,
    industries,
    min_samples,
    exclude_outliers,
    store,
    export,
):
    """Calculate historical sector multiples for a specific fiscal year

    Calculates sector/industry valuation multiples using SEC FY data from
    sec_num_data/sec_tag_data tables. Uses end of FY quarter + 1 month as
    proxy for announcement date.

    \b
    Data Sources:
      - stock.symbol: Sector/industry classification
      - sec_num_data/sec_tag_data: FY financial metrics from SEC filings
      - stock_data: Historical prices (end of month proxy)

    \b
    Storage:
      - Results stored in sector_multiples_history table
      - Can export to JSON/CSV for trend analysis

    \b
    Examples:
        # Calculate for FY 2023 (Technology sector)
        investigator sector-multiples historical --fiscal-year 2023 --sectors "Technology"

        # Calculate and export to JSON
        investigator sector-multiples historical -y 2022 --export multiples_2022.json

        # Calculate with custom minimum samples
        investigator sector-multiples historical -y 2024 -n 20

        # Calculate and view trend for Technology
        investigator sector-multiples historical -y 2023 -s "Technology" --export tech_trend.csv
    """
    from investigator.domain.services.sector_multiples_history import (
        SectorMultiplesHistory,
    )

    # Parse sector/industry lists
    sector_list: Optional[List[str]] = None
    industry_list: Optional[List[str]] = None

    if sectors:
        sector_list = [s.strip() for s in sectors.split(",")]
        click.echo(f"Target sectors: {', '.join(sector_list)}")

    if industries:
        industry_list = [i.strip() for i in industries.split(",")]
        click.echo(f"Target industries: {', '.join(industry_list)}")

    # Configure outlier filtering
    percentile_exclude = (0.05, 0.95) if exclude_outliers else (0.0, 1.0)

    click.echo("\nConfiguration:")
    click.echo(f"  Fiscal Year: {fiscal_year}")
    click.echo(f"  Minimum samples: {min_samples}")
    click.echo(f"  Exclude outliers: {exclude_outliers}")
    click.echo(f"  Store in database: {store}")
    if export:
        click.echo(f"  Export to: {export}")
    click.echo()

    # Initialize history service
    history_service = SectorMultiplesHistory(
        min_samples=min_samples,
        percentile_exclude=percentile_exclude,
    )

    # Calculate historical multiples
    click.echo(f"Calculating historical multiples for FY{fiscal_year}...")
    calculated = history_service.calculate_historical_multiples(
        fiscal_year=fiscal_year,
        sectors=sector_list,
        industries=industry_list,
        use_config_overrides=True,
    )

    if not calculated:
        click.echo(f"No historical multiples calculated for FY{fiscal_year}")
        return

    # Display results
    click.echo("\n" + "=" * 80)
    click.echo(f"HISTORICAL SECTOR/INDUSTRY MULTIPLES - FY{fiscal_year}")
    click.echo("=" * 80)

    for name, multiples in sorted(calculated.items()):
        snapshot = multiples.get("snapshot_date", "N/A")
        click.echo(f"\n{name}:")
        click.echo(f"  Snapshot Date: {snapshot}")
        click.echo(f"  Sample Size: {multiples.get('sample_size', 'N/A')}")
        if multiples.get("pe"):
            click.echo(f"  P/E: {multiples['pe']}x")
        if multiples.get("ps"):
            click.echo(f"  P/S: {multiples['ps']}x")
        if multiples.get("pb"):
            click.echo(f"  P/B: {multiples['pb']}x")

    # Store in database if requested
    if store:
        click.echo("\nStoring in database...")
        # Store sectors
        sector_data = {k: v for k, v in calculated.items() if not _is_industry(k)}
        if sector_data:
            history_service.store_history(sector_data, group_type="sector")

        # Store industries
        industry_data = {k: v for k, v in calculated.items() if _is_industry(k)}
        if industry_data:
            history_service.store_history(industry_data, group_type="industry")

        click.echo("Data stored successfully in sector_multiples_history table")

    # Export to file if requested
    if export:
        click.echo(f"\nExporting to {export}...")
        fmt = "json" if export.endswith(".json") else "csv"
        success = history_service.export_to_file(
            export,
            start_year=fiscal_year,
            end_year=fiscal_year,
            format=fmt,
        )
        if success:
            click.echo(f"Exported to {export}")
        else:
            click.echo(f"Failed to export to {export}", err=True)

    click.echo("\n" + "=" * 80)
    click.echo("Historical calculation complete!")
    click.echo("=" * 80)


def _is_industry(name: str) -> bool:
    """Determine if a name is likely an industry vs sector.

    First checks if the name is a GICS sector (11 standard sectors).
    Only then checks if it matches industry-specific keywords.

    This prevents misclassifying sector names like "Consumer Discretionary"
    or "Real Estate" as industries.
    """
    from investigator.domain.services.sector_name_mapper import SectorIndustryMapper

    # First check if it's a standard GICS sector
    if SectorIndustryMapper.is_valid_sector(name):
        return False

    # Check for industry-specific keywords (substrings)
    # Note: Avoid words that appear in GICS sector names (Communication, Financial, Industrial, Services, etc.)
    industry_keywords = [
        "Software",
        "Hardware",
        "Semiconductor",
        "Equipment",
        "Banking",
        "Insurance",
        "Pharmaceutical",
        "Biotech",
        "Medical",
        "Machinery",
        "Retail",
        "Transportation",
        "Aerospace",
        "Defense",
        "Metals",
        "Mining",
        "Chemicals",
        "Oil & Gas",
        "Electric",
        "Auto",
        "Food",
        "Beverages",
        "Tobacco",
        "Apparel",
        "Luxury",
        "REIT",  # Industry-level REITs, not Real Estate sector
    ]
    name_lower = name.lower()
    return any(keyword.lower() in name_lower for keyword in industry_keywords)


@sector_multiples.command("trend")
@click.argument("group_name")
@click.option(
    "--group-type",
    "-t",
    type=click.Choice(["sector", "industry"]),
    default="sector",
    help="Type of group (default: sector)",
)
@click.option(
    "--start-year",
    "-s",
    type=int,
    help="Start fiscal year (inclusive)",
)
@click.option(
    "--end-year",
    "-e",
    type=int,
    help="End fiscal year (inclusive)",
)
@click.option(
    "--export",
    type=click.Path(),
    help="Export trend data to file",
)
@click.pass_context
def trend(ctx, group_name, group_type, start_year, end_year, export):
    """View historical trend for a sector or industry

    Displays historical valuation multiples over time to identify
    swelling (expansion) and shrinking (contraction) trends.

    \b
    Examples:
        # View Technology sector trend
        investigator sector-multiples trend Technology

        # View with year range
        investigator sector-multiples trend Technology --start-year 2020 --end-year 2024

        # View industry trend
        investigator sector-multiples trend "Semiconductors" --group-type industry

        # Export trend data
        investigator sector-multiples trend Technology --export tech_trend.json
    """
    from investigator.domain.services.sector_multiples_history import (
        SectorMultiplesHistory,
    )

    history_service = SectorMultiplesHistory()

    click.echo(f"\nFetching trend data for {group_type}: {group_name}...")

    trend_data = history_service.get_trend_data(
        group_name=group_name,
        group_type=group_type,
        start_year=start_year,
        end_year=end_year,
    )

    if not trend_data:
        click.echo(f"No trend data found for {group_type}: {group_name}")
        return

    # Display trend table
    click.echo("\n" + "=" * 80)
    click.echo(f"{group_type.upper()} TREND: {group_name}")
    click.echo("=" * 80)

    # Header
    click.echo(f"{'FY':<6} {'Snapshot':<12} {'P/E':<10} {'P/S':<10} {'P/B':<10} {'Sample':<8}")
    click.echo("-" * 80)

    for row in trend_data:
        fy = str(row["fiscal_year"])
        snapshot = row["snapshot_date"][:10] if row.get("snapshot_date") else "N/A"
        pe = f"{row['pe']:.2f}x" if row.get("pe") else "N/A"
        ps = f"{row['ps']:.2f}x" if row.get("ps") else "N/A"
        pb = f"{row['pb']:.2f}x" if row.get("pb") else "N/A"
        sample = str(row["sample_size"])

        click.echo(f"{fy:<6} {snapshot:<12} {pe:<10} {ps:<10} {pb:<10} {sample:<8}")

    # Calculate trend analysis
    if len(trend_data) > 1:
        click.echo("\nTrend Analysis:")
        first_pe = trend_data[0].get("pe")
        last_pe = trend_data[-1].get("pe")

        if first_pe and last_pe:
            if last_pe > first_pe:
                pct_change = ((last_pe - first_pe) / first_pe) * 100
                click.echo(f"  P/E Swelling: {first_pe:.2f}x → {last_pe:.2f}x (+{pct_change:.1f}%)")
            else:
                pct_change = ((first_pe - last_pe) / first_pe) * 100
                click.echo(f"  P/E Shrinking: {first_pe:.2f}x → {last_pe:.2f}x (-{pct_change:.1f}%)")

    click.echo("=" * 80)

    # Export if requested
    if export:
        click.echo(f"\nExporting to {export}...")
        # For export, we need to get the raw data and save
        # This would require adding an export method to the service
        click.echo("Export feature coming soon - use database export for now")


@sector_multiples.command("timeline")
@click.option(
    "--sectors",
    "-s",
    help="Comma-separated list of sectors to include (default: Technology)",
)
@click.option(
    "--industries",
    "-i",
    help="Comma-separated list of industries to include",
)
@click.option(
    "--years",
    "-y",
    default="5",
    help="Number of years to show (default: 5), or specific range like '2020-2024'",
)
@click.option(
    "--metric",
    "-m",
    type=click.Choice(["pe", "ps", "pb", "all"]),
    default="all",
    help="Which metric to display (default: all)",
)
@click.pass_context
def timeline(ctx, sectors, industries, years, metric):
    """Display sector/industry multiples timeline table

    Shows a matrix view with sectors/industries as rows and years as columns.
    Highlights swelling (expansion) and shrinking (contraction) trends.

    \b
    Examples:
        # Show last 5 years for Technology sector
        investigator sector-multiples timeline --sectors "Technology"

        # Show 10 years for multiple sectors
        investigator sector-multiples timeline --sectors "Technology,Healthcare,Financials" --years 10

        # Show specific year range
        investigator sector-multiples timeline --sectors "Technology" --years 2018-2024

        # Show P/E only
        investigator sector-multiples timeline --sectors "Technology" --metric pe

        # Include industries
        investigator sector-multiples timeline --sectors "Technology" --industries "Semiconductors,Software"
    """
    from sqlalchemy import text

    from investigator.infrastructure.database.db import get_db_manager

    # Parse years
    year_list = _parse_years(years)

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
        data = {}
        for row in result:
            group_type, group_name = row[0], row[1]
            year = row[2]
            pe, ps, pb, sample = row[3], row[4], row[5], row[6]

            key = (group_type, group_name)
            if key not in data:
                data[key] = {}
            data[key][year] = {"pe": pe, "ps": ps, "pb": pb, "sample": sample}

    if not data:
        click.echo("No historical data found for the specified sectors/industries and years.")
        click.echo("\nTip: Run 'investigator sector-multiples historical' first to populate the database.")
        return

    # Display timeline
    metrics_to_show = ["pe", "ps", "pb"] if metric == "all" else [metric]

    for m in metrics_to_show:
        _print_metric_timeline(data, year_list, m)


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


def _print_metric_timeline(data: dict, years: list, metric: str):
    """Print timeline table for a specific metric."""
    import sys

    metric_labels = {"pe": "P/E", "ps": "P/S", "pb": "P/B"}

    click.echo("\n" + "=" * 90)
    click.echo(f"{metric_labels[metric].upper()} MULTIPLE TIMELINE")
    click.echo("=" * 90)

    # Header
    name_width = 50
    header = f"{'SECTOR/INDUSTRY':<{name_width}} │"
    for year in years:
        header += f" {year:>6} │"
    click.echo(header)
    click.echo("─" * (name_width + 10 * len(years)))

    # Sort and display rows
    sorted_groups = sorted(data.keys(), key=lambda x: (x[0], x[1]))

    for group_type, group_name in sorted_groups:
        year_data = data[(group_type, group_name)]

        # Format group name
        prefix = "🏢 " if group_type == "sector" else "🏭 "
        name = f"{prefix}{group_name}"
        row = f"{name:<{name_width}} │"

        # Display values for each year
        for year in years:
            if year in year_data and year_data[year].get(metric):
                val = year_data[year][metric]
                row += f" {val:>6.1f}x │"
            else:
                row += f" {'—':>6} │"

        click.echo(row)

    # Show trend summary
    if len(years) >= 2:
        click.echo(f"\n{metric.upper()} TREND SUMMARY ({years[0]} → {years[-1]}):")
        click.echo("─" * 90)

        for group_type, group_name in sorted_groups:
            year_data = data[(group_type, group_name)]

            if years[0] in year_data and years[-1] in year_data:
                start_val = year_data[years[0]].get(metric)
                end_val = year_data[years[-1]].get(metric)

                if start_val and end_val:
                    change_pct = ((end_val - start_val) / start_val) * 100
                    prefix = "🏢" if group_type == "sector" else "🏭"
                    status = "SWELLING" if change_pct > 5 else "SHRINKING" if change_pct < -5 else "STABLE"

                    click.echo(
                        f"{prefix} {group_name:<40} │ {start_val:>6.1f}x → {end_val:>6.1f}x │ "
                        f"{change_pct:+6.1f}% │ {status}"
                    )

    click.echo("\nLegend: Shows historical multiples for each fiscal year")
    click.echo("        — = No data available for that year")

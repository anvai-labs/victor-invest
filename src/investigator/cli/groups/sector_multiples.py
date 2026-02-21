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

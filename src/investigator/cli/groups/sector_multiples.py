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
def refresh(
    ctx, sectors, industries, min_samples, exclude_outliers, update_config, dry_run
):
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

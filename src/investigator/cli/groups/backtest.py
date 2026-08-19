"""
RL Backtest and training commands for InvestiGator CLI
"""

import asyncio
import json
import sys
from pathlib import Path

import click

from ..utils import validate_date


@click.group()
@click.pass_context
def backtest(ctx):
    """Reinforcement Learning backtest commands.

    Examples:
        investigator backtest run --lookback 365 --parallel 10
        investigator backtest status

    `train`, `outcomes` and `analyze` used to be advertised here. Each imported a
    name that was never written -- RLTrainer, update_outcomes,
    analyze_backtest_results -- so all three exited non-zero on every invocation.
    Their underlying scripts do work, and are run directly:

        python scripts/rl_train.py --epochs 20 --horizon 90d
        python scripts/rl_outcome_updater.py
        python scripts/analyze_backtest.py

    Re-exposing them means designing the API the CLI assumed rather than
    repairing an import, so they were removed instead of left failing.
    """


@backtest.command("run")
@click.option(
    "--symbols",
    "-s",
    help="Comma-separated list of symbols (default: all in rl_decisions)",
)
@click.option("--lookback", "-l", default=365, type=int, help="Lookback period in days")
@click.option("--start-date", callback=validate_date, help="Start date (YYYY-MM-DD)")
@click.option("--end-date", callback=validate_date, help="End date (YYYY-MM-DD)")
@click.option("--parallel", "-p", default=5, type=int, help="Number of parallel workers")
@click.option(
    "--min-confidence",
    default=0.6,
    type=float,
    help="Minimum confidence threshold (0.0-1.0)",
)
@click.option("--holding-days", default=30, type=int, help="Holding period in days")
@click.option("--output", "-o", type=click.Path(), help="Output file for results")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def run_backtest(
    ctx,
    symbols,
    lookback,
    start_date,
    end_date,
    parallel,
    min_confidence,
    holding_days,
    output,
    verbose,
):
    """Run RL backtest on historical data

    Evaluates RL model decisions against historical price movements.

    Examples:
        investigator backtest run --lookback 365
        investigator backtest run --symbols AAPL,MSFT --lookback 180
        investigator backtest run --start-date 2024-01-01 --end-date 2024-12-31
    """
    click.echo("Running RL backtest...")

    # Parse symbols
    symbol_list = None
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        click.echo(f"Symbols: {', '.join(symbol_list)}")

    click.echo(f"Lookback: {lookback} days")
    click.echo(f"Parallel workers: {parallel}")
    click.echo(f"Min confidence: {min_confidence}")
    click.echo(f"Holding period: {holding_days} days")

    try:
        # Import the backtest runner
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))
        from scripts.rl_backtest import RLBacktester

        backtester = RLBacktester(
            lookback_days=lookback,
            min_confidence=min_confidence,
            holding_days=holding_days,
            parallel_workers=parallel,
        )

        if symbol_list:
            results = asyncio.run(backtester.run_symbols(symbol_list))
        else:
            results = asyncio.run(backtester.run_all())

        # Display results
        click.echo("\n" + "=" * 60)
        click.echo("BACKTEST RESULTS")
        click.echo("=" * 60)

        if isinstance(results, dict):
            summary = results.get("summary", {})
            click.echo(f"Total decisions: {summary.get('total_decisions', 0)}")
            click.echo(f"Correct: {summary.get('correct', 0)}")
            click.echo(f"Accuracy: {summary.get('accuracy', 0):.2%}")
            click.echo(f"Avg return: {summary.get('avg_return', 0):.2%}")

            if output:
                with open(output, "w") as f:
                    json.dump(results, f, indent=2, default=str)
                click.echo(f"\nResults saved to {output}")

    except ImportError as e:
        click.echo(f"Error: Could not import backtest module: {e}", err=True)
        click.echo("Run from project root directory", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Backtest failed: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@backtest.command("status")
@click.option("--detailed", "-d", is_flag=True, help="Show detailed statistics")
@click.pass_context
def status(ctx, detailed):
    """Show RL model and backtest status

    Displays current model state, recent decisions, and performance metrics.
    """
    click.echo("RL Model Status")
    click.echo("=" * 60)

    try:
        from sqlalchemy import text

        from investigator.infrastructure.database.db import get_database_engine

        engine = get_database_engine()

        with engine.connect() as conn:
            # Count decisions
            result = conn.execute(text("SELECT COUNT(*) FROM rl_decisions"))
            total_decisions = result.scalar()

            # Count outcomes
            result = conn.execute(text("SELECT COUNT(*) FROM rl_decisions WHERE actual_return IS NOT NULL"))
            with_outcomes = result.scalar()

            # Recent accuracy
            result = conn.execute(
                text("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN correct THEN 1 ELSE 0 END) as correct
                FROM rl_decisions
                WHERE actual_return IS NOT NULL
                AND decision_timestamp > NOW() - INTERVAL '30 days'
            """)
            )
            row = result.fetchone()
            recent_total = row[0] if row else 0
            recent_correct = row[1] if row else 0

        click.echo("\nDecisions:")
        click.echo(f"  Total: {total_decisions}")
        click.echo(f"  With outcomes: {with_outcomes}")
        click.echo(f"  Pending: {total_decisions - with_outcomes}")

        if recent_total > 0:
            accuracy = recent_correct / recent_total
            click.echo("\nLast 30 days:")
            click.echo(f"  Decisions: {recent_total}")
            click.echo(f"  Accuracy: {accuracy:.2%}")

        if detailed:
            click.echo("\nDetailed breakdown by action:")
            with engine.connect() as conn:
                result = conn.execute(
                    text("""
                    SELECT
                        action,
                        COUNT(*) as count,
                        AVG(confidence) as avg_confidence,
                        AVG(actual_return) as avg_return
                    FROM rl_decisions
                    WHERE actual_return IS NOT NULL
                    GROUP BY action
                """)
                )
                for row in result:
                    click.echo(f"  {row[0]}: {row[1]} decisions, conf={row[2]:.2f}, ret={row[3]:.2%}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

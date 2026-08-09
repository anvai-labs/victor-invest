# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
# SPDX-License-Identifier: Apache-2.0

"""Victor-based CLI for investment analysis.

This module provides the command-line interface for running investment
analysis using the Victor framework with StateGraph workflows.

Usage:
    python -m victor_invest.cli analyze AAPL --mode standard
    python -m victor_invest.cli analyze MSFT --mode comprehensive --output results/
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Victor framework imports (from local wheel)
try:
    from victor.framework import Agent
except ImportError as e:
    # Victor framework is required for victor-invest CLI
    # This fallback only allows module-level imports for type checking
    import sys

    click.echo(f"[red]Error: Victor framework not available: {e}[/red]", err=True)
    # Must match the `runtime` extra in pyproject.toml. It previously advertised
    # >=0.5.0,<0.6.0, which no longer satisfies this package.
    click.echo("[yellow]Install with: pip install 'victor-invest[runtime]'[/yellow]", err=True)
    sys.exit(1)

from victor_invest import __version__ as VICTOR_INVEST_VERSION
from victor_invest.framework_bootstrap import create_investment_orchestrator
from victor_invest.workflows import (
    AnalysisMode,
    AnalysisWorkflowState,
    InvestmentWorkflowProvider,
)

logger = logging.getLogger(__name__)

console = Console()


def _get_ollama_base_url() -> str:
    try:
        from investigator.config import get_config

        config = get_config()
        base_url = getattr(config.ollama, "base_url", None)
        if base_url:
            return str(base_url)
    except Exception:
        logger.debug("_get_ollama_base_url: suppressed error", exc_info=True)
    return os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"


def _display_provider_info(provider: str | None, model: str | None) -> tuple:
    """Resolve and display provider/model information from environment variables.

    Priority: CLI param > VICTOR_PROVIDER env var > fallback

    Returns:
        Tuple of (resolved_provider, resolved_model) for use in analysis
    """
    from victor_invest.framework_bootstrap import (
        resolve_model_from_env,
    )

    # Resolve provider with correct priority: CLI param > env var > fallback
    if provider:
        # CLI parameter takes highest priority
        resolved_provider = provider
        source = "CLI override"
    elif os.getenv("VICTOR_PROVIDER"):
        # Environment variable second
        resolved_provider = os.getenv("VICTOR_PROVIDER", "").strip().lower()
        source = "$VICTOR_PROVIDER"
    else:
        # Fallback to default
        resolved_provider = "ollama"
        source = "default"

    # Resolve model with correct priority: CLI param > VICTOR_MODEL > provider default
    resolved_model = resolve_model_from_env(resolved_provider, model)

    # Display which provider/model is being used
    model_display = resolved_model or "(provider default)"
    console.print(f"Provider: [cyan]{resolved_provider}[/cyan] ([dim]{source}[/dim])")

    if model:
        console.print(f"Model: [cyan]{model_display}[/cyan] ([dim]CLI override[/dim])")
    elif os.getenv("VICTOR_MODEL"):
        console.print(f"Model: [cyan]{model_display}[/cyan] ([dim]$VICTOR_MODEL[/dim])")
    else:
        console.print(f"Model: [cyan]{model_display}[/cyan] ([dim]provider default[/dim])")

    return resolved_provider, resolved_model


async def _create_workflow_executor(provider: str | None, model: str | None, timeout: float):
    from victor_contracts.workflow_runtime import WorkflowExecutor

    from victor_invest.workflows import ensure_handlers_registered

    orchestrator = await create_investment_orchestrator(
        provider=provider,  # Will be resolved from env in create_investment_orchestrator
        model=model,
        ensure_handlers=ensure_handlers_registered,
        warning_callback=lambda msg: console.print(f"[yellow]{msg}[/yellow]"),
    )

    executor = WorkflowExecutor(
        orchestrator,
        max_parallel=4,
        default_timeout=timeout,
    )

    return executor


def _convert_workflow_result_to_state(workflow_result, symbol: str, mode: str) -> AnalysisWorkflowState:
    """Convert Victor WorkflowResult to AnalysisWorkflowState for CLI compatibility.

    Args:
        workflow_result: WorkflowResult from YAML workflow execution
        symbol: Stock symbol
        mode: Analysis mode string

    Returns:
        AnalysisWorkflowState with extracted data from workflow context
    """
    ctx = workflow_result.context

    # Extract outputs from workflow context
    fundamental = ctx.get("fundamental_analysis", {})
    technical = ctx.get("technical_analysis", {})
    market_context = ctx.get("market_context", {})
    synthesis = ctx.get("synthesis", {})

    # Build recommendation from synthesis
    recommendation = {}
    if synthesis:
        recommendation = {
            "action": synthesis.get("recommendation", "HOLD"),
            "confidence": synthesis.get("confidence", "MEDIUM"),
            "price_target": synthesis.get("price_target"),
            "thesis": synthesis.get("executive_summary", ""),
        }

    # Collect any errors from failed nodes
    errors = []
    for node_id, node_result in ctx.node_results.items():
        if node_result.error:
            errors.append(f"{node_id}: {node_result.error}")

    return AnalysisWorkflowState(
        symbol=symbol.upper(),
        mode=AnalysisMode(mode),
        fundamental_analysis=fundamental,
        technical_analysis=technical,
        market_context=market_context,
        synthesis=synthesis,
        recommendation=recommendation,
        errors=errors,
    )


def _convert_to_investment_recommendation(result, symbol: str):
    """Convert AnalysisWorkflowState to InvestmentRecommendation for PDF generation.

    Args:
        result: AnalysisWorkflowState from workflow execution
        symbol: Stock symbol

    Returns:
        InvestmentRecommendation instance for PDF report generation
    """
    from investigator.domain.models import InvestmentRecommendation

    # Extract data from actual workflow structure
    synthesis = result.synthesis or {}
    recommendation_data = result.recommendation or {}
    technical = result.technical_analysis or {}
    market_context = result.market_context or {}

    # Extract composite score from synthesis (0-100 scale)
    composite_score = synthesis.get("composite_score", 50.0)
    individual_scores = synthesis.get("individual_scores", {})

    # Map to expected score format
    overall_score = composite_score
    technical_score = individual_scores.get("technical", composite_score)
    fundamental_score = individual_scores.get("fundamental", composite_score)

    # Sub-scores default to composite if not available
    income_score = fundamental_score
    cashflow_score = fundamental_score
    balance_score = fundamental_score
    growth_score = fundamental_score
    value_score = fundamental_score
    business_quality_score = fundamental_score

    # Extract recommendation details
    final_recommendation = recommendation_data.get("action", "HOLD")
    conviction_level = recommendation_data.get("confidence", "MEDIUM").upper()

    # Extract price data from technical analysis (nested in trend or support_resistance)
    trend_data = technical.get("trend", {})
    sr_data = technical.get("support_resistance", {})

    current_price = trend_data.get("current_price") or sr_data.get("current_price")

    # Extract support/resistance levels for stop loss and price target
    support_levels = sr_data.get("support_levels", {})
    resistance_levels = sr_data.get("resistance_levels", {})
    week_52 = sr_data.get("52_week", {})

    stop_loss = support_levels.get("support_1")
    price_target = resistance_levels.get("resistance_1")

    # Check if LLM synthesis is available (new format with executive_summary, key_catalysts, etc.)
    llm_executive_summary = synthesis.get("executive_summary", "")
    llm_key_catalysts = synthesis.get("key_catalysts", [])
    llm_key_risks = synthesis.get("key_risks", [])
    llm_reasoning = synthesis.get("reasoning", "")

    # Build investment thesis from available data
    trend_signal = trend_data.get("overall_signal", "neutral")
    bullish_pct = trend_data.get("signal_percentages", {}).get("bullish_pct", 0)
    bearish_pct = trend_data.get("signal_percentages", {}).get("bearish_pct", 0)

    # Use LLM executive summary if available, otherwise build from technical data
    if llm_executive_summary:
        investment_thesis = llm_executive_summary
        if llm_reasoning:
            investment_thesis += f" {llm_reasoning}"
    else:
        # Build meaningful thesis from technical data
        thesis_parts = []
        if current_price:
            thesis_parts.append(f"{symbol} is currently trading at ${current_price:.2f}")
        if week_52:
            high_52 = week_52.get("high")
            low_52 = week_52.get("low")
            if high_52 and low_52 and current_price:
                range_position = (current_price - low_52) / (high_52 - low_52) * 100
                thesis_parts.append(f"at {range_position:.0f}% of its 52-week range (${low_52:.2f} - ${high_52:.2f})")

        thesis_parts.append(
            f"The technical outlook is {trend_signal} with {bullish_pct:.0f}% bullish and {bearish_pct:.0f}% bearish signals."
        )
        thesis_parts.append(f"Composite analysis score: {composite_score:.1f}/100.")

        if final_recommendation == "BUY":
            thesis_parts.append("The analysis suggests accumulating shares at current levels.")
        elif final_recommendation == "SELL":
            thesis_parts.append("The analysis suggests reducing exposure.")
        else:
            thesis_parts.append("The analysis suggests maintaining current positions.")

        investment_thesis = " ".join(thesis_parts)

    # Extract key insights from technical signals
    signals = trend_data.get("signals", {})
    key_insights = []
    if signals:
        for indicators in signals.values():
            if isinstance(indicators, dict):
                for indicator, signal in indicators.items():
                    if signal in ["bullish", "bearish"]:
                        key_insights.append(f"{indicator.upper()}: {signal}")

    # Use LLM catalysts/risks if available, otherwise build from technical levels
    if llm_key_catalysts:
        key_catalysts = llm_key_catalysts
    else:
        key_catalysts = []
        if price_target and current_price:
            upside = ((price_target - current_price) / current_price) * 100
            key_catalysts.append(f"Near-term resistance at ${price_target:.2f} ({upside:.1f}% upside)")
        if week_52.get("high") and current_price:
            upside_52 = ((week_52["high"] - current_price) / current_price) * 100
            key_catalysts.append(f"52-week high of ${week_52['high']:.2f} ({upside_52:.1f}% from current)")

    if llm_key_risks:
        key_risks = llm_key_risks
    else:
        key_risks = []
        if stop_loss and current_price:
            downside = ((current_price - stop_loss) / current_price) * 100
            key_risks.append(f"Support at ${stop_loss:.2f} ({downside:.1f}% downside)")
        if week_52.get("low") and current_price:
            downside_52 = ((current_price - week_52["low"]) / current_price) * 100
            key_risks.append(f"52-week low of ${week_52['low']:.2f} ({downside_52:.1f}% below current)")

    # Entry/exit strategies based on levels
    key_levels = trend_data.get("key_levels", {})
    pivot = key_levels.get("pivot")
    support = key_levels.get("support")
    resistance = key_levels.get("resistance")

    if support and current_price:
        entry_strategy = f"Consider entries near support at ${support:.2f} (current: ${current_price:.2f})"
    else:
        entry_strategy = "Scale into position at current market levels"

    if resistance:
        exit_strategy = f"Consider taking profits near resistance at ${resistance:.2f}"
    else:
        exit_strategy = "Target-based exit with trailing stop loss"

    # Time horizon and position size based on score
    if composite_score >= 70:
        time_horizon = "MEDIUM-TERM"
        position_size = "MODERATE"
    elif composite_score >= 50:
        time_horizon = "LONG-TERM"
        position_size = "SMALL"
    else:
        time_horizon = "LONG-TERM"
        position_size = "SMALL"

    # Data quality - check what analyses were included
    analyses_included = synthesis.get("analyses_included", [])
    data_completeness = len(analyses_included) / 4.0  # 4 possible: fundamental, technical, market_context, valuation
    data_quality_score = min(data_completeness, 1.0)

    # Build synthesis details with all available data
    synthesis_details = {
        "synthesis": synthesis,
        "recommendation": recommendation_data,
        "technical_trend": trend_data,
        "support_resistance": sr_data,
        "market_context": market_context,
    }

    return InvestmentRecommendation(
        symbol=symbol.upper(),
        overall_score=overall_score,
        fundamental_score=fundamental_score,
        technical_score=technical_score,
        income_score=income_score,
        cashflow_score=cashflow_score,
        balance_score=balance_score,
        growth_score=growth_score,
        value_score=value_score,
        business_quality_score=business_quality_score,
        recommendation=final_recommendation,
        confidence=conviction_level,
        price_target=price_target,
        current_price=current_price,
        investment_thesis=investment_thesis,
        time_horizon=time_horizon,
        position_size=position_size,
        key_catalysts=key_catalysts[:5],
        key_risks=key_risks[:5],
        key_insights=key_insights[:10],
        entry_strategy=entry_strategy,
        exit_strategy=exit_strategy,
        stop_loss=stop_loss,
        analysis_timestamp=datetime.now(),
        data_quality_score=data_quality_score,
        analysis_thinking=synthesis.get("reasoning"),
        synthesis_details=json.dumps(synthesis_details, default=str),
        # Include technical levels for report
        support_resistance={
            "current_price": current_price,
            "support_1": support_levels.get("support_1"),
            "support_2": support_levels.get("support_2"),
            "resistance_1": resistance_levels.get("resistance_1"),
            "resistance_2": resistance_levels.get("resistance_2"),
            "52_week_high": week_52.get("high"),
            "52_week_low": week_52.get("low"),
            "pivot": pivot,
        },
    )


def validate_victor_installed():
    """Check if Victor AI framework is installed."""
    if Agent is None:
        console.print(
            "[red]Error: victor-ai is not installed.[/red]\nInstall with: pip install 'victor-ai>=0.5.0,<0.6.0'"
        )
        sys.exit(1)


@click.group()
@click.version_option(version=VICTOR_INVEST_VERSION, prog_name="victor-invest")
def cli():
    """Victor Investment Analysis CLI - Institutional-grade equity research."""


@cli.command()
@click.argument("symbol")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["quick", "standard", "comprehensive"]),
    default="standard",
    help="Analysis mode: quick (technical only), standard (technical+fundamental), comprehensive (all)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output directory for results (default: stdout)",
)
@click.option(
    "--provider",
    "-p",
    type=str,
    default=None,
    help="LLM provider (ollama, anthropic, openai). Default: $VICTOR_PROVIDER or 'ollama'",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model name. Default: $VICTOR_MODEL or provider-specific",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="Stream output as analysis progresses",
)
@click.option(
    "--report",
    is_flag=True,
    default=False,
    help="Generate PDF investment report using LLM synthesis",
)
@click.option(
    "--detail",
    "-d",
    type=click.Choice(["minimal", "standard", "compact", "verbose"]),
    default="standard",
    help="Output detail level (compact recommended for web UI integration)",
)
@click.option(
    "--beta-source",
    type=click.Choice(["market", "ff6", "fundamental", "blended", "auto"]),
    default="market",
    show_default=True,
    help="Beta source for cost-of-equity/WACC",
)
@click.option(
    "--beta-horizon-months",
    type=int,
    default=12,
    show_default=True,
    help="Lookback horizon in months for beta source selection",
)
@click.option(
    "--holding-period",
    "-h",
    type=click.Choice(["90d", "365d", "730d"], case_sensitive=False),
    default="730d",
    show_default=True,
    help="Investment holding period for RL policy selection (90d=3mo, 365d=1yr, 730d=2yr)",
)
def analyze(
    symbol: str,
    mode: str,
    output: str | None,
    provider: str,
    model: str | None,
    stream: bool,
    report: bool,
    detail: str,
    beta_source: str,
    beta_horizon_months: int,
    holding_period: str,
):
    """Run investment analysis on a stock symbol.

    Example:
        victor-invest analyze AAPL --mode comprehensive
        victor-invest analyze MSFT -m standard -o results/
    """
    validate_victor_installed()

    console.print("\n[bold blue]Victor Investment Analysis[/bold blue]")
    console.print(f"Symbol: [green]{symbol.upper()}[/green]")
    console.print(f"Mode: [yellow]{mode}[/yellow]")
    console.print(f"Detail: [cyan]{detail}[/cyan]")

    # Resolve and display provider/model from environment variables
    resolved_provider, resolved_model = _display_provider_info(provider, model)

    console.print(f"Holding Period: [cyan]{holding_period}[/cyan]")
    if report:
        console.print("Report: [magenta]PDF generation enabled[/magenta]")
    console.print()

    prev_beta_source = os.environ.get("INVESTIGATOR_BETA_SOURCE")
    prev_beta_horizon = os.environ.get("INVESTIGATOR_BETA_HORIZON_MONTHS")
    prev_holding_period = os.environ.get("INVESTIGATOR_HOLDING_PERIOD")
    os.environ["INVESTIGATOR_BETA_SOURCE"] = beta_source
    os.environ["INVESTIGATOR_BETA_HORIZON_MONTHS"] = str(max(1, int(beta_horizon_months)))
    os.environ["INVESTIGATOR_HOLDING_PERIOD"] = holding_period
    try:
        asyncio.run(
            _run_analysis(
                symbol,
                mode,
                output,
                resolved_provider,  # Use resolved provider from env
                resolved_model,  # Use resolved model from env
                stream,
                report,
                detail,
                holding_period,
            )
        )
    finally:
        if prev_beta_source is None:
            os.environ.pop("INVESTIGATOR_BETA_SOURCE", None)
        else:
            os.environ["INVESTIGATOR_BETA_SOURCE"] = prev_beta_source

        if prev_beta_horizon is None:
            os.environ.pop("INVESTIGATOR_BETA_HORIZON_MONTHS", None)
        else:
            os.environ["INVESTIGATOR_BETA_HORIZON_MONTHS"] = prev_beta_horizon

        if prev_holding_period is None:
            os.environ.pop("INVESTIGATOR_HOLDING_PERIOD", None)
        else:
            os.environ["INVESTIGATOR_HOLDING_PERIOD"] = prev_holding_period


@cli.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["quick", "standard", "comprehensive"]),
    default="standard",
    help="Analysis mode for each symbol",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default="results",
    help="Output directory for results",
)
@click.option(
    "--provider",
    "-p",
    type=str,
    default=None,
    help="LLM provider (ollama, anthropic, openai). Default: $VICTOR_PROVIDER or 'ollama'",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model name. Default: $VICTOR_MODEL or provider-specific",
)
@click.option(
    "--parallel",
    type=int,
    default=2,
    help="Max concurrent analyses",
)
@click.option(
    "--detail",
    "-d",
    type=click.Choice(["minimal", "standard", "compact", "verbose"]),
    default="standard",
    help="Output detail level (compact recommended for web UI integration)",
)
def batch(
    symbols: tuple[str, ...],
    mode: str,
    output_dir: str,
    provider: str | None,  # Changed to Optional
    model: str | None,
    parallel: int,
    detail: str,
):
    """Run batch investment analysis across multiple symbols."""
    validate_victor_installed()

    # Resolve provider/model from environment variables
    from victor_invest.framework_bootstrap import (
        resolve_model_from_env,
        resolve_provider_from_env,
    )

    resolved_provider = resolve_provider_from_env(fallback=provider or "ollama")
    resolved_model = resolve_model_from_env(resolved_provider, model)

    console.print(f"Provider: [cyan]{resolved_provider}[/cyan]")
    console.print(f"Model: [cyan]{resolved_model or '(provider default)'}[/cyan]")

    asyncio.run(
        _run_batch(
            symbols,
            mode,
            output_dir,
            resolved_provider,
            resolved_model,
            parallel,
            detail,
        )
    )


async def _run_batch(
    symbols: tuple[str, ...],
    mode: str,
    output_dir: str,
    provider: str | None,  # Changed to Optional
    model: str | None,
    parallel: int,
    detail: str = "standard",
):
    workflow_provider = InvestmentWorkflowProvider()
    workflow_name = workflow_provider.get_workflow_for_task_type(mode) or mode
    workflow = workflow_provider.get_workflow(workflow_name)
    if not workflow:
        console.print(f"[red]Unknown workflow: {workflow_name}[/red]")
        return

    executor = await _create_workflow_executor(provider, model, timeout=300.0)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {}
    failures = {}

    semaphore = asyncio.Semaphore(max(1, parallel))

    async def run_one(symbol: str):
        async with semaphore:
            try:
                result = await executor.execute(
                    workflow,
                    initial_context={"symbol": symbol},
                    timeout=300.0,
                )
                return symbol, result
            except Exception as exc:
                return symbol, exc

    tasks = [asyncio.create_task(run_one(sym.upper())) for sym in symbols]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running batch analysis...", total=len(tasks))

        for finished in asyncio.as_completed(tasks):
            symbol, outcome = await finished
            if isinstance(outcome, Exception):
                failures[symbol] = str(outcome)
                progress.advance(task)
                continue

            if not outcome.success:
                failures[symbol] = outcome.error or "Workflow failed"
                progress.advance(task)
                continue

            state = _convert_workflow_result_to_state(outcome, symbol, mode)
            results[symbol] = state

            result_file = output_path / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(result_file, "w") as f:
                # Use compact format if detail=compact
                if detail == "compact":
                    from investigator.application import (
                        OutputDetailLevel,
                        format_analysis_output,
                    )

                    agent_format = _convert_state_to_agent_format(state)
                    formatted_output = format_analysis_output(agent_format, OutputDetailLevel.COMPACT)
                    json.dump(formatted_output, f, indent=2, default=str)
                else:
                    json.dump(
                        {
                            "symbol": state.symbol,
                            "mode": state.mode.value,
                            "fundamental_analysis": state.fundamental_analysis,
                            "technical_analysis": state.technical_analysis,
                            "market_context": state.market_context,
                            "synthesis": state.synthesis,
                            "recommendation": state.recommendation,
                            "errors": state.errors,
                        },
                        f,
                        indent=2,
                        default=str,
                    )

            progress.advance(task)

    summary_file = output_path / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w") as f:
        json.dump(
            {
                "symbols": [s.upper() for s in symbols],
                "mode": mode,
                "completed": len(results),
                "failed": len(failures),
                "failures": failures,
                "timestamp": datetime.now().isoformat(),
            },
            f,
            indent=2,
        )

    console.print(f"\n[green]Completed {len(results)}/{len(symbols)} analyses[/green]")
    console.print(f"[green]Summary saved to: {summary_file}[/green]")


@cli.command()
@click.argument("target")
@click.argument("peers", nargs=-1, required=True)
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file or directory")
@click.option(
    "--provider",
    "-p",
    type=str,
    default=None,
    help="LLM provider (ollama, anthropic, openai). Default: $VICTOR_PROVIDER or 'ollama'",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model name. Default: $VICTOR_MODEL or provider-specific",
)
def compare(
    target: str,
    peers: tuple[str, ...],
    output: str | None,
    provider: str | None,  # Changed to Optional
    model: str | None,
):
    """Compare a target company against peers."""
    validate_victor_installed()

    # Resolve provider/model from environment variables
    from victor_invest.framework_bootstrap import (
        resolve_model_from_env,
        resolve_provider_from_env,
    )

    resolved_provider = resolve_provider_from_env(fallback=provider or "ollama")
    resolved_model = resolve_model_from_env(resolved_provider, model)

    console.print(f"Provider: [cyan]{resolved_provider}[/cyan]")
    console.print(f"Model: [cyan]{resolved_model or '(provider default)'}[/cyan]")

    asyncio.run(_run_compare(target, peers, output, resolved_provider, resolved_model))


@cli.command("beta-refresh")
@click.option("--symbols", type=str, help="Comma-separated list of symbols")
@click.option(
    "--universe",
    type=click.Choice(["sp500", "russell1000", "all_listed"]),
    default="sp500",
    show_default=True,
    help="Universe to process when --symbols is not specified",
)
@click.option(
    "--models",
    type=str,
    default="all",
    show_default=True,
    help="Comma-separated models: market,ff6,fundamental,blended,all",
)
@click.option(
    "--benchmark",
    type=str,
    default="SPY",
    show_default=True,
    help="Benchmark ticker for market beta",
)
@click.option(
    "--windows",
    type=str,
    default="12,24,36,60",
    show_default=True,
    help="Lookback windows in months",
)
@click.option(
    "--frequency",
    type=click.Choice(["daily", "weekly"]),
    default="daily",
    show_default=True,
    help="Return aggregation frequency for market beta",
)
@click.option(
    "--min-obs",
    type=int,
    default=126,
    show_default=True,
    help="Minimum observations per regression",
)
@click.option(
    "--winsorize-pct",
    type=float,
    default=0.01,
    show_default=True,
    help="Tail winsorization percent",
)
@click.option(
    "--max-abs-beta",
    type=float,
    default=20.0,
    show_default=True,
    help="Reject estimates with |beta| above this threshold",
)
@click.option(
    "--no-fred-rf",
    is_flag=True,
    default=False,
    help="Disable FRED DFF fallback risk-free series",
)
@click.option("--dry-run", is_flag=True, default=False, help="Compute but do not write results")
def beta_refresh(
    symbols: str | None,
    universe: str,
    models: str,
    benchmark: str,
    windows: str,
    frequency: str,
    min_obs: int,
    winsorize_pct: float,
    max_abs_beta: float,
    no_fred_rf: bool,
    dry_run: bool,
):
    """Refresh beta models (market/FF6/fundamental/blended) for symbols."""
    project_root = Path(__file__).resolve().parent.parent
    script_path = project_root / "scripts" / "scheduled" / "calculate_beta_models.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--universe",
        universe,
        "--models",
        models,
        "--benchmark",
        benchmark,
        "--windows",
        windows,
        "--frequency",
        frequency,
        "--min-obs",
        str(min_obs),
        "--winsorize-pct",
        str(winsorize_pct),
        "--max-abs-beta",
        str(max_abs_beta),
    ]
    if symbols:
        cmd += ["--symbols", symbols]
    if no_fred_rf:
        cmd.append("--no-fred-rf")
    if dry_run:
        cmd.append("--dry-run")

    console.print("[bold blue]Running beta refresh job...[/bold blue]")
    console.print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(project_root), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


async def _run_compare(
    target: str,
    peers: tuple[str, ...],
    output: str | None,
    provider: str | None,  # Changed to Optional
    model: str | None,
):
    workflow_provider = InvestmentWorkflowProvider()
    workflow = workflow_provider.get_workflow("peer_comparison")
    if not workflow:
        console.print("[red]Peer comparison workflow not found.[/red]")
        return

    executor = await _create_workflow_executor(provider, model, timeout=300.0)

    peer_list = [{"symbol": peer.upper()} for peer in peers]
    context = {
        "symbol": target.upper(),
        "analysis_mode": "comprehensive",
        "has_peers": True,
        "peer_data": {"peers": peer_list, "peer_metrics": {}},
    }

    result = await executor.execute(
        workflow,
        initial_context=context,
        timeout=300.0,
    )

    if not result.success:
        console.print(f"[red]Workflow failed:[/red] {result.error}")
        return

    peer_comparison = result.context.get("peer_comparison") if hasattr(result, "context") else {}
    console.print("\n[bold]Peer Comparison Result[/bold]")
    if peer_comparison:
        console.print(json.dumps(peer_comparison, indent=2))
    else:
        console.print("[yellow]No peer comparison output found in context.[/yellow]")

    if output:
        output_path = Path(output)
        if output_path.suffix:
            file_path = output_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_path.mkdir(parents=True, exist_ok=True)
            file_path = output_path / f"{target.upper()}_peer_comparison.json"

        with open(file_path, "w") as f:
            json.dump(
                {
                    "target": target.upper(),
                    "peers": [p.upper() for p in peers],
                    "peer_comparison": peer_comparison,
                    "context": result.context if hasattr(result, "context") else {},
                },
                f,
                indent=2,
                default=str,
            )
        console.print(f"[green]Comparison saved to: {file_path}[/green]")


async def _run_analysis(
    symbol: str,
    mode: str,
    output: str | None,
    provider: str | None,  # Changed to Optional to support env var default
    model: str | None,
    stream: bool,
    report: bool = False,
    detail: str = "standard",
    holding_period: str = "730d",
):
    """Execute the analysis workflow using InvestmentWorkflowProvider.

    Uses Victor's agentic workflow execution for proper LLM integration:
    - Compute handlers for data collection (SEC, market data, technicals)
    - Agent nodes for LLM synthesis via Victor's SubAgentOrchestrator
    - Proper provider/model abstraction through Victor framework
    - Compact format output for web UI integration when detail=compact
    """
    # Initialize workflow provider (loads YAML workflows, registers handlers)
    workflow_provider = InvestmentWorkflowProvider()

    # Map mode to workflow name
    workflow_name = workflow_provider.get_workflow_for_task_type(mode) or mode

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Analyzing {symbol.upper()}...", total=None)

        try:
            # Execute YAML workflow with full agent node support
            # Uses Victor's SubAgentOrchestrator for LLM synthesis
            # Use longer timeout for comprehensive mode (600s) vs standard/quick (300s)
            timeout = 600.0 if mode == "comprehensive" else 300.0
            workflow_result = await workflow_provider.run_agentic_workflow(
                workflow_name,
                context={
                    "symbol": symbol.upper(),
                    "holding_period": holding_period,
                    "llm_provider": provider,  # Pass provider for LLM synthesis
                    "llm_model": model,  # Pass model for LLM synthesis
                },
                provider=provider or "openai",
                model=model,
                timeout=timeout,
            )
            progress.update(task, description="Analysis complete!")

            if not workflow_result.success:
                console.print(f"[red]Workflow failed: {workflow_result.error}[/red]")
                return

            # Convert WorkflowResult to AnalysisWorkflowState for compatibility
            result = _convert_workflow_result_to_state(workflow_result, symbol, mode)

        except Exception as e:
            console.print(f"[red]Error during analysis: {e}[/red]")
            import traceback

            traceback.print_exc()
            return

    # Display results
    _display_results(result, symbol, detail)

    # Save to file if output specified
    if output:
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)
        result_file = output_path / f"{symbol.upper()}_analysis.json"

        with open(result_file, "w") as f:
            # Use compact format if detail=compact, otherwise use standard format
            if detail == "compact":
                from investigator.application import (
                    OutputDetailLevel,
                    format_analysis_output,
                )

                # Convert result to agent-orchestrator format for compact formatting
                agent_format = _convert_state_to_agent_format(result)
                formatted_output = format_analysis_output(agent_format, OutputDetailLevel.COMPACT)
                json.dump(formatted_output, f, indent=2, default=str)
            else:
                # Convert dataclass to dict for JSON serialization
                result_dict = {
                    "symbol": result.symbol,
                    "mode": result.mode.value,
                    "fundamental_analysis": result.fundamental_analysis,
                    "technical_analysis": result.technical_analysis,
                    "market_context": result.market_context,
                    "synthesis": result.synthesis,
                    "recommendation": result.recommendation,
                    "errors": result.errors,
                }
                json.dump(result_dict, f, indent=2, default=str)

        console.print(f"\n[green]Results saved to: {result_file}[/green]")

    # Generate PDF report if requested
    if report:
        try:
            console.print("\n[bold]Generating PDF report...[/bold]")

            # Convert workflow result to InvestmentRecommendation format
            recommendation = _convert_to_investment_recommendation(result, symbol)

            # Initialize synthesizer for PDF generation
            from investigator.application import InvestmentSynthesizer

            synthesizer = InvestmentSynthesizer()

            # Generate PDF report
            report_path = synthesizer.generate_report([recommendation], report_type="synthesis")

            console.print(f"[green]✅ PDF report generated: {report_path}[/green]")

        except ImportError as e:
            console.print(f"[red]❌ PDF generation requires investigator package: {e}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Failed to generate PDF report: {e}[/red]")
            import traceback

            traceback.print_exc()


def _convert_state_to_agent_format(state: AnalysisWorkflowState) -> dict[str, Any]:
    """Convert AnalysisWorkflowState to agent orchestrator format for compact output.

    This function uses the shared converter module to ensure consistency
    between victor-invest and investigator CLIs.

    Args:
        state: AnalysisWorkflowState from Victor workflow execution

    Returns:
        Dictionary in agent orchestrator format with agents, timing, metadata
    """
    from investigator.application import convert_victor_state_to_agent_format

    return convert_victor_state_to_agent_format(state)  # type: ignore[no-any-return]


def _display_results(result, symbol: str, detail: str = "standard"):
    """Display analysis results in a formatted table."""
    console.print("\n[bold]Analysis Results[/bold]\n")

    # For compact mode, show minimal output
    if detail == "compact":
        if result.recommendation:
            rec = result.recommendation
            console.print(f"[bold]{rec.get('action', 'N/A')}[/bold]")
            if "price_target" in rec:
                price = rec["price_target"]
                if isinstance(price, (int, float)):
                    console.print(f"  Price Target: ${price:.2f}")
                else:
                    console.print(f"  Price Target: ${price}")
            if "confidence" in rec:
                console.print(f"  Confidence: {rec.get('confidence', 'N/A')}")

        # Multi-tier technical summary (if available)
        if result.technical_analysis:
            tech = result.technical_analysis
            summary = tech.get("summary") if isinstance(tech, dict) else None
            if summary and isinstance(summary, dict):
                strategic = summary.get("strategic_trend")
                tactical = summary.get("tactical_signal")
                overall = summary.get("overall_bias")
                if strategic or tactical or overall:
                    console.print("\n[dim]Technical Signals:[/dim]")
                    if strategic:
                        console.print(f"  [cyan]Strategic (Weekly):[/cyan] {strategic.upper()}")
                    if tactical:
                        console.print(f"  [cyan]Tactical (Daily):[/cyan] {tactical.upper()}")
                    if overall:
                        console.print(f"  [cyan]Overall Bias:[/cyan] {overall.upper().replace('_', ' ')}")

        # Add cache status information for key data sources
        console.print("\n[dim]Cache Status:[/dim]")

        # Check if there's cache info in the state
        import time
        from pathlib import Path

        cache_root = Path("data/cache")
        symbol_upper = symbol.upper() if symbol else ""

        # Check SEC filings cache
        sec_cache = Path("data/sec_cache/submissions") / symbol_upper
        if sec_cache.exists():
            cache_files = list(sec_cache.glob("submissions.json.gz"))
            if cache_files:
                latest_cache = max(cache_files, key=lambda p: p.stat().st_mtime)
                mtime = latest_cache.stat().st_mtime
                age_hours = (time.time() - mtime) / 3600
                if age_hours < 1:
                    time_str = f"{int(age_hours * 60)} min ago"
                else:
                    time_str = f"{int(age_hours)} hours ago"
                console.print(f"  [cyan]SEC Filings:[/cyan] ✓ Cached ({time_str})")
            else:
                console.print("  [cyan]SEC Filings:[/cyan] ✗ Not cached")
        else:
            console.print("  [cyan]SEC Filings:[/cyan] ✗ Not cached")

        # Check market data cache
        if cache_root.exists():
            market_cache = cache_root / symbol.lower()
            if market_cache.exists():
                try:
                    cache_files = list(market_cache.glob("*.parquet")) + list(market_cache.glob("*.json"))
                    if cache_files:
                        latest_cache = max(cache_files, key=lambda p: p.stat().st_mtime)
                        mtime = latest_cache.stat().st_mtime
                        age_hours = (time.time() - mtime) / 3600
                        if age_hours < 1:
                            time_str = f"{int(age_hours * 60)} min ago"
                        else:
                            time_str = f"{int(age_hours)} hours ago"
                        console.print(f"  [cyan]Market Data:[/cyan] ✓ Cached ({time_str})")
                    else:
                        console.print("  [cyan]Market Data:[/cyan] ✗ Not cached")
                except Exception:
                    console.print("  [cyan]Market Data:[/cyan] ✗ Not cached")

        console.print("  Detail: [cyan]Compact format saved to file[/cyan]")
        return

    # Summary table
    table = Table(title=f"{symbol.upper()} Analysis Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Key Findings", style="white")

    # Add rows based on what was analyzed
    if result.fundamental_analysis:
        findings = result.fundamental_analysis.get("summary", "Completed")
        table.add_row("Fundamental", "✓", str(findings)[:80])

    if result.technical_analysis:
        findings = result.technical_analysis.get("summary", "Completed")
        table.add_row("Technical", "✓", str(findings)[:80])

    if result.market_context:
        findings = result.market_context.get("summary", "Completed")
        table.add_row("Market Context", "✓", str(findings)[:80])

    if result.synthesis:
        findings = result.synthesis.get("recommendation", "See details")
        table.add_row("Synthesis", "✓", str(findings)[:80])

    if result.errors:
        for error in result.errors:
            table.add_row("Error", "✗", str(error)[:80])

    console.print(table)

    # Recommendation
    if result.recommendation:
        rec = result.recommendation
        console.print("\n[bold]Recommendation[/bold]")
        console.print(f"  Action: [bold]{rec.get('action', 'N/A')}[/bold]")
        console.print(f"  Confidence: {rec.get('confidence', 'N/A')}")
        if "price_target" in rec:
            console.print(f"  Price Target: ${rec['price_target']}")
        if "thesis" in rec:
            console.print(f"  Thesis: {rec['thesis']}")


@cli.command()
def status():
    """Check system status and dependencies."""
    console.print("\n[bold]Victor Investment System Status[/bold]\n")

    table = Table()
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="white")

    # Check victor-ai framework
    try:
        import importlib.util

        if importlib.util.find_spec("victor.framework") is not None:
            table.add_row("victor-ai", "✓ Installed", "Framework available")
        else:
            table.add_row("victor-ai", "✗ Missing", "pip install 'victor-ai>=0.5.0,<0.6.0'")
    except Exception:
        table.add_row("victor-ai", "✗ Missing", "pip install 'victor-ai>=0.5.0,<0.6.0'")

    # Check ollama
    try:
        import importlib.util

        if importlib.util.find_spec("aiohttp") is not None:
            table.add_row("aiohttp", "✓ Installed", "HTTP client available")
        else:
            table.add_row("aiohttp", "✗ Missing", "pip install aiohttp")
    except Exception:
        table.add_row("aiohttp", "✗ Missing", "pip install aiohttp")

    # Check yfinance
    try:
        import importlib.util

        if importlib.util.find_spec("yfinance") is not None:
            table.add_row("yfinance", "✓ Installed", "Market data available")
        else:
            table.add_row("yfinance", "✗ Missing", "pip install yfinance")
    except Exception:
        table.add_row("yfinance", "✗ Missing", "pip install yfinance")

    # Check pandas
    try:
        import pandas

        table.add_row("pandas", "✓ Installed", f"v{pandas.__version__}")
    except ImportError:
        table.add_row("pandas", "✗ Missing", "pip install pandas")

    console.print(table)


@cli.command()
@click.option("--days", "-d", default=7, help="Days of history to show")
def metrics(days: int):
    """View system metrics and performance."""
    import glob
    from datetime import timedelta

    cutoff_date = datetime.now() - timedelta(days=days)
    metrics_files = glob.glob("metrics/metrics_*.json")

    all_metrics = []
    for filepath in sorted(metrics_files):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                timestamp = datetime.fromisoformat(data["timestamp"])
                if timestamp >= cutoff_date:
                    all_metrics.append(data)
        except Exception:
            logger.debug("metrics: suppressed error", exc_info=True)
            continue

    if not all_metrics:
        console.print("[yellow]No metrics data available.[/yellow]")
        return

    console.print(f"\n[bold]Metrics Summary (Last {days} days)[/bold]")
    console.print("=" * 50)

    latest = all_metrics[-1]

    sys_metrics = latest.get("system_metrics", {})
    if sys_metrics:
        console.print("\n[bold]System Metrics[/bold]")
        total = sys_metrics.get("total_analyses", 0)
        success = sys_metrics.get("successful_analyses", 0)
        cache_hits = sys_metrics.get("cache_hits", 0)
        cache_misses = sys_metrics.get("cache_misses", 0)
        success_rate = (success / max(total, 1)) * 100
        cache_hit_rate = (cache_hits / max(cache_hits + cache_misses, 1)) * 100
        console.print(f"  Total Analyses: {total}")
        console.print(f"  Success Rate: {success_rate:.1f}%")
        console.print(f"  Cache Hit Rate: {cache_hit_rate:.1f}%")

    agent_metrics = latest.get("agent_metrics", {})
    if agent_metrics:
        console.print("\n[bold]Agent Performance[/bold]")
        for agent, metrics in agent_metrics.items():
            executions = metrics.get("executions", 0)
            failures = metrics.get("failures", 0)
            avg_duration = metrics.get("average_duration", 0)
            success_rate = ((executions - failures) / max(executions, 1)) * 100
            console.print(f"  {agent}:")
            console.print(f"    Executions: {executions}")
            console.print(f"    Avg Duration: {avg_duration:.2f}s")
            console.print(f"    Success Rate: {success_rate:.1f}%")


@cli.command("test-system")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def test_system(verbose: bool):
    """Run system health tests."""
    console.print("Running system health tests...")
    console.print("=" * 60)

    def run_test(name, func):
        try:
            ok, detail = func()
            return name, ok, detail
        except Exception as exc:
            return name, False, str(exc)

    def check_python():
        ok = sys.version_info >= (3, 11)
        return ok, sys.version.split()[0]

    def check_ollama():
        import urllib.request

        base_url = _get_ollama_base_url()
        try:
            with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
                return resp.status == 200, f"HTTP {resp.status}"
        except Exception as exc:
            return False, str(exc)

    def check_database():
        try:
            from sqlalchemy import text

            from investigator.infrastructure.database.db import get_database_engine

            engine = get_database_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def check_cache():
        try:
            from investigator.infrastructure.cache import get_cache_manager

            get_cache_manager()
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    tests = [
        ("Python version", check_python),
        ("Ollama connection", check_ollama),
        ("Database connection", check_database),
        ("Cache system", check_cache),
    ]

    results = [run_test(name, func) for name, func in tests]

    console.print("\nTest Results:")
    console.print("-" * 60)
    passed = 0
    for name, ok, detail in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        console.print(f"{name:30s}: {status}")
        if verbose and detail:
            console.print(f"  {detail}")
        if ok:
            passed += 1

    console.print(f"\nPassed: {passed}/{len(results)}")
    if passed < len(results):
        raise SystemExit(1)


@cli.command()
@click.argument("model")
def pull(model: str):
    """Pull an Ollama model."""
    try:
        from investigator.infrastructure.llm import VictorProviderClient
    except ImportError as exc:
        console.print(f"[red]Error:[/red] LLM provider unavailable: {exc}")
        raise SystemExit(1)

    async def pull_model():
        # Pulling is Ollama-specific model management, but victor's Ollama
        # provider exposes it, so there is no reason to keep a second client.
        client = VictorProviderClient(provider_name="ollama")

        async with client:
            console.print(f"Pulling model: [cyan]{model}[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading...", total=None)
                async for status in await client.pull_model(model):
                    if status.get("status") == "success":
                        break
                progress.update(task, description="Download complete")

            console.print(f"[green]Model {model} pulled successfully[/green]")

    asyncio.run(pull_model())


@cli.command()
@click.option("--port", "-p", default=8000, help="Port to run the API server")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
def serve(port: int, host: str):
    """Start the FastAPI server for API access."""
    try:
        import uvicorn

        from victor_invest.api.app import app

        console.print("\n[bold blue]Starting Victor Investment API[/bold blue]")
        console.print(f"Server: http://{host}:{port}")
        console.print(f"Docs: http://{host}:{port}/docs\n")

        uvicorn.run(app, host=host, port=port)
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Install with: pip install uvicorn fastapi")


@cli.command("clean-cache")
@click.option("--all", "clean_all", is_flag=True, help="Clean all caches")
@click.option("--db", "clean_db", is_flag=True, help="Clean database cache only")
@click.option("--disk", "clean_disk", is_flag=True, help="Clean disk cache only")
@click.option("--symbol", help="Clean cache for specific symbol")
def clean_cache(clean_all, clean_db, clean_disk, symbol):
    """Clean analysis caches.

    Example:
        victor-invest clean-cache --symbol AAPL
        victor-invest clean-cache --all
    """
    try:
        from investigator.infrastructure.cache import get_cache_manager
        from investigator.infrastructure.cache.cache_types import CacheType
        from investigator.infrastructure.cache.file_cache_handler import (
            FileCacheStorageHandler,
        )
        from investigator.infrastructure.cache.rdbms_cache_handler import (
            RdbmsCacheStorageHandler,
        )
    except ImportError as e:
        console.print(f"[red]Error: Cache infrastructure not available: {e}[/red]")
        return

    cache_manager = get_cache_manager()

    try:
        if clean_all:
            console.print("Cleaning all caches...")
            for cache_type in CacheType:
                try:
                    cache_manager.clear(cache_type)
                except Exception:
                    logger.debug("clean_cache: suppressed error", exc_info=True)
            console.print("[green]✅ All caches cleared[/green]")

        elif clean_db:
            if symbol:
                console.print(f"Cleaning database cache for {symbol}...")
                deleted = 0
                for handlers in cache_manager.handlers.values():
                    for handler in handlers:
                        if isinstance(handler, RdbmsCacheStorageHandler):
                            try:
                                deleted += handler.delete_by_symbol(symbol)
                            except Exception as exc:
                                console.print(f"[red]❌ Error: {exc}[/red]")
                console.print(f"[green]✅ Database cache cleared for {symbol} (entries: {deleted})[/green]")
            else:
                console.print("Cleaning database cache...")
                for ct in [
                    CacheType.LLM_RESPONSE,
                    CacheType.COMPANY_FACTS,
                    CacheType.SEC_RESPONSE,
                ]:
                    try:
                        cache_manager.clear(ct, storage_type="rdbms")
                    except Exception:
                        logger.debug("clean_cache: suppressed error", exc_info=True)
                console.print("[green]✅ Database cache cleared[/green]")

        elif clean_disk:
            if symbol:
                console.print(f"Cleaning disk cache for {symbol}...")
                deleted = 0
                for handlers in cache_manager.handlers.values():
                    for handler in handlers:
                        if isinstance(handler, FileCacheStorageHandler):
                            try:
                                deleted += handler.delete_by_symbol(symbol)
                            except Exception as exc:
                                console.print(f"[red]❌ Error: {exc}[/red]")
                console.print(f"[green]✅ Disk cache cleared for {symbol} (entries: {deleted})[/green]")
            else:
                console.print("Cleaning disk cache...")
                for ct in [
                    CacheType.LLM_RESPONSE,
                    CacheType.TECHNICAL_DATA,
                    CacheType.SEC_RESPONSE,
                ]:
                    try:
                        cache_manager.clear(ct, storage_type="disk")
                    except Exception:
                        logger.debug("clean_cache: suppressed error", exc_info=True)
                console.print("[green]✅ Disk cache cleared[/green]")

        elif symbol:
            console.print(f"Cleaning all caches for {symbol}...")
            result = cache_manager.delete_by_symbol(symbol)
            total_deleted = sum(result.values()) if isinstance(result, dict) else result
            console.print(f"[green]✅ Cache cleared for {symbol} (entries: {total_deleted})[/green]")

        else:
            console.print("Cleaning default caches (LLM responses)...")
            cache_manager.clear(CacheType.LLM_RESPONSE)
            console.print("[green]✅ LLM response cache cleared[/green]")

    except Exception as e:
        console.print(f"[red]❌ Error cleaning cache: {e}[/red]")
        sys.exit(1)


@cli.command("cache-sizes")
def cache_sizes():
    """Show cache directory sizes.

    Example:
        victor-invest cache-sizes
    """
    console.print("\n[bold]Cache Directory Sizes[/bold]\n")

    cache_dirs = {
        "SEC Cache": "data/sec_cache",
        "LLM Cache": "data/llm_cache",
        "Technical Cache": "data/technical_cache",
        "Vector DB": "data/vector_db",
    }

    table = Table()
    table.add_column("Cache Type", style="cyan")
    table.add_column("Size (MB)", justify="right", style="green")
    table.add_column("Files", justify="right", style="yellow")

    total_size = 0
    for name, path in cache_dirs.items():
        cache_path = Path(path)
        if cache_path.exists():
            files = list(cache_path.rglob("*"))
            file_count = sum(1 for f in files if f.is_file())
            size = sum(f.stat().st_size for f in files if f.is_file())
            total_size += size
            size_mb = size / (1024 * 1024)
            table.add_row(name, f"{size_mb:.2f}", str(file_count))
        else:
            table.add_row(name, "0.00", "0")

    table.add_row("─" * 20, "─" * 10, "─" * 10)
    table.add_row("[bold]Total[/bold]", f"[bold]{total_size / (1024 * 1024):.2f}[/bold]", "")

    console.print(table)


@cli.command("inspect-cache")
@click.option("--symbol", help="Inspect cache for specific symbol")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def inspect_cache(symbol, verbose):
    """Inspect cache contents for a symbol.

    Example:
        victor-invest inspect-cache --symbol AAPL
        victor-invest inspect-cache --symbol AAPL --verbose
    """
    try:
        from investigator.infrastructure.cache import get_cache_manager
        from investigator.infrastructure.cache.cache_types import CacheType
    except ImportError as e:
        console.print(f"[red]Error: Cache infrastructure not available: {e}[/red]")
        return

    cache_manager = get_cache_manager()

    console.print("\n[bold]Cache Inspection Report[/bold]\n")

    if symbol:
        console.print(f"Symbol: [cyan]{symbol.upper()}[/cyan]\n")

        table = Table()
        table.add_column("Cache Type", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Size", justify="right", style="yellow")

        for cache_type in CacheType:
            try:
                key = {"symbol": symbol.upper()}
                data = cache_manager.get(cache_type, key)
                if data:
                    size_str = f"{len(str(data))} bytes" if verbose else "✓"
                    table.add_row(cache_type.value, "[green]Cached[/green]", size_str)
                else:
                    table.add_row(cache_type.value, "[dim]Not cached[/dim]", "-")
            except Exception:
                table.add_row(cache_type.value, "[dim]Error[/dim]", "-")

        console.print(table)
    else:
        console.print("Cache Statistics:")
        stats = cache_manager.get_stats() if hasattr(cache_manager, "get_stats") else {}
        if stats:
            for key, value in stats.items():
                console.print(f"  {key}: {value}")
        else:
            console.print("  No statistics available (specify --symbol for symbol-specific info)")


@cli.command("from-batch")
@click.argument("jsonl_path", type=click.Path(exists=True))
@click.option(
    "--symbols",
    "-s",
    help="Comma-separated symbols to process (default: all successful)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="reports/batch",
    help="Output directory for reports",
)
@click.option(
    "--min-upside",
    type=float,
    default=None,
    help="Only process symbols with upside >= this percentage",
)
@click.option(
    "--tier",
    type=click.Choice(["BUY", "HOLD", "SELL"]),
    default=None,
    help="Only process symbols with this tier classification",
)
def from_batch(
    jsonl_path: str,
    symbols: str | None,
    output: str,
    min_upside: float | None,
    tier: str | None,
):
    """Generate professional reports from batch analysis results.

    Reads cached batch results and generates PDF reports without re-running analysis.

    Example:
        victor-invest from-batch batch_results/batch_analysis_results.jsonl
        victor-invest from-batch results.jsonl --symbols AAPL,MSFT,GOOGL
        victor-invest from-batch results.jsonl --min-upside 10 --tier BUY
    """
    import json
    from pathlib import Path

    console.print("\n[bold blue]Generate Reports from Batch Results[/bold blue]")
    console.print(f"Source: [green]{jsonl_path}[/green]")

    # Load batch results
    results = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    console.print(f"Loaded: {len(results)} results")

    # Filter results
    filtered = []
    symbol_filter = {s.upper() for s in symbols.split(",")} if symbols else None

    for r in results:
        # Must be successful
        if not r.get("success", False):
            continue

        # Must have required data for report
        if not r.get("fair_value") or not r.get("current_price"):
            continue

        # Apply symbol filter
        if symbol_filter and r.get("symbol") not in symbol_filter:
            continue

        # Apply upside filter
        if min_upside is not None:
            upside = r.get("upside_pct", 0) or 0
            if upside < min_upside:
                continue

        # Apply tier filter
        if tier and r.get("tier", "").upper() != tier:
            continue

        filtered.append(r)

    console.print(f"Filtered: {len(filtered)} symbols for report generation")

    if not filtered:
        console.print("[yellow]No symbols match the criteria. No reports generated.[/yellow]")
        return

    # Generate reports
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        from investigator.infrastructure.reporting.professional_report import (
            ProfessionalReportGenerator,
        )

        generator = ProfessionalReportGenerator(output_dir=output_path)

        success_count = 0
        for r in filtered:
            symbol = r.get("symbol", "UNKNOWN")
            console.print(f"  Generating report for [cyan]{symbol}[/cyan]...")

            try:
                # Convert batch result to report data format
                report_data = _convert_batch_result_to_report_data(r)
                report_path = generator.generate_report(report_data)

                if report_path:
                    success_count += 1
                    console.print(f"    [green]✓ {report_path}[/green]")
                else:
                    console.print("    [yellow]⚠ No report generated[/yellow]")

            except Exception as e:
                console.print(f"    [red]✗ Error: {e}[/red]")

        console.print(f"\n[bold green]Reports generated: {success_count}/{len(filtered)}[/bold green]")
        console.print(f"Output directory: {output_path}")

    except ImportError as e:
        console.print(f"[red]Error: Report generator not available: {e}[/red]")
        console.print("Ensure investigator package is installed.")


def _convert_batch_result_to_report_data(batch_result: dict) -> dict:
    """Convert batch analysis result to report-ready data format.

    Args:
        batch_result: SymbolResult from batch JSONL

    Returns:
        Dict compatible with ProfessionalReportGenerator
    """
    symbol = batch_result.get("symbol", "UNKNOWN")
    fair_value = batch_result.get("fair_value")
    current_price = batch_result.get("current_price")
    upside_pct = batch_result.get("upside_pct", 0)
    tier = batch_result.get("tier", "HOLD")
    model_fair_values = batch_result.get("model_fair_values", {})
    model_weights = batch_result.get("model_weights", {})
    sector = batch_result.get("sector", "")
    market_cap = batch_result.get("market_cap")

    # Map tier to recommendation
    rec_map = {
        "BUY": ("BUY", "HIGH"),
        "STRONG_BUY": ("STRONG BUY", "HIGH"),
        "HOLD": ("HOLD", "MEDIUM"),
        "SELL": ("SELL", "LOW"),
        "STRONG_SELL": ("STRONG SELL", "LOW"),
    }
    recommendation, confidence = rec_map.get(tier.upper(), ("HOLD", "MEDIUM"))

    # Calculate scores from upside
    if upside_pct is not None and upside_pct > 0:
        overall_score = min(50 + upside_pct * 2, 95)  # Scale upside to score
    else:
        overall_score = max(50 + (upside_pct or 0) * 2, 10)

    fundamental_score = overall_score + 5 if upside_pct and upside_pct > 10 else overall_score
    technical_score = overall_score - 5 if upside_pct and upside_pct < 0 else overall_score

    # Calculate stop loss (10% below current)
    stop_loss = current_price * 0.90 if current_price else None

    # Build valuation models section
    valuation_models = {}
    for model, fv in (model_fair_values or {}).items():
        if fv and current_price:
            model_upside = ((fv / current_price) - 1) * 100
            weight = (model_weights or {}).get(model, 0.33)
            valuation_models[model] = {
                "fair_value_per_share": fv,
                "upside_downside_pct": model_upside,
                "confidence": weight * 100,
            }

    # Build thesis from batch data
    thesis_parts = []
    thesis_parts.append(f"{symbol} in {sector}." if sector else f"{symbol}.")
    if upside_pct is not None:
        if upside_pct > 15:
            thesis_parts.append(
                f"Analysis indicates significant undervaluation with {upside_pct:.1f}% upside to fair value."
            )
        elif upside_pct > 5:
            thesis_parts.append(f"Moderate upside of {upside_pct:.1f}% to fair value estimate.")
        elif upside_pct > 0:
            thesis_parts.append(f"Trading near fair value with {upside_pct:.1f}% potential upside.")
        else:
            thesis_parts.append(f"Currently trading at {abs(upside_pct):.1f}% premium to fair value.")
    if market_cap:
        thesis_parts.append(f"Market cap: ${market_cap / 1e9:.1f}B.")

    # Key catalysts/risks based on tier
    if tier.upper() in ["BUY", "STRONG_BUY"]:
        key_catalysts = [
            f"Fair value estimate of ${fair_value:.2f} suggests upside potential",
            "Valuation models show favorable risk/reward",
        ]
        key_risks = [
            "Market volatility could impact near-term price action",
            "Model assumptions may not reflect current market conditions",
        ]
    else:
        key_catalysts = ["Potential rerating if fundamentals improve"]
        key_risks = [
            "Limited upside at current valuation levels",
            "Market conditions may pressure valuations further",
        ]

    return {
        "symbol": symbol,
        "recommendation": recommendation,
        "confidence": confidence,
        "overall_score": overall_score,
        "fundamental_score": min(fundamental_score, 100),
        "technical_score": max(min(technical_score, 100), 10),
        "current_price": current_price,
        "target_price": fair_value,
        "stop_loss": stop_loss,
        "investment_thesis": " ".join(thesis_parts),
        "key_catalysts": key_catalysts,
        "key_risks": key_risks,
        "time_horizon": "MEDIUM-TERM",
        "position_size": "MODERATE" if tier.upper() in ["BUY", "STRONG_BUY"] else "SMALL",
        "valuation_models": valuation_models,
        "score_breakdown": {
            "value": min(50 + (upside_pct or 0) * 2, 100),
            "growth": 60,  # Default without detailed data
            "business_quality": 70,
            "data_quality": 80,
        },
        # Market regime placeholder
        "market_regime": {"regime": "Normal"},
        # Peer data placeholder
        "peer_comparison": {"peers": [], "metrics": {}},
    }


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()

"""Context and trend helpers extracted from the legacy synthesizer monolith."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

UNKNOWN_SECTOR_CONTEXT = "Unknown Sector - Requires Research"
DEFAULT_MARKET_ENVIRONMENT_CONTEXT = (
    "Mixed signals with elevated volatility, Fed policy uncertainty, and sector rotation dynamics"
)


def extract_quarterly_trends(quarterly_analyses: List[Dict[str, Any]]) -> str:
    """Summarize the available quarterly analyses at a high level."""
    if not quarterly_analyses:
        return "No quarterly data available for trend analysis"

    trends = [f"Quarterly Analysis Summary ({len(quarterly_analyses)} quarters):"]
    for index, analysis in enumerate(quarterly_analyses[:8]):
        period = analysis.get("period", f"Q{index + 1}")
        form_type = analysis.get("form_type", "Unknown")
        trends.append(f"- {period} ({form_type}): Key financial metrics and performance indicators")

    if len(quarterly_analyses) > 8:
        trends.append(f"... and {len(quarterly_analyses) - 8} additional quarters")

    return "\n".join(trends)


def extract_financial_metrics_from_quarter(quarter_data: Any, period: str) -> Optional[Dict[str, Any]]:
    """Extract a normalized set of financial metrics from one quarter payload."""
    metrics: Dict[str, Any] = {"period": period}

    if not isinstance(quarter_data, dict):
        return None

    for key in ["revenue", "total_revenue", "revenues", "sales"]:
        if key in quarter_data:
            metrics["revenue"] = quarter_data[key]
            break

    for key in ["net_income", "net_profit", "earnings", "profit"]:
        if key in quarter_data:
            metrics["net_income"] = quarter_data[key]
            break

    for key in ["gross_margin", "operating_margin", "profit_margin"]:
        if key in quarter_data:
            metrics[key] = quarter_data[key]

    for key in ["eps", "operating_cash_flow", "free_cash_flow", "total_assets", "total_debt"]:
        if key in quarter_data:
            metrics[key] = quarter_data[key]

    return metrics if len(metrics) > 1 else None


def create_financial_trends_analysis(
    metrics_by_quarter: List[Dict[str, Any]],
    *,
    logger: Optional[Any] = None,
) -> str:
    """Create a formatted financial-trends summary from quarterly metrics."""
    try:
        if not metrics_by_quarter:
            return "[NO QUARTERLY METRICS AVAILABLE FOR TREND ANALYSIS]"

        trends = [f"📊 FINANCIAL TRENDS ANALYSIS ({len(metrics_by_quarter)} quarters):"]
        sorted_metrics = sorted(metrics_by_quarter, key=lambda item: item.get("period", ""))

        revenues = [item.get("revenue", 0) for item in sorted_metrics if item.get("revenue")]
        if len(revenues) >= 2:
            revenue_growth = ((revenues[-1] - revenues[0]) / revenues[0] * 100) if revenues[0] > 0 else 0
            trends.append(f"📈 Revenue Trend: {revenue_growth:+.1f}% over {len(revenues)} quarters")

        margins = [item.get("profit_margin", 0) for item in sorted_metrics if item.get("profit_margin")]
        if len(margins) >= 2:
            margin_change = margins[-1] - margins[0]
            trends.append(f"💰 Margin Trend: {margin_change:+.1f}pp change in profit margin")

        trends.append("\n📋 Quarterly Progression:")
        for index, metrics in enumerate(sorted_metrics[-4:]):
            period = metrics.get("period", f"Q{index + 1}")
            revenue = metrics.get("revenue", 0)
            margin = metrics.get("profit_margin", 0)
            trends.append(f"  {period}: Revenue ${revenue:,.0f}M, Margin {margin:.1f}%")

        return "\n".join(trends)
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Error creating trends analysis: {exc}")
        return "[ERROR CREATING TRENDS ANALYSIS]"


def get_sector_context(symbol: str, data_dir: Path, *, logger: Optional[Any] = None) -> str:
    """Load sector and industry context from the configured mapping file."""
    try:
        sector_mapping_file = Path(data_dir) / "sector_mapping.json"
        if sector_mapping_file.exists():
            sector_data = json.loads(sector_mapping_file.read_text(encoding="utf-8"))
            mappings = sector_data.get("sector_mappings", {})
            default = sector_data.get("default_mapping", {})

            if symbol in mappings:
                mapping = mappings[symbol]
                return f"{mapping['sector']} - {mapping['industry']}"
            return f"{default['sector']} - {default['industry']}"

        if logger is not None:
            logger.warning(f"Sector mapping file not found: {sector_mapping_file}")
        return UNKNOWN_SECTOR_CONTEXT
    except Exception as exc:
        if logger is not None:
            logger.error(f"Error loading sector mapping: {exc}")
        return UNKNOWN_SECTOR_CONTEXT


def get_market_environment_context() -> str:
    """Return the current static market-environment summary."""
    return DEFAULT_MARKET_ENVIRONMENT_CONTEXT

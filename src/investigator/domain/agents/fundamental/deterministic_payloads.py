"""Shared payload builders for deterministic fundamental analyses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def build_deterministic_response(agent_id: str, label: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic analysis response compatible with LLM-shaped contracts."""
    return {
        "response": payload,
        "prompt": "",
        "model_info": {
            "model": f"deterministic-{label}",
            "temperature": 0.0,
            "top_p": 0.0,
            "format": "json",
        },
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "agent_id": agent_id,
            "analysis_type": label,
            "cache_type": "deterministic_analysis",
        },
    }


def build_deterministic_cache_record(
    *,
    symbol: str,
    agent_id: str,
    label: str,
    payload: Dict[str, Any],
    period: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build cache key/value pair for persisted deterministic analyses."""
    cache_key: Dict[str, Any] = {"symbol": symbol, "llm_type": label}
    if period:
        cache_key["period"] = period

    wrapped = {
        "response": payload,
        "metadata": {
            "cached_at": datetime.now().isoformat(),
            "agent_id": agent_id,
            "analysis_type": label,
            "period": period,
        },
    }

    return cache_key, wrapped


def coerce_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion with caller-provided default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_deterministic_forecast_payload(
    financials: Dict[str, Any],
    growth_analysis: Dict[str, Any],
    *,
    current_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a deterministic 3-year forecast payload when LLM synthesis is bypassed."""
    year = current_year or datetime.now().year
    revenue = max(coerce_float(financials.get("revenue"), 0.0), 0.0)
    net_income = max(coerce_float(financials.get("net_income"), 0.0), 0.0)
    free_cash_flow = max(
        coerce_float(financials.get("free_cash_flow", financials.get("operating_cash_flow", 0.0)), 0.0),
        0.0,
    )
    shares = coerce_float(financials.get("shares_outstanding"), 0.0)
    eps = net_income / shares if shares > 0 else coerce_float(financials.get("eps"), 0.0)

    raw_growth = growth_analysis.get("revenue_growth_rate", growth_analysis.get("revenue_growth", 0.05))
    growth = coerce_float(raw_growth, 0.05)
    if abs(growth) > 1:
        growth = growth / 100.0
    growth = min(max(growth, -0.20), 0.30)

    rev_forecast: List[Dict[str, Any]] = []
    eps_forecast: List[Dict[str, Any]] = []
    fcf_forecast: List[Dict[str, Any]] = []

    revenue_run = revenue
    eps_run = eps
    fcf_run = free_cash_flow

    for year_offset in range(1, 4):
        fade = max(0.5, 1.0 - (year_offset - 1) * 0.15)
        annual_growth = growth * fade
        revenue_run *= 1 + annual_growth
        eps_run *= 1 + annual_growth
        fcf_run *= 1 + annual_growth

        forecast_year = year + year_offset
        rev_forecast.append(
            {
                "year": forecast_year,
                "revenue": round(revenue_run, 2),
                "growth_rate": round(annual_growth, 4),
            }
        )
        eps_forecast.append({"year": forecast_year, "eps": round(eps_run, 4)})
        fcf_forecast.append({"year": forecast_year, "fcf": round(fcf_run, 2)})

    bull_growth = min(growth + 0.03, 0.40)
    bear_growth = max(growth - 0.03, -0.25)
    revenue_terminal = rev_forecast[-1]["revenue"] if rev_forecast else revenue
    eps_terminal = eps_forecast[-1]["eps"] if eps_forecast else eps

    return {
        "revenue_forecast": rev_forecast,
        "earnings_forecast": eps_forecast,
        "free_cash_flow_forecast": fcf_forecast,
        "margin_projections": {
            "gross_margin": round(coerce_float(financials.get("gross_margin"), 0.35), 4),
            "operating_margin": round(coerce_float(financials.get("operating_margin"), 0.15), 4),
            "net_margin": round(coerce_float(financials.get("net_margin"), 0.10), 4),
        },
        "key_assumptions": [
            "Deterministic forecast mode enabled",
            "Growth rate derived from existing growth analysis inputs",
            "Linear fade applied to avoid over-extrapolation",
        ],
        "scenario_analysis": {
            "base_case": {
                "revenue_growth": round(growth, 4),
                "eps": round(eps_terminal, 4),
            },
            "bull_case": {
                "revenue_growth": round(bull_growth, 4),
                "eps": round(eps_terminal * (1 + max(bull_growth - growth, 0)), 4),
            },
            "bear_case": {
                "revenue_growth": round(bear_growth, 4),
                "eps": round(eps_terminal * (1 - max(growth - bear_growth, 0)), 4),
            },
        },
        "confidence_intervals": {
            "revenue_2028": [round(revenue_terminal * 0.9, 2), round(revenue_terminal * 1.1, 2)],
            "eps_2028": [round(eps_terminal * 0.9, 4), round(eps_terminal * 1.1, 4)],
        },
        "fallback_used": True,
    }


def build_deterministic_fundamental_report_payload(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic fallback fundamental report payload."""
    valuation_data = analysis_data.get("valuation", {})
    if isinstance(valuation_data, dict) and isinstance(valuation_data.get("response"), dict):
        valuation_data = valuation_data.get("response", {})
    elif not isinstance(valuation_data, dict):
        valuation_data = {}

    ratios = analysis_data.get("ratios", {}) or {}
    company_profile = analysis_data.get("company_data", {}) or {}
    current_price = coerce_float(ratios.get("current_price"), 0.0)
    fair_value = coerce_float(
        valuation_data.get("fair_value_estimate")
        or valuation_data.get("fair_value")
        or company_profile.get("current_price")
        or current_price,
        0.0,
    )
    upside_pct = ((fair_value - current_price) / current_price) * 100 if current_price > 0 else 0.0

    if upside_pct >= 15:
        recommendation = "buy"
    elif upside_pct <= -15:
        recommendation = "sell"
    else:
        recommendation = "hold"

    return {
        "executive_summary": ("Deterministic fallback used because LLM fundamental synthesis returned empty output."),
        "investment_thesis": ("Focus on valuation discipline and execution quality while monitoring cyclical risk."),
        "financial_analysis_summary": (
            "Core valuation and ratio inputs are available; narrative synthesis used fallback mode."
        ),
        "valuation_assessment": valuation_data.get("valuation_stance", "uncertain"),
        "growth_prospects": "Moderate growth with scenario uncertainty.",
        "risk_analysis": valuation_data.get(
            "valuation_risks",
            "Model divergence and macro sensitivity remain key risks.",
        ),
        "competitive_position": "Refer to deterministic competitive analysis output.",
        "investment_grade": valuation_data.get("investment_grade", "B"),
        "price_target": round(fair_value, 2),
        "investment_recommendation": recommendation,
        "recommendation": recommendation,
        "key_catalysts": [
            "Execution versus guidance",
            "Margin stability",
            "Cash flow resilience",
        ],
        "key_risks": [
            "Valuation compression risk",
            "Demand cyclicality",
            "Macro regime shift",
        ],
        "fallback_used": True,
    }


def calculate_quality_score(
    health: Dict[str, Any],
    growth: Dict[str, Any],
    profitability: Dict[str, Any],
    competitive: Dict[str, Any],
) -> float:
    """Calculate the weighted overall company quality score from deterministic sub-analyses."""
    scores = []
    weights = []

    if "overall_health_score" in health:
        scores.append(health["overall_health_score"])
        weights.append(0.30)
    if "growth_score" in growth:
        scores.append(growth["growth_score"])
        weights.append(0.25)
    if "profitability_score" in profitability:
        scores.append(profitability["profitability_score"])
        weights.append(0.25)
    if "strategic_positioning_score" in competitive:
        scores.append(competitive["strategic_positioning_score"])
        weights.append(0.20)

    if scores and weights:
        return float(sum(score * weight for score, weight in zip(scores, weights)) / sum(weights))

    return 50.0

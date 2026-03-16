"""Structured SEC/LLM synthesis helpers extracted from the legacy synthesizer monolith."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

PeerCountProvider = Callable[[str], Optional[int]]


def calculate_quarterly_trends(quarterly_data: List[Dict[str, Any]], *, logger: Optional[Any] = None) -> Dict[str, Any]:
    """Calculate QoQ, YoY, and chart-oriented trends for quarterly financial data."""
    if len(quarterly_data) < 2:
        return {}

    try:
        trends: Dict[str, Any] = {
            "revenue_trend": [],
            "net_income_trend": [],
            "operating_cash_flow_trend": [],
            "margin_trends": [],
            "qoq_growth": {},
            "yoy_growth": {},
        }

        latest = quarterly_data[-1]
        previous = quarterly_data[-2]
        for metric in ["revenue", "net_income", "operating_cash_flow"]:
            latest_val = latest.get(metric, 0)
            prev_val = previous.get(metric, 0)
            if latest_val and prev_val and prev_val != 0:
                growth = ((latest_val - prev_val) / abs(prev_val)) * 100
                trends["qoq_growth"][metric] = round(growth, 2)

        if len(quarterly_data) >= 5:
            for index in range(len(quarterly_data) - 4):
                current = quarterly_data[index + 4]
                year_ago = quarterly_data[index]
                for metric in ["revenue", "net_income", "operating_cash_flow"]:
                    current_val = current.get(metric, 0)
                    year_ago_val = year_ago.get(metric, 0)
                    if current_val and year_ago_val and year_ago_val != 0:
                        growth = ((current_val - year_ago_val) / abs(year_ago_val)) * 100
                        trends["yoy_growth"].setdefault(metric, []).append(
                            {"period": current["period_label"], "growth": round(growth, 2)}
                        )

        for quarter in quarterly_data:
            period = quarter["period_label"]
            if quarter.get("revenue"):
                trends["revenue_trend"].append({"period": period, "value": quarter["revenue"] / 1_000_000})
            if quarter.get("net_income"):
                trends["net_income_trend"].append({"period": period, "value": quarter["net_income"] / 1_000_000})
            if quarter.get("operating_cash_flow"):
                trends["operating_cash_flow_trend"].append(
                    {"period": period, "value": quarter["operating_cash_flow"] / 1_000_000}
                )

            if quarter.get("revenue") and quarter.get("revenue") > 0:
                net_margin = (quarter.get("net_income", 0) / quarter["revenue"]) * 100
                op_margin = (quarter.get("operating_income", 0) / quarter["revenue"]) * 100
                trends["margin_trends"].append(
                    {
                        "period": period,
                        "net_margin": round(net_margin, 2),
                        "operating_margin": round(op_margin, 2),
                    }
                )

        return trends
    except Exception as exc:
        if logger is not None:
            logger.error(f"Error calculating quarterly trends: {exc}")
        return {}


def _normalize_sec_payload(content: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "financial_health_score": content.get("financial_health_score", 0.0),
        "business_quality_score": content.get("business_quality_score", 0.0),
        "growth_prospects_score": content.get("growth_prospects_score", 0.0),
        "data_quality_score": (
            content.get("data_quality_score", {}).get("score", 0.0)
            if isinstance(content.get("data_quality_score"), dict)
            else content.get("data_quality_score", 0.0)
        ),
        "overall_score": content.get("overall_score", 0.0),
        "investment_thesis": content.get("investment_thesis", ""),
        "key_insights": content.get("key_insights", []),
        "key_risks": content.get("key_risks", []),
        "trend_analysis": content.get("trend_analysis", {}),
        "confidence_level": content.get("confidence_level", "MEDIUM"),
    }


def extract_sec_comprehensive_data(llm_responses: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured SEC comprehensive data from dict or JSON-string responses."""
    fundamental_responses = llm_responses.get("fundamental", {})
    if "comprehensive" not in fundamental_responses:
        return {}

    comp_resp = fundamental_responses["comprehensive"]
    content = comp_resp.get("content", comp_resp)
    if isinstance(content, dict):
        return _normalize_sec_payload(content)
    if isinstance(content, str):
        try:
            return _normalize_sec_payload(json.loads(content))
        except Exception:
            return {}
    return {}


def create_recommendation_from_llm_data(
    symbol: str,
    sec_data: Dict[str, Any],
    tech_indicators: Dict[str, Any],
    current_price: float,
    overall_score: float,
) -> Dict[str, Any]:
    """Build a recommendation payload directly from SEC comprehensive data and technical indicators."""
    _ = current_price

    business_quality = sec_data.get("business_quality_score", 0.0)
    fundamental_score = sec_data.get("financial_health_score", 0.0)
    growth_score = sec_data.get("growth_prospects_score", 0.0)
    data_quality = sec_data.get("data_quality_score", 0.0)

    tech_trend = tech_indicators.get("trend_direction", "NEUTRAL")
    tech_recommendation = tech_indicators.get("recommendation", "HOLD")
    support_levels = tech_indicators.get("support_levels", [])
    resistance_levels = tech_indicators.get("resistance_levels", [])
    tech_risks = tech_indicators.get("risk_factors", [])

    if fundamental_score >= 8.0 and business_quality >= 8.0:
        if tech_trend in ["BULLISH", "NEUTRAL"]:
            final_recommendation = "BUY"
            confidence = "HIGH" if tech_trend == "BULLISH" else "MEDIUM"
        else:
            final_recommendation = "HOLD"
            confidence = "MEDIUM"
    elif fundamental_score >= 6.0 and business_quality >= 6.0:
        if tech_trend == "BULLISH":
            final_recommendation = "BUY"
            confidence = "MEDIUM"
        elif tech_trend == "BEARISH":
            final_recommendation = "HOLD"
            confidence = "LOW"
        else:
            final_recommendation = "HOLD"
            confidence = "MEDIUM"
    else:
        if tech_trend == "BEARISH":
            final_recommendation = "SELL"
            confidence = "MEDIUM"
        else:
            final_recommendation = "HOLD"
            confidence = "LOW"

    if data_quality < 5.0:
        confidence = "LOW"
    elif data_quality >= 8.0 and confidence == "MEDIUM":
        confidence = "HIGH"

    sec_thesis = sec_data.get("investment_thesis", "")
    if sec_thesis and tech_indicators:
        investment_thesis = (
            f"{sec_thesis} Technical analysis shows {tech_trend.lower()} trend "
            f"with {tech_recommendation.lower()} recommendation."
        )
    elif sec_thesis:
        investment_thesis = sec_thesis
    else:
        investment_thesis = (
            f"Based on fundamental score of {fundamental_score:.1f} and business quality of "
            f"{business_quality:.1f}, with {tech_trend.lower()} technical trend."
        )

    sec_insights = sec_data.get("key_insights", [])
    sec_risks = sec_data.get("key_risks", [])
    tech_insights = []
    if support_levels:
        tech_insights.append(f"Key support levels at ${', $'.join([f'{value:.2f}' for value in support_levels[:3]])}")
    if resistance_levels:
        tech_insights.append(
            f"Key resistance levels at ${', $'.join([f'{value:.2f}' for value in resistance_levels[:3]])}"
        )

    all_insights = sec_insights + tech_insights
    all_risks = sec_risks + tech_risks

    if final_recommendation == "BUY":
        if confidence == "HIGH" and business_quality >= 9.0:
            position_size = "LARGE"
        elif confidence in ["HIGH", "MEDIUM"]:
            position_size = "MODERATE"
        else:
            position_size = "SMALL"
    elif final_recommendation == "SELL":
        position_size = "AVOID"
    else:
        position_size = "SMALL"

    if business_quality >= 8.0 and fundamental_score >= 8.0:
        time_horizon = "LONG-TERM"
    elif business_quality >= 6.0:
        time_horizon = "MEDIUM-TERM"
    else:
        time_horizon = "SHORT-TERM"

    price_target = max(resistance_levels) if resistance_levels and final_recommendation == "BUY" else None
    stop_loss = min(support_levels) * 0.95 if support_levels and final_recommendation in ["BUY", "HOLD"] else None

    return {
        "overall_score": overall_score,
        "fundamental_score": fundamental_score,
        "technical_score": tech_indicators.get("technical_score", 0.0),
        "business_quality_score": business_quality,
        "growth_score": growth_score,
        "data_quality_score": data_quality,
        "investment_recommendation": {
            "recommendation": final_recommendation,
            "confidence": confidence,
        },
        "investment_thesis": investment_thesis,
        "position_size": position_size,
        "time_horizon": time_horizon,
        "price_target": price_target,
        "stop_loss": stop_loss,
        "key_catalysts": all_insights[:5],
        "downside_risks": all_risks[:5],
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "trend_direction": tech_trend,
        "momentum_signals": tech_indicators.get("momentum_signals", []),
        "confidence_level": confidence,
        "source": "direct_llm_extraction",
        "symbol": symbol,
    }


def calculate_data_quality_detailed(
    symbol: str,
    llm_responses: Dict[str, Any],
    quarterly_metrics: List[Any],
    latest_data: Dict[str, Any],
    *,
    get_peer_count: PeerCountProvider,
    logger: Optional[Any] = None,
) -> Dict[str, Any]:
    """Calculate a detailed data-quality report with peer availability supplied via callback."""
    scores = []
    details = {}

    expected_llm_types = ["fundamental", "technical", "quarterly_summary"]
    available_llm = sum(1 for llm_type in expected_llm_types if llm_type in llm_responses)
    llm_completeness = (available_llm / len(expected_llm_types)) * 100
    scores.append(llm_completeness)
    details["llm_completeness"] = llm_completeness

    quarters_available = len(quarterly_metrics) if quarterly_metrics else 0
    quarterly_completeness = min((quarters_available / 8) * 100, 100) if quarters_available else 0
    scores.append(quarterly_completeness)
    details["quarterly_completeness"] = quarterly_completeness

    market_freshness = 100 if latest_data else 0
    scores.append(market_freshness)
    details["market_freshness"] = market_freshness

    try:
        peer_count = get_peer_count(symbol)
        peer_availability = min((peer_count / 10) * 100, 100) if peer_count else 0
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Could not get peer data availability: {exc}")
        peer_availability = 0
    scores.append(peer_availability)
    details["peer_availability"] = peer_availability

    overall_score = sum(scores) / len(scores)
    if overall_score >= 90:
        grade = "A"
    elif overall_score >= 80:
        grade = "B"
    elif overall_score >= 70:
        grade = "C"
    elif overall_score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "overall_score": round(overall_score, 1),
        "grade": grade,
        "components": details,
        "timestamp": datetime.now(timezone.utc),
    }

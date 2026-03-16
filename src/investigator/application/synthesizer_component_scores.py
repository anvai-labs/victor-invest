"""Component score extraction helpers extracted from the legacy synthesizer monolith."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict

from investigator.application.synthesizer_recommendation import calculate_consistency_bonus


FundamentalScoreCalculator = Callable[[Dict[str, Any]], float]
QuarterlyBusinessQualityAnalyzer = Callable[[str, str], float]


def _normalize_response_content(content: Any) -> str:
    """Normalize mixed response payloads to searchable text."""
    if isinstance(content, dict):
        return json.dumps(content)
    if isinstance(content, str):
        return content
    return str(content)


def extract_income_score(
    llm_responses: Dict[str, Any],
    ai_recommendation: Dict[str, Any],
    *,
    calculate_fundamental_score: FundamentalScoreCalculator,
) -> float:
    """Extract the income-statement score from AI output or profitability metrics."""
    if "income_statement_score" in ai_recommendation:
        return float(ai_recommendation["income_statement_score"])

    comp_analysis = llm_responses.get("fundamental", {}).get("comprehensive", {})
    content = comp_analysis.get("content", comp_analysis) if isinstance(comp_analysis, dict) else {}
    if isinstance(content, dict):
        income_analysis = content.get("income_statement_analysis", {})
        if income_analysis:
            profitability = income_analysis.get("profitability_analysis", {})
            margins = [
                profitability.get("gross_margin", 0),
                profitability.get("operating_margin", 0),
                profitability.get("net_margin", 0),
            ]
            positive_margins = [margin for margin in margins if margin > 0]
            avg_margin = sum(positive_margins) / len(positive_margins) if positive_margins else 0
            if avg_margin > 0:
                return min(10.0, max(1.0, avg_margin * 100 / 3))

    base_fundamental = calculate_fundamental_score(llm_responses)
    return base_fundamental * 0.9 if base_fundamental > 0 else 0.0


def extract_cashflow_score(
    llm_responses: Dict[str, Any],
    ai_recommendation: Dict[str, Any],
    *,
    calculate_fundamental_score: FundamentalScoreCalculator,
) -> float:
    """Extract the cash-flow score by applying keyword adjustments to the base fundamental score."""
    del ai_recommendation

    base_fundamental = calculate_fundamental_score(llm_responses)
    cashflow_keywords = [
        "cash flow",
        "cash",
        "liquidity",
        "fcf",
        "working capital",
        "operating cash",
    ]
    adjustments = []

    for resp in llm_responses.get("fundamental", {}).values():
        content = _normalize_response_content(resp.get("content", "")).lower()
        cashflow_mentions = sum(1 for keyword in cashflow_keywords if keyword in content)
        if cashflow_mentions > 3:
            adjustments.append(0.5)
        elif cashflow_mentions > 0:
            adjustments.append(0.0)
        else:
            adjustments.append(-0.5)

    adjustment = sum(adjustments) / len(adjustments) if adjustments else 0
    return max(0.0, min(10.0, base_fundamental + adjustment)) if base_fundamental > 0 else 0.0


def extract_balance_score(
    llm_responses: Dict[str, Any],
    ai_recommendation: Dict[str, Any],
    *,
    calculate_fundamental_score: FundamentalScoreCalculator,
) -> float:
    """Extract the balance-sheet score by applying keyword adjustments to the base fundamental score."""
    del ai_recommendation

    base_fundamental = calculate_fundamental_score(llm_responses)
    balance_keywords = [
        "asset",
        "liability",
        "equity",
        "debt",
        "balance sheet",
        "leverage",
        "solvency",
    ]
    adjustments = []

    for resp in llm_responses.get("fundamental", {}).values():
        content = _normalize_response_content(resp.get("content", "")).lower()
        balance_mentions = sum(1 for keyword in balance_keywords if keyword in content)
        if balance_mentions > 3:
            adjustments.append(0.5)
        elif balance_mentions > 0:
            adjustments.append(0.0)
        else:
            adjustments.append(-0.5)

    adjustment = sum(adjustments) / len(adjustments) if adjustments else 0
    return max(0.0, min(10.0, base_fundamental + adjustment)) if base_fundamental > 0 else 0.0


def extract_growth_score(
    llm_responses: Dict[str, Any],
    ai_recommendation: Dict[str, Any],
    *,
    calculate_fundamental_score: FundamentalScoreCalculator,
) -> float:
    """Extract the growth score from structured fields or keyword-driven adjustments."""
    if "comprehensive" in llm_responses.get("fundamental", {}):
        comp_content = llm_responses["fundamental"]["comprehensive"].get("content", {})
        if isinstance(comp_content, dict) and "growth_prospects_score" in comp_content:
            return float(comp_content["growth_prospects_score"])

    if "fundamental_assessment" in ai_recommendation:
        fund_assess = ai_recommendation["fundamental_assessment"]
        if "growth_prospects" in fund_assess:
            growth_data = fund_assess["growth_prospects"]
            if isinstance(growth_data, dict) and "score" in growth_data:
                return float(growth_data["score"])

    base_fundamental = calculate_fundamental_score(llm_responses)
    growth_keywords = [
        "growth",
        "expansion",
        "increase",
        "momentum",
        "acceleration",
        "scaling",
    ]
    adjustments = []

    for resp in llm_responses.get("fundamental", {}).values():
        content = _normalize_response_content(resp.get("content", "")).lower()
        growth_mentions = sum(1 for keyword in growth_keywords if keyword in content)
        if growth_mentions > 5:
            adjustments.append(1.0)
        elif growth_mentions > 2:
            adjustments.append(0.5)
        else:
            adjustments.append(0.0)

    adjustment = sum(adjustments) / len(adjustments) if adjustments else 0
    return max(0.0, min(10.0, base_fundamental + adjustment)) if base_fundamental > 0 else 0.0


def extract_value_score(
    llm_responses: Dict[str, Any],
    ai_recommendation: Dict[str, Any],
    *,
    calculate_fundamental_score: FundamentalScoreCalculator,
) -> float:
    """Extract the valuation score from structured fields or text sentiment around value."""
    if "fundamental_assessment" in ai_recommendation:
        fund_assess = ai_recommendation["fundamental_assessment"]
        if "valuation" in fund_assess:
            valuation = fund_assess["valuation"]
            if isinstance(valuation, dict) and "score" in valuation:
                return float(valuation["score"])

    base_fundamental = calculate_fundamental_score(llm_responses)
    value_keywords = [
        "undervalued",
        "discount",
        "cheap",
        "value",
        "pe ratio",
        "price to book",
        "dividend yield",
    ]
    negative_value_keywords = ["overvalued", "expensive", "premium", "overpriced"]
    adjustments = []

    for resp in llm_responses.get("fundamental", {}).values():
        content = _normalize_response_content(resp.get("content", "")).lower()
        value_mentions = sum(1 for keyword in value_keywords if keyword in content)
        negative_mentions = sum(1 for keyword in negative_value_keywords if keyword in content)
        net_value_signal = value_mentions - negative_mentions

        if net_value_signal > 3:
            adjustments.append(1.0)
        elif net_value_signal > 0:
            adjustments.append(0.5)
        elif net_value_signal < -3:
            adjustments.append(-1.0)
        else:
            adjustments.append(0.0)

    adjustment = sum(adjustments) / len(adjustments) if adjustments else 0
    return max(0.0, min(10.0, base_fundamental + adjustment)) if base_fundamental > 0 else 0.0


def extract_business_quality_score(
    llm_responses: Dict[str, Any],
    ai_recommendation: Dict[str, Any],
    *,
    analyze_quarterly_business_quality: QuarterlyBusinessQualityAnalyzer,
) -> float:
    """Extract the business-quality score from comprehensive or quarterly analysis payloads."""
    del ai_recommendation

    comprehensive_analysis = llm_responses.get("fundamental", {}).get("comprehensive", {})
    if isinstance(comprehensive_analysis, dict):
        if "business_quality_score" in comprehensive_analysis:
            score_data = comprehensive_analysis["business_quality_score"]
            if isinstance(score_data, dict):
                return float(score_data.get("score", 5.0))
            return float(score_data)

        content = comprehensive_analysis.get("content", {})
        if isinstance(content, dict) and "business_quality_score" in content:
            score_data = content["business_quality_score"]
            if isinstance(score_data, dict):
                return float(score_data.get("score", 5.0))
            return float(score_data)

    if isinstance(comprehensive_analysis, str):
        try:
            parsed = json.loads(comprehensive_analysis)
            if "business_quality_score" in parsed:
                return float(parsed["business_quality_score"])
        except Exception:
            pass

    quarterly_analyses = llm_responses.get("fundamental", {})
    quality_indicators = []
    for period_key, analysis in quarterly_analyses.items():
        if period_key == "comprehensive":
            continue

        content = _normalize_response_content(analysis.get("content", ""))
        quality_score = analyze_quarterly_business_quality(content, period_key)
        if quality_score > 0:
            quality_indicators.append(quality_score)

    if quality_indicators:
        avg_quality = sum(quality_indicators) / len(quality_indicators)
        consistency_bonus = calculate_consistency_bonus(quality_indicators)
        return min(10.0, max(1.0, avg_quality + consistency_bonus))

    return 0.0


def analyze_quarterly_business_quality(content: str, period: str) -> float:
    """Analyze individual quarterly content for business-quality indicators."""
    del period

    content_lower = content.lower()
    revenue_quality_keywords = [
        "recurring revenue",
        "subscription",
        "diversified revenue",
        "stable revenue",
        "revenue growth",
        "market share",
        "competitive advantage",
        "moat",
    ]
    operational_keywords = [
        "margin expansion",
        "efficiency",
        "productivity",
        "automation",
        "cost control",
        "operating leverage",
        "scalability",
    ]
    innovation_keywords = [
        "innovation",
        "r&d",
        "research and development",
        "patent",
        "technology",
        "differentiation",
        "competitive position",
        "market leadership",
    ]
    management_keywords = [
        "capital allocation",
        "strategic initiative",
        "execution",
        "guidance",
        "shareholder value",
        "dividend",
        "buyback",
        "investment",
    ]
    categories = [
        (revenue_quality_keywords, 1.5),
        (operational_keywords, 1.2),
        (innovation_keywords, 1.0),
        (management_keywords, 0.8),
    ]

    total_weight = 0.0
    weighted_score = 0.0
    for keywords, weight in categories:
        category_score = sum(1 for keyword in keywords if keyword in content_lower)
        normalized_score = min(10.0, (category_score / len(keywords)) * 10)
        weighted_score += normalized_score * weight
        total_weight += weight

    quality_score = weighted_score / total_weight if total_weight > 0 else 5.0
    return max(1.0, min(10.0, quality_score))

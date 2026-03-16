"""Recommendation and risk helpers extracted from InvestmentSynthesizer."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def calculate_consistency_bonus(quality_indicators: List[float]) -> float:
    """Calculate consistency bonus for quarterly quality indicators."""
    if len(quality_indicators) < 2:
        return 0.0

    mean_quality = sum(quality_indicators) / len(quality_indicators)
    variance = sum((x - mean_quality) ** 2 for x in quality_indicators) / len(quality_indicators)
    std_dev = variance**0.5

    max_bonus = 1.0
    return max(0.0, max_bonus - (std_dev / 2.0))


def determine_final_recommendation(
    overall_score: float, ai_recommendation: Dict[str, Any], data_quality: float
) -> Dict[str, str]:
    """Determine final recommendation with score and data-quality adjustments."""
    if "investment_recommendation" in ai_recommendation:
        inv_rec = ai_recommendation["investment_recommendation"]
        base_recommendation = inv_rec.get("recommendation", "HOLD")
        confidence = inv_rec.get("confidence_level", "MEDIUM")
    else:
        rec_data = ai_recommendation.get("recommendation", "HOLD")
        if isinstance(rec_data, dict):
            base_recommendation = rec_data.get("rating", "HOLD")
            confidence = rec_data.get("confidence", "LOW")
        else:
            base_recommendation = rec_data if isinstance(rec_data, str) else "HOLD"
            confidence = ai_recommendation.get("confidence", "MEDIUM")

    if data_quality < 0.5:
        confidence = "LOW"
        if base_recommendation in ["STRONG BUY", "STRONG SELL"]:
            base_recommendation = base_recommendation.replace("STRONG ", "")

    if overall_score >= 8.0 and base_recommendation not in ["BUY", "STRONG BUY"]:
        base_recommendation = "BUY"
    elif overall_score <= 3.0 and base_recommendation not in ["SELL", "STRONG SELL"]:
        base_recommendation = "SELL"
    elif 4.0 <= overall_score <= 6.0 and base_recommendation in [
        "STRONG BUY",
        "STRONG SELL",
    ]:
        base_recommendation = "HOLD"

    return {"recommendation": base_recommendation, "confidence": confidence}


def calculate_price_target(symbol: str, ai_recommendation: Dict[str, Any], current_price: float, logger: Any) -> float:
    """Calculate 12-month target price from structured fields or score mapping."""
    if "investment_recommendation" in ai_recommendation:
        target_data = ai_recommendation["investment_recommendation"].get("target_price", {})
        if target_data.get("12_month_target"):
            return target_data["12_month_target"]

    ai_targets = ai_recommendation.get("price_targets", {})
    if ai_targets.get("12_month"):
        return ai_targets["12_month"]

    if current_price <= 0:
        logger.warning(f"No current price available for {symbol}, using placeholder for target calculation")
        current_price = 100

    overall_score = 5.0
    if "composite_scores" in ai_recommendation:
        overall_score = ai_recommendation["composite_scores"].get("overall_score", 5.0)
    elif "overall_score" in ai_recommendation:
        overall_score = ai_recommendation.get("overall_score", 5.0)

    if overall_score >= 8.0:
        expected_return = 0.15
    elif overall_score >= 6.5:
        expected_return = 0.10
    elif overall_score >= 5.0:
        expected_return = 0.05
    else:
        expected_return = -0.05

    price_target = round(current_price * (1 + expected_return), 2)
    logger.info(
        f"Calculated price target for {symbol}: ${price_target:.2f} "
        f"(current: ${current_price:.2f}, score: {overall_score:.1f})"
    )
    return price_target


def calculate_stop_loss(current_price: float, recommendation: Dict[str, Any], overall_score: float) -> float:
    """Calculate stop loss level from recommendation and conviction."""
    if not current_price or current_price <= 0:
        return 0

    rec_type = recommendation.get("recommendation", "HOLD")
    if "STRONG BUY" in rec_type:
        stop_loss_pct = 0.12
    elif "BUY" in rec_type:
        stop_loss_pct = 0.10
    elif "HOLD" in rec_type:
        stop_loss_pct = 0.08
    else:
        stop_loss_pct = 0.05

    if overall_score < 4.0:
        stop_loss_pct *= 0.5

    return round(current_price * (1 - stop_loss_pct), 2)


def extract_position_size(ai_recommendation: Dict[str, Any]) -> str:
    """Extract normalized position size bucket."""
    if "investment_recommendation" in ai_recommendation:
        pos_sizing = ai_recommendation["investment_recommendation"].get("position_sizing", {})
        weight = pos_sizing.get("recommended_weight", 0.0)
        if weight >= 0.05:
            return "LARGE"
        if weight >= 0.03:
            return "MODERATE"
        if weight > 0:
            return "SMALL"
    return ai_recommendation.get("position_size", "MODERATE")


def extract_catalysts(ai_recommendation: Dict[str, Any]) -> List[str]:
    """Extract up to three catalysts from structured recommendation payloads."""
    catalysts: List[str] = []

    if "key_catalysts" in ai_recommendation:
        cat_data = ai_recommendation["key_catalysts"]
        if isinstance(cat_data, list):
            for cat in cat_data[:3]:
                if isinstance(cat, dict):
                    catalysts.append(cat.get("catalyst", ""))
                elif isinstance(cat, str):
                    catalysts.append(cat)

    return catalysts or ai_recommendation.get("catalysts", [])


def create_fallback_recommendation(
    raw_response: Any,
    symbol: str,
    overall_score: float,
    logger: Any,
) -> Dict[str, Any]:
    """Create a conservative fallback recommendation when response parsing fails."""
    try:
        response_text = str(raw_response) if raw_response else ""

        recommendation = "HOLD"
        rec_patterns = [
            r'recommendation["\']?\s*:\s*["\']?(STRONG_BUY|STRONG_SELL|BUY|SELL|HOLD)["\']?',
            r"FINAL\s+RECOMMENDATION[:\s]*\*?\*?\s*\[?([A-Z\s]+)\]?",
            r'"recommendation":\s*"([^"]+)"',
        ]
        for pattern in rec_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                rec_text = match.group(1).strip().upper()
                if any(valid in rec_text for valid in ["BUY", "SELL", "HOLD"]):
                    recommendation = rec_text
                    break

        confidence = "LOW"
        conf_patterns = [
            r'confidence["\']?\s*:\s*["\']?(HIGH|MEDIUM|LOW)["\']?',
            r'"confidence_level":\s*"([^"]+)"',
        ]
        for pattern in conf_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                confidence = match.group(1).strip().upper()
                break

        thesis = f"Analysis completed for {symbol} with computed overall score of {overall_score:.1f}/10."
        thesis_patterns = [
            r'investment_thesis["\']?\s*:\s*["\']([^"\']+)["\']',
            r'thesis["\']?\s*:\s*["\']([^"\']+)["\']',
            r"INVESTMENT\s+THESIS[:\s]*([^{}\[\]]+?)(?=\*\*|##|\n\n|$)",
        ]
        for pattern in thesis_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
            if match:
                extracted_thesis = match.group(1).strip()
                if len(extracted_thesis) > 20:
                    thesis = extracted_thesis[:500]
                    break

        fallback_recommendation = {
            "overall_score": overall_score,
            "fundamental_score": overall_score,
            "technical_score": overall_score,
            "investment_recommendation": {
                "recommendation": recommendation,
                "confidence_level": confidence,
            },
            "executive_summary": {"investment_thesis": thesis},
            "key_catalysts": [
                f"Technical and fundamental analysis for {symbol}",
                "Market position assessment",
                "Financial performance review",
            ],
            "key_risks": [
                "JSON parsing failure indicates potential data quality issues",
                "LLM response formatting problems",
                "Analysis may be incomplete due to parsing errors",
            ],
            "position_size": "SMALL",
            "time_horizon": "MEDIUM-TERM",
            "entry_strategy": "Conservative approach recommended due to analysis parsing issues",
            "exit_strategy": "Monitor for improved data quality and re-analyze",
            "details": (
                "Fallback recommendation created due to JSON parsing failure. "
                f"Raw response length: {len(response_text)} characters."
            ),
            "_fallback_created": True,
            "_parsing_error": True,
        }

        logger.info(f"Created fallback recommendation for {symbol}: {recommendation} (confidence: {confidence})")
        return fallback_recommendation
    except Exception as exc:
        logger.error(f"Error creating fallback recommendation: {exc}")
        return {
            "overall_score": 5.0,
            "fundamental_score": 5.0,
            "technical_score": 5.0,
            "investment_recommendation": {
                "recommendation": "HOLD",
                "confidence_level": "LOW",
            },
            "executive_summary": {
                "investment_thesis": f"Unable to complete analysis for {symbol} due to processing errors."
            },
            "key_catalysts": ["Analysis pending"],
            "key_risks": ["Analysis incomplete", "Data processing errors"],
            "position_size": "AVOID",
            "time_horizon": "UNKNOWN",
            "entry_strategy": "Wait for successful analysis",
            "exit_strategy": "Not applicable",
            "details": "Emergency fallback due to complete parsing failure",
            "_fallback_created": True,
            "_parsing_error": True,
            "_emergency_fallback": True,
        }

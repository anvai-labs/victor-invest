"""Technical parsing helpers extracted from the legacy synthesizer monolith."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_momentum_signals(content: dict[str, Any]) -> list[str]:
    """Extract momentum and volume signals from structured technical content."""
    signals: list[str] = []

    momentum = content.get("momentum_analysis", {})
    if momentum:
        rsi = momentum.get("rsi_14", 0)
        rsi_assessment = momentum.get("rsi_assessment", "")
        if rsi and rsi_assessment:
            signals.append(f"RSI ({rsi:.1f}) indicates {str(rsi_assessment).lower()} conditions")

        macd = momentum.get("macd", {})
        if macd.get("signal"):
            signals.append(f"MACD shows {str(macd['signal']).lower()} momentum")

        stochastic = momentum.get("stochastic", {})
        if stochastic.get("signal"):
            signals.append(f"Stochastic indicates {str(stochastic['signal']).lower()} conditions")

    volume = content.get("volume_analysis", {})
    if volume.get("volume_trend"):
        signals.append(f"Volume trend is {str(volume['volume_trend']).lower()}")

    return signals


def extract_legacy_technical_indicators(content: str) -> dict[str, Any]:
    """Extract technical indicators from a legacy text response."""
    indicators: dict[str, Any] = {}

    support_match = re.search(r"support_levels[:\s]*\[([^\]]+)\]", content, re.IGNORECASE)
    resistance_match = re.search(r"resistance_levels[:\s]*\[([^\]]+)\]", content, re.IGNORECASE)
    trend_match = re.search(r'trend_direction[:\s]*["\']?([A-Z]+)["\']?', content, re.IGNORECASE)

    if support_match:
        try:
            indicators["support_levels"] = [float(x.strip()) for x in support_match.group(1).split(",")]
        except Exception:
            indicators["support_levels"] = []

    if resistance_match:
        try:
            indicators["resistance_levels"] = [float(x.strip()) for x in resistance_match.group(1).split(",")]
        except Exception:
            indicators["resistance_levels"] = []

    if trend_match:
        indicators["trend_direction"] = trend_match.group(1).upper()

    return indicators


def _parse_json_from_response(content: str) -> dict[str, Any]:
    """Extract the first JSON object from a potentially mixed text response."""
    json_content = content
    if "=== AI RESPONSE ===" in content:
        json_start = content.find("=== AI RESPONSE ===") + len("=== AI RESPONSE ===")
        json_content = content[json_start:].strip()

    json_start = json_content.find("{")
    if json_start >= 0:
        json_part = json_content[json_start:]
        brace_count = 0
        json_end = 0
        for i, char in enumerate(json_part):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break

        if json_end > 0:
            return json.loads(json_part[:json_end])
        return json.loads(json_part)

    return json.loads(json_content)


def extract_technical_indicators(llm_responses: dict[str, Any], *, logger: Any | None = None) -> dict[str, Any]:
    """Extract normalized technical indicators from structured or legacy LLM responses."""
    technical_response = llm_responses.get("technical")
    if not technical_response:
        return {}

    content = technical_response.get("content", "")
    if logger is not None:
        logger.debug(f"Technical response content type: {type(content)}")
        if isinstance(content, str) and content:
            logger.debug(f"Technical content preview: {content[:100]}...")

    indicators: dict[str, Any] = {}
    if isinstance(content, dict):
        indicators = {
            "technical_score": content.get("technical_score", {}).get("score", 0.0),
            "trend_direction": content.get("trend_analysis", {}).get("primary_trend", "NEUTRAL"),
            "trend_strength": content.get("trend_analysis", {}).get("trend_strength", "WEAK"),
            "support_levels": [
                content.get("support_resistance", {}).get("immediate_support", 0.0),
                content.get("support_resistance", {}).get("major_support", 0.0),
            ],
            "resistance_levels": [
                content.get("support_resistance", {}).get("immediate_resistance", 0.0),
                content.get("support_resistance", {}).get("major_resistance", 0.0),
            ],
            "fibonacci_levels": content.get("support_resistance", {}).get("fibonacci_levels", {}),
            "momentum_signals": extract_momentum_signals(content),
            "risk_factors": content.get("risk_factors", []),
            "key_insights": content.get("key_insights", []),
            "catalysts": content.get("catalysts", []),
            "time_horizon": content.get("recommendation", {}).get("time_horizon", "MEDIUM"),
            "recommendation": content.get("recommendation", {}).get("technical_rating", "HOLD"),
            "confidence": content.get("recommendation", {}).get("confidence", "MEDIUM"),
            "position_sizing": content.get("recommendation", {}).get("position_sizing", "MODERATE"),
            "entry_strategy": content.get("entry_exit_strategy", {}),
            "volume_analysis": content.get("volume_analysis", {}),
            "volatility_analysis": content.get("volatility_analysis", {}),
            "sector_relative_strength": content.get("sector_relative_strength", {}),
        }
    elif isinstance(content, str):
        try:
            parsed = _parse_json_from_response(content)
            indicators = {
                "technical_score": parsed.get("technical_score", 0.0),
                "trend_direction": parsed.get("trend_direction", "NEUTRAL"),
                "trend_strength": parsed.get("trend_strength", "WEAK"),
                "support_levels": parsed.get("support_levels", []),
                "resistance_levels": parsed.get("resistance_levels", []),
                "fibonacci_levels": parsed.get("support_resistance", {}).get("fibonacci_levels", {}),
                "momentum_signals": parsed.get("momentum_signals", []),
                "risk_factors": parsed.get("risk_factors", []),
                "key_insights": parsed.get("key_insights", []),
                "catalysts": parsed.get("catalysts", []),
                "time_horizon": parsed.get("time_horizon", "MEDIUM"),
                "recommendation": parsed.get("recommendation", "HOLD"),
                "confidence": parsed.get("confidence", "MEDIUM"),
                "position_sizing": "MODERATE",
                "entry_strategy": {},
                "volume_analysis": {},
                "volatility_analysis": {},
                "sector_relative_strength": {},
            }
        except json.JSONDecodeError:
            indicators = extract_legacy_technical_indicators(content)

    indicators["support_levels"] = [level for level in indicators.get("support_levels", []) if level > 0]
    indicators["resistance_levels"] = [level for level in indicators.get("resistance_levels", []) if level > 0]
    return indicators


def extract_technical_signals_from_text(technical_text: str, *, logger: Any | None = None) -> dict[str, Any]:
    """Extract a few canonical technical signals from narrative text."""
    try:
        signals: dict[str, Any] = {}

        rsi_match = re.search(r"RSI[^:]*:\s*([\d.]+)", technical_text, re.IGNORECASE)
        if rsi_match:
            signals["rsi"] = float(rsi_match.group(1))

        macd_match = re.search(r"MACD[^:]*:\s*([-\d.]+)", technical_text, re.IGNORECASE)
        if macd_match:
            signals["macd"] = float(macd_match.group(1))

        trend_match = re.search(r"trend[^:]*:\s*([A-Za-z]+)", technical_text, re.IGNORECASE)
        if trend_match:
            signals["trend"] = trend_match.group(1).upper()

        support_match = re.search(r"support[^:]*:\s*\$?([\d.]+)", technical_text, re.IGNORECASE)
        if support_match:
            signals["support"] = float(support_match.group(1))

        resistance_match = re.search(r"resistance[^:]*:\s*\$?([\d.]+)", technical_text, re.IGNORECASE)
        if resistance_match:
            signals["resistance"] = float(resistance_match.group(1))

        return signals
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Error extracting technical signals: {exc}")
        return {}


def calculate_ma_position(current_price: float, ma_price: float) -> str:
    """Calculate moving-average position relative to current price."""
    if not current_price or not ma_price:
        return "N/A"
    if current_price > ma_price * 1.02:
        return "Strong Above"
    if current_price > ma_price:
        return "Above"
    if current_price < ma_price * 0.98:
        return "Strong Below"
    return "Below"


def check_ma_cross(sma_50: float, sma_200: float) -> str:
    """Classify the 50/200-day moving-average cross state."""
    if not sma_50 or not sma_200:
        return "N/A"
    if sma_50 > sma_200 * 1.01:
        return "Golden Cross"
    if sma_50 < sma_200 * 0.99:
        return "Death Cross"
    return "Neutral"


def assess_trend_strength(tech_data: dict[str, Any]) -> str:
    """Assess overall trend strength from RSI and recent price change."""
    try:
        rsi = tech_data.get("rsi", 50)
        price_change_1m = tech_data.get("price_change_1m", 0)

        if rsi > 60 and price_change_1m > 5:
            return "Strong Bullish"
        if rsi > 50 and price_change_1m > 0:
            return "Bullish"
        if rsi < 40 and price_change_1m < -5:
            return "Strong Bearish"
        if rsi < 50 and price_change_1m < 0:
            return "Bearish"
        return "Neutral"
    except Exception:
        return "N/A"


def calculate_bb_position(tech_data: dict[str, Any]) -> str:
    """Calculate the current Bollinger-band position."""
    try:
        current_price = tech_data.get("current_price", 0)
        bb_upper = tech_data.get("bollinger_upper", 0)
        bb_lower = tech_data.get("bollinger_lower", 0)

        if not all([current_price, bb_upper, bb_lower]):
            return "N/A"

        bb_range = bb_upper - bb_lower
        position = (current_price - bb_lower) / bb_range
        if position > 0.8:
            return "Upper Band"
        if position > 0.6:
            return "Above Middle"
        if position > 0.4:
            return "Middle Range"
        if position > 0.2:
            return "Below Middle"
        return "Lower Band"
    except Exception:
        return "N/A"


def assess_volume_trend(tech_data: dict[str, Any]) -> str:
    """Classify the relative volume level."""
    try:
        volume_ratio = tech_data.get("volume_ratio", 1)
        if volume_ratio > 2.0:
            return "Very High"
        if volume_ratio > 1.5:
            return "High"
        if volume_ratio > 0.8:
            return "Normal"
        if volume_ratio > 0.5:
            return "Low"
        return "Very Low"
    except Exception:
        return "N/A"


def assess_volume_price_relationship(tech_data: dict[str, Any]) -> str:
    """Assess whether volume confirms or contradicts recent price action."""
    try:
        price_change_1d = tech_data.get("price_change_1d", 0)
        volume_ratio = tech_data.get("volume_ratio", 1)

        if price_change_1d > 0 and volume_ratio > 1.2:
            return "Bullish Confirmation"
        if price_change_1d < 0 and volume_ratio > 1.2:
            return "Bearish Confirmation"
        if abs(price_change_1d) > 2 and volume_ratio < 0.8:
            return "Divergence Warning"
        return "Neutral"
    except Exception:
        return "N/A"

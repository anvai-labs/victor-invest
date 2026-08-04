"""Core scoring and response parsing helpers extracted from the legacy synthesizer monolith."""

from __future__ import annotations

import json
import re
from typing import Any


def calculate_fundamental_score(llm_responses: dict[str, Any]) -> float:
    """Calculate the fundamental score from comprehensive or quarterly responses."""
    fundamental_responses = llm_responses.get("fundamental", {})
    if not fundamental_responses:
        return 0.0

    if "comprehensive" in fundamental_responses:
        comp_resp = fundamental_responses["comprehensive"]
        content = comp_resp.get("content", comp_resp)

        if isinstance(content, dict):
            if "financial_health_score" in content:
                return float(content["financial_health_score"])
            if "overall_score" in content:
                return float(content["overall_score"])
        elif isinstance(content, str):
            try:
                parsed = json.loads(content)
                if "financial_health_score" in parsed:
                    return float(parsed["financial_health_score"])
                if "overall_score" in parsed:
                    return float(parsed["overall_score"])
            except Exception:
                score_match = re.search(r"(?:Financial Health|Overall|Score)[:\s]*(\d+(?:\.\d+)?)/10", content)
                if score_match:
                    return float(score_match.group(1))

    scores = []
    for key, response in fundamental_responses.items():
        if key == "comprehensive":
            continue
        content = response.get("content", "")
        if isinstance(content, dict) and "financial_health_score" in content:
            scores.append(float(content["financial_health_score"]))
        elif isinstance(content, str):
            score_match = re.search(r"(?:Financial Health|Overall|Score)[:\s]*(\d+(?:\.\d+)?)/10", content)
            if score_match:
                scores.append(float(score_match.group(1)))

    return sum(scores) / len(scores) if scores else 0.0


def calculate_technical_score(llm_responses: dict[str, Any]) -> float:
    """Calculate the technical score from structured or legacy responses."""
    technical_response = llm_responses.get("technical")
    if not technical_response:
        return 0.0

    content = technical_response.get("content", "")
    if isinstance(content, dict):
        if "technical_score" in content:
            score_data = content["technical_score"]
            if isinstance(score_data, dict):
                return float(score_data.get("score", 0.0))
            return float(score_data)
    elif isinstance(content, str):
        json_content = content
        if "=== AI RESPONSE ===" in content:
            json_start = content.find("=== AI RESPONSE ===") + len("=== AI RESPONSE ===")
            json_content = content[json_start:].strip()

        try:
            parsed = json.loads(json_content)
            if "technical_score" in parsed:
                score_data = parsed["technical_score"]
                if isinstance(score_data, dict):
                    return float(score_data.get("score", 0.0))
                return float(score_data)
        except json.JSONDecodeError:
            pass

        score_match = re.search(
            r"(?:TECHNICAL[_\s]SCORE|technical_score)[:\s]*(\d+(?:\.\d+)?)",
            json_content,
            re.IGNORECASE,
        )
        if score_match:
            return float(score_match.group(1))

    return 0.0


def calculate_weighted_score(
    fundamental_score: float,
    technical_score: float,
    *,
    fundamental_weight: float,
    technical_weight: float,
) -> float:
    """Calculate a weighted overall score with slight bias for extreme component scores."""
    if fundamental_score is None or technical_score is None:
        return 5.0

    fund_weight = fundamental_weight
    tech_weight = technical_weight

    if fundamental_score >= 8.5 or fundamental_score <= 2.5:
        fund_weight *= 1.2
    if technical_score >= 8.5 or technical_score <= 2.5:
        tech_weight *= 1.1

    total_weight = fund_weight + tech_weight
    if total_weight == 0:
        return 0.0

    norm_fund_weight = fund_weight / total_weight
    norm_tech_weight = tech_weight / total_weight
    overall_score = fundamental_score * norm_fund_weight + technical_score * norm_tech_weight
    return round(overall_score, 1)


def assess_data_quality(llm_responses: dict[str, Any], latest_data: dict[str, Any]) -> float:
    """Assess data quality on a 1-10 scale, preferring comprehensive SEC-provided scores."""
    comprehensive_analysis = llm_responses.get("fundamental", {}).get("comprehensive", {})
    if isinstance(comprehensive_analysis, dict):
        if "data_quality_score" in comprehensive_analysis:
            score_data = comprehensive_analysis["data_quality_score"]
            if isinstance(score_data, dict):
                return float(score_data.get("score", 0.0))
            return float(score_data)

        content = comprehensive_analysis.get("content", {})
        if isinstance(content, dict) and "data_quality_score" in content:
            score_data = content["data_quality_score"]
            if isinstance(score_data, dict):
                return float(score_data.get("score", 0.0))
            return float(score_data)

    quality_score = 0.0
    if llm_responses.get("fundamental"):
        quality_score += 4.0
        if len(llm_responses["fundamental"]) >= 3:
            quality_score += 1.0
    if llm_responses.get("technical"):
        quality_score += 3.0
    if latest_data.get("technical", {}).get("current_price"):
        quality_score += 1.0
    if latest_data.get("fundamental"):
        quality_score += 1.0

    return min(quality_score, 10.0)


def parse_synthesis_response(response: str, *, logger: Any | None = None) -> dict[str, Any]:
    """Parse the structured text synthesis response into a normalized recommendation payload."""
    result: dict[str, Any] = {
        "recommendation": "HOLD",
        "confidence": "MEDIUM",
        "investment_thesis": "",
        "key_catalysts": [],
        "key_risks": [],
        "price_targets": {},
        "position_size": "MODERATE",
        "time_horizon": "MEDIUM-TERM",
        "entry_strategy": "",
        "exit_strategy": "",
    }

    try:
        rec_match = re.search(r"FINAL RECOMMENDATION[:\s]*\*?\*?\s*\[?([A-Z\s]+)\]?", response, re.IGNORECASE)
        if rec_match:
            rec_text = rec_match.group(1).strip().upper()
            if "STRONG BUY" in rec_text:
                result["recommendation"] = "STRONG BUY"
            elif "STRONG SELL" in rec_text:
                result["recommendation"] = "STRONG SELL"
            elif "BUY" in rec_text:
                result["recommendation"] = "BUY"
            elif "SELL" in rec_text:
                result["recommendation"] = "SELL"
            else:
                result["recommendation"] = "HOLD"

        conf_match = re.search(r"CONFIDENCE LEVEL[:\s]*\*?\*?\s*\[?([A-Z]+)\]?", response, re.IGNORECASE)
        if conf_match:
            result["confidence"] = conf_match.group(1).strip().upper()

        thesis_match = re.search(
            r"INVESTMENT THESIS[:\s]*\*?\*?(.*?)(?=\*\*[A-Z]|\n\n)",
            response,
            re.IGNORECASE | re.DOTALL,
        )
        if thesis_match:
            result["investment_thesis"] = thesis_match.group(1).strip()

        catalysts_match = re.search(
            r"KEY CATALYSTS[:\s]*\*?\*?(.*?)(?=\*\*[A-Z]|\n\n)",
            response,
            re.IGNORECASE | re.DOTALL,
        )
        if catalysts_match:
            catalysts_text = catalysts_match.group(1)
            result["key_catalysts"] = [cat.strip() for cat in re.findall(r"[•\-]\s*(.+)", catalysts_text)]

        risks_match = re.search(
            r"RISK ASSESSMENT[:\s]*\*?\*?(.*?)(?=\*\*[A-Z]|\n\n)",
            response,
            re.IGNORECASE | re.DOTALL,
        )
        if risks_match:
            risks_text = risks_match.group(1)
            result["key_risks"] = [risk.strip() for risk in re.findall(r"[•\-]\s*(.+)", risks_text)]

        target_match = re.search(r"12-month.*?Target[:\s]*\$?([\d.]+)", response, re.IGNORECASE)
        if target_match:
            result["price_targets"]["12_month"] = float(target_match.group(1))

        pos_match = re.search(r"POSITION SIZING[:\s]*\*?\*?\s*\[?([A-Z\s\/%]+)\]?", response, re.IGNORECASE)
        if pos_match:
            pos_text = pos_match.group(1).strip().upper()
            if "LARGE" in pos_text or "CONCENTRATED" in pos_text:
                result["position_size"] = "LARGE"
            elif "SMALL" in pos_text or "STARTER" in pos_text:
                result["position_size"] = "SMALL"
            else:
                result["position_size"] = "MODERATE"

        horizon_match = re.search(r"TIME HORIZON[:\s]*\*?\*?\s*\[?([A-Z\s\-]+)\]?", response, re.IGNORECASE)
        if horizon_match:
            result["time_horizon"] = horizon_match.group(1).strip().upper()
    except Exception as exc:
        if logger is not None:
            logger.warning(f"Error parsing synthesis response: {exc}")

    return result

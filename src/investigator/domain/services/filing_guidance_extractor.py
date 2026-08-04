"""Deterministic extraction of forward guidance from SEC filing text."""

from __future__ import annotations

import html
import math
import re
from typing import Any

_RANGE_SEP = r"(?:to|and|-|–|—)"
_AMOUNT = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)"
_UNIT = r"(billion|million|thousand|bn|mm|m|b)"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
        if math.isnan(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _amount_to_usd(value: str, unit: str | None) -> float | None:
    number = _to_float(value)
    if number is None:
        return None

    unit_norm = (unit or "").strip().lower()
    scale = 1.0
    if unit_norm in {"billion", "bn", "b"}:
        scale = 1_000_000_000.0
    elif unit_norm in {"million", "mm", "m"}:
        scale = 1_000_000.0
    elif unit_norm in {"thousand", "k"}:
        scale = 1_000.0
    return number * scale


def _normalize_text(text: str) -> str:
    """
    Strip SEC inline HTML/XBRL markup before regex extraction.
    """
    decoded = html.unescape(text or "")
    no_tags = re.sub(r"<[^>]+>", " ", decoded)
    return re.sub(r"\s+", " ", no_tags).strip()


def _infer_horizon(window: str, form_type: str) -> str:
    snippet = (window or "").lower()
    if re.search(r"\b(full[- ]?year|fiscal year|fy\s*20\d{2})\b", snippet):
        return "1y"
    if re.search(r"\b(next quarter|current quarter|quarter|q[1-4])\b", snippet):
        return "1q"
    return "1y" if str(form_type or "").upper() in {"10-K", "10-Q"} else "1q"


def _extract_context_window(text: str, start: int, end: int, width: int = 220) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    return text[left:right]


def _extract_revenue_range(text: str) -> dict[str, Any] | None:
    patterns = [
        re.compile(
            rf"(?:revenue|net sales|sales)[^\.\n]{{0,180}}?(?:guidance|outlook|forecast|expect(?:s|ed)?)"
            rf"[^\.\n]{{0,180}}?between\s*\$?\s*{_AMOUNT}\s*{_UNIT}?\s*{_RANGE_SEP}\s*\$?\s*{_AMOUNT}\s*{_UNIT}?",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:revenue|net sales|sales)[^\.\n]{{0,180}}?(?:guidance|outlook|forecast|expect(?:s|ed)?)"
            rf"[^\.\n]{{0,180}}?\$?\s*{_AMOUNT}\s*{_UNIT}?\s*{_RANGE_SEP}\s*\$?\s*{_AMOUNT}\s*{_UNIT}?",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:guidance|outlook|forecast|expect(?:s|ed|ation)?|project(?:s|ed)?|anticipat(?:e|es|ed)|target(?:s|ed)?)"
            rf"[^\.\n]{{0,220}}?(?:revenue|net sales|sales)[^\.\n]{{0,220}}?"
            rf"(?:in\s+the\s+range\s+of|range\s+of|between)?\s*\$?\s*{_AMOUNT}\s*{_UNIT}?\s*{_RANGE_SEP}\s*\$?\s*{_AMOUNT}\s*{_UNIT}?",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:expect(?:s|ed|ation)?|project(?:s|ed)?|anticipat(?:e|es|ed))"
            rf"[^\.\n]{{0,220}}?(?:revenue|net sales|sales)[^\.\n]{{0,220}}?"
            rf"(?:in\s+the\s+range\s+of|range\s+of|between)?\s*\$?\s*{_AMOUNT}\s*{_UNIT}?\s*{_RANGE_SEP}\s*\$?\s*{_AMOUNT}\s*{_UNIT}?",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue

        groups = match.groups()
        low_raw = groups[0]
        low_unit = groups[1]
        high_raw = groups[2]
        high_unit = groups[3]
        unit = high_unit or low_unit

        low = _amount_to_usd(low_raw, unit)
        high = _amount_to_usd(high_raw, unit)
        if low is None or high is None:
            continue
        if low > high:
            low, high = high, low

        window = _extract_context_window(text, match.start(), match.end())
        return {
            "low": low,
            "high": high,
            "mid": (low + high) / 2.0,
            "horizon": _infer_horizon(window, form_type=""),
            "snippet": window[:280],
        }
    return None


def _extract_eps_range(text: str) -> dict[str, Any] | None:
    patterns = [
        re.compile(
            rf"(?:earnings per share|diluted eps|eps)[^\.\n]{{0,160}}?"
            rf"(?:guidance|outlook|forecast|expect(?:s|ed|ation)?|range|target(?:s|ed)?|project(?:s|ed)?|anticipat(?:e|es|ed)|between)"
            rf"[^\.\n]{{0,120}}?"
            rf"\$?\s*(-?\d+(?:\.\d+)?)\s*{_RANGE_SEP}\s*\$?\s*(-?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:guidance|outlook|forecast|expect(?:s|ed|ation)?|range|target(?:s|ed)?|project(?:s|ed)?|anticipat(?:e|es|ed)|between)"
            rf"[^\.\n]{{0,160}}?(?:earnings per share|diluted eps|eps)[^\.\n]{{0,120}}?"
            rf"\$?\s*(-?\d+(?:\.\d+)?)\s*{_RANGE_SEP}\s*\$?\s*(-?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue

        low_raw = match.group(1)
        high_raw = match.group(2)
        matched_text = match.group(0) or ""

        # Guard against matching fiscal years (e.g., "2024 and 2025") as EPS values.
        has_currency_or_decimal = "$" in matched_text or ("." in low_raw or "." in high_raw)
        if not has_currency_or_decimal:
            continue

        low = _to_float(low_raw)
        high = _to_float(high_raw)
        if low is None or high is None:
            continue
        if low > high:
            low, high = high, low
        if low > 0 and high > 0 and (high / max(low, 1e-6)) > 5.0:
            continue

        window = _extract_context_window(text, match.start(), match.end())
        return {
            "low": low,
            "high": high,
            "mid": (low + high) / 2.0,
            "horizon": _infer_horizon(window, form_type=""),
            "snippet": window[:280],
        }
    return None


def _extract_growth_percent(text: str, metric: str) -> float | None:
    metric_pattern = "revenue|net sales|sales" if metric == "revenue" else "eps|earnings"
    forward_cue = (
        "guidance|outlook|forecast|expect(?:s|ed|ation)?|project(?:s|ed)?|"
        "anticipat(?:e|es|ed)|target(?:s|ed)?|raise(?:d)?|reaffirm(?:ed)?"
    )
    patterns = [
        re.compile(
            rf"(?:{forward_cue})[^\.\n]{{0,180}}?(?:{metric_pattern})[^\.\n]{{0,120}}?"
            rf"(?:growth|grow(?:th)?|increase|up|rise|decline|down|decrease)"
            rf"[^\.\n]{{0,80}}?(-?\d+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:{metric_pattern})[^\.\n]{{0,120}}?(?:growth|grow(?:th)?|increase|up|rise|decline|down|decrease)"
            rf"[^\.\n]{{0,80}}?(-?\d+(?:\.\d+)?)\s*%[^\.\n]{{0,120}}?(?:{forward_cue})",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        pct = _to_float(match.group(1))
        if pct is None:
            continue
        # Convert to decimal ratio
        return pct / 100.0
    return None


def extract_forward_guidance(
    *,
    text: str,
    form_type: str,
    filing_date: str | None = None,
) -> dict[str, Any]:
    """
    Extract deterministic forward guidance signals from filing text.

    Returns empty dict when no usable guidance is found.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return {}

    revenue_range = _extract_revenue_range(normalized)
    eps_range = _extract_eps_range(normalized)
    revenue_growth = _extract_growth_percent(normalized, metric="revenue")
    eps_growth = _extract_growth_percent(normalized, metric="eps")

    if revenue_range and revenue_range.get("horizon"):
        revenue_range["horizon"] = _infer_horizon(revenue_range.get("snippet", ""), form_type)
    if eps_range and eps_range.get("horizon"):
        eps_range["horizon"] = _infer_horizon(eps_range.get("snippet", ""), form_type)

    has_any_signal = any(
        [
            revenue_range is not None,
            eps_range is not None,
            revenue_growth is not None,
            eps_growth is not None,
        ]
    )
    if not has_any_signal:
        return {}

    confidence = 0.0
    if revenue_range:
        confidence += 0.40
    if eps_range:
        confidence += 0.35
    if revenue_growth is not None:
        confidence += 0.15
    if eps_growth is not None:
        confidence += 0.10

    payload: dict[str, Any] = {
        "source": "sec_filing_regex",
        "source_form": str(form_type or "").upper(),
        "filing_date": filing_date,
        "confidence_score": round(min(confidence, 1.0), 2),
    }
    if revenue_range:
        payload["revenue_guidance"] = revenue_range
    if eps_range:
        payload["eps_guidance"] = eps_range
    if revenue_growth is not None:
        payload["revenue_growth_guidance"] = revenue_growth
    if eps_growth is not None:
        payload["earnings_growth_guidance"] = eps_growth
    return payload


def select_best_guidance(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the strongest guidance payload from multiple filings."""
    if not candidates:
        return {}

    def _score(item: dict[str, Any]) -> tuple[float, int]:
        confidence = _to_float(item.get("confidence_score")) or 0.0
        signal_count = int(
            bool(item.get("revenue_guidance"))
            + bool(item.get("eps_guidance"))
            + bool(item.get("revenue_growth_guidance") is not None)
            + bool(item.get("earnings_growth_guidance") is not None)
        )
        return confidence, signal_count

    return max(candidates, key=_score)

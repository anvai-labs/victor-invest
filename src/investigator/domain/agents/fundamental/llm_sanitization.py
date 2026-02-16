"""Helpers for sanitizing company/ratio payloads before LLM synthesis."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Tuple


def _extract_numeric(financials: Dict[str, Any], *keys: str) -> Optional[float]:
    """Return first parseable numeric value for the provided keys."""
    for key in keys:
        if key not in financials:
            continue
        value = financials.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def backfill_market_fields(
    *,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    symbol: str,
    logger: Any,
) -> None:
    """Backfill market cap, price, and shares when ratios contain canonical values."""
    if company_data.get("market_cap", 0) == 0 and ratios.get("market_cap", 0) > 0:
        company_data["market_cap"] = ratios["market_cap"]
        logger.warning(
            "⚠️  %s: Backfilled market_cap from ratios: $%s",
            symbol,
            format(company_data["market_cap"], ",.0f"),
        )

    current_price = company_data.get("market_data", {}).get("current_price", 0)
    if current_price == 0 and ratios.get("current_price", 0) > 0:
        if "market_data" not in company_data:
            company_data["market_data"] = {}
        company_data["market_data"]["current_price"] = ratios["current_price"]
        logger.warning(
            "⚠️  %s: Backfilled price from ratios: $%.2f",
            symbol,
            ratios["current_price"],
        )

    if company_data.get("shares_outstanding", 0) == 0 and ratios.get("shares_outstanding", 0) > 0:
        company_data["shares_outstanding"] = ratios["shares_outstanding"]
        logger.warning(
            "⚠️  %s: Backfilled shares from ratios: %s",
            symbol,
            format(ratios["shares_outstanding"], ",.0f"),
        )


def normalize_leverage_ratios(
    *,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    symbol: str,
    logger: Any,
    leverage_abs_tol: float = 0.05,
    leverage_rel_tol: float = 0.05,
) -> None:
    """Normalize debt leverage ratios from underlying core financial totals."""
    financials = company_data.get("financials") or {}

    total_debt = _extract_numeric(financials, "total_debt")
    if total_debt is None:
        long_term_debt = _extract_numeric(financials, "long_term_debt")
        short_term_debt = _extract_numeric(financials, "short_term_debt", "debt_current")
        if long_term_debt is not None or short_term_debt is not None:
            total_debt = (long_term_debt or 0.0) + (short_term_debt or 0.0)

    total_equity = _extract_numeric(financials, "stockholders_equity", "equity")
    total_assets = _extract_numeric(financials, "total_assets", "assets")

    def normalize_ratio(name: str, recomputed: Optional[float]) -> None:
        if recomputed is None or not math.isfinite(recomputed):
            return

        existing_raw = ratios.get(name)
        needs_log = False
        if existing_raw is None:
            needs_log = recomputed != 0
        else:
            try:
                existing_value = float(existing_raw)
            except (TypeError, ValueError):
                needs_log = True
            else:
                if not math.isfinite(existing_value):
                    needs_log = True
                elif abs(existing_value - recomputed) > max(leverage_abs_tol, leverage_rel_tol * abs(recomputed)):
                    needs_log = True

        if needs_log:
            logger.warning(
                "⚠️  %s: Normalized %s from %s to %.3f using core financials.",
                symbol,
                name.replace("_", " "),
                existing_raw if existing_raw is not None else "missing",
                recomputed,
            )
        ratios[name] = recomputed

    if total_debt is not None and total_equity and total_equity != 0:
        normalize_ratio("debt_to_equity", total_debt / total_equity)

    if total_debt is not None and total_assets and total_assets != 0:
        normalize_ratio("debt_to_assets", total_debt / total_assets)


def enforce_quick_ratio_bound(*, ratios: Dict[str, Any], symbol: str, logger: Any) -> None:
    """Ensure quick ratio never exceeds current ratio when both are positive."""
    current_ratio = ratios.get("current_ratio", 0)
    quick_ratio = ratios.get("quick_ratio", 0)
    if quick_ratio > current_ratio and current_ratio > 0:
        logger.warning(
            "⚠️  %s: Invalid ratios - quick_ratio (%.2f) > current_ratio (%.2f). "
            "Adjusting quick_ratio to equal current_ratio.",
            symbol,
            quick_ratio,
            current_ratio,
        )
        ratios["quick_ratio"] = current_ratio


def sanitize_for_llm_inputs(
    *,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    symbol: str,
    logger: Any,
    log_data_quality_issues: Callable[[Any, str, Dict[str, Any], Dict[str, Any]], None],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply deterministic sanitation to company/ratio payloads before LLM usage."""
    backfill_market_fields(company_data=company_data, ratios=ratios, symbol=symbol, logger=logger)
    normalize_leverage_ratios(company_data=company_data, ratios=ratios, symbol=symbol, logger=logger)
    enforce_quick_ratio_bound(ratios=ratios, symbol=symbol, logger=logger)
    log_data_quality_issues(logger, symbol, company_data, ratios)
    return company_data, ratios

"""Helpers for CAPM-based cost-of-equity calculation."""

from __future__ import annotations

from typing import Any, Callable, Dict


def calculate_cost_of_equity_capm(
    *,
    symbol: str,
    get_stock_info: Callable[[str], Dict[str, Any]],
    get_latest_indicators: Callable[[list[str]], Dict[str, Any]],
    logger: Any,
    beta_floor: float = 0.50,
    beta_cap: float = 2.50,
    default_risk_free_rate: float = 0.045,
    market_risk_premium: float = 0.07,
    fallback_cost_of_equity: float = 0.10,
) -> float:
    """Compute CAPM cost of equity with bounded beta and risk-free fallback handling."""
    try:
        info = get_stock_info(symbol) or {}
        raw_beta = info.get("beta", 1.0) or 1.0

        beta_adjustment = None
        if raw_beta < beta_floor:
            beta_adjustment = f"low_beta_floor ({raw_beta:.2f} -> {beta_floor})"
            beta = beta_floor
        elif raw_beta > beta_cap:
            beta_adjustment = f"high_beta_cap ({raw_beta:.2f} -> {beta_cap})"
            beta = beta_cap
        else:
            beta = raw_beta

        indicators = get_latest_indicators(["DGS10"]) or {}
        risk_free_rate = default_risk_free_rate
        if "DGS10" in indicators:
            dgs10 = indicators.get("DGS10") or {}
            value = dgs10.get("value")
            if value is not None:
                risk_free_rate = value / 100

        cost_of_equity = risk_free_rate + beta * market_risk_premium

        log_msg = (
            f"{symbol} - Cost of Equity (CAPM): {cost_of_equity * 100:.2f}% "
            f"(Rf={risk_free_rate * 100:.2f}%, Beta={beta:.2f}, MRP={market_risk_premium * 100:.0f}%)"
        )
        if beta_adjustment:
            log_msg += f" [adjustment: {beta_adjustment}]"
        logger.info(log_msg)

        return cost_of_equity
    except Exception as exc:
        logger.warning("%s - Error calculating cost of equity: %s, using default 10%%", symbol, exc)
        return fallback_cost_of_equity

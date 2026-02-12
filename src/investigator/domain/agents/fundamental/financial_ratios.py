"""Helpers for deterministic financial-ratio computation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def log_ratio_calc_debug(
    *, logger: Any, symbol: str, company_data: Dict[str, Any]
) -> None:
    """Emit ratio-calculation debug context."""
    logger.info(
        "RATIOS_CALC_DEBUG - _calculate_financial_ratios() called for %s", symbol
    )
    logger.info("RATIOS_CALC_DEBUG - company_data keys: %s", list(company_data.keys()))
    quarterly_data_check = company_data.get("quarterly_data", [])
    logger.info(
        "RATIOS_CALC_DEBUG - quarterly_data exists: %s, length: %s",
        quarterly_data_check is not None,
        len(quarterly_data_check) if quarterly_data_check else 0,
    )


def resolve_market_inputs(
    *,
    symbol: str,
    cik: str,
    financials: Dict[str, Any],
    market_data: Dict[str, Any],
    get_shares_outstanding: Callable[[str, str], float],
    get_public_float: Callable[[str, str], float],
    logger: Any,
    ratios: Dict[str, Any],
) -> Dict[str, float]:
    """Resolve price/shares/market-cap inputs and update market-dependent ratio seeds."""
    price = market_data.get("current_price", market_data.get("price", 0))
    shares = get_shares_outstanding(symbol, cik)

    public_float_usd = get_public_float(symbol, cik)
    if public_float_usd > 0:
        ratios["public_float_usd"] = public_float_usd
        ratios["current_price"] = price

    if shares == 0:
        estimated_equity = financials.get("stockholders_equity") or 0
        if price > 0 and estimated_equity > 0:
            shares = estimated_equity / price
            logger.info(
                "Estimated shares for %s from equity/price: %s",
                symbol,
                format(shares, ",.0f"),
            )

    if shares == 0:
        shares = 1
        logger.warning(
            "Using shares=1 for %s - per-share metrics will be inaccurate", symbol
        )

    if price > 0 and shares > 1:
        market_cap = price * shares
        logger.info(
            "Calculated market cap for %s: $%s (%.2f × %s)",
            symbol,
            format(market_cap, ",.0f"),
            price,
            format(shares, ",.0f"),
        )
    else:
        market_cap = financials.get("stockholders_equity") or 0
        logger.warning(
            "Using total equity as market cap proxy for %s: $%s",
            symbol,
            format(market_cap, ",.0f"),
        )

    return {"price": price, "shares": shares, "market_cap": market_cap}


def apply_valuation_ratios(
    *,
    symbol: str,
    financials: Dict[str, Any],
    quarterly_data: List[Any],
    ratios: Dict[str, Any],
    market_cap: float,
    shares: float,
    calculate_ttm_net_income: Callable[[List[Any], str], float],
    calculate_growth_rate: Callable[[Dict[str, Any], str], float],
    logger: Any,
) -> None:
    """Populate valuation metrics that depend on market-cap and earnings growth."""
    ttm_net_income = calculate_ttm_net_income(quarterly_data, symbol)
    earnings = (
        ttm_net_income if ttm_net_income > 0 else (financials.get("net_income") or 0)
    )

    if earnings > 0 and market_cap > 0:
        ratios["pe_ratio"] = float(market_cap) / float(earnings)
        ratios["eps"] = float(earnings) / float(shares) if shares > 0 else 0
        if ttm_net_income > 0:
            quarterly_ni = financials.get("net_income") or 0
            logger.info(
                "%s - Using TTM net income for EPS: $%s (vs quarterly: $%s) -> EPS=%.2f",
                symbol,
                format(ttm_net_income, ",.0f"),
                format(quarterly_ni, ",.0f"),
                ratios["eps"],
            )
        else:
            logger.warning(
                "%s - TTM net income not available, falling back to quarterly for EPS",
                symbol,
            )

    book_value = financials.get("stockholders_equity") or 0
    if book_value > 0 and market_cap > 0:
        ratios["price_to_book"] = float(market_cap) / float(book_value)
        ratios["book_value_per_share"] = (
            float(book_value) / float(shares) if shares > 0 else 0
        )

    revenue = financials.get("revenues") or 0
    if revenue > 0 and market_cap > 0:
        ratios["price_to_sales"] = float(market_cap) / float(revenue)
        ratios["revenue_per_share"] = (
            float(revenue) / float(shares) if shares > 0 else 0
        )

    growth_rate = calculate_growth_rate(financials, "net_income")
    if ratios.get("pe_ratio") and growth_rate > 0:
        ratios["peg_ratio"] = ratios["pe_ratio"] / (growth_rate * 100)


def apply_balance_sheet_and_cashflow_ratios(
    *,
    financials: Dict[str, Any],
    ratios: Dict[str, Any],
    market_cap: float,
    price: float,
) -> None:
    """Populate liquidity/leverage/profitability/efficiency/cashflow ratios."""
    current_assets = financials.get("current_assets") or 0
    current_liabilities = financials.get("current_liabilities") or 0
    inventory = financials.get("inventory") or 0

    ratios["current_ratio"] = (
        current_assets / current_liabilities if current_liabilities > 0 else 0
    )
    ratios["quick_ratio"] = (
        (current_assets - inventory) / current_liabilities
        if current_liabilities > 0
        else 0
    )

    total_debt = financials.get("total_debt") or 0
    total_equity = financials.get("stockholders_equity") or 0
    total_assets = financials.get("total_assets") or 0

    ratios["debt_to_equity"] = total_debt / total_equity if total_equity > 0 else 0
    ratios["debt_to_assets"] = total_debt / total_assets if total_assets > 0 else 0

    net_income = financials.get("net_income") or 0
    revenue = financials.get("revenues") or 0
    gross_profit = financials.get("gross_profit") or 0
    operating_income = financials.get("operating_income") or 0

    ratios["roe"] = net_income / total_equity if total_equity > 0 else 0
    ratios["roa"] = net_income / total_assets if total_assets > 0 else 0
    ratios["gross_margin"] = gross_profit / revenue if revenue > 0 else 0
    ratios["operating_margin"] = operating_income / revenue if revenue > 0 else 0
    ratios["net_margin"] = net_income / revenue if revenue > 0 else 0

    ratios["asset_turnover"] = revenue / total_assets if total_assets > 0 else 0
    ratios["inventory_turnover"] = (
        (financials.get("cost_of_revenue") or 0) / inventory if inventory > 0 else 0
    )

    operating_cash_flow = financials.get("operating_cash_flow") or 0
    capex = financials.get("capital_expenditures") or 0
    free_cash_flow = operating_cash_flow - abs(capex)

    ratios["operating_cash_flow"] = operating_cash_flow
    ratios["free_cash_flow"] = free_cash_flow
    ratios["fcf_yield"] = free_cash_flow / market_cap if market_cap > 0 else 0

    common_divs = abs(financials.get("dividends_paid", 0) or 0)
    preferred_divs = abs(financials.get("preferred_stock_dividends", 0) or 0)
    total_dividends = common_divs + preferred_divs
    ratios["dividend_yield"] = total_dividends / price if price > 0 else 0
    ratios["payout_ratio"] = total_dividends / net_income if net_income > 0 else 0


def add_market_context_ratios(
    *,
    ratios: Dict[str, Any],
    market_data: Dict[str, Any],
    financials: Dict[str, Any],
    market_cap: float,
    shares: float,
    price: float,
) -> None:
    """Store market-cap/share inputs for downstream prompt hydration."""
    if market_data and financials:
        ratios["market_cap"] = market_cap
        ratios["shares_outstanding"] = shares
        ratios["current_price"] = price


def calculate_revenue_growth_yoy(
    *,
    quarterly_data: List[Any],
    logger: Any,
) -> Optional[float]:
    """Calculate YoY revenue growth from quarterly-only entries (current quarter vs 4Q prior)."""
    if not quarterly_data or len(quarterly_data) < 5:
        return None

    quarter_order = {"Q4": 4, "Q3": 3, "Q2": 2, "Q1": 1}
    quarterly_only = []
    for entry in quarterly_data:
        if isinstance(entry, dict):
            period = entry.get("fiscal_period")
            fiscal_year = entry.get("fiscal_year", 0)
        else:
            period = getattr(entry, "fiscal_period", None)
            fiscal_year = getattr(entry, "fiscal_year", 0)

        if (
            period
            and isinstance(period, str)
            and period.startswith("Q")
            and period not in ["QFY", "FY"]
        ):
            quarterly_only.append((entry, fiscal_year, period))

    quarterly_sorted = sorted(
        quarterly_only,
        key=lambda x: (x[1], quarter_order.get(x[2], 0)),
        reverse=True,
    )
    revenues: List[float] = []
    for entry, _fy, _period in quarterly_sorted[:8]:
        if isinstance(entry, dict):
            rev = entry.get("financial_data", {}).get("revenues", 0) or entry.get(
                "revenues", 0
            )
        else:
            financial_data = getattr(entry, "financial_data", {}) or {}
            rev = financial_data.get("revenues", 0)
        revenues.append(float(rev) if rev else 0)

    if len(revenues) >= 5 and revenues[4] > 0:
        yoy_growth = (revenues[0] - revenues[4]) / revenues[4]
        logger.info(
            "Calculated revenue_growth_yoy from quarterly data: %.1f%%",
            yoy_growth * 100,
        )
        return yoy_growth
    return None

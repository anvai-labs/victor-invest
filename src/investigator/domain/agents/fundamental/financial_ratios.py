"""Helpers for deterministic financial-ratio computation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

_QUARTER_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def _coerce_float(value: Any) -> float:
    """Convert values to float with a safe 0.0 fallback."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_fiscal_year_period(entry: Any) -> tuple[int, str]:
    """Extract `(fiscal_year, fiscal_period)` from dict or QuarterlyData-like objects."""
    if isinstance(entry, dict):
        fiscal_year = entry.get("fiscal_year", 0)
        fiscal_period = (entry.get("fiscal_period") or "").upper()
    else:
        fiscal_year = getattr(entry, "fiscal_year", 0)
        fiscal_period = (getattr(entry, "fiscal_period", "") or "").upper()

    try:
        fiscal_year = int(fiscal_year)
    except (TypeError, ValueError):
        fiscal_year = 0
    return fiscal_year, fiscal_period


def _extract_quarter_metric(entry: Any, metric_candidates: List[str]) -> float:
    """Extract a metric value from a quarter payload across common nesting patterns."""
    candidate_dicts: List[Dict[str, Any]] = []

    if isinstance(entry, dict):
        candidate_dicts.append(entry)
        for key in ("financial_data", "income_statement", "cash_flow", "balance_sheet"):
            nested = entry.get(key)
            if isinstance(nested, dict):
                candidate_dicts.append(nested)
    else:
        financial_data = getattr(entry, "financial_data", None)
        if isinstance(financial_data, dict):
            candidate_dicts.append(financial_data)

    saw_zero = False
    for payload in candidate_dicts:
        for metric in metric_candidates:
            if metric not in payload:
                continue
            value = _coerce_float(payload.get(metric))
            if value != 0:
                return value
            saw_zero = True

    return 0.0 if saw_zero else 0.0


def calculate_ttm_metrics(
    *,
    quarterly_data: List[Any],
    symbol: str,
    logger: Any,
) -> Dict[str, float]:
    """
    Compute TTM metrics from the 4 most recent actual quarters (Q1-Q4 only).

    Input lists may be ascending or descending and may include FY rows. This helper
    enforces a deterministic sort and always excludes FY to avoid double counting.
    """
    if not quarterly_data:
        return {}

    actual_quarters: List[Any] = []
    for quarter in quarterly_data:
        _, fiscal_period = _extract_fiscal_year_period(quarter)
        if fiscal_period in _QUARTER_ORDER:
            actual_quarters.append(quarter)

    if len(actual_quarters) < 4:
        logger.warning(
            "%s - Insufficient actual quarters for TTM metrics (%s < 4)",
            symbol,
            len(actual_quarters),
        )
        return {}

    actual_quarters.sort(
        key=lambda quarter: (
            _extract_fiscal_year_period(quarter)[0],
            _QUARTER_ORDER.get(_extract_fiscal_year_period(quarter)[1], 0),
        ),
        reverse=True,
    )
    last_4_quarters = actual_quarters[:4]

    ttm_revenue = 0.0
    ttm_net_income = 0.0
    ttm_ebitda = 0.0
    ttm_free_cash_flow = 0.0
    ttm_dividends_paid = 0.0

    for quarter in last_4_quarters:
        quarter_revenue = _extract_quarter_metric(quarter, ["revenues", "revenue", "total_revenue"])
        quarter_net_income = _extract_quarter_metric(quarter, ["net_income", "earnings", "NetIncomeLoss"])

        quarter_ebitda = _extract_quarter_metric(quarter, ["ebitda"])
        if quarter_ebitda == 0:
            quarter_operating_income = _extract_quarter_metric(quarter, ["operating_income"])
            quarter_depr_amort = _extract_quarter_metric(
                quarter,
                [
                    "depreciation_amortization",
                    "depreciation_and_amortization",
                    "depreciation_depletion_and_amortization",
                ],
            )
            if quarter_operating_income != 0:
                quarter_ebitda = quarter_operating_income + quarter_depr_amort

        quarter_fcf = _extract_quarter_metric(quarter, ["free_cash_flow"])
        if quarter_fcf == 0:
            quarter_ocf = _extract_quarter_metric(quarter, ["operating_cash_flow"])
            quarter_capex = _extract_quarter_metric(quarter, ["capital_expenditures"])
            if quarter_ocf != 0:
                quarter_fcf = quarter_ocf - abs(quarter_capex)

        quarter_dividends_paid = abs(
            _extract_quarter_metric(quarter, ["dividends_paid", "dividends", "PaymentsOfDividends"])
        )

        ttm_revenue += quarter_revenue
        ttm_net_income += quarter_net_income
        ttm_ebitda += quarter_ebitda
        ttm_free_cash_flow += quarter_fcf
        ttm_dividends_paid += quarter_dividends_paid

    ttm_metrics = {
        "revenues": ttm_revenue,
        "net_income": ttm_net_income,
        "ebitda": ttm_ebitda,
        "free_cash_flow": ttm_free_cash_flow,
        "dividends_paid": ttm_dividends_paid,
        "quarters_used": float(len(last_4_quarters)),
    }
    logger.info(
        "%s - Computed TTM metrics from latest %s quarters: revenue=$%s, net_income=$%s, ebitda=$%s",
        symbol,
        len(last_4_quarters),
        format(ttm_revenue, ",.0f"),
        format(ttm_net_income, ",.0f"),
        format(ttm_ebitda, ",.0f"),
    )
    return ttm_metrics


def log_ratio_calc_debug(*, logger: Any, symbol: str, company_data: Dict[str, Any]) -> None:
    """Emit ratio-calculation debug context."""
    logger.info("RATIOS_CALC_DEBUG - _calculate_financial_ratios() called for %s", symbol)
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
        logger.warning("Using shares=1 for %s - per-share metrics will be inaccurate", symbol)

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
    ttm_metrics: Optional[Dict[str, float]],
    ratios: Dict[str, Any],
    market_cap: float,
    shares: float,
    calculate_ttm_net_income: Callable[[List[Any], str], float],
    calculate_growth_rate: Callable[[Dict[str, Any], str], float],
    logger: Any,
) -> None:
    """Populate valuation metrics that depend on market-cap and earnings growth."""
    ttm_metrics = ttm_metrics or {}
    ttm_net_income = _coerce_float(ttm_metrics.get("net_income")) or calculate_ttm_net_income(quarterly_data, symbol)
    earnings = ttm_net_income if ttm_net_income > 0 else (financials.get("net_income") or 0)
    ttm_revenue = _coerce_float(ttm_metrics.get("revenues"))
    ttm_ebitda = _coerce_float(ttm_metrics.get("ebitda"))

    if ttm_net_income:
        ratios["ttm_net_income"] = ttm_net_income
    if ttm_revenue:
        ratios["ttm_revenue"] = ttm_revenue
    if ttm_ebitda:
        ratios["ttm_ebitda"] = ttm_ebitda

    if earnings > 0 and market_cap > 0:
        ratios["pe_ratio"] = float(market_cap) / float(earnings)
        calculated_eps = float(earnings) / float(shares) if shares > 0 else 0
        ratios["eps"] = calculated_eps

        # DEBUG: Log detailed EPS calculation with unit validation
        logger.info(
            "[EPS_DEBUG] %s - EPS Calculation: earnings=$%s, shares=%s, eps=$%.2f, " "market_cap=$%s",
            symbol,
            format(earnings, ",.0f"),
            format(shares, ",.0f"),
            calculated_eps,
            format(market_cap, ",.0f"),
        )

        # Warn if EPS looks suspicious (too high or too low)
        if calculated_eps > 1000:
            logger.warning(
                "[EPS_SUSPICIOUS] %s - EPS seems too high ($%.2f) - possible unit mismatch. "
                "earnings=$%s, shares=%s. Expected EPS < $100 for normal companies.",
                symbol,
                calculated_eps,
                format(earnings, ",.0f"),
                format(shares, ",.0f"),
            )
        elif calculated_eps < 0.01 and calculated_eps > 0:
            logger.warning(
                "[EPS_SUSPICIOUS] %s - EPS seems too low ($%.4f) - possible unit mismatch. " "earnings=$%s, shares=%s.",
                symbol,
                calculated_eps,
                format(earnings, ",.0f"),
                format(shares, ",.0f"),
            )

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
        ratios["book_value_per_share"] = float(book_value) / float(shares) if shares > 0 else 0

    revenue = ttm_revenue if ttm_revenue > 0 else (financials.get("revenues") or 0)
    if revenue > 0 and market_cap > 0:
        ratios["price_to_sales"] = float(market_cap) / float(revenue)
        calculated_rps = float(revenue) / float(shares) if shares > 0 else 0
        ratios["revenue_per_share"] = calculated_rps

        # DEBUG: Log detailed revenue_per_share calculation with unit validation
        logger.info(
            "[RPS_DEBUG] %s - Revenue Per Share Calculation: revenue=$%s, shares=%s, rps=$%.2f, " "market_cap=$%s",
            symbol,
            format(revenue, ",.0f"),
            format(shares, ",.0f"),
            calculated_rps,
            format(market_cap, ",.0f"),
        )

        # Warn if RPS looks suspicious (too high or too low)
        if calculated_rps > 10000:
            logger.warning(
                "[RPS_SUSPICIOUS] %s - Revenue per share seems too high ($%.2f) - possible unit mismatch. "
                "revenue=$%s, shares=%s. Expected RPS < $1000 for normal companies.",
                symbol,
                calculated_rps,
                format(revenue, ",.0f"),
                format(shares, ",.0f"),
            )
        elif calculated_rps < 0.01 and calculated_rps > 0:
            logger.warning(
                "[RPS_SUSPICIOUS] %s - Revenue per share seems too low ($%.4f) - possible unit mismatch. "
                "revenue=$%s, shares=%s.",
                symbol,
                calculated_rps,
                format(revenue, ",.0f"),
                format(shares, ",.0f"),
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

    ratios["current_ratio"] = current_assets / current_liabilities if current_liabilities > 0 else 0
    ratios["quick_ratio"] = (current_assets - inventory) / current_liabilities if current_liabilities > 0 else 0

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
    ratios["inventory_turnover"] = (financials.get("cost_of_revenue") or 0) / inventory if inventory > 0 else 0

    operating_cash_flow = financials.get("operating_cash_flow") or 0
    capex = financials.get("capital_expenditures") or 0
    free_cash_flow = operating_cash_flow - abs(capex)

    ratios["operating_cash_flow"] = operating_cash_flow
    ratios["free_cash_flow"] = free_cash_flow
    ratios["fcf_yield"] = free_cash_flow / market_cap if market_cap > 0 else 0

    common_divs = abs(financials.get("dividends_paid", 0) or 0)
    preferred_divs = abs(financials.get("preferred_stock_dividends", 0) or 0)
    total_dividends = common_divs + preferred_divs
    # Dividends are absolute currency values; convert to yield using market cap.
    ratios["dividend_yield"] = total_dividends / market_cap if market_cap > 0 else 0
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
    """Calculate revenue growth using TTM (Trailing Twelve Months) comparison.

    Primary method: TTM Revenue Growth
        - Compares TTM revenue now vs TTM revenue 4 quarters ago
        - Smooths seasonality and quarter-to-quarter noise
        - Industry standard for growth-adjusted valuation multiples

    Fallback method: Same-quarter YoY
        - Compares current quarter to same quarter in prior year
        - More current but can be volatile
        - Used when insufficient quarters for TTM calculation

    Args:
        quarterly_data: List of quarterly entries (dicts or QuarterlyData objects)
        logger: Logger instance

    Returns:
        Revenue growth rate as decimal (e.g., 0.368 for 36.8%) or None
    """
    if not quarterly_data or len(quarterly_data) < 2:
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

        if period and isinstance(period, str) and period.startswith("Q") and period not in ["QFY", "FY"]:
            quarterly_only.append((entry, fiscal_year, period))

    if not quarterly_only:
        return None

    quarterly_sorted = sorted(
        quarterly_only,
        key=lambda x: (x[1], quarter_order.get(x[2], 0)),
        reverse=True,
    )

    # Extract revenues with metadata
    quarters_with_revenue = []
    for entry, fy, period in quarterly_sorted[:12]:
        if isinstance(entry, dict):
            rev = (
                entry.get("financial_data", {}).get("revenues", 0)
                or entry.get("revenues", 0)
                or entry.get("total_revenue", 0)
            )
        else:
            financial_data = getattr(entry, "financial_data", {}) or {}
            rev = financial_data.get("revenues", 0) or financial_data.get("total_revenue", 0)
        quarters_with_revenue.append({"revenue": float(rev) if rev else 0, "fy": fy, "period": period})

    # Method 1: TTM Revenue Growth (preferred)
    # Need at least 8 quarters: 4 for current TTM, 4 for prior TTM
    if len(quarters_with_revenue) >= 8:
        current_ttm = sum(q["revenue"] for q in quarters_with_revenue[:4])
        prior_ttm = sum(q["revenue"] for q in quarters_with_revenue[4:8])

        if prior_ttm > 0:
            ttm_growth = (current_ttm - prior_ttm) / prior_ttm
            logger.info(
                "Calculated TTM revenue growth: %.1f%% (TTM: $%.0fM vs $%.0fM)",
                ttm_growth * 100,
                current_ttm,
                prior_ttm,
            )
            return ttm_growth

    # Method 2: Same-quarter YoY (fallback)
    # Find the most recent quarter and compare to same quarter from prior year
    if len(quarters_with_revenue) >= 2:
        current = quarters_with_revenue[0]
        current_period = current["period"]
        current_revenue = current["revenue"]

        # Find same quarter from prior year
        for q in quarters_with_revenue[1:]:
            if q["period"] == current_period and q["fy"] < current["fy"]:
                prior_revenue = q["revenue"]
                if prior_revenue > 0:
                    yoy_growth = (current_revenue - prior_revenue) / prior_revenue
                    logger.info(
                        "Calculated same-quarter YoY growth: %.1f%% (%s %s vs %s %s: $%.0fM vs $%.0fM)",
                        yoy_growth * 100,
                        current["fy"],
                        current_period,
                        q["fy"],
                        q["period"],
                        current_revenue,
                        prior_revenue,
                    )
                    return yoy_growth
                break

    logger.warning("Could not calculate revenue growth: insufficient data")
    return None

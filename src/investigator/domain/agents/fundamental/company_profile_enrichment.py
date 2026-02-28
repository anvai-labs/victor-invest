"""Helpers for enriching CompanyProfile instances from fetched company data."""

from __future__ import annotations

from typing import Any, Dict, Optional

from investigator.domain.services.valuation.models import (
    CompanyArchetype,
    DataQualityFlag,
)

from .models import QuarterlyData


def _calculate_market_cap_with_split_adjustment(
    symbol: str,
    current_price: float,
    shares_outstanding: float,
    shares_source: str = "tickerdata",
) -> Optional[float]:
    """
    Calculate market cap with proper split adjustment.

    Args:
        symbol: Stock ticker
        current_price: Current stock price
        shares_outstanding: Shares outstanding
        shares_source: "tickerdata" (split-adjusted) or "sec" (actual)

    Returns:
        Market cap or None if calculation fails
    """
    try:
        if shares_source == "tickerdata":
            # Both price and shares are split-adjusted
            return float(current_price) * float(shares_outstanding)
        else:
            # Shares from SEC need split adjustment for historical prices
            from investigator.domain.services.valuation_shared.split_adjusted_market_cap import (
                calculate_market_cap,
            )

            return calculate_market_cap(
                symbol=symbol,
                price=current_price,
                shares=shares_outstanding,
                price_date=None,  # Current date
                shares_source=shares_source,
            )
    except (TypeError, ValueError):
        return None


def enrich_company_profile(
    *,
    profile: Any,
    symbol: str,
    sector: str,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    financials: Dict[str, Any],
    market_data: Dict[str, Any],
    data_quality: Dict[str, Any],
    logger: Any,
) -> None:
    """Populate profile attributes and archetype/quality flags from loaded fundamentals."""
    ttm_metrics = company_data.get("ttm_metrics", {})

    free_cash_flow = (
        ttm_metrics.get("free_cash_flow") or ttm_metrics.get("FreeCashFlow") or financials.get("free_cash_flow") or 0
    )
    revenue = (
        ttm_metrics.get("revenues")
        or ttm_metrics.get("total_revenue")
        or financials.get("revenues")
        or financials.get("total_revenue")
        or 0
    )
    net_income = ttm_metrics.get("net_income") or ttm_metrics.get("NetIncomeLoss") or financials.get("net_income") or 0
    ebitda = (
        ttm_metrics.get("ebitda")
        or ttm_metrics.get("operating_income")
        or financials.get("ebitda")
        or financials.get("operating_income")
        or 0
    )

    logger.info(
        "%s - _build_company_profile extracted values: FCF=$%.2fB, Revenue=$%.2fB, NetIncome=$%.2fB, EBITDA=$%.2fB",
        symbol,
        free_cash_flow / 1e9,
        revenue / 1e9,
        net_income / 1e9,
        ebitda / 1e9,
    )

    profile.has_positive_fcf = (free_cash_flow or 0) > 0
    profile.has_positive_earnings = (net_income or 0) > 0
    profile.has_positive_ebitda = (ebitda or 0) > 0
    profile.ttm_fcf = free_cash_flow
    profile.fcf_margin = (free_cash_flow / revenue) if revenue else None
    profile.free_cash_flow = free_cash_flow
    profile.ebitda = ebitda
    profile.net_income = net_income
    profile.revenue = revenue

    revenue_growth_yoy = ratios.get("revenue_growth") or ratios.get("revenue_growth_yoy")
    if revenue_growth_yoy is None:
        quarterly_data = company_data.get("quarterly_data", [])
        if quarterly_data and len(quarterly_data) >= 5:
            try:
                revenues = []
                for quarter in quarterly_data[:8]:
                    if isinstance(quarter, QuarterlyData):
                        rev = quarter.financial_data.get("revenues", 0)
                    elif isinstance(quarter, dict):
                        rev = quarter.get("financial_data", {}).get("revenues", 0) or quarter.get("revenues", 0)
                    else:
                        rev = 0
                    revenues.append(float(rev) if rev else 0)
                if len(revenues) >= 5 and revenues[4] > 0:
                    revenue_growth_yoy = (revenues[0] - revenues[4]) / revenues[4]
                    logger.debug(
                        "%s - Calculated revenue_growth_yoy from quarterly data: %.1f%%",
                        symbol,
                        revenue_growth_yoy * 100,
                    )
            except Exception as exc:
                logger.warning("%s - Failed to calculate revenue_growth_yoy: %s", symbol, exc)

    profile.revenue_growth_yoy = revenue_growth_yoy
    profile.earnings_growth_yoy = ratios.get("earnings_growth") or ratios.get("earnings_growth_yoy")
    profile.revenue_volatility = ratios.get("revenue_volatility")
    profile.gross_margin_trend = ratios.get("gross_margin_trend")
    profile.gross_margin = ratios.get("gross_margin")
    profile.net_revenue_retention = ratios.get("net_revenue_retention")
    profile.ebitda_margin_trend = ratios.get("ebitda_margin_trend")
    profile.return_on_equity = ratios.get("return_on_equity") or ratios.get("roe")
    profile.earnings_quality_score = ratios.get("earnings_quality_score")

    total_debt = financials.get("total_debt") or 0
    cash = financials.get("cash") or 0
    net_debt = total_debt - cash if total_debt is not None and cash is not None else None
    profile.net_debt_to_ebitda = (
        (net_debt / ebitda) if ebitda not in (None, 0) and net_debt is not None else ratios.get("net_debt_to_ebitda")
    )
    profile.interest_coverage = ratios.get("interest_coverage")
    profile.debt_to_equity = ratios.get("debt_to_equity") or ratios.get("debt_to_capital")

    dividends_paid = abs(
        ttm_metrics.get("dividends_paid")
        or ttm_metrics.get("PaymentsOfDividends")
        or ttm_metrics.get("payments_of_dividends")
        or financials.get("dividends_paid")
        or financials.get("PaymentsOfDividends")
        or 0
    )
    # Use diluted shares for dual-class companies (e.g., GOOGL)
    shares_outstanding = (
        financials.get("weighted_average_diluted_shares_outstanding")  # PRIORITY 1: Industry standard for EPS
        or financials.get("shares_outstanding_diluted")  # PRIORITY 2: Legacy field (doesn't exist in DB)
        or financials.get("shares_outstanding")  # PRIORITY 3: Basic shares
        or market_data.get("shares_outstanding")  # PRIORITY 4: Market data fallback
    )
    profile.pays_dividends = dividends_paid > 0
    profile.dividends_paid = dividends_paid
    logger.info(
        "%s - dividends_paid extracted: $%.2fB, pays_dividends=%s",
        symbol,
        dividends_paid / 1e9,
        profile.pays_dividends,
    )
    profile.dividend_yield = ratios.get("dividend_yield") or market_data.get("dividend_yield")
    profile.dividend_payout_ratio = ratios.get("payout_ratio") or ratios.get("dividend_payout_ratio")
    profile.dividend_growth_rate = ratios.get("dividend_growth_rate")

    profile.book_value_per_share = ratios.get("book_value_per_share")
    # For dual-class companies (e.g., GOOGL), use diluted shares to capture all classes
    # Otherwise DCF valuation divides by too few shares, inflating per-share value
    # CRITICAL: Use weighted_average_diluted_shares_outstanding for accurate EPS calculations
    profile.shares_outstanding = (
        financials.get("weighted_average_diluted_shares_outstanding")  # PRIORITY 1: Industry standard for EPS
        or financials.get("shares_outstanding_diluted")  # PRIORITY 2: Legacy field (doesn't exist in DB)
        or financials.get("shares_outstanding")  # PRIORITY 3: Basic shares (may be single class)
        or ratios.get("shares_outstanding")
        or company_data.get("shares_outstanding")
        or market_data.get("shares_outstanding")
    )

    cash_candidates = [
        financials.get("cash"),
        financials.get("cash_and_equivalents"),
        financials.get("cash_and_cash_equivalents"),
    ]
    profile.cash = next((float(c) for c in cash_candidates if c is not None), None)

    debt_candidates = [
        financials.get("total_debt"),
        financials.get("long_term_debt"),
        financials.get("total_liabilities"),
        market_data.get("total_debt"),
    ]
    profile.total_debt = next((float(d) for d in debt_candidates if d is not None), None)
    profile.current_price = (
        market_data.get("price")
        or market_data.get("close")
        or market_data.get("current_price")
        or ratios.get("current_price")
    )
    profile.market_cap = market_data.get("market_cap") or market_data.get("market_capitalization")
    if not profile.market_cap and profile.current_price and profile.shares_outstanding:
        # Calculate market cap with split adjustment
        # Determine shares source: SEC data is actual, tickerdata is split-adjusted
        shares_source = (
            "sec" if financials.get("shares_outstanding") or company_data.get("shares_outstanding") else "tickerdata"
        )
        profile.market_cap = _calculate_market_cap_with_split_adjustment(
            symbol=symbol,
            current_price=float(profile.current_price),
            shares_outstanding=float(profile.shares_outstanding),
            shares_source=shares_source,
        )

    profile.beta = market_data.get("beta") or market_data.get("five_year_beta") or ratios.get("beta")
    average_volume = (
        market_data.get("average_daily_volume")
        or market_data.get("avg_daily_volume")
        or market_data.get("three_month_avg_volume")
    )
    if average_volume and profile.current_price:
        profile.daily_liquidity_usd = float(average_volume) * float(profile.current_price)
        if profile.daily_liquidity_usd < 5_000_000:
            profile.add_flag(DataQualityFlag.LOW_LIQUIDITY)

    quarters = company_data.get("quarterly_data") or []
    profile.quarters_available = len(quarters)
    if profile.quarters_available and profile.quarters_available < 8:
        profile.add_flag(DataQualityFlag.MISSING_QUARTERS)

    dq_score = data_quality.get("data_quality_score")
    if isinstance(dq_score, (int, float)):
        profile.data_completeness_score = max(0.0, min(float(dq_score) / 100.0, 1.0))
    if data_quality.get("consistency_issues"):
        profile.add_flag(DataQualityFlag.OUTLIER_DETECTED)
    if data_quality.get("stale_data"):
        profile.add_flag(DataQualityFlag.STALE_REFERENCE_DATA)

    profile.rule_of_40_score = company_data.get("rule_of_40_score")
    profile.rule_of_40_classification = company_data.get("rule_of_40_classification")
    if shares_outstanding:
        profile.dividend_yield = profile.dividend_yield or (
            (dividends_paid / shares_outstanding) / (profile.current_price or 1) if profile.current_price else None
        )

    revenue_growth = profile.revenue_growth_yoy or 0
    rule_of_40 = profile.rule_of_40_score or 0
    payout_ratio = profile.dividend_payout_ratio or 0
    pays_dividends = profile.pays_dividends or False

    if rule_of_40 > 40 or revenue_growth > 0.20:
        profile.primary_archetype = CompanyArchetype.HIGH_GROWTH
        logger.info(
            "%s - Detected HIGH_GROWTH archetype (Rule of 40: %.1f%%, Revenue Growth: %.1f%%)",
            symbol,
            rule_of_40,
            revenue_growth * 100,
        )
    elif pays_dividends and payout_ratio >= 40:
        profile.primary_archetype = CompanyArchetype.MATURE_DIVIDEND
        logger.info(
            "%s - Detected MATURE_DIVIDEND archetype (Payout: %s)",
            symbol,
            f"{payout_ratio:.1f}%",
        )
    elif sector in ["Banks", "Financial Services", "Insurance", "Financials"]:
        profile.primary_archetype = CompanyArchetype.FINANCIAL
        logger.info("%s - Detected FINANCIAL archetype (Sector: %s)", symbol, sector)
    elif sector in ["Energy", "Materials", "Industrials"]:
        profile.primary_archetype = CompanyArchetype.CYCLICAL
        logger.info("%s - Detected CYCLICAL archetype (Sector: %s)", symbol, sector)
    else:
        logger.debug(
            "%s - No primary archetype detected (Rule of 40: %.1f%%, Revenue Growth: %.1f%%, Sector: %s)",
            symbol,
            rule_of_40,
            revenue_growth * 100,
            sector,
        )

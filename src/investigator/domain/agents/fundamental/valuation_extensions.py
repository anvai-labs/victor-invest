"""Helpers for GGM and extension valuation models (Damodaran, Rule of 40, SaaS)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from investigator.domain.services.valuation.damodaran_dcf import DamodaranDCFModel
from investigator.domain.services.valuation.models.saas_valuation import (
    SaaSValuationModel,
)
from investigator.domain.services.valuation.rule_of_40_valuation import (
    RuleOf40Valuation,
)


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_percent(value: Any) -> float | None:
    """
    Normalize payout ratio to percentage points.

    Examples:
      0.42 -> 42.0
      42 -> 42.0
    """
    numeric = _to_float(value)
    if numeric <= 0:
        return None
    pct = numeric * 100.0 if numeric <= 1.5 else numeric
    if pct <= 0 or pct > 500:
        return None
    return pct


def _to_ratio(value: Any) -> float | None:
    """
    Normalize payout ratio to ratio format.

    Examples:
      0.42 -> 0.42
      42 -> 0.42
    """
    numeric = _to_float(value)
    if numeric <= 0:
        return None
    ratio = numeric / 100.0 if numeric > 1.5 else numeric
    if ratio <= 0 or ratio > 5.0:
        return None
    return ratio


def _to_yield_decimal(value: Any) -> float | None:
    """
    Normalize dividend yield to decimal.

    Examples:
      0.031 -> 0.031
      3.1 -> 0.031
    """
    numeric = _to_float(value)
    if numeric <= 0:
        return None
    yld = numeric / 100.0 if numeric > 1 else numeric
    if yld <= 0 or yld >= 1:
        return None
    return yld


async def calculate_valuation_extensions(
    *,
    symbol: str,
    valuation_results: dict[str, Any],
    financials: dict[str, Any],
    ratios: dict[str, Any],
    market_data: dict[str, Any],
    company_profile: Any,
    quarterly_data: list[Any],
    calculate_cost_of_equity: Callable[[str], float],
    calculate_ggm: Callable[[str, float, list[Any], Any], Awaitable[dict[str, Any]]],
    normalize_model_output: Callable[[Any], dict[str, Any]],
    log_model_result: Callable[[Any, str, str, dict[str, Any]], None],
    logger: Any,
) -> float:
    """Populate extension valuation models and return payout ratio used for synthesis context."""
    common_divs = abs(_to_float(financials.get("dividends_paid", 0) or 0))
    profile_common_divs = abs(_to_float(getattr(company_profile, "dividends_paid", None) or 0))
    common_divs = max(common_divs, profile_common_divs)
    preferred_divs = abs(_to_float(financials.get("preferred_stock_dividends", 0) or 0))
    dividends_paid = common_divs + preferred_divs

    if preferred_divs > 0:
        logger.debug(
            "%s - Preferred stock dividends found: $%s (27%% coverage - rare field)",
            symbol,
            format(preferred_divs, ",.0f"),
        )

    net_income = _to_float(financials.get("net_income", 0) or 0)

    payout_ratio_candidates = []
    for source, value in (
        ("financials.payout_ratio", financials.get("payout_ratio")),
        ("financials.dividend_payout_ratio", financials.get("dividend_payout_ratio")),
        ("ratios.payout_ratio", ratios.get("payout_ratio")),
        ("ratios.dividend_payout_ratio", ratios.get("dividend_payout_ratio")),
        (
            "company_profile.dividend_payout_ratio",
            getattr(company_profile, "dividend_payout_ratio", None),
        ),
    ):
        pct = _to_percent(value)
        if pct is not None:
            payout_ratio_candidates.append((pct, source))

    payout_ratio_from_ratios = max((pct for pct, _ in payout_ratio_candidates), default=None)
    if len(payout_ratio_candidates) >= 2:
        min_pct = min(pct for pct, _ in payout_ratio_candidates)
        max_pct = max(pct for pct, _ in payout_ratio_candidates)
        if min_pct > 0 and max_pct >= 20 and (max_pct / min_pct) >= 5:
            logger.warning(
                "%s - Payout ratio source mismatch detected: %s. Using highest plausible value %.1f%%",
                symbol,
                ", ".join([f"{src}={pct:.1f}%" for pct, src in payout_ratio_candidates]),
                max_pct,
            )

    dividend_yield = (
        _to_yield_decimal(financials.get("dividend_yield"))
        or _to_yield_decimal(ratios.get("dividend_yield"))
        or _to_yield_decimal(getattr(company_profile, "dividend_yield", None))
    )
    market_cap = (
        _to_float(market_data.get("market_cap"))
        or _to_float(market_data.get("market_capitalization"))
        or _to_float(market_data.get("mktcap"))
        or _to_float(getattr(company_profile, "market_cap", None))
    )

    # Recovery path: if dividends are missing from raw extracts, infer from payout ratio.
    if common_divs <= 0 and net_income > 0 and payout_ratio_from_ratios:
        inferred_common_divs = net_income * (payout_ratio_from_ratios / 100.0)
        if inferred_common_divs > 0:
            common_divs = inferred_common_divs
            dividends_paid = common_divs + preferred_divs
            logger.info(
                "%s - Inferred dividends_paid from payout ratio %.1f%%: $%s",
                symbol,
                payout_ratio_from_ratios,
                format(dividends_paid, ",.0f"),
            )

    # Secondary recovery: infer annual dividends from dividend yield and market cap.
    if common_divs <= 0 and dividend_yield and market_cap > 0:
        inferred_common_divs = market_cap * dividend_yield
        if inferred_common_divs > 0:
            common_divs = inferred_common_divs
            dividends_paid = common_divs + preferred_divs
            logger.info(
                "%s - Inferred dividends_paid from dividend yield %.2f%% and market cap: $%s",
                symbol,
                dividend_yield * 100.0,
                format(dividends_paid, ",.0f"),
            )

    payout_ratio_from_yield = (
        (market_cap * dividend_yield / net_income * 100.0)
        if (dividend_yield and market_cap > 0 and net_income > 0)
        else None
    )
    payout_ratio_from_cashflow = (
        (dividends_paid / net_income * 100) if (net_income > 0 and dividends_paid > 0) else None
    )

    reference_payout = max(payout_ratio_from_ratios or 0.0, payout_ratio_from_yield or 0.0) or None

    # If payout ratio from ratios/yield is much higher than cashflow-derived ratio, treat this
    # as a likely scale/period mismatch in extracted dividends and trust normalized ratio.
    if (
        reference_payout
        and net_income > 0
        and (
            payout_ratio_from_cashflow is None
            or payout_ratio_from_cashflow <= 0
            or payout_ratio_from_cashflow < (0.5 * reference_payout)
        )
    ):
        inferred_common_divs = net_income * (reference_payout / 100.0)
        if inferred_common_divs > common_divs:
            common_divs = inferred_common_divs
            dividends_paid = common_divs + preferred_divs
            logger.warning(
                "%s - Dividend scale mismatch detected (cashflow payout %.2f%% vs reference payout %.2f%%). "
                "Using inferred dividends from payout/yield: $%s",
                symbol,
                payout_ratio_from_cashflow or 0.0,
                reference_payout,
                format(dividends_paid, ",.0f"),
            )
        payout_ratio = reference_payout
    else:
        payout_ratio = payout_ratio_from_cashflow if payout_ratio_from_cashflow is not None else (reference_payout or 0)

    payout_ratio_ratio = _to_ratio(payout_ratio)
    if payout_ratio_ratio is not None:
        financials["payout_ratio"] = payout_ratio_ratio
        ratios["payout_ratio"] = payout_ratio_ratio
        if ratios.get("dividend_payout_ratio") in (None, 0):
            ratios["dividend_payout_ratio"] = payout_ratio_ratio
    if dividends_paid > 0:
        financials["dividends_paid"] = dividends_paid

    is_significant_dividend_stock = dividends_paid > 0 and payout_ratio >= 20.0

    if is_significant_dividend_stock:
        cost_of_equity = calculate_cost_of_equity(symbol)
        logger.info("%s - GGM cost_of_equity passed: %.2f%%", symbol, cost_of_equity * 100)
        ggm_result = await calculate_ggm(symbol, cost_of_equity, quarterly_data, company_profile)
        ggm_result = dict(ggm_result or {})
        ggm_result["model"] = "ggm"
        valuation_results["ggm"] = ggm_result
        logger.info(
            "%s - GGM applicable: payout ratio %.1f%% (≥20%% threshold for meaningful dividend policy)",
            symbol,
            payout_ratio,
        )
        log_model_result(logger, symbol, "GGM", ggm_result)
    else:
        if dividends_paid > 0 and payout_ratio < 20.0:
            reason = (
                f"Low payout ratio ({payout_ratio:.1f}%) - token dividend, not meaningful dividend policy (need ≥20%)"
            )
        elif dividends_paid == 0:
            reason = "No dividends paid - GGM requires dividend-paying stock"
        else:
            reason = "Negative net income - cannot calculate meaningful payout ratio"

        ggm_result = {
            "model": "ggm",
            "applicable": False,
            "reason": reason,
            "fair_value_per_share": 0,
            "payout_ratio": payout_ratio,
        }
        valuation_results["ggm"] = ggm_result
        logger.info("%s - GGM not applicable: %s", symbol, reason)
        log_model_result(logger, symbol, "GGM", ggm_result)

    try:
        damodaran_model = DamodaranDCFModel(company_profile)
        damodaran_result = damodaran_model.calculate(
            current_fcf=financials.get("free_cash_flow") or financials.get("fcf"),
            revenue_growth=company_profile.revenue_growth_yoy,
            fcf_margin=ratios.get("fcf_margin") or ratios.get("free_cash_flow_margin"),
            current_revenue=financials.get("revenues") or financials.get("revenue") or financials.get("total_revenue"),
            shares_outstanding=company_profile.shares_outstanding,
        )
        normalized_damodaran = normalize_model_output(damodaran_result)
        valuation_results["damodaran_dcf"] = normalized_damodaran
        log_model_result(logger, symbol, "Damodaran DCF", normalized_damodaran)
    except Exception as exc:
        logger.warning("%s - Damodaran DCF failed: %s", symbol, exc)
        valuation_results["damodaran_dcf"] = {
            "applicable": False,
            "reason": str(exc),
            "model": "damodaran_dcf",
        }

    is_saas_company = bool(
        company_profile.industry
        and any(kw in company_profile.industry.lower() for kw in ["software", "saas", "cloud", "internet"])
    )
    is_growth_company = bool(company_profile.revenue_growth_yoy and company_profile.revenue_growth_yoy > 0.10)

    if is_saas_company or is_growth_company:
        try:
            rule_of_40_model = RuleOf40Valuation(company_profile)
            rule_of_40_result = rule_of_40_model.calculate(
                revenue_growth=company_profile.revenue_growth_yoy,
                fcf_margin=ratios.get("fcf_margin") or ratios.get("free_cash_flow_margin"),
                current_revenue=financials.get("revenues")
                or financials.get("revenue")
                or financials.get("total_revenue"),
                current_price=market_data.get("price") or market_data.get("close") or market_data.get("current_price"),
                shares_outstanding=company_profile.shares_outstanding,
            )
            normalized_rule_of_40 = normalize_model_output(rule_of_40_result)
            valuation_results["rule_of_40"] = normalized_rule_of_40
            log_model_result(logger, symbol, "Rule of 40", normalized_rule_of_40)
        except Exception as exc:
            logger.warning("%s - Rule of 40 failed: %s", symbol, exc)
            valuation_results["rule_of_40"] = {
                "applicable": False,
                "reason": str(exc),
                "model": "rule_of_40",
            }
    else:
        valuation_results["rule_of_40"] = {
            "applicable": False,
            "reason": "Not a growth/SaaS company (requires >10% revenue growth or SaaS industry)",
            "model": "rule_of_40",
        }

    if is_saas_company:
        try:
            saas_model = SaaSValuationModel(company_profile)
            saas_result = saas_model.calculate(
                revenue_growth=company_profile.revenue_growth_yoy,
                current_revenue=financials.get("revenues")
                or financials.get("revenue")
                or financials.get("total_revenue"),
                current_price=market_data.get("price") or market_data.get("close") or market_data.get("current_price"),
                shares_outstanding=company_profile.shares_outstanding,
                gross_margin=ratios.get("gross_margin") or ratios.get("gross_profit_margin"),
                nrr=ratios.get("net_revenue_retention") or ratios.get("nrr"),
                ltv_cac=ratios.get("ltv_cac") or ratios.get("ltv_cac_ratio"),
                fcf_margin=ratios.get("fcf_margin") or ratios.get("free_cash_flow_margin"),
            )
            normalized_saas = normalize_model_output(saas_result)
            valuation_results["saas"] = normalized_saas
            log_model_result(logger, symbol, "SaaS", normalized_saas)
        except Exception as exc:
            logger.warning("%s - SaaS valuation failed: %s", symbol, exc)
            valuation_results["saas"] = {
                "applicable": False,
                "reason": str(exc),
                "model": "saas",
            }
    else:
        valuation_results["saas"] = {
            "applicable": False,
            "reason": "Not a SaaS company (requires software/cloud/internet industry)",
            "model": "saas",
        }

    return payout_ratio

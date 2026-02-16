"""Helpers for cost-of-capital input hydration, diagnostics, and penalties."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


def hydrate_cost_of_capital_inputs(
    *,
    profile: Any,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    symbol: str,
    get_stock_info: Callable[[str], Dict[str, Any]],
    require_financials: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Populate missing beta/debt/coverage inputs from available company data."""
    market_data = company_data.get("market_data", {})
    stock_info: Dict[str, Any] = {}
    try:
        stock_info = get_stock_info(symbol) or {}
    except Exception:
        stock_info = {}

    if getattr(profile, "beta", None) is None:
        fallback_beta = (
            ratios.get("beta")
            or market_data.get("beta")
            or company_data.get("beta")
            or stock_info.get("beta")
        )
        try:
            if fallback_beta is not None:
                profile.beta = float(fallback_beta)
        except (TypeError, ValueError):
            pass

    financials = require_financials(company_data)
    if getattr(profile, "total_debt", None) is None:
        total_debt = financials.get("total_debt")
        if total_debt is None:
            long_term_debt = financials.get("long_term_debt")
            short_term_debt = financials.get("short_term_debt")
            if long_term_debt is not None or short_term_debt is not None:
                total_debt = (long_term_debt or 0) + (short_term_debt or 0)
        if total_debt is not None:
            profile.total_debt = total_debt

    if getattr(profile, "interest_coverage", None) is None:
        coverage = ratios.get("interest_coverage") or company_data.get(
            "interest_coverage"
        )
        if coverage is not None:
            profile.interest_coverage = coverage

    if financials.get("interest_expense") in (None, 0):
        derived_interest = company_data.get("facts", {}).get("interest_expense")
        if derived_interest:
            financials["interest_expense"] = derived_interest


def evaluate_cost_of_capital_inputs(
    *,
    profile: Any,
    company_data: Dict[str, Any],
    require_financials: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> List[str]:
    """Identify missing inputs that force DCF/WACC fallback assumptions."""
    issues: List[str] = []
    if getattr(profile, "beta", None) is None:
        issues.append("missing_beta")

    financials = require_financials(company_data)
    total_debt = getattr(profile, "total_debt", None)
    if total_debt is None:
        total_debt = financials.get("total_debt")

    interest_expense = financials.get("interest_expense")
    if (total_debt or 0) > 0 and not interest_expense:
        issues.append("missing_interest_expense")
    if (total_debt or 0) > 0 and not getattr(profile, "interest_coverage", None):
        issues.append("missing_interest_coverage")

    return issues


def apply_cost_of_capital_penalty(
    *,
    valuation_dict: Dict[str, Any],
    issues: List[str],
) -> Dict[str, Any]:
    """Reduce valuation confidence when cost-of-capital inputs were missing."""
    if not issues or not isinstance(valuation_dict, dict):
        return valuation_dict
    if not valuation_dict.get("applicable", True):
        return valuation_dict

    penalty = min(0.15 * len(issues), 0.45)
    current_confidence = valuation_dict.get("confidence_score") or 0.0
    valuation_dict["confidence_score"] = max(0.0, current_confidence - penalty)

    diagnostics = valuation_dict.get("diagnostics") or {}
    flags = diagnostics.get("flags") or []
    for issue in issues:
        flag = f"COST_INPUT_{issue.upper()}"
        if flag not in flags:
            flags.append(flag)
    diagnostics["flags"] = flags

    diag_score = diagnostics.get("data_quality_score")
    if isinstance(diag_score, (int, float)):
        diagnostics["data_quality_score"] = max(0.0, diag_score - (penalty * 100))
    else:
        diagnostics["data_quality_score"] = max(0.0, 100 - (penalty * 100))
    valuation_dict["diagnostics"] = diagnostics

    metadata = valuation_dict.get("metadata") or {}
    metadata["cost_of_capital_issues"] = issues
    valuation_dict["metadata"] = metadata
    return valuation_dict

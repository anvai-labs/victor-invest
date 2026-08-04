"""Relative valuation model computation helpers."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from investigator.domain.services.valuation.helpers import normalize_model_output
from investigator.domain.services.valuation.models import (
    EVEBITDAModel,
    PBMultipleModel,
    PEMultipleModel,
    PSMultipleModel,
)
from investigator.domain.services.valuation.models.common import clamp

_VALID_VALUATION_BASIS = {"ttm", "forward"}
_FORWARD_HORIZON_TO_QUARTERS = {"1q": 1, "2q": 2, "3q": 3, "1y": 4}


def _normalize_basis_inputs(
    *,
    symbol: str,
    valuation_basis: str | None,
    forward_horizon: str | None,
    logger: Any,
) -> tuple[str, str]:
    basis = str(valuation_basis or "ttm").strip().lower()
    horizon = str(forward_horizon or "1y").strip().lower()

    if basis not in _VALID_VALUATION_BASIS:
        logger.warning(
            "%s - Invalid valuation_basis '%s'; falling back to 'ttm'",
            symbol,
            valuation_basis,
        )
        basis = "ttm"
    if horizon not in _FORWARD_HORIZON_TO_QUARTERS:
        logger.warning(
            "%s - Invalid forward_horizon '%s'; falling back to '1y'",
            symbol,
            forward_horizon,
        )
        horizon = "1y"

    if basis == "ttm":
        logger.info("%s - Relative valuation input basis: TTM", symbol)
    else:
        logger.info("%s - Relative valuation input basis: FORWARD (%s)", symbol, horizon)

    return basis, horizon


def _annual_growth_factor(
    *,
    growth_value: float | None,
    forward_horizon: str,
) -> float:
    if growth_value is None:
        return 1.0

    try:
        growth = float(growth_value)
    except (TypeError, ValueError):
        return 1.0

    # Accept either decimal (0.25) or percentage (25.0) inputs.
    if abs(growth) > 2.0:
        growth /= 100.0

    growth = clamp(growth, -0.75, 2.5)
    quarters = _FORWARD_HORIZON_TO_QUARTERS.get(forward_horizon, 4)
    exponent = quarters / 4.0
    return float(max((1.0 + growth) ** exponent, 0.1))


def _normalize_growth_value(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if abs(parsed) > 2.0:
        parsed /= 100.0
    return clamp(parsed, -0.75, 2.5)


def _normalize_share_count(value: Any) -> float | None:
    try:
        shares = float(value)
    except (TypeError, ValueError):
        return None
    if shares <= 0:
        return None

    original_shares = shares
    # Guard against SEC payloads that encode shares in millions.
    if shares < 100_000:
        shares *= 1_000_000.0
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "[SHARES_NORMALIZE] Shares value < 100,000 (%s) - multiplying by 1M: %s -> %s",
            format(original_shares, ",.0f"),
            format(original_shares, ",.0f"),
            format(shares, ",.0f"),
        )
    return shares


def _extract_midpoint(value: Any) -> tuple[float | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    mid = value.get("mid")
    low_val = value.get("low")
    high_val = value.get("high")
    if mid is None and low_val is not None and high_val is not None:
        try:
            mid = (float(low_val) + float(high_val)) / 2.0
        except (TypeError, ValueError):
            mid = None
    try:
        mid_float = float(mid) if mid is not None else None
    except (TypeError, ValueError):
        mid_float = None
    horizon = str(value.get("horizon") or "1y").strip().lower()
    if horizon not in _FORWARD_HORIZON_TO_QUARTERS:
        horizon = "1y"
    return mid_float, horizon


def _annualize_by_horizon(value: float, horizon: str) -> float:
    quarters = _FORWARD_HORIZON_TO_QUARTERS.get(horizon, 4)
    return value * (4.0 / max(quarters, 1))


def _is_plausible_eps_override(*, annualized_eps: float | None, base_eps: float | None) -> bool:
    if annualized_eps is None:
        return False
    try:
        annualized = float(annualized_eps)
    except (TypeError, ValueError):
        return False
    if annualized <= 0:
        return False

    if base_eps is None:
        return True
    try:
        baseline = float(base_eps)
    except (TypeError, ValueError):
        return True
    if baseline <= 0.01:
        return True

    ratio = annualized / baseline
    return 0.2 <= ratio <= 5.0


def _resolve_guidance_overrides(
    *,
    guidance_context: dict[str, Any] | None,
    base_eps: float | None,
    base_revenue: float | None,
) -> tuple[float | None, float | None, float | None, dict[str, Any]]:
    """
    Convert extracted guidance payload into growth overrides for forward valuation.

    Returns:
      (revenue_growth_override, earnings_growth_override, annualized_eps_override, metadata)
    """
    if not isinstance(guidance_context, dict) or not guidance_context:
        return None, None, None, {}

    metadata: dict[str, Any] = {
        "guidance_source_form": guidance_context.get("source_form"),
        "guidance_confidence_score": guidance_context.get("confidence_score"),
    }

    revenue_growth = _normalize_growth_value(guidance_context.get("revenue_growth_guidance"))
    earnings_growth = _normalize_growth_value(guidance_context.get("earnings_growth_guidance"))
    annualized_eps_override: float | None = None

    revenue_mid, revenue_horizon = _extract_midpoint(guidance_context.get("revenue_guidance"))
    if revenue_mid is not None:
        metadata["guidance_revenue_mid"] = revenue_mid
        metadata["guidance_revenue_horizon"] = revenue_horizon
        if base_revenue and base_revenue > 0:
            annualized_revenue = _annualize_by_horizon(revenue_mid, revenue_horizon or "1y")
            implied_growth = (annualized_revenue / float(base_revenue)) - 1.0
            implied_growth = clamp(implied_growth, -0.75, 2.5)
            metadata["guidance_revenue_growth_implied"] = implied_growth
            if revenue_growth is None:
                revenue_growth = implied_growth

    eps_mid, eps_horizon = _extract_midpoint(guidance_context.get("eps_guidance"))
    if eps_mid is not None:
        annualized_eps_candidate = _annualize_by_horizon(eps_mid, eps_horizon or "1y")
        if _is_plausible_eps_override(annualized_eps=annualized_eps_candidate, base_eps=base_eps):
            metadata["guidance_eps_mid"] = eps_mid
            metadata["guidance_eps_horizon"] = eps_horizon
            annualized_eps_override = annualized_eps_candidate
            metadata["guidance_eps_annualized"] = annualized_eps_override
            if base_eps and base_eps > 0:
                implied_growth = (annualized_eps_override / float(base_eps)) - 1.0
                implied_growth = clamp(implied_growth, -0.75, 2.5)
                metadata["guidance_eps_growth_implied"] = implied_growth
                if earnings_growth is None:
                    earnings_growth = implied_growth
        else:
            metadata["guidance_eps_mid_rejected"] = eps_mid
            metadata["guidance_eps_horizon_rejected"] = eps_horizon
            metadata["guidance_eps_annualized_rejected"] = annualized_eps_candidate
            if base_eps and base_eps > 0:
                ratio = annualized_eps_candidate / float(base_eps)
                metadata["guidance_eps_rejected_reason"] = f"implausible_ratio_{ratio:.2f}x"
            else:
                metadata["guidance_eps_rejected_reason"] = "implausible_eps_override"

    if revenue_growth is not None:
        metadata["guidance_revenue_growth_used"] = revenue_growth
    if earnings_growth is not None:
        metadata["guidance_earnings_growth_used"] = earnings_growth

    return revenue_growth, earnings_growth, annualized_eps_override, metadata


def _attach_basis_metadata(
    *,
    model_output: Any,
    valuation_basis: str,
    forward_horizon: str,
    denominator_label: str,
    denominator_value: float | None,
) -> None:
    if not isinstance(model_output, dict):
        return

    assumptions = model_output.setdefault("assumptions", {})
    if isinstance(assumptions, dict):
        assumptions.setdefault("valuation_basis", valuation_basis)
        assumptions.setdefault("forward_horizon", forward_horizon)
        if denominator_value is not None:
            assumptions.setdefault(denominator_label, denominator_value)

    metadata = model_output.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata.setdefault("valuation_basis", valuation_basis)
        metadata.setdefault("forward_horizon", forward_horizon)


_logger = logging.getLogger(__name__)


def _lookup_industry_ev_ebitda(industry: str | None, config: Any) -> float | None:
    """Look up industry-level EV/EBITDA override from config."""
    if not industry:
        return None
    valuation_settings = getattr(config, "valuation", None)
    if isinstance(valuation_settings, dict):
        overrides = valuation_settings.get("ev_ebitda_industry_overrides", {})
    elif valuation_settings is not None:
        overrides = getattr(valuation_settings, "ev_ebitda_industry_overrides", {})
    else:
        return None
    if not isinstance(overrides, dict):
        return None
    value = overrides.get(industry)
    return float(value) if value is not None else None


def calculate_relative_valuation_models(
    *,
    symbol: str,
    company_profile: Any,
    company_data: dict[str, Any],
    ratios: dict[str, Any],
    financials: dict[str, Any],
    market_data: dict[str, Any],
    config: Any,
    sector_specific_result: dict[str, Any] | None,
    lookup_sector_multiple: Callable[[str | None, str, str | None], float | None],
    calculate_enterprise_value: Callable[[dict[str, Any], dict[str, Any]], float | None],
    logger: Any,
    valuation_basis: str = "ttm",
    forward_horizon: str = "1y",
    guidance_context: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Calculate P/E, EV/EBITDA, P/S and P/B model outputs."""
    valuation_basis, forward_horizon = _normalize_basis_inputs(
        symbol=symbol,
        valuation_basis=valuation_basis,
        forward_horizon=forward_horizon,
        logger=logger,
    )

    normalized_shares_outstanding = _normalize_share_count(
        getattr(company_profile, "shares_outstanding", None)
        or ratios.get("shares_outstanding")
        or financials.get("shares_outstanding")
    )

    base_eps = ratios.get("eps") or ratios.get("eps_basic") or ratios.get("eps_diluted")
    try:
        base_eps = float(base_eps) if base_eps is not None else None
    except (TypeError, ValueError):
        base_eps = None

    # DEBUG: Log EPS source and value
    logger.info(
        "[VALUATION_EPS_DEBUG] %s - EPS from ratios: eps=$%.2f, eps_basic=$%.2f, eps_diluted=$%.2f -> selected=$%.2f",
        symbol,
        ratios.get("eps") or 0,
        ratios.get("eps_basic") or 0,
        ratios.get("eps_diluted") or 0,
        base_eps or 0,
    )

    # Guard against unit-mismatched EPS values (e.g., shares encoded in millions).
    if base_eps is not None and abs(base_eps) > 500:
        net_income_candidate = financials.get("net_income") or ratios.get("net_income") or ratios.get("ttm_net_income")
        recomputed_eps = None
        if normalized_shares_outstanding and net_income_candidate is not None:
            try:
                recomputed_eps = float(net_income_candidate) / float(normalized_shares_outstanding)
            except (TypeError, ValueError, ZeroDivisionError):
                recomputed_eps = None

        logger.info(
            "[VALUATION_EPS_RECOMPUTE] %s - Implausible EPS=$%.2f. Attempting recompute: "
            "net_income=$%s, shares=%s -> recomputed=$%.2f",
            symbol,
            base_eps,
            format(net_income_candidate, ",.0f") if net_income_candidate else "N/A",
            format(normalized_shares_outstanding, ",.0f") if normalized_shares_outstanding else "N/A",
            recomputed_eps or 0,
        )

        if recomputed_eps is not None and math.isfinite(recomputed_eps) and abs(recomputed_eps) <= 500:
            logger.warning(
                "%s - Replacing implausible EPS input %.2f with recomputed EPS %.4f (net_income/shares)",
                symbol,
                base_eps,
                recomputed_eps,
            )
            base_eps = recomputed_eps
        else:
            logger.warning(
                "%s - Dropping implausible EPS input %.2f (no reliable recompute path)",
                symbol,
                base_eps,
            )
            base_eps = None
    revenue_growth = (
        ratios.get("revenue_growth_yoy")
        or ratios.get("revenue_growth")
        or getattr(company_profile, "revenue_growth_yoy", None)
    )
    earnings_growth = (
        ratios.get("earnings_growth_yoy")
        or ratios.get("earnings_growth")
        or getattr(company_profile, "earnings_growth_yoy", None)
        or revenue_growth
    )
    base_annual_revenue = ratios.get("ttm_revenue") or financials.get("revenues")
    guidance_metadata: dict[str, Any] = {}
    annualized_eps_override: float | None = None
    if valuation_basis == "forward":
        (
            guidance_revenue_growth,
            guidance_earnings_growth,
            annualized_eps_override,
            guidance_metadata,
        ) = _resolve_guidance_overrides(
            guidance_context=guidance_context,
            base_eps=base_eps,
            base_revenue=base_annual_revenue,
        )
        if guidance_revenue_growth is not None:
            revenue_growth = guidance_revenue_growth
        if guidance_earnings_growth is not None:
            earnings_growth = guidance_earnings_growth
        if guidance_metadata:
            logger.info(
                "%s - Applying filing guidance to forward valuation (form=%s, confidence=%s)",
                symbol,
                guidance_metadata.get("guidance_source_form", "unknown"),
                guidance_metadata.get("guidance_confidence_score", "n/a"),
            )

    ttm_eps = base_eps
    if valuation_basis == "forward" and ttm_eps is not None:
        if annualized_eps_override is not None and annualized_eps_override > 0:
            ttm_eps = annualized_eps_override
        else:
            ttm_eps = float(ttm_eps) * _annual_growth_factor(
                growth_value=earnings_growth,
                forward_horizon=forward_horizon,
            )

    sector_median_pe = (
        company_data.get("sector_metrics", {}).get("median_pe")
        or company_data.get("sector_data", {}).get("median_pe")
        or lookup_sector_multiple(company_profile.sector, "pe", company_profile.industry)
    )
    growth_adjusted_pe = None
    peg_ratio = ratios.get("peg_ratio") or ratios.get("peg")
    if sector_median_pe:
        try:
            if revenue_growth is not None:
                # Use shared GrowthCalculator for consistency
                try:
                    from investigator.domain.services.valuation.common import (
                        GrowthCalculator,
                    )

                    growth_multiplier = GrowthCalculator.calculate_growth_multiplier_pe(revenue_growth)
                except Exception:
                    # Fallback to inline calculation
                    growth_multiplier = clamp(1.0 + float(revenue_growth), 0.8, 2.5)
                growth_adjusted_pe = sector_median_pe * growth_multiplier
            elif peg_ratio and peg_ratio > 0:
                peg_clamped = clamp(float(peg_ratio), 0.5, 3.0)
                growth_adjusted_pe = sector_median_pe / peg_clamped
        except (TypeError, ValueError):
            growth_adjusted_pe = None

    current_price = (
        market_data.get("price")
        or market_data.get("close")
        or market_data.get("current_price")
        or ratios.get("current_price")
    )

    # SBC earnings quality penalty: when SBC is high relative to net income,
    # reduce earnings_quality_score to lower P/E model confidence in the blend.
    pe_earnings_quality = company_profile.earnings_quality_score
    sbc_for_quality = financials.get("stock_based_compensation") or financials.get("stock_based_compensation_expense")
    net_income_for_quality = financials.get("net_income") or financials.get("net_income_common")
    if sbc_for_quality and net_income_for_quality:
        try:
            sbc_val = float(sbc_for_quality)
            ni_val = float(net_income_for_quality)
            if sbc_val > 0 and ni_val > 0:
                sbc_to_ni = sbc_val / ni_val
                if sbc_to_ni > 0.30:
                    quality_penalty = clamp(sbc_to_ni - 0.30, 0.0, 0.3)
                    base_quality = pe_earnings_quality if pe_earnings_quality is not None else 0.7
                    pe_earnings_quality = max(base_quality - quality_penalty, 0.3)
                    logger.info(
                        "%s - SBC earnings quality penalty: SBC/NI=%.1f%%, quality %.2f→%.2f",
                        symbol,
                        sbc_to_ni * 100,
                        base_quality,
                        pe_earnings_quality,
                    )
        except (TypeError, ValueError):
            pass

    pe_model = PEMultipleModel(
        company_profile=company_profile,
        ttm_eps=ttm_eps,
        current_price=current_price,
        sector_median_pe=sector_median_pe,
        growth_adjusted_pe=growth_adjusted_pe,
        earnings_quality_score=pe_earnings_quality,
    )
    normalized_pe = normalize_model_output(pe_model.calculate())

    base_ttm_ebitda = (
        ratios.get("ttm_ebitda")
        or financials.get("ttm_ebitda")
        or financials.get("ebitda")
        or ratios.get("ebitda")
        or financials.get("operating_income")
    )

    # SBC add-back: EBITDA should exclude SBC for EV/EBITDA comparability.
    # Most sell-side comps use adjusted EBITDA (ex-SBC).
    sbc_annual = (
        financials.get("stock_based_compensation")
        or financials.get("stock_based_compensation_expense")
        or ratios.get("stock_based_compensation")
    )
    if base_ttm_ebitda and sbc_annual:
        try:
            sbc_float = float(sbc_annual)
            base_float = float(base_ttm_ebitda)
            if sbc_float > 0 and base_float > 0:
                sbc_ratio = sbc_float / base_float
                # Only add back if SBC is material (>5% of EBITDA)
                # Cap SBC add-back at 100% of base EBITDA to avoid extreme adjustments
                if sbc_ratio > 0.05:
                    sbc_addback = min(sbc_float, base_float)
                    base_ttm_ebitda = base_float + sbc_addback
                    logger.info(
                        "%s - SBC-adjusted EBITDA: base=%.2fB + SBC=%.2fB = %.2fB (SBC ratio=%.1f%%)",
                        symbol,
                        base_float / 1e9,
                        sbc_addback / 1e9,
                        float(base_ttm_ebitda) / 1e9,
                        sbc_ratio * 100,
                    )
        except (TypeError, ValueError):
            pass

    ebitda_growth = ratios.get("ebitda_growth_yoy") or ratios.get("ebitda_growth") or earnings_growth or revenue_growth
    ttm_ebitda = base_ttm_ebitda
    if valuation_basis == "forward" and ttm_ebitda is not None:
        ttm_ebitda = float(ttm_ebitda) * _annual_growth_factor(
            growth_value=ebitda_growth,
            forward_horizon=forward_horizon,
        )

    enterprise_value = calculate_enterprise_value(market_data, financials)
    sector_ev_ebitda = (
        company_data.get("sector_metrics", {}).get("median_ev_ebitda")
        or company_data.get("sector_data", {}).get("median_ev_ebitda")
        or _lookup_industry_ev_ebitda(company_profile.industry, config)
        or lookup_sector_multiple(company_profile.sector, "ev_ebitda", company_profile.industry)
    )

    leverage_adjusted_multiple = None
    if sector_ev_ebitda and company_profile.net_debt_to_ebitda is not None:
        leverage_delta = max(company_profile.net_debt_to_ebitda - 2.0, 0.0)
        leverage_adjusted_multiple = sector_ev_ebitda * clamp(1.0 - 0.06 * leverage_delta, 0.6, 1.1)

    ev_ebitda_model = EVEBITDAModel(
        company_profile=company_profile,
        ttm_ebitda=ttm_ebitda,
        enterprise_value=enterprise_value,
        sector_median_ev_ebitda=sector_ev_ebitda,
        leverage_adjusted_multiple=leverage_adjusted_multiple,
        interest_coverage=ratios.get("interest_coverage") or ratios.get("interest_coverage_ratio"),
        revenue_growth=_normalize_growth_value(revenue_growth),
    )
    normalized_ev_ebitda = normalize_model_output(ev_ebitda_model.calculate())

    annual_revenue = base_annual_revenue
    if valuation_basis == "forward" and annual_revenue is not None:
        annual_revenue = float(annual_revenue) * _annual_growth_factor(
            growth_value=revenue_growth,
            forward_horizon=forward_horizon,
        )

    revenue_per_share = None
    if ratios.get("revenue_per_share"):
        revenue_per_share = float(ratios["revenue_per_share"])
        if valuation_basis == "forward":
            revenue_per_share *= _annual_growth_factor(
                growth_value=revenue_growth,
                forward_horizon=forward_horizon,
            )
    elif annual_revenue and normalized_shares_outstanding:
        try:
            revenue_per_share = float(annual_revenue) / float(normalized_shares_outstanding)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            revenue_per_share = None
            logger.debug("%s - Failed to calculate revenue_per_share: %s", symbol, exc)

    sector_ps = (
        company_data.get("sector_metrics", {}).get("median_ps")
        or company_data.get("sector_data", {}).get("median_ps")
        or lookup_sector_multiple(company_profile.sector, "ps", company_profile.industry)
    )

    # Apply growth adjustment to P/S for consistency with victor_invest
    try:
        from investigator.domain.services.valuation.common import (
            GrowthAdjustedMultiples,
        )

        growth_adjusted_ps = GrowthAdjustedMultiples.calculate_adjusted_ps(
            sector=company_profile.sector,
            industry=company_profile.industry,
            base_multiple=sector_ps,
            revenue_growth=revenue_growth,
        )
    except Exception:
        growth_adjusted_ps = sector_ps

    valuation_settings = getattr(config, "valuation", None)
    liquidity_floor = 5_000_000
    if isinstance(valuation_settings, dict):
        liquidity_floor = valuation_settings.get("liquidity_floor_usd", liquidity_floor)
    elif valuation_settings is not None:
        liquidity_floor = getattr(valuation_settings, "liquidity_floor_usd", liquidity_floor)

    ps_model = PSMultipleModel(
        company_profile=company_profile,
        revenue_per_share=revenue_per_share,
        current_price=current_price,
        sector_median_ps=growth_adjusted_ps,
        liquidity_floor_usd=liquidity_floor,
    )
    normalized_ps = normalize_model_output(ps_model.calculate())

    sector_pb = (
        company_data.get("sector_metrics", {}).get("median_pb")
        or company_data.get("sector_data", {}).get("median_pb")
        or lookup_sector_multiple(company_profile.sector, "pb", company_profile.industry)
    )
    pb_model = PBMultipleModel(
        company_profile=company_profile,
        book_value_per_share=company_profile.book_value_per_share,
        tangible_book_value_per_share=ratios.get("tangible_book_value_per_share"),
        current_price=current_price,
        sector_median_pb=sector_pb,
    )
    normalized_pb = normalize_model_output(pb_model.calculate())

    _attach_basis_metadata(
        model_output=normalized_pe,
        valuation_basis=valuation_basis,
        forward_horizon=forward_horizon,
        denominator_label="valuation_eps_used",
        denominator_value=ttm_eps if ttm_eps is not None else None,
    )
    _attach_basis_metadata(
        model_output=normalized_ev_ebitda,
        valuation_basis=valuation_basis,
        forward_horizon=forward_horizon,
        denominator_label="valuation_ebitda_used",
        denominator_value=ttm_ebitda if ttm_ebitda is not None else None,
    )
    _attach_basis_metadata(
        model_output=normalized_ps,
        valuation_basis=valuation_basis,
        forward_horizon=forward_horizon,
        denominator_label="valuation_revenue_per_share_used",
        denominator_value=revenue_per_share if revenue_per_share is not None else None,
    )
    _attach_basis_metadata(
        model_output=normalized_pb,
        valuation_basis=valuation_basis,
        forward_horizon=forward_horizon,
        denominator_label="valuation_book_value_per_share_used",
        denominator_value=company_profile.book_value_per_share,
    )
    if guidance_metadata:
        for output in (
            normalized_pe,
            normalized_ev_ebitda,
            normalized_ps,
            normalized_pb,
        ):
            assumptions = output.setdefault("assumptions", {})
            metadata = output.setdefault("metadata", {})
            if isinstance(assumptions, dict):
                assumptions["guidance_applied"] = True
                for key, value in guidance_metadata.items():
                    assumptions.setdefault(key, value)
            if isinstance(metadata, dict):
                metadata["guidance_applied"] = True
                for key, value in guidance_metadata.items():
                    metadata.setdefault(key, value)

    if sector_specific_result and "P/BV" in sector_specific_result.get("method", ""):
        confidence_map = {"high": 0.9, "medium": 0.7, "low": 0.5}
        insurance_confidence = confidence_map.get(sector_specific_result.get("confidence", "medium"), 0.7)
        normalized_pb = {
            "model": "pb",
            "fair_value_per_share": sector_specific_result.get("fair_value"),
            "applicable": True,
            "confidence_score": insurance_confidence,
            "method": sector_specific_result.get("method"),
            "details": sector_specific_result.get("details", {}),
            "warnings": sector_specific_result.get("warnings", []),
            "upside_percent": sector_specific_result.get("upside_percent"),
            "current_price": sector_specific_result.get("current_price"),
        }
        logger.info(
            "🏦 %s - INSURANCE OVERRIDE: Using P/BV insurance valuation for P/B model (FV=$%.2f, confidence=%s)",
            symbol,
            sector_specific_result.get("fair_value", 0),
            sector_specific_result.get("confidence"),
        )

    return {
        "pe": normalized_pe,
        "ev_ebitda": normalized_ev_ebitda,
        "ps": normalized_ps,
        "pb": normalized_pb,
    }

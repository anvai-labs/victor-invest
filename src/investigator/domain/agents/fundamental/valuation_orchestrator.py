"""Helpers for multi-model valuation blending, summary logging, and synthesis dispatch."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from investigator.domain.services.deterministic_valuation_synthesizer import (
    synthesize_valuation,
)

from .valuation_blending import (
    apply_weight_lookup,
    collect_models_for_blending,
    filter_models_for_company,
    hydrate_financials_for_blending,
)
from .valuation_synthesis import build_valuation_summary_rows


def run_sector_specific_valuation(
    *,
    symbol: str,
    company_profile: Any,
    market_data: Dict[str, Any],
    financials: Dict[str, Any],
    xbrl_data: Optional[Dict[str, Any]],
    router_cls: Any,
    get_config: Callable[[], Any],
    logger: Any,
) -> Optional[Dict[str, Any]]:
    """Attempt sector-specific valuation routing and return normalized result if applicable."""
    if not (company_profile.sector and company_profile.industry):
        return None
    current_price = market_data.get("current_price")
    if not current_price:
        return None

    financials_for_routing = dict(financials or {})
    if not financials_for_routing.get("shares_outstanding"):
        financials_for_routing["shares_outstanding"] = getattr(
            company_profile, "shares_outstanding", None
        ) or market_data.get("shares_outstanding")
    if not financials_for_routing.get("market_cap"):
        financials_for_routing["market_cap"] = (
            getattr(company_profile, "market_cap", None)
            or market_data.get("market_cap")
            or market_data.get("market_capitalization")
        )
    if not financials_for_routing.get("current_price"):
        financials_for_routing["current_price"] = current_price

    try:
        router = router_cls()
        config = get_config()
        database_url = (
            f"postgresql://{config.database.username}:{config.database.password}"
            f"@{config.database.host}:{config.database.port}/{config.database.database}"
        )
        valuation_result = router.route_valuation(
            symbol=symbol,
            sector=company_profile.sector,
            industry=company_profile.industry,
            financials=financials_for_routing,
            current_price=current_price,
            database_url=database_url,
            xbrl_data=xbrl_data,
        )
        if valuation_result is None:
            return None

        normalized = {
            "method": valuation_result.method,
            "fair_value": valuation_result.fair_value,
            "current_price": valuation_result.current_price,
            "upside_percent": valuation_result.upside_percent,
            "confidence": valuation_result.confidence,
            "details": valuation_result.details,
            "warnings": valuation_result.warnings,
        }
        logger.info(
            "%s - Used sector-specific valuation: %s (FV=$%.2f, Upside=%+.1f%%)",
            symbol,
            valuation_result.method,
            valuation_result.fair_value,
            valuation_result.upside_percent,
        )
        return normalized
    except Exception as exc:
        logger.warning(
            "%s - Sector-specific valuation failed: %s, falling back to DCF",
            symbol,
            exc,
        )
        return None


async def run_sector_and_dcf(
    *,
    symbol: str,
    company_profile: Any,
    company_data: Dict[str, Any],
    market_data: Dict[str, Any],
    financials: Dict[str, Any],
    quarterly_data: List[Any],
    valuation_results: Dict[str, Any],
    cost_of_capital_issues: List[str],
    router_cls: Any,
    get_config: Callable[[], Any],
    calculate_dcf_professional: Callable[
        [str, List[Any], Any], Awaitable[Dict[str, Any]]
    ],
    apply_cost_of_capital_penalty: Callable[
        [Dict[str, Any], List[str]], Dict[str, Any]
    ],
    store_deterministic_analysis: Callable[..., None],
    log_model_result: Callable[[Any, str, str, Dict[str, Any]], None],
    logger: Any,
) -> Dict[str, Any]:
    """Run sector-specific routing + DCF preparation and update valuation_results."""
    xbrl_data = None
    if isinstance(company_data, dict):
        candidate = company_data.get("facts")
        if isinstance(candidate, dict):
            xbrl_data = candidate

    sector_specific_result = run_sector_specific_valuation(
        symbol=symbol,
        company_profile=company_profile,
        market_data=market_data,
        financials=financials,
        xbrl_data=xbrl_data,
        router_cls=router_cls,
        get_config=get_config,
        logger=logger,
    )
    if sector_specific_result is not None:
        valuation_results["sector_specific"] = sector_specific_result

    dcf_professional = await calculate_dcf_professional(
        symbol, quarterly_data, company_profile
    )
    dcf_professional = prepare_dcf_result(
        symbol=symbol,
        dcf_professional=dcf_professional,
        cost_of_capital_issues=cost_of_capital_issues,
        apply_cost_of_capital_penalty=apply_cost_of_capital_penalty,
        store_deterministic_analysis=store_deterministic_analysis,
        period=company_data.get("fiscal_period"),
        log_model_result=log_model_result,
        logger=logger,
    )
    valuation_results["dcf_professional"] = dcf_professional
    return {
        "dcf_professional": dcf_professional,
        "sector_specific_result": sector_specific_result,
    }


def assign_and_log_relative_models(
    *,
    symbol: str,
    valuation_results: Dict[str, Any],
    company_profile: Any,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    financials: Dict[str, Any],
    market_data: Dict[str, Any],
    config: Any,
    calculate_relative_models: Callable[..., Dict[str, Any]],
    lookup_sector_multiple: Callable[[str, str, str], Optional[float]],
    calculate_enterprise_value: Callable[[Dict[str, Any], Dict[str, Any]], float],
    log_model_result: Callable[[Any, str, str, Dict[str, Any]], None],
    logger: Any,
    valuation_basis: str = "ttm",
    forward_horizon: str = "1y",
    guidance_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute relative models, write into valuation_results, and emit model logs."""
    relative_models = calculate_relative_models(
        symbol=symbol,
        company_profile=company_profile,
        company_data=company_data,
        ratios=ratios,
        financials=financials,
        market_data=market_data,
        config=config,
        sector_specific_result=valuation_results.get("sector_specific"),
        lookup_sector_multiple=lookup_sector_multiple,
        calculate_enterprise_value=calculate_enterprise_value,
        logger=logger,
        valuation_basis=valuation_basis,
        forward_horizon=forward_horizon,
        guidance_context=guidance_context,
    )
    normalized_pe = relative_models["pe"]
    normalized_ev_ebitda = relative_models["ev_ebitda"]
    normalized_ps = relative_models["ps"]
    normalized_pb = relative_models["pb"]
    valuation_results["pe"] = normalized_pe
    valuation_results["ev_ebitda"] = normalized_ev_ebitda
    valuation_results["ps"] = normalized_ps
    valuation_results["pb"] = normalized_pb

    log_model_result(logger, symbol, "P/E", normalized_pe)
    log_model_result(logger, symbol, "EV/EBITDA", normalized_ev_ebitda)
    log_model_result(logger, symbol, "P/S", normalized_ps)
    log_model_result(logger, symbol, "P/B", normalized_pb)

    return {
        "pe": normalized_pe,
        "ev_ebitda": normalized_ev_ebitda,
        "ps": normalized_ps,
        "pb": normalized_pb,
    }


def prepare_dcf_result(
    *,
    symbol: str,
    dcf_professional: Dict[str, Any],
    cost_of_capital_issues: List[str],
    apply_cost_of_capital_penalty: Callable[
        [Dict[str, Any], List[str]], Dict[str, Any]
    ],
    store_deterministic_analysis: Callable[..., None],
    period: Optional[str],
    log_model_result: Callable[[Any, str, str, Dict[str, Any]], None],
    logger: Any,
) -> Dict[str, Any]:
    """Normalize DCF payload for blending, apply penalties, persist snapshot, and log result."""
    if isinstance(dcf_professional, dict) and dcf_professional.get(
        "fair_value_per_share"
    ):
        dcf_professional.setdefault("model", "dcf")
        dcf_professional.setdefault("applicable", True)
        dcf_professional.setdefault("confidence_score", 0.7)
        dcf_professional.setdefault("weight", 0.0)
        logger.info(
            "🔧 %s - Added orchestrator fields to DCF: model=%s, applicable=%s, confidence=%s",
            symbol,
            dcf_professional.get("model"),
            dcf_professional.get("applicable"),
            dcf_professional.get("confidence_score"),
        )
    else:
        logger.warning(
            "⚠️ %s - DCF did not get orchestrator fields: isinstance=%s, fair_value=%s",
            symbol,
            isinstance(dcf_professional, dict),
            dcf_professional.get("fair_value_per_share")
            if isinstance(dcf_professional, dict)
            else "N/A",
        )

    dcf_professional = apply_cost_of_capital_penalty(
        dcf_professional, cost_of_capital_issues
    )
    store_deterministic_analysis(
        symbol=symbol,
        label="deterministic_dcf",
        payload=dcf_professional,
        period=period,
    )
    log_model_result(logger, symbol, "DCF", dcf_professional)
    return dcf_professional


def run_multi_model_blending(
    *,
    symbol: str,
    valuation_results: Dict[str, Any],
    company_profile: Any,
    company_data: Dict[str, Any],
    ratios: Dict[str, Any],
    financials: Dict[str, Any],
    dcf_professional: Optional[Dict[str, Any]],
    normalized_pe: Optional[Dict[str, Any]],
    normalized_ev_ebitda: Optional[Dict[str, Any]],
    normalized_ps: Optional[Dict[str, Any]],
    normalized_pb: Optional[Dict[str, Any]],
    select_models_for_company: Callable[[Any], Optional[List[str]]],
    resolve_fallback_weights: Callable[
        [Any, List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]],
        Any,
    ],
    multi_model_orchestrator: Any,
    logger: Any,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Run model blending pipeline and return `(multi_model_summary, tier_classification)`."""
    tier_classification: Optional[str] = None
    try:
        models_for_blending, blending_messages = collect_models_for_blending(
            dcf_professional=dcf_professional,
            valuation_results=valuation_results,
            normalized_pe=normalized_pe,
            normalized_ev_ebitda=normalized_ev_ebitda,
            normalized_ps=normalized_ps,
            normalized_pb=normalized_pb,
        )
        for message in blending_messages:
            if "sector-specific" in message:
                logger.info("✅ [SECTOR_VALUATION] %s - %s", symbol, message)
            else:
                logger.info("✅ %s - %s", symbol, message)
        logger.debug(
            "%s - Models for blending: %s",
            symbol,
            [m.get("model") for m in models_for_blending],
        )

        allowed_models = select_models_for_company(company_profile)
        models_for_blending, resolved_allowed_models, added_pb_for_insurance = (
            filter_models_for_company(
                models_for_blending=models_for_blending,
                allowed_models=allowed_models,
                industry=company_profile.industry,
            )
        )
        if resolved_allowed_models is not None:
            if added_pb_for_insurance:
                logger.info(
                    "🏦 %s - Added 'pb' to allowed_models for insurance company", symbol
                )
            logger.debug(
                "%s - Filtered models (allowed=%s): %s",
                symbol,
                resolved_allowed_models,
                [m.get("model") for m in models_for_blending],
            )

        pre_market_cap = financials.get("market_cap")
        hydration = hydrate_financials_for_blending(
            financials=financials,
            company_data=company_data,
            company_profile=company_profile,
            ratios=ratios,
        )
        if (
            ratios
            and "market_cap" in ratios
            and pre_market_cap is None
            and financials.get("market_cap") is not None
        ):
            logger.debug(
                "%s - Copied market_cap from ratios to financials: $%s",
                symbol,
                format(ratios["market_cap"], ",.0f"),
            )

        if financials.get("revenue"):
            if not (financials.get("revenues") or financials.get("total_revenue")):
                logger.info(
                    "%s - Added missing 'revenue' key to financials: $%s",
                    symbol,
                    format(financials.get("revenue", 0), ",.0f"),
                )

        if hydration["fcf_quarters_count"] == 4 and (
            not getattr(company_profile, "quarterly_metrics", None)
            or len(getattr(company_profile, "quarterly_metrics", []) or []) == 0
        ):
            logger.info("%s - Inferred fcf_quarters_count=4 from TTM FCF value", symbol)

        logger.info(
            "%s - Applicability fields added: fcf_quarters=%s, fcf=$%.2fB, ebitda=$%.2fB, dividends_paid=$%.2fB, payout_ratio=%.1f%%, net_income=$%.2fB, book_value=$%.2fB",
            symbol,
            hydration["fcf_quarters_count"],
            hydration["free_cash_flow"] / 1e9,
            hydration["ebitda"] / 1e9,
            hydration["dividends_paid"] / 1e9,
            hydration["payout_ratio"],
            hydration["net_income"] / 1e9,
            hydration["book_value"] / 1e9,
        )

        fallback_weights_result = resolve_fallback_weights(
            company_profile, models_for_blending, financials, ratios
        )
        if isinstance(fallback_weights_result, tuple):
            fallback_weights, tier_classification = fallback_weights_result
        else:
            fallback_weights = fallback_weights_result
            tier_classification = None

        multi_model_summary = multi_model_orchestrator.combine(
            company_profile,
            models_for_blending,
            fallback_weights=fallback_weights,
            tier_classification=tier_classification,
        )
        valuation_results["multi_model"] = multi_model_summary

        try:
            apply_weight_lookup(
                multi_model_summary=multi_model_summary,
                dcf_professional=dcf_professional,
                valuation_results=valuation_results,
                normalized_pe=normalized_pe,
                normalized_ev_ebitda=normalized_ev_ebitda,
                normalized_ps=normalized_ps,
                normalized_pb=normalized_pb,
            )
        except Exception as exc2:  # pragma: no cover
            logger.warning("%s - Weight lookup failed: %s", symbol, exc2)

    except Exception as exc:  # pragma: no cover
        import traceback

        logger.error("%s - Multi-model blending failed: %s", symbol, exc)
        logger.debug("%s - Traceback: %s", symbol, traceback.format_exc())

    return valuation_results.get("multi_model", {}), tier_classification


def log_multi_model_summary(
    *,
    symbol: str,
    valuation_results: Dict[str, Any],
    company_data: Dict[str, Any],
    tier_classification: Optional[str],
    dcf_professional: Optional[Dict[str, Any]],
    normalized_pe: Optional[Dict[str, Any]],
    normalized_ev_ebitda: Optional[Dict[str, Any]],
    normalized_ps: Optional[Dict[str, Any]],
    normalized_pb: Optional[Dict[str, Any]],
    log_valuation_snapshot: Callable[[Any, str, Dict[str, Any]], None],
    format_valuation_summary_table: Callable[..., str],
    logger: Any,
) -> Dict[str, Any]:
    """
    Emit valuation snapshot + table logs and return summary metrics.

    Returns dict with `multi_model_summary`, `blended_fair_value`, `overall_confidence`,
    `model_agreement_score`, `divergence_flag`, `applicable_models`, `notes`.
    """
    multi_model_summary = valuation_results.get("multi_model", {})
    blended_fair_value = multi_model_summary.get("blended_fair_value")
    overall_confidence = multi_model_summary.get("overall_confidence")
    model_agreement_score = multi_model_summary.get("model_agreement_score")
    divergence_flag = multi_model_summary.get("divergence_flag")
    applicable_models = multi_model_summary.get("applicable_models")
    notes = multi_model_summary.get("notes", [])

    log_valuation_snapshot(logger, symbol, valuation_results)
    ggm_entry = valuation_results.get("ggm", {})

    try:
        current_price = company_data.get("current_price", 0)
        all_models_data = build_valuation_summary_rows(
            dcf_professional=dcf_professional,
            ggm_entry=ggm_entry,
            normalized_pe=normalized_pe,
            normalized_ev_ebitda=normalized_ev_ebitda,
            normalized_ps=normalized_ps,
            normalized_pb=normalized_pb,
        )
        tier_display = tier_classification if tier_classification else "N/A"
        valuation_table = format_valuation_summary_table(
            symbol=symbol,
            all_models=all_models_data,
            dynamic_weights={m["name"].lower(): m["weight"] for m in all_models_data},
            blended_fair_value=blended_fair_value if blended_fair_value else 0,
            current_price=current_price,
            tier=tier_display,
            notes=multi_model_summary.get("notes"),
        )
        logger.info(valuation_table)
    except Exception as exc:  # pragma: no cover
        logger.warning("%s - Failed to format valuation summary table: %s", symbol, exc)

    if blended_fair_value and blended_fair_value > 0:
        agreement_str = (
            f"{model_agreement_score:.2f}"
            if model_agreement_score is not None
            else "N/A"
        )
        confidence_str = (
            f"{overall_confidence:.1%}" if overall_confidence is not None else "N/A"
        )
        logger.info(
            "✅ %s - Multi-Model Blended Fair Value: $%.2f | Confidence: %s | Agreement: %s | Applicable Models: %s",
            symbol,
            blended_fair_value,
            confidence_str,
            agreement_str,
            applicable_models,
        )
        if divergence_flag and model_agreement_score is not None:
            logger.warning(
                "⚠️  %s - Model divergence detected! Agreement score %.2f indicates significant spread between model outputs.",
                symbol,
                model_agreement_score,
            )
    else:
        logger.warning(
            "⚠️  %s - No blended fair value calculated (applicable models: %s)",
            symbol,
            applicable_models,
        )

    return {
        "multi_model_summary": multi_model_summary,
        "blended_fair_value": blended_fair_value,
        "overall_confidence": overall_confidence,
        "model_agreement_score": model_agreement_score,
        "divergence_flag": divergence_flag,
        "applicable_models": applicable_models,
        "notes": notes,
    }


async def dispatch_valuation_synthesis(
    *,
    symbol: str,
    prompt: str,
    company_data: Dict[str, Any],
    market_data: Dict[str, Any],
    valuation_results: Dict[str, Any],
    multi_model_summary: Dict[str, Any],
    data_quality: Dict[str, Any],
    company_profile_payload: Dict[str, Any],
    notes: List[str],
    use_deterministic: bool,
    deterministic_valuation_synthesis: bool,
    build_deterministic_response: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    debug_log_prompt: Callable[[str, str], None],
    debug_log_response: Callable[[str, Any], None],
    ollama_client: Any,
    valuation_model: str,
    cache_llm_response: Callable[..., Awaitable[None]],
    wrap_llm_response: Callable[..., Dict[str, Any]],
    logger: Any,
) -> Dict[str, Any]:
    """Run deterministic or LLM valuation synthesis and return wrapped response."""
    if use_deterministic and deterministic_valuation_synthesis:
        logger.debug(
            "%s - Using deterministic valuation synthesis (LLM bypass)", symbol
        )
        response_data = synthesize_valuation(
            symbol=symbol,
            current_price=market_data.get("current_price", market_data.get("price", 0)),
            valuation_results=valuation_results,
            multi_model_summary=multi_model_summary,
            data_quality=data_quality,
            company_profile=company_profile_payload,
            notes=notes,
        )
        response_data["valuation_methods"] = valuation_results
        response_data["current_price"] = market_data.get(
            "current_price", market_data.get("price", 0)
        )
        response_data["company_profile"] = company_profile_payload
        return build_deterministic_response("valuation_synthesis", response_data)

    prompt_name = "_perform_valuation_synthesis_prompt"
    debug_log_prompt(prompt_name, prompt)

    response = await ollama_client.generate(
        model=valuation_model,
        prompt=prompt,
        system="Synthesize valuation analysis and provide fair value estimate.",
        format="json",
        period=company_data.get("fiscal_period"),
        prompt_name=prompt_name,
    )
    debug_log_response(prompt_name, response)

    await cache_llm_response(
        response=response,
        model=valuation_model,
        symbol=symbol,
        llm_type="fundamental_valuation",
        prompt=prompt,
        temperature=0.3,
        top_p=0.9,
        format="json",
        period=company_data.get("fiscal_period"),
    )

    response_data: Any
    if isinstance(response, dict) and "response" in response:
        response_data = response["response"]
    else:
        response_data = response

    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data.strip())
        except Exception:
            response_data = {}

    if isinstance(response_data, dict):
        response_data["valuation_methods"] = valuation_results
        response_data["current_price"] = market_data.get(
            "current_price", market_data.get("price", 0)
        )
        response_data["company_profile"] = company_profile_payload

    return wrap_llm_response(
        response=response_data,
        model=valuation_model,
        prompt=prompt,
        temperature=0.3,
        top_p=0.9,
        format="json",
        period=company_data.get("fiscal_period"),
    )

"""
Result Formatter - Configurable Output Detail Levels

Provides configurable output formatting to reduce duplication and verbosity
in analysis results. Supports three detail levels:

- MINIMAL: Executive summary only (for quick decisions)
- STANDARD: Investor decision-making details (default, removes duplicates/metadata)
- VERBOSE: Full analysis with all metadata and prompts

Usage:
    from investigator.application.result_formatter import format_analysis_output, OutputDetailLevel

    formatted = format_analysis_output(raw_results, OutputDetailLevel.STANDARD)
"""

import copy
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

from investigator.application.summary_data_extractor import SummaryDataExtractor

logger = logging.getLogger(__name__)


def _is_empty_value(value: Any) -> bool:
    """
    Check if a value should be considered "empty" for removal.

    Handles numpy arrays safely (they raise ValueError on ambiguous truth checks).

    Empty values:
    - None
    - Empty string ""
    - Empty list []
    - Empty dict {}
    - Empty numpy array (size == 0)

    NOT empty (retained):
    - Non-empty numpy arrays
    - Zero values (0, 0.0)
    - False boolean
    - Non-empty collections

    Returns:
        True if value should be removed, False otherwise.
    """
    # Handle None first (simplest case)
    if value is None:
        return True

    # Handle numpy arrays and array-like objects (they fail on ambiguous truth comparisons)
    # Check for ndarray explicitly first
    if isinstance(value, np.ndarray):
        return value.size == 0

    # Check for any object with __array__ method (numpy-compatible objects)
    # This catches masked arrays, memoryviews, etc.
    if hasattr(value, "__array__") or hasattr(value, "size"):
        try:
            # Try to check size attribute for array-like objects
            if hasattr(value, "size"):
                return value.size == 0
            # Convert to numpy array and check
            arr = np.asarray(value)
            return arr.size == 0
        except (ValueError, TypeError):
            # If conversion fails, keep the value
            return False

    # Handle pandas objects if present (they also have ambiguous truth values)
    # Check for pandas-like objects by duck typing (has 'empty' attribute)
    if hasattr(value, "empty"):
        try:
            empty_attr = getattr(value, "empty", None)
            # Check if it's a property/attribute (not callable)
            if not callable(empty_attr):
                return bool(empty_attr)
        except (ValueError, AttributeError):
            # If empty check fails, keep the value
            return False

    # Standard Python types - use type checks to avoid __eq__ issues
    if isinstance(value, str):
        return value == ""
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0

    return False


class OutputDetailLevel(Enum):
    """Output detail level for analysis results"""

    MINIMAL = "minimal"  # Executive summary only
    STANDARD = "standard"  # Investor decision-making (default, no duplicates)
    COMPACT = "compact"  # Machine-readable, consolidated schema
    VERBOSE = "verbose"  # Full analysis with all metadata


def format_analysis_output(
    analysis_results: Dict[str, Any],
    detail_level: OutputDetailLevel = OutputDetailLevel.STANDARD,
) -> Dict[str, Any]:
    """
    Format analysis results according to specified detail level.

    Args:
        analysis_results: Raw analysis results from orchestrator
        detail_level: Desired output detail level

    Returns:
        Formatted analysis results

    Example:
        >>> results = await orchestrator.get_results(task_id)
        >>> formatted = format_analysis_output(results, OutputDetailLevel.STANDARD)
        >>> # Output is ~95% smaller, removes duplicates and metadata
    """
    if detail_level == OutputDetailLevel.VERBOSE:
        # Return full analysis unchanged
        return analysis_results

    elif detail_level == OutputDetailLevel.COMPACT:
        # Return consolidated machine-readable schema
        return _format_compact(analysis_results)

    elif detail_level == OutputDetailLevel.MINIMAL:
        # Return executive summary only
        return _format_minimal(analysis_results)

    else:  # STANDARD (default)
        # Remove duplicates, prompts, and metadata
        return _format_standard(analysis_results)


def _format_minimal(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract minimal executive summary only.

    Uses SummaryDataExtractor for robust field extraction with fallback chains.

    Returns only critical decision-making data:
    - Symbol, timestamp
    - Recommendation, confidence, price target
    - Key strengths and risks
    - Investment thesis

    The extractor handles:
    - Field name variations (fair_value vs price_target_12_month)
    - Nested structure differences
    - Missing data with fallback calculations (e.g., investment_grade from upside%)
    """
    # Use SOLID-based extractor with fallback chains
    extractor = SummaryDataExtractor(analysis_results, enable_audit=True)
    summary = extractor.extract_minimal_summary()

    # Log extraction audit for debugging if issues occur
    audit = extractor.get_audit()
    if audit:
        missing_fields = [
            name for name, result in audit.extractions.items() if not result.has_value
        ]
        if missing_fields:
            logger.debug(f"Summary extraction missing fields: {missing_fields}")
            audit.log_summary()

    # Remove internal audit from output (keep it clean for display)
    summary.pop("_extraction_audit", None)

    # Add data quality assessment if score is available
    if summary.get("data_quality", {}).get("overall_score") is not None:
        score = summary["data_quality"]["overall_score"]
        if score >= 80:
            summary["data_quality"]["assessment"] = "Excellent"
        elif score >= 60:
            summary["data_quality"]["assessment"] = "Good"
        elif score >= 40:
            summary["data_quality"]["assessment"] = "Fair"
        else:
            summary["data_quality"]["assessment"] = "Limited"

    return summary


def _format_standard(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format for investor decision-making (removes duplicates and metadata).

    Removes:
    - All prompts
    - Internal metadata (cached_at, agent_id, raw_thinking, prompt_length, model_info)
    - Duplicate data points (signals, valuation, company data repeated across sections)
    - Empty/null fields

    Keeps:
    - All analysis conclusions and insights
    - Financial data and ratios
    - Recommendations and targets
    - Risk analysis
    - Data quality scores
    """
    # Deep copy to avoid modifying original
    result = copy.deepcopy(analysis_results)

    # Remove top-level metadata
    _remove_keys(result, ["task_id", "execution_metadata", "execution_trace"])

    # Clean each agent section (handle both direct and 'agents' wrapper)
    agents_dict = result.get("agents", result)  # Support both structures
    for agent_name in [
        "fundamental",
        "technical",
        "synthesis",
        "market_context",
        "sec",
        "symbol_update",
    ]:
        if agent_name in agents_dict:
            _clean_agent_section(agents_dict[agent_name])

    # Consolidate duplicate data (keep single source of truth)
    _consolidate_duplicates(result)

    # Remove empty/null values
    result = _remove_empty_values(result)

    # Add detail level indicator
    result["detail_level"] = "standard"

    return result


def _format_compact(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce a consolidated, machine-readable schema with minimal duplication.

    Design goals:
    - Stable top-level keys for downstream systems
    - Single source of truth for valuation model outputs
    - Keep only actionable fields (drop heavy nested narrative duplicates)
    """
    src = copy.deepcopy(analysis_results or {})
    agents = src.get("agents", {}) if isinstance(src.get("agents"), dict) else {}

    fundamental = (
        agents.get("fundamental", {})
        if isinstance(agents.get("fundamental"), dict)
        else {}
    )
    technical = (
        agents.get("technical", {}) if isinstance(agents.get("technical"), dict) else {}
    )
    synthesis = (
        agents.get("synthesis", {}) if isinstance(agents.get("synthesis"), dict) else {}
    )
    market_context = (
        agents.get("market_context", {})
        if isinstance(agents.get("market_context"), dict)
        else {}
    )
    sec = agents.get("sec", {}) if isinstance(agents.get("sec"), dict) else {}

    valuation = (
        fundamental.get("valuation", {})
        if isinstance(fundamental.get("valuation"), dict)
        else {}
    )
    methods = (
        valuation.get("valuation_methods", {})
        if isinstance(valuation.get("valuation_methods"), dict)
        else {}
    )
    multi_model = (
        methods.get("multi_model")
        if isinstance(methods.get("multi_model"), dict)
        else (
            fundamental.get("multi_model_summary")
            if isinstance(fundamental.get("multi_model_summary"), dict)
            else {}
        )
    )
    ratios = (
        fundamental.get("ratios", {})
        if isinstance(fundamental.get("ratios"), dict)
        else {}
    )
    data_quality = (
        fundamental.get("data_quality", {})
        if isinstance(fundamental.get("data_quality"), dict)
        else {}
    )

    basis, horizon = _extract_basis_and_horizon(methods)
    current_price = (
        valuation.get("current_price")
        or ratios.get("current_price")
        or technical.get("current_price")
    )
    blended_fair_value = valuation.get("fair_value_estimate") or valuation.get(
        "fair_value"
    )
    expected_return_pct = _calculate_expected_return(blended_fair_value, current_price)

    compact_models = _compact_valuation_models(methods)

    synthesis_payload = (
        synthesis.get("synthesis", {})
        if isinstance(synthesis.get("synthesis"), dict)
        else {}
    )
    recommendation_payload = (
        synthesis.get("recommendation", {})
        if isinstance(synthesis.get("recommendation"), dict)
        else {}
    )
    final_recommendation = (
        recommendation_payload.get("final_recommendation")
        or fundamental.get("recommendation")
        or valuation.get("recommendation")
    )
    aligned_recommendation, recommendation_adjustment = (
        _align_recommendation_with_expected_return(
            final_recommendation, expected_return_pct
        )
    )

    output = {
        "schema_version": "analysis.compact.v1",
        "symbol": src.get("symbol"),
        "mode": src.get("mode"),
        "timing": {
            "started_at": src.get("started_at"),
            "completed_at": src.get("completed_at"),
            "duration_seconds": src.get("duration"),
        },
        "status": {
            "overall": "completed" if src.get("completed_at") else "incomplete",
            "agents": _extract_agent_statuses(agents),
        },
        "price": {
            "current": current_price,
            "target": blended_fair_value,
            "expected_return_pct": expected_return_pct,
        },
        "recommendation": {
            "action": aligned_recommendation,
            "confidence_score": (
                recommendation_payload.get("confidence")
                or synthesis.get("confidence")
                or fundamental.get("confidence", {}).get("confidence_score")
            ),
            "investment_grade": (
                valuation.get("investment_grade") or fundamental.get("investment_grade")
            ),
        },
        "quality": {
            "data_quality_score": data_quality.get("data_quality_score"),
            "quality_grade": data_quality.get("quality_grade"),
            "completeness_score": data_quality.get("completeness_score"),
            "confidence_level": (
                fundamental.get("confidence", {}).get("confidence_level")
                if isinstance(fundamental.get("confidence"), dict)
                else None
            ),
        },
        "valuation": {
            "basis": basis,
            "forward_horizon": horizon,
            "blended_fair_value": blended_fair_value,
            "overall_confidence": multi_model.get("overall_confidence"),
            "model_agreement_score": multi_model.get("model_agreement_score"),
            "dispersion_ratio": multi_model.get("dispersion_ratio"),
            "divergence_flag": multi_model.get("divergence_flag"),
            "applicable_models": multi_model.get("applicable_models"),
            "models": compact_models,
        },
        "technical": {
            "recommendation": technical.get("recommendation"),
            "rating": technical.get("technical_rating"),
            "levels": _compact_levels(technical.get("levels")),
            # Multi-tier analysis (weekly strategic + daily tactical)
            "multi_tier": _compact_multi_tier_technical(technical),
        },
        "market": {
            "sector": market_context.get("sector"),
            "market_regime": (
                market_context.get("market_context", {}).get("market_regime")
                if isinstance(market_context.get("market_context"), dict)
                else None
            ),
            "sector_strength": (
                market_context.get("sector_context", {}).get("sector_strength")
                if isinstance(market_context.get("sector_context"), dict)
                else None
            ),
        },
        "sec": {
            "entity_name": (
                sec.get("companyfacts_summary", {}).get("entityName")
                if isinstance(sec.get("companyfacts_summary"), dict)
                else None
            ),
            "fact_count": (
                sec.get("companyfacts_summary", {}).get("fact_count")
                if isinstance(sec.get("companyfacts_summary"), dict)
                else None
            ),
            "data_cached": sec.get("data_cached"),
            "forward_guidance": (
                sec.get("forward_guidance")
                if isinstance(sec.get("forward_guidance"), dict)
                else (
                    fundamental.get("sec_data", {}).get("forward_guidance")
                    if isinstance(fundamental.get("sec_data"), dict)
                    else None
                )
            ),
            # Quarterly metrics summary (for UI display)
            "quarterly_metrics": (
                fundamental.get("sec_data", {}).get("quarterly_metrics", [])[:4]
                if isinstance(fundamental.get("sec_data"), dict)
                else []
            ),
            "recent_filings": (
                sec.get("recent_filings", [])[:5]
                if isinstance(sec.get("recent_filings"), list)
                else (
                    fundamental.get("sec_data", {}).get("recent_filings", [])[:5]
                    if isinstance(fundamental.get("sec_data"), dict)
                    else []
                )
            ),
        },
        "notes": (
            multi_model.get("notes")
            if isinstance(multi_model.get("notes"), list)
            else []
        ),
        "cache_status": _compact_cache_status(src),
        "trace": {
            "source_detail_level": src.get("detail_level"),
            "compact_generated": True,
            "synthesis_report_mode": (
                synthesis_payload.get("report_mode")
                if isinstance(synthesis_payload, dict)
                else None
            ),
            "recommendation_adjusted_for_valuation_consistency": recommendation_adjustment,
        },
    }

    return _remove_empty_values(output)


def _clean_agent_section(agent_data: Dict[str, Any]) -> None:
    """
    Clean agent section by removing metadata and prompts.

    Modifies agent_data in-place.
    """
    # Remove agent metadata
    _remove_keys(
        agent_data,
        [
            "agent_id",
            "task_id",
            "cached_at",
            "cache_hit",
            "execution_time",
            "model_info",
            "prompt_length",
            "raw_thinking",
            "full_prompt",
            "system_prompt",
            "user_prompt",
        ],
    )

    # Clean ALL nested sections (analysis, valuation, ratios, confidence, data_quality, etc.)
    for key, value in list(agent_data.items()):
        if isinstance(value, dict):
            # Remove prompts and metadata from this section
            _remove_keys(
                value,
                [
                    "prompt",
                    "raw_thinking",
                    "cached_at",
                    "agent_id",
                    "model_info",
                    "metadata",
                    "prompt_length",
                ],
            )

            # If this section has a 'response' dict, clean it recursively
            if "response" in value and isinstance(value["response"], dict):
                _clean_analysis_section(value["response"])


def _clean_analysis_section(analysis_data: Dict[str, Any]) -> None:
    """
    Clean nested analysis sections.

    Modifies analysis_data in-place.
    """
    # Remove prompts and metadata from nested response objects
    for key, value in list(analysis_data.items()):
        if isinstance(value, dict):
            _remove_keys(
                value,
                [
                    "prompt",
                    "raw_thinking",
                    "cached_at",
                    "agent_id",
                    "model",
                    "model_info",
                    "metadata",
                    "temperature",
                    "max_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                ],
            )

            # Recursively clean nested 'response' objects
            if "response" in value and isinstance(value["response"], dict):
                _clean_analysis_section(value["response"])


def _consolidate_duplicates(result: Dict[str, Any]) -> None:
    """
    Remove duplicate data points across sections.

    Strategy:
    - Keep company data in fundamental only
    - Keep valuation in fundamental only
    - Keep signals in technical only
    - Synthesis references but doesn't duplicate

    Modifies result in-place.
    """
    # Handle both legacy (top-level) and wrapped ("agents") structures
    agents = result.get("agents") if isinstance(result.get("agents"), dict) else result

    # Remove company data duplicates from synthesis
    if isinstance(agents, dict) and "synthesis" in agents:
        synthesis = agents["synthesis"]
        if isinstance(synthesis, dict) and "synthesis" in synthesis:
            synth_data = synthesis["synthesis"]
            if isinstance(synth_data, dict):
                _remove_keys(synth_data, ["company_data", "market_data"])

                # Keep only references in response, not full data
                if "response" in synth_data and isinstance(
                    synth_data["response"], dict
                ):
                    synth_response = synth_data["response"]
                    _remove_keys(
                        synth_response,
                        [
                            "financial_data",
                            "technical_signals",
                            "valuation_details",
                            "complete_ratios",
                        ],
                    )

    # Remove duplicate valuation payloads from fundamental section
    if isinstance(agents, dict) and "fundamental" in agents:
        fundamental = agents["fundamental"]
        if isinstance(fundamental, dict):
            # Duplicate of valuation.multi_model / valuation_methods
            _remove_keys(
                fundamental, ["multi_model_summary", "llm_fair_value_estimate"]
            )


def _extract_agent_statuses(agents: Dict[str, Any]) -> Dict[str, Any]:
    statuses: Dict[str, Any] = {}
    for name, payload in (agents or {}).items():
        if isinstance(payload, dict):
            statuses[name] = payload.get("status", "unknown")
        else:
            statuses[name] = "unknown"
    return statuses


def _extract_basis_and_horizon(methods: Dict[str, Any]) -> tuple[str, Optional[str]]:
    basis: Optional[str] = None
    horizon: Optional[str] = None
    for model in (methods or {}).values():
        if not isinstance(model, dict):
            continue
        assumptions = (
            model.get("assumptions", {})
            if isinstance(model.get("assumptions"), dict)
            else {}
        )
        metadata = (
            model.get("metadata", {}) if isinstance(model.get("metadata"), dict) else {}
        )
        basis = (
            assumptions.get("valuation_basis")
            or metadata.get("valuation_basis")
            or basis
        )
        horizon = (
            assumptions.get("forward_horizon")
            or metadata.get("forward_horizon")
            or horizon
        )
        if basis and horizon:
            break

    basis = basis or "ttm"
    if basis != "forward":
        horizon = None
    return basis, horizon


def _compact_valuation_models(methods: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for model_name in [
        "dcf_professional",
        "pe",
        "ev_ebitda",
        "ps",
        "pb",
        "ggm",
        "damodaran_dcf",
    ]:
        model = methods.get(model_name)
        if not isinstance(model, dict):
            continue
        compact[model_name] = {
            "applicable": model.get("applicable"),
            "fair_value_per_share": model.get("fair_value_per_share"),
            "reason": model.get("reason"),
            "weight": model.get("weight"),
            "confidence_score": model.get("confidence_score"),
            "assumptions": _pick_assumptions(model.get("assumptions")),
            "diagnostics": _pick_diagnostics(model.get("diagnostics")),
        }
    return _remove_empty_values(compact)


def _pick_assumptions(assumptions: Any) -> Dict[str, Any]:
    if not isinstance(assumptions, dict):
        return {}
    keep = [
        "valuation_basis",
        "forward_horizon",
        "guidance_applied",
        "guidance_source_form",
        "guidance_confidence_score",
        "guidance_revenue_mid",
        "guidance_revenue_horizon",
        "guidance_revenue_growth_implied",
        "guidance_eps_mid",
        "guidance_eps_horizon",
        "guidance_eps_annualized",
        "guidance_eps_growth_implied",
        "guidance_revenue_growth_used",
        "guidance_earnings_growth_used",
        "target_pe",
        "target_ps",
        "target_ev_ebitda",
        "wacc",
        "terminal_growth_rate",
        "projection_years",
        "current_dps",
        "expected_dps_next_year",
        "growth_rate",
        "required_return",
        "dividend_yield",
    ]
    return {k: assumptions.get(k) for k in keep if k in assumptions}


def _pick_diagnostics(diagnostics: Any) -> Dict[str, Any]:
    if not isinstance(diagnostics, dict):
        return {}
    keep = ["flags", "data_quality_score", "fit_score", "calibration_score"]
    return {k: diagnostics.get(k) for k in keep if k in diagnostics}


def _compact_levels(levels: Any) -> Dict[str, Any]:
    if not isinstance(levels, dict):
        return {}
    keep = [
        "pivot_point",
        "support_1",
        "resistance_1",
        "support_2",
        "resistance_2",
        # Weekly levels (strategic)
        "weekly_support_1",
        "weekly_resistance_1",
        "weekly_support_2",
        "weekly_resistance_2",
        # Daily levels (tactical)
        "daily_support_1",
        "daily_resistance_1",
        "daily_support_2",
        "daily_resistance_2",
        # 52-week range
        "high_52w",
        "low_52w",
    ]
    return {k: levels.get(k) for k in keep if k in levels}


def _compact_multi_tier_technical(technical: Any) -> Dict[str, Any]:
    """Extract multi-tier technical analysis summary.

    Returns:
        Dict with strategic_trend, tactical_signal, overall_bias
    """
    if not isinstance(technical, dict):
        return {}

    # Check if multi-tier summary is available
    summary = technical.get("summary")
    if isinstance(summary, dict):
        return {
            "strategic_trend": summary.get("strategic_trend"),
            "tactical_signal": summary.get("tactical_signal"),
            "overall_bias": summary.get("overall_bias"),
        }

    # Fallback: try to derive from data
    # Check if weekly/daily data exists
    has_weekly = isinstance(technical.get("weekly"), dict)
    has_daily = isinstance(technical.get("daily"), dict)

    if not has_weekly and not has_daily:
        return {}

    # Return structure even if empty (indicates multi-tier analysis ran)
    return {
        "strategic_trend": None,
        "tactical_signal": None,
        "overall_bias": None,
        "multi_tier_analysis": True,
    }


def _compact_cache_status(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """Extract cache status information from analysis results.

    Returns:
        Dict with cache status for SEC filings, market data, and other sources
    """
    from pathlib import Path

    cache_info = {}

    # Get symbol from results
    symbol = analysis_results.get("symbol", "").upper()
    if not symbol:
        return cache_info

    # Check SEC filings cache
    sec_cache_path = Path("data/sec_cache/submissions") / symbol
    if sec_cache_path.exists():
        cache_files = list(sec_cache_path.glob("submissions.json.gz"))
        if cache_files:
            import time

            latest_cache = max(cache_files, key=lambda p: p.stat().st_mtime)
            mtime = latest_cache.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            cache_info["sec_filings"] = {
                "cached": True,
                "age_hours": round(age_hours, 1),
                "age_readable": f"{int(age_hours)}h ago"
                if age_hours >= 1
                else f"{int(age_hours * 60)}m ago",
            }
        else:
            cache_info["sec_filings"] = {"cached": False}
    else:
        cache_info["sec_filings"] = {"cached": False}

    # Check market data cache
    market_cache_path = Path("data/cache") / symbol.lower() if symbol else None
    if market_cache_path and market_cache_path.exists():
        import time

        try:
            # Get most recent file in market cache
            cache_files = list(market_cache_path.glob("*.parquet")) + list(
                market_cache_path.glob("*.json")
            )
            if cache_files:
                latest_cache = max(cache_files, key=lambda p: p.stat().st_mtime)
                mtime = latest_cache.stat().st_mtime
                age_hours = (time.time() - mtime) / 3600
                cache_info["market_data"] = {
                    "cached": True,
                    "age_hours": round(age_hours, 1),
                    "age_readable": f"{int(age_hours)}h ago"
                    if age_hours >= 1
                    else f"{int(age_hours * 60)}m ago",
                }
            else:
                cache_info["market_data"] = {"cached": False}
        except Exception:
            cache_info["market_data"] = {"cached": False}

    return cache_info


def _remove_keys(data: Dict[str, Any], keys: List[str]) -> None:
    """
    Remove specified keys from dictionary.

    Modifies data in-place.
    """
    for key in keys:
        data.pop(key, None)


def _remove_empty_values(data: Any) -> Any:
    """
    Recursively remove empty/null values from data structure.

    Handles numpy arrays and pandas objects safely (they raise ValueError
    on ambiguous truth comparisons like `arr in [None, [], {}]`).

    Returns cleaned data structure.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            # Skip empty values
            if _is_empty_value(v):
                continue
            # Skip zero scores (but keep other zero values)
            if isinstance(v, (int, float)) and v == 0 and k.endswith("_score"):
                continue
            # Recursively clean and add
            cleaned[k] = _remove_empty_values(v)
        return cleaned
    elif isinstance(data, list):
        return [
            _remove_empty_values(item) for item in data if not _is_empty_value(item)
        ]
    elif isinstance(data, np.ndarray):
        # Convert numpy arrays to lists for JSON serialization
        return data.tolist() if data.size > 0 else []
    else:
        return data


def _calculate_expected_return(
    target_price: Optional[float], current_price: Optional[float]
) -> Optional[float]:
    """Calculate expected return percentage."""
    if target_price and current_price and current_price > 0:
        return round((target_price - current_price) / current_price * 100, 2)
    return None


def _normalize_recommendation_action(action: Optional[str]) -> Optional[str]:
    """Normalize recommendation action labels to canonical compact values."""
    if not action or not isinstance(action, str):
        return None
    norm = action.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "strongbuy": "strong_buy",
        "strongsell": "strong_sell",
    }
    norm = aliases.get(norm, norm)
    valid = {"strong_buy", "buy", "hold", "sell", "strong_sell"}
    return norm if norm in valid else None


def _recommendation_from_expected_return(
    expected_return_pct: Optional[float],
) -> Optional[str]:
    """
    Map valuation-implied expected return (%) to canonical recommendation action.
    """
    if expected_return_pct is None:
        return None
    if expected_return_pct >= 30:
        return "strong_buy"
    if expected_return_pct >= 10:
        return "buy"
    if expected_return_pct > -10:
        return "hold"
    if expected_return_pct > -30:
        return "sell"
    return "strong_sell"


def _action_polarity(action: Optional[str]) -> Optional[str]:
    if action in {"strong_buy", "buy"}:
        return "bullish"
    if action in {"strong_sell", "sell"}:
        return "bearish"
    if action == "hold":
        return "neutral"
    return None


def _action_score(action: Optional[str]) -> Optional[int]:
    mapping = {
        "strong_buy": 2,
        "buy": 1,
        "hold": 0,
        "sell": -1,
        "strong_sell": -2,
    }
    return mapping.get(action)


def _align_recommendation_with_expected_return(
    action: Optional[str], expected_return_pct: Optional[float]
) -> tuple[Optional[str], bool]:
    """
    Keep recommendation coherent with computed expected return.

    Returns:
        (final_action, adjusted_flag)
    """
    normalized = _normalize_recommendation_action(action)
    implied = _recommendation_from_expected_return(expected_return_pct)

    if not normalized:
        return implied or normalized, bool(implied)
    if not implied:
        return normalized, False

    # For low expected-return regimes, avoid extreme recommendations.
    if abs(expected_return_pct or 0) < 10 and normalized != "hold":
        return "hold", True

    # Override when polarity conflicts materially, or severity is clearly mismatched.
    norm_pol = _action_polarity(normalized)
    imp_pol = _action_polarity(implied)
    norm_score = _action_score(normalized)
    imp_score = _action_score(implied)

    if (
        norm_pol
        and imp_pol
        and norm_pol != imp_pol
        and abs(expected_return_pct or 0) >= 10
    ):
        return implied, True
    if (
        norm_score is not None
        and imp_score is not None
        and abs(norm_score - imp_score) >= 2
        and abs(expected_return_pct or 0) < 30
    ):
        return implied, True

    return normalized, False


def _extract_list(data: Dict[str, Any], key: str, max_items: int = 3) -> List[str]:
    """Extract list from dict, limiting to max_items."""
    items = data.get(key, [])
    if isinstance(items, list):
        return items[:max_items]
    return []


# Export public interface
__all__ = [
    "OutputDetailLevel",
    "format_analysis_output",
]

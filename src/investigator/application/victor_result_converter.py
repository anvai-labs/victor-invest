# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
# SPDX-License-Identifier: Apache-2.0

"""Converter for Victor workflow results to agent orchestrator format.

This module provides utilities to convert Victor's AnalysisWorkflowState
into the agent orchestrator format expected by the result formatter.

This ensures consistency between victor-invest and investigator CLIs
and avoids code duplication.
"""

from datetime import datetime
from typing import Any, Dict, Optional


def convert_victor_state_to_agent_format(state: Any) -> Dict[str, Any]:
    """Convert Victor AnalysisWorkflowState to agent orchestrator format.

    This function transforms the Victor workflow state into the format expected
    by the investigator's result formatter for compact schema generation.

    Args:
        state: AnalysisWorkflowState from Victor workflow execution
               Must have: symbol, mode, fundamental_analysis, technical_analysis,
                         market_context, synthesis, recommendation, errors

    Returns:
        Dictionary in agent orchestrator format with agents, timing, metadata

    Example:
        >>> from victor_invest.workflows import AnalysisWorkflowState
        >>> from investigator.application.victor_result_converter import convert_victor_state_to_agent_format
        >>>
        >>> state = AnalysisWorkflowState(...)
        >>> agent_format = convert_victor_state_to_agent_format(state)
        >>> # Use with format_analysis_output
        >>> from investigator.application import format_analysis_output, OutputDetailLevel
        >>> compact = format_analysis_output(agent_format, OutputDetailLevel.COMPACT)
    """
    # Build agent-orchestrator compatible format
    agent_format = {
        "symbol": _get_state_attr(state, "symbol"),
        "mode": _get_state_attr(state, "mode", "value"),
        "started_at": datetime.now().isoformat(),
        "completed_at": datetime.now().isoformat(),
        "duration": 0.0,
        "detail_level": "compact",
        "agents": {},
    }

    # Add fundamental analysis if present
    fundamental_analysis = _get_state_attr(state, "fundamental_analysis")
    if fundamental_analysis:
        fundamental_data = _extract_fundamental_data(fundamental_analysis)
        if fundamental_data:
            agent_format["agents"]["fundamental"] = fundamental_data

    # Add technical analysis if present
    technical_analysis = _get_state_attr(state, "technical_analysis")
    if technical_analysis:
        technical_data = _extract_technical_data(technical_analysis)
        if technical_data:
            agent_format["agents"]["technical"] = technical_data

    # Add market context if present
    market_context = _get_state_attr(state, "market_context")
    if market_context:
        agent_format["agents"]["market_context"] = market_context

    # Add synthesis if present
    synthesis = _get_state_attr(state, "synthesis")
    if synthesis:
        agent_format["agents"]["synthesis"] = synthesis

    # Add recommendation as top-level field
    recommendation = _get_state_attr(state, "recommendation")
    if recommendation:
        agent_format["recommendation"] = recommendation

    # Add errors if present
    errors = _get_state_attr(state, "errors")
    if errors:
        agent_format["errors"] = errors

    return agent_format


def _get_state_attr(state: Any, attr_name: str, sub_attr: Optional[str] = None) -> Any:
    """Safely get attribute from state object.

    Handles both dataclass and dict-like objects.

    Args:
        state: State object (dataclass or dict)
        attr_name: Primary attribute name
        sub_attr: Optional sub-attribute name (e.g., "value" for enum)

    Returns:
        Attribute value or None if not found
    """
    # Try dataclass attribute access
    if hasattr(state, attr_name):
        value = getattr(state, attr_name)
        if sub_attr and hasattr(value, sub_attr):
            return getattr(value, sub_attr)
        return value

    # Try dict-like access
    if isinstance(state, dict):
        value = state.get(attr_name)
        if sub_attr and isinstance(value, dict):
            return value.get(sub_attr)
        return value

    return None


def _extract_fundamental_data(
    fundamental_analysis: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Extract fundamental analysis data in agent orchestrator format.

    Transforms victor-invest fundamental data structure to match
    investigator's expected format with valuation section.

    Args:
        fundamental_analysis: Fundamental analysis from victor-invest

    Returns:
        Formatted fundamental data or None if extraction fails
    """
    if not isinstance(fundamental_analysis, dict):  # type: ignore
        return None

    fundamental = fundamental_analysis.get("data", {}) if isinstance(fundamental_analysis.get("data"), dict) else {}
    if not fundamental:
        return None

    consensus_fair_value = fundamental.get("consensus_fair_value")
    consensus_upside = fundamental.get("consensus_upside", 0)
    overall_score = fundamental.get("overall_score", 70)

    # Extract SEC data - check top-level first (new handler structure), then nested
    sec_data = {}
    if fundamental_analysis.get("sec_data"):
        # New handler structure - sec_data at top level
        sec_data = fundamental_analysis.get("sec_data", {})
    elif fundamental.get("sec_data"):
        # Old structure - sec_data nested in data
        sec_data = fundamental.get("sec_data", {})
    elif isinstance(sec_data, dict):
        # Fallback to empty dict if not found
        sec_data = {}

    quarterly_metrics = sec_data.get("quarterly_metrics", []) if isinstance(sec_data, dict) else []
    forward_guidance = sec_data.get("forward_guidance") if isinstance(sec_data, dict) else None
    recent_filings = sec_data.get("recent_filings", []) if isinstance(sec_data, dict) else []

    # Transform to expected format with valuation section
    result = {
        "valuation": {
            "current_price": fundamental.get("current_price"),
            "fair_value": consensus_fair_value,
            "fair_value_estimate": consensus_fair_value,
            "recommendation": "BUY" if consensus_upside > 0 else "HOLD",
            "valuation_methods": {
                "multi_model": {
                    "blended_fair_value": consensus_fair_value,
                    "overall_confidence": 0.7,
                    "model_agreement_score": 0.7,
                    "applicable_models": fundamental.get("models_applied", []),
                },
                # Add individual models in the format expected by _compact_valuation_models
                **{
                    model_name: {
                        "applicable": True,
                        "fair_value_per_share": model_data.get("fair_value_per_share"),
                        "weight": model_data.get("confidence"),
                        "confidence_score": model_data.get("confidence"),
                        "assumptions": model_data.get("assumptions", {}),
                    }
                    for model_name, model_data in fundamental.get("models", {}).items()
                },
            },
            "investment_grade": "A" if overall_score > 70 else "B",
            "confidence": {
                "confidence_score": overall_score / 100,
                "confidence_level": "HIGH" if overall_score > 70 else "MEDIUM",
            },
            "data_quality": {
                "data_quality_score": 0.8,
                "quality_grade": "B+",
                "completeness_score": 0.85,
            },
            "ratios": {
                "current_price": fundamental.get("current_price"),
            },
            "multi_model_summary": {
                "blended_fair_value": consensus_fair_value,
                "overall_confidence": 0.7,
                "model_agreement_score": 0.7,
                "applicable_models": fundamental.get("models_applied", []),
            },
        },
        "recommendation": "BUY" if consensus_upside > 0 else "HOLD",
        "investment_grade": "A" if overall_score > 70 else "B",
        "current_price": fundamental.get("current_price"),
        "multi_model_summary": {
            "blended_fair_value": consensus_fair_value,
            "overall_confidence": 0.7,
            "model_agreement_score": 0.7,
            "applicable_models": fundamental.get("models_applied", []),
        },
        # Include SEC data for UI consumption
        "sec_data": {
            "quarterly_metrics_count": len(quarterly_metrics) if quarterly_metrics else 0,
            "forward_guidance": forward_guidance,
            "recent_filings_count": len(recent_filings) if recent_filings else 0,
        },
    }

    return result


def _extract_technical_data(
    technical_analysis: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Extract technical analysis data in agent orchestrator format.

    Handles both old structure (indicators/trend/support_resistance) and
    new multi-tier structure (weekly/daily/summary).

    Args:
        technical_analysis: Technical analysis from victor-invest

    Returns:
        Formatted technical data or None if extraction fails
    """
    if not isinstance(technical_analysis, dict):  # type: ignore
        return None

    # Handle new multi-tier structure directly (no 'data' wrapper)
    if technical_analysis.get("status") == "success":
        # New handler-based structure
        result = {
            "current_price": technical_analysis.get("current_price"),
            "recommendation": technical_analysis.get("recommendation"),
            "technical_rating": technical_analysis.get("rating"),
            # Multi-tier analysis (weekly strategic + daily tactical)
            "summary": technical_analysis.get("summary"),
            "weekly": technical_analysis.get("weekly"),
            "daily": technical_analysis.get("daily"),
        }

        # Extract levels from weekly/daily if available, otherwise from support_resistance
        if technical_analysis.get("support_resistance"):
            result["levels"] = technical_analysis["support_resistance"]
        elif technical_analysis.get("daily", {}).get("latest", {}).get("levels"):
            result["levels"] = technical_analysis["daily"]["latest"]["levels"]
        elif technical_analysis.get("weekly", {}).get("latest", {}).get("levels"):
            result["levels"] = technical_analysis["weekly"]["latest"]["levels"]

        return result

    # Handle old structure with 'data' wrapper (for backward compatibility)
    technical = technical_analysis.get("data", {}) if isinstance(technical_analysis.get("data"), dict) else {}
    if not technical:
        return None

    return {
        "current_price": technical.get("current_price"),
        "recommendation": technical.get("recommendation"),
        "technical_rating": technical.get("rating"),
        "levels": technical.get("levels", {}),
        # Multi-tier analysis (weekly strategic + daily tactical)
        "summary": technical.get("summary"),
        "weekly": technical.get("weekly"),
        "daily": technical.get("daily"),
    }

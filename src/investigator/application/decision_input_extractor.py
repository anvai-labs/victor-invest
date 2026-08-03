"""Adapters that normalize existing payloads into decision-policy inputs."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from investigator.domain.services.investment_decision_policy import DecisionInputs


def from_legacy_analysis_result(results: Mapping[str, Any]) -> DecisionInputs:
    symbol = _symbol(results)
    current_price = _first_number(
        results,
        (
            ("agents", "fundamental", "valuation", "current_price"),
            ("agents", "fundamental", "current_price"),
            ("fundamental", "valuation", "current_price"),
            ("valuation", "current_price"),
            ("price", "current"),
        ),
    )
    fair_value = _first_number(
        results,
        (
            ("agents", "fundamental", "multi_model_summary", "blended_fair_value"),
            ("agents", "fundamental", "valuation", "blended_fair_value"),
            ("agents", "fundamental", "valuation", "fair_value"),
            ("fundamental", "multi_model_summary", "blended_fair_value"),
            ("fundamental", "valuation", "blended_fair_value"),
            ("fundamental", "valuation", "fair_value"),
            ("valuation", "price_target_12m"),
            ("valuation", "fair_value"),
        ),
    )
    expected_return = _first_number(
        results,
        (
            ("valuation", "expected_return_pct"),
            ("agents", "fundamental", "multi_model_summary", "blended_upside_pct"),
            ("agents", "fundamental", "valuation", "upside_downside_pct"),
        ),
    )
    if expected_return is None:
        expected_return = _derive_expected_return(current_price, fair_value)

    return DecisionInputs(
        symbol=symbol,
        current_price=current_price,
        fair_value=fair_value,
        expected_return_pct=expected_return,
        technical_score=_first_number(
            results,
            (
                ("agents", "technical", "technical_score"),
                ("agents", "technical", "score"),
                ("technical", "technical_score"),
                ("technical_analysis", "score"),
            ),
        ),
        technical_signal=_first_value(
            results,
            (
                ("agents", "technical", "trend", "overall_signal"),
                ("agents", "technical", "overall_signal"),
                ("technical", "overall_signal"),
                ("technical_analysis", "trend", "overall_signal"),
            ),
        ),
        model_agreement_score=_normalize_agreement(
            _first_number(
                results,
                (
                    ("agents", "fundamental", "multi_model_summary", "model_agreement_score"),
                    ("fundamental", "multi_model_summary", "model_agreement_score"),
                    ("valuation", "model_agreement_score"),
                ),
            )
        ),
        dispersion_ratio=_first_number(
            results,
            (
                ("agents", "fundamental", "multi_model_summary", "dispersion_ratio"),
                ("fundamental", "multi_model_summary", "dispersion_ratio"),
                ("valuation", "dispersion_ratio"),
            ),
        ),
        data_quality_score=_normalize_quality(
            _first_number(
                results,
                (
                    ("agents", "fundamental", "data_quality", "data_quality_score"),
                    ("agents", "fundamental", "data_quality_score"),
                    ("fundamental", "data_quality", "data_quality_score"),
                    ("data_quality", "overall_score"),
                ),
            )
        ),
        applicable_models=_first_int(
            results,
            (
                ("agents", "fundamental", "multi_model_summary", "applicable_models"),
                ("fundamental", "multi_model_summary", "applicable_models"),
                ("valuation", "applicable_models"),
            ),
        ),
        valuation_age_hours=_first_number(results, (("valuation", "age_hours"), ("age_hours",))),
        divergence_flag=bool(
            _first_value(
                results,
                (
                    ("agents", "fundamental", "multi_model_summary", "divergence_flag"),
                    ("fundamental", "multi_model_summary", "divergence_flag"),
                    ("valuation", "divergence_flag"),
                ),
            )
            or False
        ),
        split_suspect=bool(_first_value(results, (("split_suspect",), ("valuation", "split_suspect"))) or False),
        llm_recommendation=_extract_recommendation(results),
    )


def from_victor_workflow_state(state: Mapping[str, Any]) -> DecisionInputs:
    payload = {
        "symbol": state.get("symbol"),
        "fundamental": state.get("fundamental_analysis") or {},
        "technical_analysis": state.get("technical_analysis") or {},
        "synthesis": state.get("synthesis") or {},
    }
    return DecisionInputs(
        symbol=_symbol(payload),
        current_price=_first_number(
            payload,
            (
                ("fundamental", "valuation_models", "current_price"),
                ("fundamental", "valuation", "current_price"),
                ("fundamental", "current_price"),
            ),
        ),
        fair_value=_first_number(
            payload,
            (
                ("fundamental", "valuation_models", "blended_fair_value"),
                ("fundamental", "multi_model_summary", "blended_fair_value"),
                ("fundamental", "valuation", "fair_value"),
                ("fundamental", "fair_value"),
            ),
        ),
        expected_return_pct=_expected_return_for_payload(
            payload,
            (
                ("fundamental", "valuation_models", "expected_return_pct"),
                ("fundamental", "valuation_models", "blended_upside_pct"),
                ("fundamental", "valuation", "upside_downside_pct"),
            ),
        ),
        technical_score=_first_number(
            payload,
            (
                ("technical_analysis", "technical_score"),
                ("technical_analysis", "score"),
            ),
        ),
        technical_signal=_first_value(
            payload,
            (
                ("technical_analysis", "trend", "overall_signal"),
                ("technical_analysis", "overall_signal"),
                ("technical_analysis", "signals", "trend"),
            ),
        ),
        model_agreement_score=_normalize_agreement(
            _first_number(
                payload,
                (
                    ("fundamental", "valuation_models", "model_agreement_score"),
                    ("fundamental", "multi_model_summary", "model_agreement_score"),
                ),
            )
        ),
        dispersion_ratio=_first_number(
            payload,
            (
                ("fundamental", "valuation_models", "dispersion_ratio"),
                ("fundamental", "multi_model_summary", "dispersion_ratio"),
            ),
        ),
        data_quality_score=_normalize_quality(
            _first_number(
                payload,
                (
                    ("fundamental", "data_quality", "data_quality_score"),
                    ("fundamental", "data_quality_score"),
                ),
            )
        ),
        applicable_models=_first_int(
            payload,
            (
                ("fundamental", "valuation_models", "applicable_models"),
                ("fundamental", "multi_model_summary", "applicable_models"),
            ),
        ),
        valuation_age_hours=_first_number(payload, (("fundamental", "valuation_age_hours"), ("age_hours",))),
        divergence_flag=bool(
            _first_value(
                payload,
                (
                    ("fundamental", "valuation_models", "divergence_flag"),
                    ("fundamental", "multi_model_summary", "divergence_flag"),
                ),
            )
            or False
        ),
        split_suspect=bool(_first_value(payload, (("fundamental", "split_suspect"),)) or False),
        llm_recommendation=_extract_recommendation(payload),
    )


def from_symbol_ranking_row(row: Mapping[str, Any]) -> DecisionInputs:
    current_price = _to_float(row.get("current_price"))
    fair_value = _to_float(row.get("target_price") or row.get("fair_value") or row.get("blended_fair_value"))
    expected_return = _to_float(row.get("expected_return_pct"))
    if expected_return is None:
        expected_return = _derive_expected_return(current_price, fair_value)

    return DecisionInputs(
        symbol=str(row.get("symbol") or row.get("ticker") or "").upper(),
        current_price=current_price,
        fair_value=fair_value,
        expected_return_pct=expected_return,
        technical_score=_to_float(row.get("technical_score")),
        technical_signal=_to_optional_str(row.get("technical_signal") or row.get("overall_signal")),
        model_agreement_score=_normalize_agreement(_to_float(row.get("model_agreement_score"))),
        dispersion_ratio=_to_float(row.get("dispersion_ratio")),
        data_quality_score=_normalize_quality(_to_float(row.get("data_quality_score"))),
        applicable_models=_to_int(row.get("weighted_model_count") or row.get("applicable_models")),
        valuation_age_hours=_to_float(row.get("age_hours") or row.get("valuation_age_hours")),
        divergence_flag=bool(row.get("divergence_flag") or False),
        split_suspect=bool(row.get("split_suspect") or row.get("split_suspect_excluded") or False),
        llm_recommendation=_to_optional_str(row.get("action") or row.get("recommendation")),
    )


def from_ui_cache_summary(summary: Mapping[str, Any]) -> DecisionInputs:
    current_price = _first_number(summary, (("price", "current"), ("valuation", "current_price"), ("current_price",)))
    fair_value = _first_number(
        summary,
        (
            ("valuation", "blended_fair_value"),
            ("valuation", "fair_value"),
            ("price", "target"),
            ("target_price",),
        ),
    )
    expected_return = _first_number(summary, (("price", "expected_return_pct"), ("valuation", "expected_return_pct")))
    if expected_return is None:
        expected_return = _derive_expected_return(current_price, fair_value)

    return DecisionInputs(
        symbol=_symbol(summary),
        current_price=current_price,
        fair_value=fair_value,
        expected_return_pct=expected_return,
        technical_score=_first_number(summary, (("technical", "technical_score"), ("technical_score",))),
        technical_signal=_first_value(summary, (("technical", "overall_signal"), ("overall_signal",))),
        model_agreement_score=_normalize_agreement(_first_number(summary, (("valuation", "model_agreement_score"),))),
        dispersion_ratio=_first_number(summary, (("valuation", "dispersion_ratio"),)),
        data_quality_score=_normalize_quality(
            _first_number(summary, (("quality", "data_quality_score"), ("data_quality_score",)))
        ),
        applicable_models=_first_int(summary, (("valuation", "applicable_models"), ("weighted_model_count",))),
        valuation_age_hours=_first_number(summary, (("age_hours",), ("valuation", "age_hours"))),
        divergence_flag=bool(_first_value(summary, (("valuation", "divergence_flag"), ("divergence_flag",))) or False),
        split_suspect=bool(_first_value(summary, (("valuation", "split_suspect"), ("split_suspect",))) or False),
        llm_recommendation=_extract_recommendation(summary),
    )


def _expected_return_for_payload(payload: Mapping[str, Any], paths: Iterable[tuple[str, ...]]) -> float | None:
    expected_return = _first_number(payload, paths)
    if expected_return is not None:
        return expected_return
    return _derive_expected_return(
        _first_number(
            payload, (("fundamental", "valuation_models", "current_price"), ("fundamental", "current_price"))
        ),
        _first_number(
            payload,
            (
                ("fundamental", "valuation_models", "blended_fair_value"),
                ("fundamental", "multi_model_summary", "blended_fair_value"),
                ("fundamental", "fair_value"),
            ),
        ),
    )


def _extract_recommendation(payload: Mapping[str, Any]) -> str | None:
    value = _first_value(
        payload,
        (
            ("recommendation", "action"),
            ("recommendation", "recommendation"),
            ("synthesis", "recommendation", "action"),
            ("synthesis", "recommendation", "final_recommendation"),
            ("synthesis", "recommendation", "recommendation"),
            ("agents", "synthesis", "recommendation", "action"),
            ("agents", "synthesis", "recommendation", "final_recommendation"),
            ("agents", "synthesis", "recommendation", "recommendation"),
            ("agents", "synthesis", "recommendation"),
        ),
    )
    if isinstance(value, Mapping):
        value = value.get("action") or value.get("recommendation") or value.get("rating")
    return _to_optional_str(value)


def _symbol(payload: Mapping[str, Any]) -> str:
    return str(payload.get("symbol") or payload.get("ticker") or "").upper()


def _first_value(payload: Mapping[str, Any], paths: Iterable[tuple[str, ...]]) -> Any:
    for path in paths:
        value = _get_path(payload, path)
        if value is not None:
            return value
    return None


def _first_number(payload: Mapping[str, Any], paths: Iterable[tuple[str, ...]]) -> float | None:
    for path in paths:
        value = _to_float(_get_path(payload, path))
        if value is not None:
            return value
    return None


def _first_int(payload: Mapping[str, Any], paths: Iterable[tuple[str, ...]]) -> int | None:
    for path in paths:
        value = _to_int(_get_path(payload, path))
        if value is not None:
            return value
    return None


def _get_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if math.isnan(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_agreement(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 1.0:
        return round(value / 100.0, 4)
    return round(value, 4)


def _normalize_quality(value: float | None) -> float | None:
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return round(value * 100.0, 2)
    return round(value, 2)


def _derive_expected_return(current_price: float | None, fair_value: float | None) -> float | None:
    if current_price is None or fair_value is None or current_price <= 0:
        return None
    return round(((fair_value / current_price) - 1.0) * 100.0, 2)

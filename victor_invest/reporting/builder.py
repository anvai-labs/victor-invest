# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deterministic builder that assembles an :class:`AnalystReport`.

Reads the dicts the pipeline already produced (synthesis, fundamental/valuation,
technical, market context) and surfaces analytics that the legacy PDF path drops
(full indicator set, support/resistance/Fibonacci, fair-value range, scenarios,
quality flags). No LLM calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from victor_invest.reporting import scoring
from victor_invest.reporting.financial_health import compute_quality_flags
from victor_invest.reporting.provenance import build_provenance
from victor_invest.reporting.schema import (
    AnalystReport,
    RatingBlock,
    RiskItem,
    Scenario,
    ScenarioAnalysis,
    TechnicalSetup,
    ValuationModelLine,
    ValuationSummary,
)

_MODEL_ORDER = ["dcf", "ggm", "pe", "ps", "pb", "ev_ebitda"]


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, dict):
            return result
    return {}


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_valuation(fund_data: Dict[str, Any]) -> ValuationSummary:
    models_raw = fund_data.get("models") or {}
    lines: List[ValuationModelLine] = []
    fair_values: List[float] = []
    methodology: Dict[str, Any] = {}
    for name in list(_MODEL_ORDER) + [m for m in models_raw if m not in _MODEL_ORDER]:
        model = models_raw.get(name)
        if not isinstance(model, dict):
            continue
        fv = _f(model.get("fair_value_per_share"))
        lines.append(
            ValuationModelLine(
                model=name,
                fair_value=fv,
                upside_pct=_f(model.get("upside_percent")),
                weight=_f(model.get("weight")),
            )
        )
        if fv is not None and fv > 0:
            fair_values.append(fv)
        if name == "dcf":
            methodology["wacc"] = _f(model.get("wacc"))
            methodology["terminal_growth_rate"] = _f(model.get("terminal_growth_rate"))
        elif name == "pe":
            methodology["target_pe"] = _f(model.get("pe_ratio"))
        elif name == "ps":
            methodology["target_ps"] = _f(model.get("ps_ratio"))
        elif name == "ev_ebitda":
            methodology["target_ev_ebitda"] = _f(model.get("ev_ebitda_ratio"))

    blended = _f(fund_data.get("consensus_fair_value"))
    current_price = _f(fund_data.get("current_price"))
    mos = None
    if blended and blended > 0 and current_price and current_price > 0:
        mos = round((blended - current_price) / blended * 100.0, 1)

    return ValuationSummary(
        blended_fair_value=blended,
        fair_value_low=round(min(fair_values), 2) if fair_values else None,
        fair_value_high=round(max(fair_values), 2) if fair_values else None,
        consensus_upside_pct=_f(fund_data.get("consensus_upside")),
        margin_of_safety_pct=mos,
        tier_classification=fund_data.get("tier_classification"),
        model_agreement_score=_f(fund_data.get("model_agreement_score")),
        divergence_flag=fund_data.get("divergence_flag"),
        models=lines,
        methodology=methodology,
    )


def _latest_technical(technical: Dict[str, Any]) -> Dict[str, Any]:
    # Prefer the daily tier; fall back to weekly. Each is the calculate_all output.
    for tier in ("daily", "weekly"):
        block = technical.get(tier)
        if isinstance(block, dict):
            latest = block.get("latest")
            if isinstance(latest, dict):
                return latest
    # Some shapes expose latest directly.
    direct = technical.get("latest")
    if isinstance(direct, dict):
        return direct
    return {}


def _build_technical(technical: Dict[str, Any]) -> TechnicalSetup:
    latest = _latest_technical(technical)
    summary_raw = technical.get("summary")
    summary: Dict[str, Any] = summary_raw if isinstance(summary_raw, dict) else {}
    price = latest.get("price") or {}
    ma = latest.get("moving_averages") or {}
    mom = latest.get("momentum") or {}
    vol = latest.get("volatility") or {}
    volume = latest.get("volume") or {}
    levels = latest.get("levels") or {}

    return TechnicalSetup(
        overall_bias=summary.get("overall_bias"),
        strategic_trend=summary.get("strategic_trend"),
        tactical_signal=summary.get("tactical_signal"),
        current_price=_f(price.get("close")),
        rsi_14=_f(mom.get("rsi_14")),
        macd=_f(mom.get("macd")),
        macd_signal=_f(mom.get("macd_signal")),
        macd_histogram=_f(mom.get("macd_histogram")),
        stoch_k=_f(mom.get("stoch_k")),
        stoch_d=_f(mom.get("stoch_d")),
        sma_20=_f(ma.get("sma_20")),
        sma_50=_f(ma.get("sma_50")),
        sma_200=_f(ma.get("sma_200")),
        ema_12=_f(ma.get("ema_12")),
        ema_26=_f(ma.get("ema_26")),
        bb_upper=_f(vol.get("bb_upper")),
        bb_middle=_f(vol.get("bb_middle")),
        bb_lower=_f(vol.get("bb_lower")),
        atr_14=_f(vol.get("atr_14")),
        obv=_f(volume.get("obv")),
        vwap=_f(volume.get("vwap")),
        support_1=_f(levels.get("support_1")),
        resistance_1=_f(levels.get("resistance_1")),
        pivot_point=_f(levels.get("pivot_point")),
        high_52w=_f(levels.get("high_52w")),
        low_52w=_f(levels.get("low_52w")),
        fib_38_2=_f(levels.get("fib_38_2")),
        fib_50_0=_f(levels.get("fib_50_0")),
        fib_61_8=_f(levels.get("fib_61_8")),
    )


def _build_scenarios(valuation: ValuationSummary, current_price: Optional[float]) -> ScenarioAnalysis:
    base = valuation.blended_fair_value
    if base is None:
        return ScenarioAnalysis()

    low = valuation.fair_value_low if valuation.fair_value_low is not None else base * 0.85
    high = valuation.fair_value_high if valuation.fair_value_high is not None else base * 1.15

    def _ret(pt: Optional[float]) -> Optional[float]:
        return scoring.upside_pct(current_price, pt)

    weights = {"Bull": 0.25, "Base": 0.50, "Bear": 0.25}
    scenarios = [
        Scenario(
            "Bull",
            weights["Bull"],
            round(high, 2),
            _ret(high),
            "Highest model fair value realized (multiple re-rating / upside execution).",
        ),
        Scenario(
            "Base",
            weights["Base"],
            round(base, 2),
            _ret(base),
            "Blended consensus fair value across applicable valuation models.",
        ),
        Scenario(
            "Bear",
            weights["Bear"],
            round(low, 2),
            _ret(low),
            "Lowest model fair value realized (de-rating / execution risk).",
        ),
    ]
    pw_target = round(sum(s.probability * (s.price_target or 0.0) for s in scenarios), 2)
    pw_return = _ret(pw_target)
    return ScenarioAnalysis(
        scenarios=scenarios,
        probability_weighted_target=pw_target,
        probability_weighted_return_pct=pw_return,
    )


def _risk_items(synthesis: Dict[str, Any]) -> List[RiskItem]:
    detailed = synthesis.get("risk_factors_detailed")
    items: List[RiskItem] = []
    if isinstance(detailed, list) and detailed:
        for entry in detailed:
            if isinstance(entry, dict):
                items.append(
                    RiskItem(
                        description=str(entry.get("description") or entry.get("risk") or entry),
                        category=entry.get("category"),
                        severity=entry.get("severity"),
                    )
                )
            else:
                items.append(RiskItem(description=str(entry)))
        return items
    for risk in synthesis.get("key_risks") or []:
        items.append(RiskItem(description=str(risk)))
    return items


def build_analyst_report(
    state: Any,
    *,
    data_as_of: Optional[str] = None,
) -> AnalystReport:
    """Assemble an :class:`AnalystReport` from an AnalysisWorkflowState or dict."""
    state_dict = _as_dict(state)
    symbol = state_dict.get("symbol") or getattr(state, "symbol", "") or ""
    mode = state_dict.get("mode") or getattr(state, "mode", None)
    mode_str = getattr(mode, "value", None) or (str(mode) if mode is not None else None)

    synthesis = _as_dict(state_dict.get("synthesis"))
    fundamental = _as_dict(state_dict.get("fundamental_analysis"))
    fund_data = _as_dict(fundamental.get("data"))
    technical = _as_dict(state_dict.get("technical_analysis"))
    sec_data = _as_dict(fundamental.get("sec_data"))

    valuation = _build_valuation(fund_data)
    technical_setup = _build_technical(technical)
    current_price = (
        _f(fund_data.get("current_price")) or technical_setup.current_price or _f(synthesis.get("current_price"))
    )

    # Canonical scoring / rating / price target.
    individual = _as_dict(synthesis.get("individual_scores"))
    fundamental_score = _f(individual.get("fundamental")) or _f(fund_data.get("overall_score"))
    technical_score = _f(individual.get("technical"))
    composite = scoring.composite_score(fundamental_score, technical_score)
    price_target = scoring.derive_price_target(
        valuation.blended_fair_value,
        _f(synthesis.get("price_target")),
        technical_setup.resistance_1,
    )
    target_upside = scoring.upside_pct(current_price, price_target)
    action, confidence = scoring.derive_rating(composite, target_upside)

    rating = RatingBlock(
        action=action,
        confidence=confidence,
        composite_score=composite,
        fundamental_score=fundamental_score,
        technical_score=technical_score,
        current_price=current_price,
        price_target=price_target,
        upside_pct=target_upside,
        methodology=scoring.METHODOLOGY,
    )

    scenarios = _build_scenarios(valuation, current_price)

    quarterly = sec_data.get("quarterly_metrics")
    latest_q = quarterly[0] if isinstance(quarterly, list) and quarterly else None
    prior_q = quarterly[1] if isinstance(quarterly, list) and len(quarterly) > 1 else None
    quality = compute_quality_flags(symbol, _as_dict(latest_q) or None, _as_dict(prior_q) or None)

    report = AnalystReport(
        symbol=symbol,
        as_of=data_as_of,
        thesis=str(synthesis.get("executive_summary") or ""),
        rating=rating,
        valuation=valuation,
        technical=technical_setup,
        scenarios=scenarios,
        catalysts=[str(c) for c in (synthesis.get("key_catalysts") or [])],
        risks=_risk_items(synthesis),
        quality=quality,
        score_breakdown=_as_dict(synthesis.get("score_breakdown")),
        fundamental_commentary=str(synthesis.get("fundamental_analysis_thinking") or ""),
        technical_commentary=str(synthesis.get("technical_analysis_thinking") or ""),
        provenance=build_provenance(
            data_as_of=data_as_of,
            llm_provider=state_dict.get("llm_provider"),
            llm_model=state_dict.get("llm_model"),
            workflow_mode=mode_str,
            synthesis_method=synthesis.get("synthesis_method"),
        ),
        warnings=list(state_dict.get("errors") or []),
    )
    return report

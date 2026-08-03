"""Deterministic investment decision policy.

This module owns the headline investment action used by CLI/API/UI surfaces.
LLM output may be carried as evidence, but it must not silently override the
deterministic decision produced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

ACTION_STRONG_BUY = "STRONG_BUY"
ACTION_BUY = "BUY"
ACTION_HOLD = "HOLD"
ACTION_SELL = "SELL"
ACTION_STRONG_SELL = "STRONG_SELL"
ACTION_REVIEW = "REVIEW"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

MIN_DATA_QUALITY = 60.0
REVIEW_DATA_QUALITY = 40.0
MIN_MODEL_AGREEMENT = 0.35
REVIEW_MODEL_AGREEMENT = 0.15
MAX_DISPERSION = 0.75
REVIEW_DISPERSION = 1.25
MAX_VALUATION_AGE_HOURS = 24.0 * 30.0

STRONG_BUY_UPSIDE = 25.0
BUY_UPSIDE = 12.0
SELL_DOWNSIDE = -10.0
STRONG_SELL_DOWNSIDE = -25.0


@dataclass(frozen=True)
class DecisionInputs:
    symbol: str
    current_price: Optional[float]
    fair_value: Optional[float]
    expected_return_pct: Optional[float]
    technical_score: Optional[float]
    technical_signal: Optional[str]
    model_agreement_score: Optional[float]
    dispersion_ratio: Optional[float]
    data_quality_score: Optional[float]
    applicable_models: Optional[int]
    valuation_age_hours: Optional[float]
    divergence_flag: bool = False
    split_suspect: bool = False
    llm_recommendation: Optional[str] = None
    extra_evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionOutput:
    action: str
    confidence: str
    score: float
    expected_return_pct: Optional[float]
    guardrails_triggered: tuple[str, ...]
    evidence: dict[str, Any]


class InvestmentDecisionPolicy:
    """Evaluate deterministic fair-value, technical, and quality evidence."""

    def evaluate(self, inputs: DecisionInputs) -> DecisionOutput:
        guardrails: list[str] = []
        evidence: dict[str, Any] = {
            "symbol": inputs.symbol.upper(),
            "current_price": inputs.current_price,
            "fair_value": inputs.fair_value,
            "expected_return_pct": self._expected_return(inputs),
            "technical_score": inputs.technical_score,
            "technical_signal": self._normalize_signal(inputs.technical_signal),
            "model_agreement_score": inputs.model_agreement_score,
            "dispersion_ratio": inputs.dispersion_ratio,
            "data_quality_score": inputs.data_quality_score,
            "applicable_models": inputs.applicable_models,
            "valuation_age_hours": inputs.valuation_age_hours,
        }
        evidence.update(dict(inputs.extra_evidence or {}))

        self._apply_hard_data_guardrails(inputs, guardrails)
        if self._requires_review(guardrails):
            return self._output(ACTION_REVIEW, CONFIDENCE_LOW, 0.0, inputs, guardrails, evidence)

        expected_return = evidence["expected_return_pct"]
        action = self._action_from_expected_return(expected_return)
        score = self._score_from_expected_return(expected_return)

        technical_signal = evidence["technical_signal"]
        technical_contradiction = self._is_technical_contradiction(action, technical_signal, inputs.technical_score)
        if technical_contradiction:
            guardrails.append("technical_contradiction")
            action = ACTION_HOLD
            score = self._move_score_toward_neutral(score)

        self._apply_soft_quality_guardrails(inputs, guardrails)
        action = self._apply_quality_action_downgrades(action, guardrails)

        llm_action = self._normalize_action(inputs.llm_recommendation)
        if llm_action:
            evidence["llm_recommendation"] = llm_action
            if self._is_action_opposed(action, llm_action):
                guardrails.append("llm_dissent")

        confidence = self._confidence(inputs, action, guardrails)
        return self._output(action, confidence, score, inputs, guardrails, evidence)

    def _apply_hard_data_guardrails(self, inputs: DecisionInputs, guardrails: list[str]) -> None:
        if inputs.current_price is None or inputs.current_price <= 0:
            guardrails.append("missing_current_price")
        if inputs.fair_value is None or inputs.fair_value <= 0:
            guardrails.append("missing_fair_value")
        if inputs.split_suspect:
            guardrails.append("split_suspect")
        if inputs.divergence_flag:
            guardrails.append("valuation_divergence")
        if inputs.data_quality_score is not None and inputs.data_quality_score < REVIEW_DATA_QUALITY:
            guardrails.append("low_data_quality")
        if inputs.model_agreement_score is not None and inputs.model_agreement_score < REVIEW_MODEL_AGREEMENT:
            guardrails.append("very_low_model_agreement")
        if inputs.dispersion_ratio is not None and inputs.dispersion_ratio > REVIEW_DISPERSION:
            guardrails.append("extreme_model_dispersion")
        if inputs.valuation_age_hours is not None and inputs.valuation_age_hours > MAX_VALUATION_AGE_HOURS:
            guardrails.append("stale_valuation")

    def _apply_soft_quality_guardrails(self, inputs: DecisionInputs, guardrails: list[str]) -> None:
        if inputs.data_quality_score is not None and inputs.data_quality_score < MIN_DATA_QUALITY:
            guardrails.append("low_data_quality")
        if inputs.model_agreement_score is not None and inputs.model_agreement_score < MIN_MODEL_AGREEMENT:
            guardrails.append("low_model_agreement")
        if inputs.dispersion_ratio is not None and inputs.dispersion_ratio > MAX_DISPERSION:
            guardrails.append("high_model_dispersion")
        if inputs.applicable_models is not None and inputs.applicable_models < 2:
            guardrails.append("single_model_valuation")

    @staticmethod
    def _requires_review(guardrails: list[str]) -> bool:
        review_guardrails = {
            "missing_current_price",
            "missing_fair_value",
            "split_suspect",
            "valuation_divergence",
            "low_data_quality",
            "very_low_model_agreement",
            "extreme_model_dispersion",
            "stale_valuation",
        }
        return any(guardrail in review_guardrails for guardrail in guardrails)

    @staticmethod
    def _apply_quality_action_downgrades(action: str, guardrails: list[str]) -> str:
        quality_guards = {"low_model_agreement", "high_model_dispersion", "single_model_valuation"}
        if not quality_guards.intersection(guardrails):
            return action
        if action in {ACTION_STRONG_BUY, ACTION_BUY}:
            return ACTION_BUY if action == ACTION_STRONG_BUY else action
        if action in {ACTION_STRONG_SELL, ACTION_SELL}:
            return ACTION_SELL if action == ACTION_STRONG_SELL else action
        return action

    @staticmethod
    def _expected_return(inputs: DecisionInputs) -> Optional[float]:
        if inputs.expected_return_pct is not None:
            return float(inputs.expected_return_pct)
        if inputs.current_price and inputs.current_price > 0 and inputs.fair_value and inputs.fair_value > 0:
            return ((float(inputs.fair_value) / float(inputs.current_price)) - 1.0) * 100.0
        return None

    @staticmethod
    def _action_from_expected_return(expected_return: Optional[float]) -> str:
        if expected_return is None:
            return ACTION_REVIEW
        if expected_return >= STRONG_BUY_UPSIDE:
            return ACTION_STRONG_BUY
        if expected_return >= BUY_UPSIDE:
            return ACTION_BUY
        if expected_return <= STRONG_SELL_DOWNSIDE:
            return ACTION_STRONG_SELL
        if expected_return <= SELL_DOWNSIDE:
            return ACTION_SELL
        return ACTION_HOLD

    @staticmethod
    def _score_from_expected_return(expected_return: Optional[float]) -> float:
        if expected_return is None:
            return 0.0
        return round(max(0.0, min(100.0, 50.0 + float(expected_return))), 2)

    @staticmethod
    def _move_score_toward_neutral(score: float) -> float:
        return round((score + 50.0) / 2.0, 2)

    def _is_technical_contradiction(
        self, action: str, technical_signal: Optional[str], technical_score: Optional[float]
    ) -> bool:
        if action in {ACTION_HOLD, ACTION_REVIEW}:
            return False

        normalized_signal = self._normalize_signal(technical_signal)
        bearish = normalized_signal == "bearish" or (technical_score is not None and technical_score <= 35.0)
        bullish = normalized_signal == "bullish" or (technical_score is not None and technical_score >= 65.0)

        if action in {ACTION_BUY, ACTION_STRONG_BUY} and bearish:
            return True
        return action in {ACTION_SELL, ACTION_STRONG_SELL} and bullish

    @staticmethod
    def _normalize_signal(signal: Optional[str]) -> Optional[str]:
        if signal is None:
            return None
        value = str(signal).strip().lower().replace("_", " ")
        if value in {"bullish", "buy", "strong buy", "positive", "uptrend"}:
            return "bullish"
        if value in {"bearish", "sell", "strong sell", "negative", "downtrend"}:
            return "bearish"
        if value in {"hold", "neutral", "mixed", "sideways"}:
            return "neutral"
        return value or None

    @staticmethod
    def _normalize_action(action: Optional[str]) -> Optional[str]:
        if action is None:
            return None
        value = str(action).strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "STRONGBUY": ACTION_STRONG_BUY,
            "BUY": ACTION_BUY,
            "HOLD": ACTION_HOLD,
            "NEUTRAL": ACTION_HOLD,
            "SELL": ACTION_SELL,
            "STRONGSELL": ACTION_STRONG_SELL,
            "REVIEW": ACTION_REVIEW,
        }
        return aliases.get(value.replace("_", ""), value if value in _VALID_ACTIONS else None)

    @staticmethod
    def _is_action_opposed(policy_action: str, other_action: str) -> bool:
        positive = {ACTION_BUY, ACTION_STRONG_BUY}
        negative = {ACTION_SELL, ACTION_STRONG_SELL}
        return (policy_action in positive and other_action in negative) or (
            policy_action in negative and other_action in positive
        )

    def _confidence(self, inputs: DecisionInputs, action: str, guardrails: list[str]) -> str:
        if action == ACTION_REVIEW:
            return CONFIDENCE_LOW
        if any(g in guardrails for g in ("technical_contradiction", "low_model_agreement", "high_model_dispersion")):
            return CONFIDENCE_LOW
        if any(g in guardrails for g in ("single_model_valuation", "llm_dissent")):
            return CONFIDENCE_MEDIUM
        if (
            inputs.data_quality_score is not None
            and inputs.data_quality_score >= 80.0
            and inputs.model_agreement_score is not None
            and inputs.model_agreement_score >= 0.7
            and action in {ACTION_STRONG_BUY, ACTION_STRONG_SELL}
        ):
            return CONFIDENCE_HIGH
        return CONFIDENCE_MEDIUM

    @staticmethod
    def _output(
        action: str,
        confidence: str,
        score: float,
        inputs: DecisionInputs,
        guardrails: list[str],
        evidence: dict[str, Any],
    ) -> DecisionOutput:
        return DecisionOutput(
            action=action,
            confidence=confidence,
            score=round(float(score), 2),
            expected_return_pct=InvestmentDecisionPolicy._expected_return(inputs),
            guardrails_triggered=tuple(dict.fromkeys(guardrails)),
            evidence=evidence,
        )


_VALID_ACTIONS = {
    ACTION_STRONG_BUY,
    ACTION_BUY,
    ACTION_HOLD,
    ACTION_SELL,
    ACTION_STRONG_SELL,
    ACTION_REVIEW,
}

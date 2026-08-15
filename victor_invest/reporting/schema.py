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

"""Typed schema for an institutional-style analyst report.

One dataclass tree populated identically regardless of how the underlying
analysis ran (rule-based or LLM synthesis). Everything is optional-friendly so a
partial pipeline still yields a coherent (if sparser) report.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Provenance:
    """Reproducibility manifest embedded in every report."""

    generated_at: str
    code_sha: str | None = None
    config_version: str | None = None
    data_as_of: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    workflow_mode: str | None = None
    synthesis_method: str | None = None


@dataclass
class RatingBlock:
    """Rating, conviction and price target with explicit derivation."""

    action: str = "HOLD"
    confidence: str = "MEDIUM"
    composite_score: float = 0.0
    fundamental_score: float | None = None
    technical_score: float | None = None
    current_price: float | None = None
    price_target: float | None = None
    upside_pct: float | None = None
    methodology: str = ""


@dataclass
class ValuationModelLine:
    model: str
    fair_value: float | None = None
    upside_pct: float | None = None
    weight: float | None = None


@dataclass
class ValuationSummary:
    blended_fair_value: float | None = None
    fair_value_low: float | None = None
    fair_value_high: float | None = None
    consensus_upside_pct: float | None = None
    margin_of_safety_pct: float | None = None
    tier_classification: str | None = None
    model_agreement_score: float | None = None
    divergence_flag: bool | None = None
    models: list[ValuationModelLine] = field(default_factory=list)
    methodology: dict[str, Any] = field(default_factory=dict)


@dataclass
class TechnicalSetup:
    overall_bias: str | None = None
    strategic_trend: str | None = None
    tactical_signal: str | None = None
    current_price: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    atr_14: float | None = None
    obv: float | None = None
    vwap: float | None = None
    support_1: float | None = None
    resistance_1: float | None = None
    pivot_point: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    fib_38_2: float | None = None
    fib_50_0: float | None = None
    fib_61_8: float | None = None
    signals: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    probability: float
    price_target: float | None = None
    return_pct: float | None = None
    narrative: str = ""


@dataclass
class ScenarioAnalysis:
    scenarios: list[Scenario] = field(default_factory=list)
    probability_weighted_target: float | None = None
    probability_weighted_return_pct: float | None = None


@dataclass
class RiskItem:
    description: str
    category: str | None = None
    severity: str | None = None


@dataclass
class QualityFlags:
    """Financial-health / earnings-quality screens."""

    altman_z: float | None = None
    altman_interpretation: str | None = None
    piotroski_f: float | None = None
    piotroski_interpretation: str | None = None
    beneish_m: float | None = None
    beneish_interpretation: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalystReport:
    """Top-level institutional-style analyst report."""

    symbol: str
    as_of: str | None = None
    thesis: str = ""
    rating: RatingBlock = field(default_factory=RatingBlock)
    valuation: ValuationSummary = field(default_factory=ValuationSummary)
    technical: TechnicalSetup = field(default_factory=TechnicalSetup)
    scenarios: ScenarioAnalysis = field(default_factory=ScenarioAnalysis)
    catalysts: list[str] = field(default_factory=list)
    risks: list[RiskItem] = field(default_factory=list)
    quality: QualityFlags = field(default_factory=QualityFlags)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    fundamental_commentary: str = ""
    technical_commentary: str = ""
    provenance: Provenance | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

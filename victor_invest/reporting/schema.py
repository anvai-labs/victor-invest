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
from typing import Any, Dict, List, Optional


@dataclass
class Provenance:
    """Reproducibility manifest embedded in every report."""

    generated_at: str
    code_sha: Optional[str] = None
    config_version: Optional[str] = None
    data_as_of: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    workflow_mode: Optional[str] = None
    synthesis_method: Optional[str] = None


@dataclass
class RatingBlock:
    """Rating, conviction and price target with explicit derivation."""

    action: str = "HOLD"
    confidence: str = "MEDIUM"
    composite_score: float = 0.0
    fundamental_score: Optional[float] = None
    technical_score: Optional[float] = None
    current_price: Optional[float] = None
    price_target: Optional[float] = None
    upside_pct: Optional[float] = None
    methodology: str = ""


@dataclass
class ValuationModelLine:
    model: str
    fair_value: Optional[float] = None
    upside_pct: Optional[float] = None
    weight: Optional[float] = None


@dataclass
class ValuationSummary:
    blended_fair_value: Optional[float] = None
    fair_value_low: Optional[float] = None
    fair_value_high: Optional[float] = None
    consensus_upside_pct: Optional[float] = None
    margin_of_safety_pct: Optional[float] = None
    tier_classification: Optional[str] = None
    model_agreement_score: Optional[float] = None
    divergence_flag: Optional[bool] = None
    models: List[ValuationModelLine] = field(default_factory=list)
    methodology: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TechnicalSetup:
    overall_bias: Optional[str] = None
    strategic_trend: Optional[str] = None
    tactical_signal: Optional[str] = None
    current_price: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None
    obv: Optional[float] = None
    vwap: Optional[float] = None
    support_1: Optional[float] = None
    resistance_1: Optional[float] = None
    pivot_point: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    fib_38_2: Optional[float] = None
    fib_50_0: Optional[float] = None
    fib_61_8: Optional[float] = None
    signals: List[str] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    probability: float
    price_target: Optional[float] = None
    return_pct: Optional[float] = None
    narrative: str = ""


@dataclass
class ScenarioAnalysis:
    scenarios: List[Scenario] = field(default_factory=list)
    probability_weighted_target: Optional[float] = None
    probability_weighted_return_pct: Optional[float] = None


@dataclass
class RiskItem:
    description: str
    category: Optional[str] = None
    severity: Optional[str] = None


@dataclass
class QualityFlags:
    """Financial-health / earnings-quality screens."""

    altman_z: Optional[float] = None
    altman_interpretation: Optional[str] = None
    piotroski_f: Optional[float] = None
    piotroski_interpretation: Optional[str] = None
    beneish_m: Optional[float] = None
    beneish_interpretation: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class AnalystReport:
    """Top-level institutional-style analyst report."""

    symbol: str
    as_of: Optional[str] = None
    thesis: str = ""
    rating: RatingBlock = field(default_factory=RatingBlock)
    valuation: ValuationSummary = field(default_factory=ValuationSummary)
    technical: TechnicalSetup = field(default_factory=TechnicalSetup)
    scenarios: ScenarioAnalysis = field(default_factory=ScenarioAnalysis)
    catalysts: List[str] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    quality: QualityFlags = field(default_factory=QualityFlags)
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    fundamental_commentary: str = ""
    technical_commentary: str = ""
    provenance: Optional[Provenance] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

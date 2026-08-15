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

"""Single canonical scoring rubric for the analyst report.

The audit found three divergent composite-score formulas across the codebase
(0.6/0.4, 0.7/0.3, and a 5-factor blend). This module is the one documented
rubric the report uses, so rating and price-target derivation are explicit and
reproducible. It does not mutate the live synthesis path — it derives the
report's headline numbers from whatever scores the synthesis produced.

Rubric
------
composite = 0.60 * fundamental_score + 0.40 * technical_score      (0-100)
rating:    composite >= 70 -> BUY ; >= 45 -> HOLD ; else SELL
           (overridden to BUY/SELL when |upside| vs fair value is decisive)
price target: prefer the blended fair value; fall back to the synthesis
              price_target, then to the first resistance level.
"""

from __future__ import annotations

FUNDAMENTAL_WEIGHT = 0.60
TECHNICAL_WEIGHT = 0.40

BUY_THRESHOLD = 70.0
HOLD_THRESHOLD = 45.0

# Upside (vs price target) that forces a directional call regardless of score.
DECISIVE_UPSIDE_PCT = 20.0

METHODOLOGY = (
    f"Composite = {FUNDAMENTAL_WEIGHT:.0%} fundamental + {TECHNICAL_WEIGHT:.0%} technical "
    f"(0-100). Rating: >= {BUY_THRESHOLD:.0f} BUY, >= {HOLD_THRESHOLD:.0f} HOLD, else SELL; "
    f"overridden to BUY/SELL when target upside exceeds +/-{DECISIVE_UPSIDE_PCT:.0f}%. "
    "Price target prefers blended fair value."
)


def composite_score(fundamental_score: float | None, technical_score: float | None) -> float:
    """Weighted composite in [0, 100]. Missing inputs are treated as neutral 50."""
    f = 50.0 if fundamental_score is None else float(fundamental_score)
    t = 50.0 if technical_score is None else float(technical_score)
    return round(FUNDAMENTAL_WEIGHT * f + TECHNICAL_WEIGHT * t, 1)


def upside_pct(current_price: float | None, target: float | None) -> float | None:
    if not current_price or current_price <= 0 or target is None:
        return None
    return round((target / current_price - 1.0) * 100.0, 1)


def derive_rating(composite: float, target_upside_pct: float | None) -> tuple[str, str]:
    """Return (action, confidence) from the canonical rubric."""
    if target_upside_pct is not None and target_upside_pct >= DECISIVE_UPSIDE_PCT:
        return "BUY", "HIGH"
    if target_upside_pct is not None and target_upside_pct <= -DECISIVE_UPSIDE_PCT:
        return "SELL", "HIGH"
    if composite >= BUY_THRESHOLD:
        return "BUY", "MEDIUM"
    if composite >= HOLD_THRESHOLD:
        return "HOLD", "MEDIUM"
    return "SELL", "MEDIUM"


def derive_price_target(
    blended_fair_value: float | None,
    synthesis_target: float | None,
    resistance_1: float | None,
) -> float | None:
    """Explicit, documented price-target precedence."""
    for candidate in (blended_fair_value, synthesis_target, resistance_1):
        if candidate is not None and float(candidate) > 0:
            return round(float(candidate), 2)
    return None

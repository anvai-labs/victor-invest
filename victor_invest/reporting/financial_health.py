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

"""Financial-health quality flags (Altman Z / Piotroski F / Beneish M).

Thin adapter that maps the pipeline's quarterly fundamentals into the existing
``FinancialData`` contract and delegates to the existing credit-risk
calculators, then projects the results onto the report's ``QualityFlags``. The
calculators degrade gracefully (partial components + warnings) when inputs such
as retained earnings or market cap are missing, so a sparse fundamentals payload
still yields whatever screens are computable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from victor_invest.reporting.schema import QualityFlags

logger = logging.getLogger(__name__)

# Map FinancialData field -> candidate metric keys (handles flat + nested shapes).
_FIELD_ALIASES = {
    "total_assets": ("total_assets",),
    "current_assets": ("current_assets",),
    "cash_and_equivalents": ("cash_and_equivalents", "cash"),
    "accounts_receivable": ("accounts_receivable", "receivables"),
    "inventory": ("inventory",),
    "property_plant_equipment": ("property_plant_equipment_net", "property_plant_equipment", "ppe"),
    "total_liabilities": ("total_liabilities",),
    "current_liabilities": ("current_liabilities",),
    "total_debt": ("total_debt",),
    "long_term_debt": ("long_term_debt",),
    "short_term_debt": ("short_term_debt",),
    "stockholders_equity": ("stockholders_equity", "total_equity"),
    "retained_earnings": ("retained_earnings",),
    "revenue": ("total_revenue", "revenue"),
    "gross_profit": ("gross_profit",),
    "operating_income": ("operating_income",),
    "net_income": ("net_income",),
    "cost_of_revenue": ("cost_of_revenue",),
    "sga_expense": ("sga_expense", "selling_general_administrative"),
    "depreciation_amortization": ("depreciation_amortization",),
    "interest_expense": ("interest_expense",),
    "operating_cash_flow": ("operating_cash_flow",),
    "capital_expenditures": ("capital_expenditures",),
    "market_cap": ("market_cap",),
    "shares_outstanding": ("shares_outstanding", "weighted_average_diluted_shares_outstanding"),
}


def _flatten(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a quarterly metrics dict (nested income/balance/cash or flat)."""
    flat: Dict[str, Any] = {}
    for key, value in metrics.items():
        if key in ("income_statement", "balance_sheet", "cash_flow", "market_metrics") and isinstance(value, dict):
            flat.update(value)
        else:
            flat.setdefault(key, value)
    return flat


def _coerce(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_financial_data(metrics: Dict[str, Any], symbol: str, prior: Optional[Dict[str, Any]] = None) -> Any:
    from investigator.domain.services.credit_risk.protocols import FinancialData

    flat = _flatten(metrics)
    kwargs: Dict[str, Any] = {"symbol": symbol}
    for field_name, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in flat and flat[alias] is not None:
                kwargs[field_name] = _coerce(flat[alias])
                break
    data = FinancialData(**kwargs)
    if prior is not None:
        data.prior_period = _to_financial_data(prior, symbol)
    return data


def compute_quality_flags(
    symbol: str,
    metrics: Optional[Dict[str, Any]],
    prior_metrics: Optional[Dict[str, Any]] = None,
    market_cap: Optional[float] = None,
) -> QualityFlags:
    """Compute Altman/Piotroski/Beneish screens into QualityFlags.

    Args:
        symbol: Ticker.
        metrics: Latest quarterly/annual fundamentals (flat or nested shape).
        prior_metrics: Prior-period fundamentals (enables Piotroski/Beneish deltas).
        market_cap: Optional market cap to backfill Altman X4 when absent.
    """
    flags = QualityFlags()
    if not metrics:
        flags.warnings.append("No fundamentals available for financial-health screens")
        return flags

    try:
        from investigator.domain.services.credit_risk.service import CreditRiskService

        data = _to_financial_data(metrics, symbol, prior_metrics)
        if market_cap and getattr(data, "market_cap", None) is None:
            data.market_cap = float(market_cap)

        service = CreditRiskService()
        altman = service.calculate_altman(data)
        piotroski = service.calculate_piotroski(data)
        beneish = service.calculate_beneish(data)

        flags.altman_z = altman.score
        flags.altman_interpretation = altman.interpretation or None
        flags.piotroski_f = piotroski.score
        flags.piotroski_interpretation = piotroski.interpretation or None
        flags.beneish_m = beneish.score
        flags.beneish_interpretation = beneish.interpretation or None

        collected: List[str] = []
        for result in (altman, piotroski, beneish):
            collected.extend(getattr(result, "warnings", []) or [])
        flags.warnings = collected
    except Exception as exc:  # noqa: BLE001 - screens are best-effort
        logger.warning("Financial-health screens failed for %s: %s", symbol, exc)
        flags.warnings.append(f"financial-health screens unavailable: {exc}")

    return flags

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

"""
Q4 Quarterly Data Derivation Service

This module provides functionality to derive Q4 quarterly data from FY (full year)
filings when Q4 is missing from the SEC Company Facts API.

The SEC Company Facts API often provides FY (full year) as an aggregate but doesn't
provide Q4 as a separate entry. This service derives Q4 by subtracting Q1+Q2+Q3 from the FY total.

Usage:
    from investigator.domain.services.valuation_shared.q4_derivation import derive_q4_from_fy

    quarters_data = [...]  # List with Q1, Q2, Q3, FY entries
    result = derive_q4_from_fy(quarters_data, "AAPL")
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


def subtract_metric(
    fy_val: Optional[float],
    q1_val: Optional[float],
    q2_val: Optional[float],
    q3_val: Optional[float],
) -> Optional[float]:
    """
    Safely subtract Q1+Q2+Q3 from FY value.

    Args:
        fy_val: FY total value
        q1_val: Q1 value
        q2_val: Q2 value
        q3_val: Q3 value

    Returns:
        Derived Q4 value, or None if any value is missing
    """
    vals = [v for v in [fy_val, q1_val, q2_val, q3_val] if v is not None]
    if len(vals) == 4:
        return fy_val - q1_val - q2_val - q3_val
    return None


def derive_q4_from_fy(
    quarters_data: List[Dict[str, Any]], symbol: str
) -> List[Dict[str, Any]]:
    """
    Derive Q4 quarterly data from FY filings when Q4 is missing.

    The SEC Company Facts API often provides FY (full year) as an aggregate
    but doesn't provide Q4 as a separate entry. This function derives Q4 by
    subtracting Q1+Q2+Q3 from the FY total.

    Args:
        quarters_data: List of quarterly entries from database
        symbol: Stock ticker (for logging)

    Returns:
        Updated list with derived Q4 entries replacing FY entries

    Example:
        >>> quarters = [
        ...     {"fiscal_year": 2025, "fiscal_period": "Q1", "net_income": 305_000_000},
        ...     {"fiscal_year": 2025, "fiscal_period": "Q2", "net_income": 336_000_000},
        ...     {"fiscal_year": 2025, "fiscal_period": "Q3", "net_income": 340_000_000},
        ...     {"fiscal_year": 2025, "fiscal_period": "FY", "net_income": 1_469_000_000},
        ... ]
        >>> result = derive_q4_from_fy(quarters, "STX")
        >>> # result will have Q1, Q2, Q3, Q4 (FY replaced with derived Q4)
    """
    # Group by fiscal year
    fy_groups = defaultdict(list)
    for q in quarters_data:
        fy = q.get("fiscal_year")
        if fy:
            fy_groups[fy].append(q)

    derived_quarters = []
    q4_derived_count = 0

    for fy in sorted(fy_groups.keys(), reverse=True):
        fy_quarters = fy_groups[fy]

        # Get the fiscal periods present
        periods = [q.get("fiscal_period") for q in fy_quarters]
        has_fy = "FY" in periods
        has_q1 = "Q1" in periods
        has_q2 = "Q2" in periods
        has_q3 = "Q3" in periods
        has_q4 = "Q4" in periods

        # If we have FY, Q1, Q2, Q3 but no Q4, derive Q4 from FY
        if has_fy and has_q1 and has_q2 and has_q3 and not has_q4:
            fy_entry = next(q for q in fy_quarters if q.get("fiscal_period") == "FY")
            q1_entry = next(q for q in fy_quarters if q.get("fiscal_period") == "Q1")
            q2_entry = next(q for q in fy_quarters if q.get("fiscal_period") == "Q2")
            q3_entry = next(q for q in fy_quarters if q.get("fiscal_period") == "Q3")

            # Derive Q4 by subtracting Q1+Q2+Q3 from FY
            derived_q4 = {
                "symbol": symbol,
                "fiscal_year": fy,
                "fiscal_period": "Q4",
                "adsh": fy_entry.get("adsh", ""),
                "filed": fy_entry.get("filed"),
                "period_end": fy_entry.get("period_end"),
                "period_end_date": fy_entry.get("period_end"),
                "filed_date": fy_entry.get("filed"),
                "form": fy_entry.get("form", "10-K"),
                "_derived": True,  # Flag as derived
                # Derive financial metrics
                "shares_outstanding": fy_entry.get(
                    "weighted_average_diluted_shares_outstanding"
                )
                or fy_entry.get("shares_outstanding"),
                "actual_shares_outstanding": fy_entry.get("shares_outstanding"),
                "weighted_average_diluted_shares_outstanding": fy_entry.get(
                    "weighted_average_diluted_shares_outstanding"
                ),
                # Income statement metrics
                "total_revenue": subtract_metric(
                    fy_entry.get("total_revenue"),
                    q1_entry.get("total_revenue"),
                    q2_entry.get("total_revenue"),
                    q3_entry.get("total_revenue"),
                ),
                "net_income": subtract_metric(
                    fy_entry.get("net_income"),
                    q1_entry.get("net_income"),
                    q2_entry.get("net_income"),
                    q3_entry.get("net_income"),
                ),
                "gross_profit": subtract_metric(
                    fy_entry.get("gross_profit"),
                    q1_entry.get("gross_profit"),
                    q2_entry.get("gross_profit"),
                    q3_entry.get("gross_profit"),
                ),
                "operating_income": subtract_metric(
                    fy_entry.get("operating_income"),
                    q1_entry.get("operating_income"),
                    q2_entry.get("operating_income"),
                    q3_entry.get("operating_income"),
                ),
                "interest_expense": subtract_metric(
                    fy_entry.get("interest_expense"),
                    q1_entry.get("interest_expense"),
                    q2_entry.get("interest_expense"),
                    q3_entry.get("interest_expense"),
                ),
                "income_tax_expense": subtract_metric(
                    fy_entry.get("income_tax_expense"),
                    q1_entry.get("income_tax_expense"),
                    q2_entry.get("income_tax_expense"),
                    q3_entry.get("income_tax_expense"),
                ),
                "cost_of_revenue": subtract_metric(
                    fy_entry.get("cost_of_revenue"),
                    q1_entry.get("cost_of_revenue"),
                    q2_entry.get("cost_of_revenue"),
                    q3_entry.get("cost_of_revenue"),
                ),
                "depreciation_amortization": subtract_metric(
                    fy_entry.get("depreciation_amortization"),
                    q1_entry.get("depreciation_amortization"),
                    q2_entry.get("depreciation_amortization"),
                    q3_entry.get("depreciation_amortization"),
                ),
                # Cash flow metrics
                "operating_cash_flow": subtract_metric(
                    fy_entry.get("operating_cash_flow"),
                    q1_entry.get("operating_cash_flow"),
                    q2_entry.get("operating_cash_flow"),
                    q3_entry.get("operating_cash_flow"),
                ),
                "capital_expenditures": subtract_metric(
                    fy_entry.get("capital_expenditures"),
                    q1_entry.get("capital_expenditures"),
                    q2_entry.get("capital_expenditures"),
                    q3_entry.get("capital_expenditures"),
                ),
                "free_cash_flow": subtract_metric(
                    fy_entry.get("free_cash_flow"),
                    q1_entry.get("free_cash_flow"),
                    q2_entry.get("free_cash_flow"),
                    q3_entry.get("free_cash_flow"),
                ),
                "dividends_paid": subtract_metric(
                    fy_entry.get("dividends_paid"),
                    q1_entry.get("dividends_paid"),
                    q2_entry.get("dividends_paid"),
                    q3_entry.get("dividends_paid"),
                ),
            }

            # Add nested structure for compatibility
            derived_q4["income_statement"] = {
                "total_revenue": derived_q4["total_revenue"],
                "net_income": derived_q4["net_income"],
                "gross_profit": derived_q4["gross_profit"],
                "operating_income": derived_q4["operating_income"],
                "interest_expense": derived_q4["interest_expense"],
                "income_tax_expense": derived_q4["income_tax_expense"],
                "cost_of_revenue": derived_q4["cost_of_revenue"],
                "depreciation_amortization": derived_q4["depreciation_amortization"],
                "stock_based_compensation": None,  # Not derived
                "research_and_development_expense": None,  # Not derived
                "selling_general_administrative_expense": None,  # Not derived
            }

            derived_q4["cash_flow"] = {
                "operating_cash_flow": derived_q4["operating_cash_flow"],
                "capital_expenditures": derived_q4["capital_expenditures"],
                "free_cash_flow": derived_q4["free_cash_flow"],
                "dividends_paid": derived_q4["dividends_paid"],
                "is_ytd": False,
                "value_type": "quarterly",
            }

            derived_q4["balance_sheet"] = {
                # Balance sheet not derived (point-in-time, not additive)
                "total_assets": None,
                "total_liabilities": None,
                "stockholders_equity": None,
                "current_assets": None,
                "current_liabilities": None,
                "accounts_receivable": None,
                "inventory": None,
                "cash_and_equivalents": None,
                "long_term_debt": None,
                "short_term_debt": None,
                "total_debt": None,
            }

            # Add Q1, Q2, Q3 as-is, replace FY with derived Q4
            fy_quarterly_periods = [
                q for q in fy_quarters if q.get("fiscal_period") in ["Q1", "Q2", "Q3"]
            ]
            fy_quarterly_periods.append(derived_q4)

            # Sort by period_end_date (descending = most recent first)
            # Handle None values by treating them as oldest (empty string)
            def sort_key(x):
                val = x.get("period_end")
                if val is None:
                    return ""
                return str(val)

            fy_quarterly_periods.sort(key=sort_key, reverse=True)

            derived_quarters.extend(fy_quarterly_periods)

            q4_derived_count += 1

            # Safe logging that handles None values and Decimal types
            ni_val = derived_q4.get("net_income")
            rev_val = derived_q4.get("total_revenue")
            ni_float = float(ni_val) if ni_val is not None else None
            rev_float = float(rev_val) if rev_val is not None else None
            ni_str = f"${ni_float / 1e6:.0f}M" if ni_float is not None else "N/A"
            rev_str = f"${rev_float / 1e9:.2f}B" if rev_float is not None else "N/A"
            logger.info(
                f"[Q4 Derivation] {symbol} FY{fy}: Derived Q4 from FY filing "
                f"(NI: {ni_str}, Revenue: {rev_str})"
            )
        else:
            # No derivation needed, add all quarters as-is
            derived_quarters.extend(fy_quarters)

    if q4_derived_count > 0:
        logger.info(
            f"[Q4 Derivation] {symbol}: Derived {q4_derived_count} Q4 quarters from FY filings"
        )

    return derived_quarters


def filter_quarters_only(quarters_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter to only include Q1-Q4 periods, excluding FY periods.

    This is important for TTM calculations because including FY would
    double-count the quarterly data.

    Args:
        quarters_data: List of quarterly entries

    Returns:
        Filtered list with only Q1, Q2, Q3, Q4 periods
    """
    return [
        q for q in quarters_data if q.get("fiscal_period") in ["Q1", "Q2", "Q3", "Q4"]
    ]

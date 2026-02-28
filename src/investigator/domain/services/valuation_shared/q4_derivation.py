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

IMPORTANT: The SEC Company Facts API DOES provide Q4 data, but it's labeled incorrectly:
- Q4 data is filed in the Q1 10-Q report of the FOLLOWING fiscal year
- Example: Q4 2024 data ($36.33B, end=2024-12-27) is filed in Q1 FY2025 10-Q
- So it's stored as fiscal_period='Q1', fiscal_year=2025
- But the frame='CY2024Q4' correctly identifies it as Q4 2024 data

Two approaches are provided:
1. use_frame_based_quarters(): Uses frame field to identify actual quarters (PREFERRED)
2. derive_q4_from_fy(): Derives Q4 by FY - Q1 - Q2 - Q3 (LEGACY FALLBACK)

Usage:
    from investigator.domain.services.valuation_shared.q4_derivation import use_frame_based_quarters, derive_q4_from_fy

    # PREFERRED: Use frame-based quarter identification
    quarters_data = [...]  # List with mixed fiscal_period labels
    result = use_frame_based_quarters(quarters_data, "AAPL")

    # FALLBACK: Derive Q4 from FY when frame not available
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


def derive_q4_from_fy(quarters_data: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
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
                "shares_outstanding": fy_entry.get("weighted_average_diluted_shares_outstanding")
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

            # Balance sheet - COPIED from FY (not derived)
            # The FY filing's balance sheet IS the Q4 balance sheet (point-in-time as of fiscal year end)
            # Add to BOTH nested structure AND top level for compatibility with SEC filing tool
            derived_q4["balance_sheet"] = {
                "total_assets": fy_entry.get("total_assets"),
                "total_liabilities": fy_entry.get("total_liabilities"),
                "stockholders_equity": fy_entry.get("stockholders_equity"),
                "current_assets": fy_entry.get("current_assets"),
                "current_liabilities": fy_entry.get("current_liabilities"),
                "accounts_receivable": fy_entry.get("accounts_receivable"),
                "inventory": fy_entry.get("inventory"),
                "cash_and_equivalents": fy_entry.get("cash_and_equivalents"),
                "long_term_debt": fy_entry.get("long_term_debt"),
                "short_term_debt": fy_entry.get("short_term_debt"),
                "total_debt": fy_entry.get("total_debt"),
            }

            # Also add at top level for SEC filing tool compatibility
            derived_q4["total_assets"] = fy_entry.get("total_assets")
            derived_q4["total_liabilities"] = fy_entry.get("total_liabilities")
            derived_q4["stockholders_equity"] = fy_entry.get("stockholders_equity")
            derived_q4["current_assets"] = fy_entry.get("current_assets")
            derived_q4["current_liabilities"] = fy_entry.get("current_liabilities")
            derived_q4["accounts_receivable"] = fy_entry.get("accounts_receivable")
            derived_q4["inventory"] = fy_entry.get("inventory")
            derived_q4["cash_and_equivalents"] = fy_entry.get("cash_and_equivalents")
            derived_q4["long_term_debt"] = fy_entry.get("long_term_debt")
            derived_q4["short_term_debt"] = fy_entry.get("short_term_debt")
            derived_q4["total_debt"] = fy_entry.get("total_debt")

            # Debug: Log balance sheet values
            bs_values = derived_q4["balance_sheet"]
            logger.info(
                f"[Q4_COMPUTE] FY {fy} balance_sheet copied to derived Q4: "
                f"stockholders_equity=${bs_values.get('stockholders_equity') or 0:,.0f}, "
                f"total_assets=${bs_values.get('total_assets') or 0:,.0f}"
            )

            # Add Q1, Q2, Q3 as-is, replace FY with derived Q4
            fy_quarterly_periods = [q for q in fy_quarters if q.get("fiscal_period") in ["Q1", "Q2", "Q3"]]
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
                f"[Q4 Derivation] {symbol} FY{fy}: Derived Q4 from FY filing " f"(NI: {ni_str}, Revenue: {rev_str})"
            )
        else:
            # No derivation needed, add all quarters as-is
            derived_quarters.extend(fy_quarters)

    if q4_derived_count > 0:
        logger.info(f"[Q4 Derivation] {symbol}: Derived {q4_derived_count} Q4 quarters from FY filings")

    return derived_quarters


def extract_quarter_from_frame(frame: str) -> Optional[str]:
    """
    Extract quarter identifier from frame field.

    The frame field uses format like 'CY2024Q1', 'CY2024Q2', 'CY2024Q3', 'CY2024Q4'.
    This correctly identifies which quarter the data represents, unlike fiscal_period
    which reflects the filing period.

    Args:
        frame: Frame string from SEC data (e.g., 'CY2024Q1', 'CY2024Q3', '')

    Returns:
        'Q1', 'Q2', 'Q3', 'Q4', or None if frame doesn't match expected pattern

    Examples:
        >>> extract_quarter_from_frame('CY2024Q1')
        'Q1'
        >>> extract_quarter_from_frame('CY2024Q4')
        'Q4'
        >>> extract_quarter_from_frame('')
        None
        >>> extract_quarter_from_frame('N/A')
        None
    """
    if not frame or frame == "N/A":
        return None

    # Match pattern CY<year>Q<quarter>
    import re

    match = re.match(r"CY\d{4}Q([1-4])", frame)
    if match:
        return f"Q{match.group(1)}"

    return None


def extract_year_from_frame(frame: str) -> Optional[int]:
    """
    Extract year from frame field.

    Args:
        frame: Frame string from SEC data (e.g., 'CY2024Q1', 'CY2024Q3')

    Returns:
        Year as integer, or None if frame doesn't match expected pattern

    Examples:
        >>> extract_year_from_frame('CY2024Q1')
        2024
        >>> extract_year_from_frame('CY2025Q4')
        2025
    """
    if not frame or frame == "N/A":
        return None

    # Match pattern CY<year>Q<quarter>
    import re

    match = re.match(r"CY(\d{4})Q[1-4]", frame)
    if match:
        return int(match.group(1))

    return None


def use_frame_based_quarters(quarters_data: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
    """
    Reorganize quarterly data using frame field for accurate quarter identification.

    BACKGROUND: The SEC data has a critical issue where fiscal_period reflects the
    FILING period, not the DATA period. For example:
    - Q4 2024 data is filed in Q1 FY2025 10-Q report
    - So it's stored as fiscal_period='Q1', fiscal_year=2025
    - But frame='CY2024Q4' correctly identifies it as Q4 2024 data

    This function re-labels quarters based on the frame field, not fiscal_period.

    IMPORTANT: FY entries with frame like 'CY2025Q3' are NOT Q3 data - they are
    FY data filed in Q3. These should NOT be relabelled as quarters.

    Args:
        quarters_data: List of quarterly entries from database (may have mixed labels)
        symbol: Stock ticker (for logging)

    Returns:
        Reorganized list with correct fiscal_period and fiscal_year based on frame

    Example:
        >>> quarters = [
        ...     {"fiscal_period": "Q1", "fiscal_year": 2025, "frame": "CY2024Q4", "net_income": 36_330_000_000},
        ...     {"fiscal_period": "Q2", "fiscal_year": 2025, "frame": "CY2025Q1", "net_income": 24_780_000_000},
        ...     {"fiscal_period": "Q3", "fiscal_year": 2025, "frame": "CY2025Q2", "net_income": 23_434_000_000},
        ... ]
        >>> result = use_frame_based_quarters(quarters, "AAPL")
        >>> # result will have correct fiscal_period and fiscal_year from frame
    """
    reorganized = []

    for entry in quarters_data:
        frame = entry.get("frame", "")
        original_period = entry.get("fiscal_period", "")
        original_year = entry.get("fiscal_year")

        # CRITICAL: Don't relabel FY entries as quarters
        # FY entries with frame='CY2025Q3' means "FY data filed in Q3", not "Q3 data"
        if original_period == "FY":
            # Keep FY entries as-is
            reorganized.append(entry)
            continue

        # Try to extract quarter and year from frame (only for Q1-Q3 entries)
        frame_quarter = extract_quarter_from_frame(frame)
        frame_year = extract_year_from_frame(frame)

        if frame_quarter and frame_year:
            # Create a new entry with corrected fiscal_period and fiscal_year
            corrected_entry = entry.copy()
            corrected_entry["fiscal_period"] = frame_quarter
            corrected_entry["fiscal_year"] = frame_year
            corrected_entry["_original_fiscal_period"] = original_period
            corrected_entry["_original_fiscal_year"] = original_year
            corrected_entry["_relabelled_from_frame"] = True

            reorganized.append(corrected_entry)

            # Log relabeling for transparency
            if original_period != frame_quarter or original_year != frame_year:
                logger.debug(
                    f"[FRAME_RELABEL] {symbol} Relabelled: {original_period} FY{original_year} "
                    f"→ {frame_quarter} FY{frame_year} (from frame='{frame}')"
                )
        else:
            # No frame info, keep original entry
            reorganized.append(entry)

    # Group by (fiscal_year, fiscal_period) and keep only one entry per quarter
    # Prefer entries with explicit frames over entries without frames
    quarter_map = {}

    for entry in reorganized:
        key = (entry.get("fiscal_year"), entry.get("fiscal_period"))
        frame = entry.get("frame", "")

        # If we already have an entry for this quarter
        if key in quarter_map:
            existing_entry = quarter_map[key]
            existing_frame = existing_entry.get("frame", "")

            # Prefer entry with explicit frame (CY2024Q1) over empty frame
            if not existing_frame and frame:
                quarter_map[key] = entry
            elif existing_frame and not frame:
                # Keep existing entry with frame
                pass
            elif not existing_frame and not frame:
                # Both have no frame, keep the one with more data (more non-None fields)
                existing_data_count = sum(1 for v in existing_entry.values() if v is not None)
                new_data_count = sum(1 for v in entry.values() if v is not None)
                if new_data_count > existing_data_count:
                    quarter_map[key] = entry
        else:
            quarter_map[key] = entry

    # Convert back to list and sort by year/period (most recent first)
    result = list(quarter_map.values())
    result.sort(
        key=lambda x: (
            x.get("fiscal_year", 0),
            {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}.get(x.get("fiscal_period", ""), 0),
        ),
        reverse=True,
    )

    relabelled_count = sum(1 for e in result if e.get("_relabelled_from_frame"))
    if relabelled_count > 0:
        logger.info(
            f"[FRAME_RELABEL] {symbol}: Relabelled {relabelled_count} quarters "
            f"using frame field (total quarters: {len(result)})"
        )

    return result


def filter_quarters_only(quarters_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter to only include Q1-Q4 periods, excluding FY periods.

    This is important for TTM calculations because including FY would
    double-count the quarterly data.

    CRITICAL: With frame-based approach, we now handle multiple cases:

    1. FY periods (fiscal_period='FY') - these are full year data, EXCLUDE
    2. Derived Q4 periods (fiscal_period='Q4' with _derived=True) - INCLUDE
    3. Frame-based Q4 periods (e.g., frame='CY2024Q4') - INCLUDE
    4. Raw 10-K filings that are not derived Q4 - EXCLUDE

    Args:
        quarters_data: List of quarterly entries

    Returns:
        Filtered list with only Q1, Q2, Q3, Q4 periods
    """
    filtered = []
    for q in quarters_data:
        period = q.get("fiscal_period")
        form = q.get("form")
        frame = q.get("frame", "")
        derived = q.get("_derived", False)

        # Must be Q1-Q4 (not FY)
        if period not in ["Q1", "Q2", "Q3", "Q4"]:
            continue

        # Include derived Q4 entries
        if derived:
            filtered.append(q)
            continue

        # Include frame-based Q4 entries (frame ends with Q4)
        if frame and "Q4" in frame:
            filtered.append(q)
            continue

        # Exclude raw 10-K filings (unless derived Q4)
        if form == "10-K":
            continue

        # Include all other entries (Q1-Q3 from 10-Q, frame-based quarters)
        filtered.append(q)

    # Debug: Log what was filtered
    excluded = [q for q in quarters_data if q not in filtered]
    if excluded:
        symbol = quarters_data[0].get("symbol", "UNKNOWN") if quarters_data else "UNKNOWN"
        logger.info(
            f"[FILTER_QUARTERS] {symbol}: Filtered {len(quarters_data)} → {len(filtered)} quarters. "
            f"Excluded: {[(q.get('fiscal_period'), q.get('form'), q.get('frame', ''), q.get('_derived')) for q in excluded]}"
        )

    return filtered

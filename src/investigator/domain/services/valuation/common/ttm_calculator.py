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

"""TTM (Trailing Twelve Months) metric calculations.

Provides standardized calculations for TTM metrics from quarterly data:
- TTM EPS (earnings per share)
- TTM Revenue
- TTM EBITDA
- TTM Free Cash Flow

These calculations support both dict format (from processed table) and
object format (QuarterlyData objects).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TTMMetrics:
    """Calculate TTM (Trailing Twelve Months) financial metrics.

    All methods handle both dict format (from sec_companyfacts_processed table)
    and object format (QuarterlyData from legacy pipeline).

    Methods:
        calculate_ttm_eps: TTM earnings per share
        calculate_ttm_revenue: TTM total revenue
        calculate_ttm_ebitda: TTM EBITDA
        calculate_ttm_fcf: TTM free cash flow
        calculate_all_ttm_metrics: Get all TTM metrics in one call
    """

    @staticmethod
    def _extract_metric(entry: Any, keys: List[str]) -> Optional[float]:
        """Extract a metric value from entry, trying multiple possible keys.

        Args:
            entry: Dict or object with financial data
            keys: List of possible key names to try

        Returns:
            Metric value as float, or None if not found
        """
        if isinstance(entry, dict):
            # Try direct keys in dict
            for key in keys:
                value = entry.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        continue

            # Try nested financial_data
            financial_data = entry.get("financial_data", {})
            if financial_data:
                for key in keys:
                    value = financial_data.get(key)
                    if value is not None:
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            continue
        else:
            # Object format (QuarterlyData)
            financial_data = getattr(entry, "financial_data", {}) or {}
            for key in keys:
                value = (
                    financial_data.get(key)
                    if isinstance(financial_data, dict)
                    else getattr(financial_data, key, None)
                )
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        continue

        return None

    @staticmethod
    def calculate_ttm_eps(
        *, quarterly_data: List[Any], shares_outstanding: Optional[float]
    ) -> Optional[float]:
        """Calculate TTM (Trailing Twelve Months) earnings per share.

        Args:
            quarterly_data: List of quarterly entries (most recent first)
            shares_outstanding: Weighted average diluted shares outstanding

        Returns:
            TTM EPS or None if insufficient data or missing shares

        Example:
            >>> eps = TTMMetrics.calculate_ttm_eps(
            ...     quarterly_data=quarters,
            ...     shares_outstanding=1000000000
            ... )
        """
        if not shares_outstanding or shares_outstanding <= 0:
            return None

        if not quarterly_data or len(quarterly_data) < 4:
            return None

        # Sum net income from last 4 quarters
        ttm_net_income = 0.0
        count = 0

        for entry in quarterly_data[:4]:
            net_income = TTMMetrics._extract_metric(
                entry, ["net_income", "net_income_loss", "net_income_common"]
            )
            if net_income is not None:
                ttm_net_income += net_income
                count += 1

        if count == 0:
            return None

        return ttm_net_income / shares_outstanding

    @staticmethod
    def calculate_ttm_revenue(*, quarterly_data: List[Any]) -> Optional[float]:
        """Calculate TTM (Trailing Twelve Months) total revenue.

        Args:
            quarterly_data: List of quarterly entries (most recent first)

        Returns:
            TTM revenue or None if insufficient data

        Example:
            >>> revenue = TTMMetrics.calculate_ttm_revenue(quarterly_data=quarters)
        """
        if not quarterly_data or len(quarterly_data) < 1:
            return None

        # Use up to 4 quarters for TTM
        quarters_to_use = min(len(quarterly_data), 4)
        ttm_revenue = 0.0
        count = 0

        for entry in quarterly_data[:quarters_to_use]:
            revenue = TTMMetrics._extract_metric(
                entry, ["total_revenue", "revenue", "revenues"]
            )
            if revenue is not None:
                ttm_revenue += revenue
                count += 1

        if count == 0:
            return None

        return ttm_revenue

    @staticmethod
    def calculate_ttm_ebitda(*, quarterly_data: List[Any]) -> Optional[float]:
        """Calculate TTM (Trailing Twelve Months) EBITDA.

        First tries direct ebitda field, then calculates as:
        EBITDA = Operating Income + Depreciation & Amortization

        Args:
            quarterly_data: List of quarterly entries (most recent first)

        Returns:
            TTM EBITDA or None if insufficient data

        Example:
            >>> ebitda = TTMMetrics.calculate_ttm_ebitda(quarterly_data=quarters)
        """
        if not quarterly_data or len(quarterly_data) < 1:
            return None

        quarters_to_use = min(len(quarterly_data), 4)
        ttm_ebitda = 0.0
        count = 0

        for entry in quarterly_data[:quarters_to_use]:
            # Try direct EBITDA first
            ebitda = TTMMetrics._extract_metric(entry, ["ebitda"])

            if ebitda is not None:
                ttm_ebitda += ebitda
                count += 1
            else:
                # Calculate EBITDA = Operating Income + Depreciation & Amortization
                operating_income = TTMMetrics._extract_metric(
                    entry, ["operating_income", "operating_profit"]
                )
                depreciation = TTMMetrics._extract_metric(
                    entry,
                    [
                        "depreciation_amortization",
                        "depreciation_and_amortization",
                        "da",
                    ],
                )

                if operating_income is not None and depreciation is not None:
                    ttm_ebitda += operating_income + depreciation
                    count += 1

        if count == 0:
            return None

        return ttm_ebitda

    @staticmethod
    def calculate_ttm_fcf(*, quarterly_data: List[Any]) -> Optional[float]:
        """Calculate TTM (Trailing Twelve Months) free cash flow.

        FCF = Operating Cash Flow - Capital Expenditures

        Args:
            quarterly_data: List of quarterly entries (most recent first)

        Returns:
            TTM FCF or None if insufficient data

        Example:
            >>> fcf = TTMMetrics.calculate_ttm_fcf(quarterly_data=quarters)
        """
        if not quarterly_data or len(quarterly_data) < 1:
            return None

        quarters_to_use = min(len(quarterly_data), 4)
        ttm_fcf = 0.0
        count = 0

        for entry in quarterly_data[:quarters_to_use]:
            # Try direct FCF first
            fcf = TTMMetrics._extract_metric(entry, ["free_cash_flow", "fcf"])

            if fcf is not None:
                ttm_fcf += fcf
                count += 1
            else:
                # Calculate FCF = Operating Cash Flow - CapEx
                ocf = TTMMetrics._extract_metric(
                    entry, ["operating_cash_flow", "ocf", "cash_from_operations"]
                )
                capex = TTMMetrics._extract_metric(
                    entry, ["capital_expenditures", "capex", "purchase_of_ppe"]
                )

                if ocf is not None:
                    capex_value = capex if capex is not None else 0
                    ttm_fcf += ocf - capex_value
                    count += 1

        if count == 0:
            return None

        return ttm_fcf

    @staticmethod
    def calculate_all_ttm_metrics(
        *, quarterly_data: List[Any], shares_outstanding: Optional[float]
    ) -> Dict[str, Optional[float]]:
        """Calculate all TTM metrics in a single call.

        Args:
            quarterly_data: List of quarterly entries (most recent first)
            shares_outstanding: Weighted average diluted shares outstanding

        Returns:
            Dictionary with all TTM metrics:
            - ttm_eps: TTM earnings per share
            - ttm_revenue: TTM total revenue
            - ttm_ebitda: TTM EBITDA
            - ttm_fcf: TTM free cash flow

        Example:
            >>> metrics = TTMMetrics.calculate_all_ttm_metrics(
            ...     quarterly_data=quarters,
            ...     shares_outstanding=1000000000
            ... )
            >>> print(f"TTM EPS: ${metrics['ttm_eps']:.2f}")
            >>> print(f"TTM Revenue: ${metrics['ttm_revenue']/1e9:.1f}B")
        """
        return {
            "ttm_eps": TTMMetrics.calculate_ttm_eps(
                quarterly_data=quarterly_data, shares_outstanding=shares_outstanding
            ),
            "ttm_revenue": TTMMetrics.calculate_ttm_revenue(
                quarterly_data=quarterly_data
            ),
            "ttm_ebitda": TTMMetrics.calculate_ttm_ebitda(
                quarterly_data=quarterly_data
            ),
            "ttm_fcf": TTMMetrics.calculate_ttm_fcf(quarterly_data=quarterly_data),
        }

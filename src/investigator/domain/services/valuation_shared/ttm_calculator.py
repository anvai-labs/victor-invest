# Copyright 2025 Vijaykumar Singh
# SPDX-License-Identifier: Apache-2.0
"""
TTM Calculator - Consistent trailing twelve months calculation regardless of input format.

This service handles the key drift point between data sources:
- SEC Filing Tool returns single FY snapshot (already represents ~TTM)
- Database returns quarterly data (needs 4 quarters summed for TTM)

The calculator detects the input format and applies the appropriate logic.

Example:
    from investigator.domain.services.valuation_shared import TTMCalculator

    calc = TTMCalculator()

    # From SEC FY data (single snapshot = TTM)
    sec_data = [{"fiscal_period": "FY", "income_statement": {"total_revenue": 400000}, ...}]
    ttm = calc.calculate_ttm(sec_data)

    # From quarterly data (sum 4 quarters)
    quarterly_data = [{"fiscal_period": "Q1", ...}, {"fiscal_period": "Q2", ...}, ...]
    ttm = calc.calculate_ttm(quarterly_data)
"""

import logging
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class TTMCalculator:
    """
    Calculator for trailing twelve months metrics.

    Handles format detection and consistent TTM calculation regardless
    of whether input is SEC FY data or quarterly data.
    """

    # Flow metrics that should be summed for TTM
    FLOW_METRICS: ClassVar[dict] = {
        "income_statement": [
            "total_revenue",
            "net_income",
            "gross_profit",
            "operating_income",
            "interest_expense",
            "income_tax_expense",
            "ebitda",
        ],
        "cash_flow": [
            "operating_cash_flow",
            "free_cash_flow",
            "capital_expenditures",
            "dividends_paid",
        ],
    }

    # Stock metrics that use most recent value (not summed)
    STOCK_METRICS: ClassVar[dict] = {
        "balance_sheet": [
            "total_assets",
            "total_liabilities",
            "stockholders_equity",
            "cash_and_equivalents",
            "long_term_debt",
            "short_term_debt",
            "current_assets",
            "current_liabilities",
        ],
    }

    def detect_data_format(self, data: dict | list | None) -> str:
        """
        Detect the format of input financial data.

        Args:
            data: Input data (single dict or list of dicts)

        Returns:
            One of:
            - "sec_fy": SEC annual filing (FY period) - treat as TTM
            - "quarterly": Quarterly data - sum 4 quarters for TTM
            - "ttm": Already calculated TTM (has quarters_included key)
            - "nested_single": Single period with nested structure
            - "flat": Flat structure with direct metric keys
            - "empty": Empty or None input
            - "unknown": Unrecognized format
        """
        if data is None:
            return "empty"

        if isinstance(data, list):
            if not data:
                return "empty"

            first = data[0] if data else {}
            if not isinstance(first, dict):
                return "unknown"

            fiscal_period = first.get("fiscal_period", "")
            if fiscal_period == "FY":
                return "sec_fy"
            elif fiscal_period in ("Q1", "Q2", "Q3", "Q4"):
                return "quarterly"
            elif "income_statement" in first:
                return "nested_single"
            else:
                return "flat"

        elif isinstance(data, dict):
            # Check if already TTM
            if "quarters_included" in data:
                return "ttm"

            fiscal_period = data.get("fiscal_period", "")
            if fiscal_period == "FY":
                return "sec_fy"
            elif fiscal_period in ("Q1", "Q2", "Q3", "Q4"):
                return "quarterly"
            elif "income_statement" in data:
                return "nested_single"
            elif "total_revenue" in data or "revenue" in data:
                return "flat"

        return "unknown"

    def calculate_ttm(
        self,
        data: dict | list[dict],
        require_full_year: bool = True,
    ) -> dict[str, Any]:
        """
        Calculate TTM metrics from input data.

        Handles different formats:
        - SEC FY: Returns the FY data as TTM (already represents ~12 months)
        - Quarterly list: Sums the last 4 quarters
        - Single quarter: Returns as-is with warning
        - Already TTM: Returns as-is

        Args:
            data: Input financial data (dict or list of dicts)
            require_full_year: If True, returns empty dict if < 4 quarters available

        Returns:
            Dict with TTM metrics in nested structure:
            {
                "income_statement": {...},
                "cash_flow": {...},
                "balance_sheet": {...},
                "shares_outstanding": float,
                "data_format": str,
                "quarters_included": int,
            }
        """
        data_format = self.detect_data_format(data)

        if data_format == "empty":
            return {}

        if data_format == "ttm":
            # Already TTM, return as-is. detect_data_format only reports "ttm" for a
            # mapping, so the list arm cannot occur here.
            return data if isinstance(data, dict) else data[0]

        if data_format == "sec_fy":
            # SEC FY data - treat as TTM
            return self._fy_to_ttm(data)

        if data_format == "quarterly":
            # Sum 4 quarters. detect_data_format only reports "quarterly" for a list
            # of period mappings, so the dict arm cannot occur here.
            quarters: list[dict] = data if isinstance(data, list) else [data]
            return self._quarterly_to_ttm(quarters, require_full_year)

        if data_format == "nested_single":
            # Single nested record - return with warning
            logger.warning("Single quarter data provided, returning as-is")
            if isinstance(data, list):
                data = data[0]
            data["quarters_included"] = 1
            data["data_format"] = "single_quarter"
            return data

        if data_format == "flat":
            # Flat structure - normalize and return
            return self._flat_to_ttm(data)

        logger.warning(f"Unknown data format: {data_format}")
        return {}

    def _fy_to_ttm(self, data: dict | list) -> dict[str, Any]:
        """
        Convert SEC FY data to TTM format.

        FY data already represents ~12 months, so we just normalize the structure.
        """
        # Bind to a separate name: reassigning the parameter does not narrow its
        # declared `dict | list`, so every `.get()` below is reported against the
        # list arm even though the isinstance check has already excluded it.
        if isinstance(data, list):
            if not data:
                return {}
            record: dict[str, Any] = data[0]
        else:
            record = data

        # If already nested structure
        if "income_statement" in record and isinstance(record["income_statement"], dict):
            result = {
                "income_statement": record.get("income_statement", {}).copy(),
                "cash_flow": record.get("cash_flow", {}).copy(),
                "balance_sheet": record.get("balance_sheet", {}).copy(),
                "shares_outstanding": record.get("shares_outstanding"),
                "fiscal_year": record.get("fiscal_year"),
                "fiscal_period": "TTM",
                "data_format": "sec_fy",
                "quarters_included": 4,  # FY = 4 quarters
            }
        else:
            # Flat structure from FY record
            result = {
                "income_statement": {
                    "total_revenue": record.get("total_revenue"),
                    "net_income": record.get("net_income"),
                    "gross_profit": record.get("gross_profit"),
                    "operating_income": record.get("operating_income"),
                    "interest_expense": record.get("interest_expense"),
                    "income_tax_expense": record.get("income_tax_expense"),
                    "ebitda": record.get("ebitda"),
                },
                "cash_flow": {
                    "operating_cash_flow": record.get("operating_cash_flow"),
                    "free_cash_flow": record.get("free_cash_flow"),
                    "capital_expenditures": record.get("capital_expenditures"),
                    "dividends_paid": record.get("dividends_paid"),
                },
                "balance_sheet": {
                    "total_assets": record.get("total_assets"),
                    "total_liabilities": record.get("total_liabilities"),
                    "stockholders_equity": record.get("stockholders_equity"),
                    "cash_and_equivalents": record.get("cash_and_equivalents"),
                    "long_term_debt": record.get("long_term_debt"),
                    "short_term_debt": record.get("short_term_debt"),
                    "current_assets": record.get("current_assets"),
                    "current_liabilities": record.get("current_liabilities"),
                },
                "shares_outstanding": record.get("shares_outstanding"),
                "fiscal_year": record.get("fiscal_year"),
                "fiscal_period": "TTM",
                "data_format": "sec_fy",
                "quarters_included": 4,
            }

        return result

    def _quarterly_to_ttm(
        self,
        quarters: list[dict],
        require_full_year: bool = True,
    ) -> dict[str, Any]:
        """
        Calculate TTM by summing 4 quarters of data.

        Flow metrics are summed, stock metrics use most recent value.
        """
        if not quarters:
            return {}

        # Take up to 4 most recent quarters
        recent_quarters = quarters[:4] if len(quarters) >= 4 else quarters

        if require_full_year and len(recent_quarters) < 4:
            logger.warning(f"Insufficient quarters for TTM: {len(recent_quarters)} < 4")
            return {}

        # Sum flow metrics
        ttm_income = {}
        for metric in self.FLOW_METRICS["income_statement"]:
            values = []
            for q in recent_quarters:
                if "income_statement" in q:
                    val = q["income_statement"].get(metric)
                else:
                    val = q.get(metric)
                if val is not None:
                    values.append(float(val))
            ttm_income[metric] = sum(values) if values else None

        ttm_cash_flow = {}
        for metric in self.FLOW_METRICS["cash_flow"]:
            values = []
            for q in recent_quarters:
                if "cash_flow" in q:
                    val = q["cash_flow"].get(metric)
                else:
                    val = q.get(metric)
                if val is not None:
                    values.append(float(val))
            ttm_cash_flow[metric] = sum(values) if values else None

        # Stock metrics use most recent quarter
        most_recent = recent_quarters[0]
        if "balance_sheet" in most_recent:
            ttm_balance_sheet = most_recent["balance_sheet"].copy()
        else:
            ttm_balance_sheet = {metric: most_recent.get(metric) for metric in self.STOCK_METRICS["balance_sheet"]}

        return {
            "income_statement": ttm_income,
            "cash_flow": ttm_cash_flow,
            "balance_sheet": ttm_balance_sheet,
            "shares_outstanding": most_recent.get("shares_outstanding"),
            "fiscal_year": most_recent.get("fiscal_year"),
            "fiscal_period": "TTM",
            "data_format": "quarterly",
            "quarters_included": len(recent_quarters),
            "most_recent_quarter": {
                "fiscal_year": most_recent.get("fiscal_year"),
                "fiscal_period": most_recent.get("fiscal_period"),
            },
        }

    def _flat_to_ttm(self, data: dict | list) -> dict[str, Any]:
        """
        Convert flat structure to TTM format.

        Assumes flat data represents TTM values already.
        """
        # Same reason as _fy_to_ttm: reassigning the parameter leaves its declared
        # `dict | list` intact, so the list arm is reported against every .get().
        if isinstance(data, list):
            if not data:
                return {}
            record: dict[str, Any] = data[0]
        else:
            record = data

        return {
            "income_statement": {
                "total_revenue": record.get("total_revenue") or record.get("revenue"),
                "net_income": record.get("net_income"),
                "gross_profit": record.get("gross_profit"),
                "operating_income": record.get("operating_income"),
                "interest_expense": record.get("interest_expense"),
                "income_tax_expense": record.get("income_tax_expense"),
                "ebitda": record.get("ebitda"),
            },
            "cash_flow": {
                "operating_cash_flow": record.get("operating_cash_flow"),
                "free_cash_flow": record.get("free_cash_flow"),
                "capital_expenditures": record.get("capital_expenditures") or record.get("capex"),
                "dividends_paid": record.get("dividends_paid") or record.get("dividends"),
            },
            "balance_sheet": {
                "total_assets": record.get("total_assets"),
                "total_liabilities": record.get("total_liabilities"),
                "stockholders_equity": record.get("stockholders_equity") or record.get("equity"),
                "cash_and_equivalents": record.get("cash_and_equivalents") or record.get("cash"),
                "long_term_debt": record.get("long_term_debt"),
                "short_term_debt": record.get("short_term_debt"),
                "current_assets": record.get("current_assets"),
                "current_liabilities": record.get("current_liabilities"),
            },
            "shares_outstanding": record.get("shares_outstanding") or record.get("shares"),
            "fiscal_period": "TTM",
            "data_format": "flat",
            "quarters_included": 4,  # Assume flat record represents TTM
        }

    def get_metric(
        self,
        ttm_data: dict[str, Any],
        metric_name: str,
        default: float | None = None,
    ) -> float | None:
        """
        Extract a specific metric from TTM record.

        Searches in order: income_statement, cash_flow, balance_sheet, top-level.

        Args:
            ttm_data: TTM record dict
            metric_name: Metric to extract
            default: Default value if not found

        Returns:
            Metric value or default
        """
        # Check nested sections first
        for section in ["income_statement", "cash_flow", "balance_sheet"]:
            if section in ttm_data and isinstance(ttm_data[section], dict):
                if metric_name in ttm_data[section]:
                    value = ttm_data[section][metric_name]
                    return float(value) if value is not None else None

        # Check top-level
        if metric_name in ttm_data:
            value = ttm_data[metric_name]
            return float(value) if value is not None else None

        return default

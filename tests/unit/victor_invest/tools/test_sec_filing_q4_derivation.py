"""
Test Suite for Q4 Derivation Logic in SEC Filing Tool

This test suite verifies that the Q4 derivation logic correctly derives
Q4 quarterly data from FY (full year) filings when Q4 is missing from
the SEC Company Facts API.

Test Coverage:
- Q4 derivation for complete fiscal years (Q1, Q2, Q3, FY)
- Metrics calculation (net_income, revenue, OCF, CapEx, FCF)
- Ordering of quarters (period_end_date descending)
- Edge cases (missing Q1, Q2, or Q3)
- Derived flag is set correctly
"""

import pytest


class TestQ4Derivation:
    """Test cases for Q4 derivation from FY filings."""

    def setup_method(self):
        """Set up test fixtures."""
        # Import here to avoid import errors if dependencies not available
        import sys

        sys.path.insert(0, "/Users/vijaysingh/code/victor-invest")
        from victor_invest.tools.sec_filing import SECFilingTool

        self.tool = SECFilingTool()
        self.symbol = "TEST"

    def _create_quarter_entry(
        self,
        fiscal_year: int,
        fiscal_period: str,
        period_end: str,
        net_income: float,
        total_revenue: float,
        operating_cash_flow: float | None = None,
        capital_expenditures: float | None = None,
        free_cash_flow: float | None = None,
        shares_outstanding: float = 228000000,
    ) -> dict:
        """Create a mock quarterly entry."""
        return {
            "symbol": self.symbol,
            "fiscal_year": fiscal_year,
            "fiscal_period": fiscal_period,
            "period_end": period_end,
            "period_end_date": period_end,
            "filed": period_end,
            "filed_date": period_end,
            "form": "10-Q" if fiscal_period in ["Q1", "Q2", "Q3"] else "10-K",
            "shares_outstanding": shares_outstanding,
            "weighted_average_diluted_shares_outstanding": shares_outstanding,
            "net_income": net_income,
            "total_revenue": total_revenue,
            "operating_cash_flow": operating_cash_flow,
            "capital_expenditures": capital_expenditures,
            "free_cash_flow": free_cash_flow,
            "income_statement": {
                "total_revenue": total_revenue,
                "net_income": net_income,
            },
            "cash_flow": {
                "operating_cash_flow": operating_cash_flow,
                "capital_expenditures": capital_expenditures,
                "free_cash_flow": free_cash_flow,
            },
        }

    def test_q4_derivation_complete_fy(self):
        """Test Q4 derivation when FY, Q1, Q2, Q3 are all present."""
        # Create test data matching STX FY 2025
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)

        # Verify Q4 was derived and FY was removed
        assert len(result) == 4  # Q1, Q2, Q3, Q4 (FY replaced with Q4)

        fiscal_periods = [q["fiscal_period"] for q in result]
        assert "Q4" in fiscal_periods
        assert "FY" not in fiscal_periods

        # Get derived Q4
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        # Verify Q4 values
        assert q4["fiscal_year"] == 2025
        assert q4["period_end"] == "2025-06-27"
        assert q4["_derived"] is True  # Derived flag

        # Verify net income: Q4 = FY - (Q1 + Q2 + Q3)
        # Q4 = 1,469 - (305 + 336 + 340) = 488
        assert q4["net_income"] == 488_000_000

        # Verify total revenue
        # Q4 = 9,097 - (2,168 + 2,325 + 2,160) = 2,444
        assert q4["total_revenue"] == 2_444_000_000

    def test_q4_derivation_ordering(self):
        """Test that derived quarters are ordered by period_end_date (descending)."""
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)

        # Verify ordering by period_end_date (descending - most recent first)
        assert result[0]["fiscal_period"] == "Q4"
        assert result[0]["period_end"] == "2025-06-27"

        assert result[1]["fiscal_period"] == "Q3"
        assert result[1]["period_end"] == "2025-03-27"

        assert result[2]["fiscal_period"] == "Q2"
        assert result[2]["period_end"] == "2024-12-27"

        assert result[3]["fiscal_period"] == "Q1"
        assert result[3]["period_end"] == "2024-09-27"

    def test_q4_derivation_with_cash_flow_metrics(self):
        """Test Q4 derivation includes cash flow metrics."""
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
                operating_cash_flow=95_000_000,
                capital_expenditures=68_000_000,
                free_cash_flow=27_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
                operating_cash_flow=221_000_000,
                capital_expenditures=71_000_000,
                free_cash_flow=150_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
                operating_cash_flow=259_000_000,
                capital_expenditures=43_000_000,
                free_cash_flow=216_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
                operating_cash_flow=1_083_000_000,
                capital_expenditures=265_000_000,
                free_cash_flow=818_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        # Verify cash flow metrics
        # OCF: 1,083 - (95 + 221 + 259) = 508
        assert q4["operating_cash_flow"] == 508_000_000

        # CapEx: 265 - (68 + 71 + 43) = 83
        assert q4["capital_expenditures"] == 83_000_000

        # FCF: 818 - (27 + 150 + 216) = 425
        assert q4["free_cash_flow"] == 425_000_000

    def test_no_derivation_when_q4_exists(self):
        """Test that derivation doesn't happen when Q4 already exists."""
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q4",
                "2025-06-27",
                net_income=488_000_000,
                total_revenue=2_444_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)

        # Should have all 4 quarters, no derivation
        assert len(result) == 4

        # None should be derived
        assert all(not q.get("_derived") for q in result)

        # Q4 should have original values
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)
        assert q4["net_income"] == 488_000_000
        assert q4.get("_derived") is not True

    def test_no_derivation_when_missing_quarters(self):
        """Test that derivation doesn't happen when Q1, Q2, or Q3 is missing."""
        # Missing Q3
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)

        # Should return original data (no derivation possible)
        assert len(result) == 3
        fiscal_periods = [q["fiscal_period"] for q in result]
        assert "Q4" not in fiscal_periods  # Q4 not derived

    def test_multiple_fiscal_years(self):
        """Test Q4 derivation across multiple fiscal years."""
        quarters_data = [
            # FY 2025
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
            # FY 2024
            self._create_quarter_entry(
                2024,
                "Q1",
                "2023-09-27",
                net_income=-184_000_000,
                total_revenue=1_454_000_000,
            ),
            self._create_quarter_entry(
                2024,
                "Q2",
                "2023-12-27",
                net_income=-19_000_000,
                total_revenue=1_555_000_000,
            ),
            self._create_quarter_entry(
                2024,
                "Q3",
                "2024-03-27",
                net_income=25_000_000,
                total_revenue=1_655_000_000,
            ),
            self._create_quarter_entry(
                2024,
                "FY",
                "2024-06-27",
                net_income=335_000_000,
                total_revenue=6_551_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)

        # Should have derived Q4 for both years
        q4_entries = [q for q in result if q["fiscal_period"] == "Q4"]
        assert len(q4_entries) == 2

        # Verify FY 2025 Q4
        q4_2025 = next(q for q in q4_entries if q["fiscal_year"] == 2025)
        assert q4_2025["net_income"] == 488_000_000

        # Verify FY 2024 Q4
        q4_2024 = next(q for q in q4_entries if q["fiscal_year"] == 2024)
        # Q4 = 335 - (-184 + -19 + 25) = 335 - (-178) = 513
        assert q4_2024["net_income"] == 513_000_000

    def test_ttm_calculation_with_derived_q4(self):
        """Test TTM calculation uses derived Q4 correctly."""
        quarters_data = [
            self._create_quarter_entry(
                2026,
                "Q2",
                "2025-12-27",
                net_income=593_000_000,
                total_revenue=2_825_000_000,
            ),
            self._create_quarter_entry(
                2026,
                "Q1",
                "2025-09-27",
                net_income=549_000_000,
                total_revenue=2_629_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)

        # Get first 4 quarters (TTM)
        ttm_quarters = [q for q in result if q["fiscal_period"] in ["Q1", "Q2", "Q3", "Q4"]][:4]

        # Calculate TTM net income
        ttm_ni = sum(q["net_income"] for q in ttm_quarters)

        # Should be: 593 + 549 + 488 (derived) + 340 = 1,970
        assert ttm_ni == 1_970_000_000

        # Verify the quarters in TTM
        assert ttm_quarters[0]["fiscal_period"] == "Q2"
        assert ttm_quarters[0]["fiscal_year"] == 2026

        assert ttm_quarters[1]["fiscal_period"] == "Q1"
        assert ttm_quarters[1]["fiscal_year"] == 2026

        assert ttm_quarters[2]["fiscal_period"] == "Q4"
        assert ttm_quarters[2]["fiscal_year"] == 2025
        assert ttm_quarters[2]["_derived"] is True

        assert ttm_quarters[3]["fiscal_period"] == "Q3"
        assert ttm_quarters[3]["fiscal_year"] == 2025

    def test_derived_q4_has_nested_structure(self):
        """Test that derived Q4 has nested structure for compatibility."""
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        # Verify nested structure exists
        assert "income_statement" in q4
        assert "cash_flow" in q4
        assert "balance_sheet" in q4

        # Verify nested values match top-level values
        assert q4["income_statement"]["net_income"] == q4["net_income"]
        assert q4["income_statement"]["total_revenue"] == q4["total_revenue"]

    def test_derived_q4_balance_sheet_is_none(self):
        """Test that balance sheet metrics are None for derived Q4."""
        quarters_data = [
            self._create_quarter_entry(
                2025,
                "Q1",
                "2024-09-27",
                net_income=305_000_000,
                total_revenue=2_168_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q2",
                "2024-12-27",
                net_income=336_000_000,
                total_revenue=2_325_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "Q3",
                "2025-03-27",
                net_income=340_000_000,
                total_revenue=2_160_000_000,
            ),
            self._create_quarter_entry(
                2025,
                "FY",
                "2025-06-27",
                net_income=1_469_000_000,
                total_revenue=9_097_000_000,
            ),
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, self.symbol)
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        # Balance sheet should be None (not additive like P&L and CF)
        assert q4["balance_sheet"]["total_assets"] is None
        assert q4["balance_sheet"]["stockholders_equity"] is None
        assert q4["balance_sheet"]["total_debt"] is None


class TestQ4DerivationEdgeCases:
    """Test edge cases and error handling for Q4 derivation."""

    def setup_method(self):
        """Set up test fixtures."""
        import sys

        sys.path.insert(0, "/Users/vijaysingh/code/victor-invest")
        from victor_invest.tools.sec_filing import SECFilingTool

        self.tool = SECFilingTool()

    def test_empty_list(self):
        """Test with empty quarters list."""
        result = self.tool._derive_missing_q4_quarters([], "TEST")
        assert result == []

    def test_missing_none_values(self):
        """Test when some metrics have None values."""
        quarters_data = [
            {
                "fiscal_year": 2025,
                "fiscal_period": "Q1",
                "period_end": "2024-09-27",
                "net_income": 305_000_000,
                "total_revenue": None,  # Missing
                "operating_cash_flow": 95_000_000,
            },
            {
                "fiscal_year": 2025,
                "fiscal_period": "Q2",
                "period_end": "2024-12-27",
                "net_income": 336_000_000,
                "total_revenue": 2_325_000_000,
                "operating_cash_flow": 221_000_000,
            },
            {
                "fiscal_year": 2025,
                "fiscal_period": "Q3",
                "period_end": "2025-03-27",
                "net_income": 340_000_000,
                "total_revenue": 2_160_000_000,
                "operating_cash_flow": None,  # Missing
            },
            {
                "fiscal_year": 2025,
                "fiscal_period": "FY",
                "period_end": "2025-06-27",
                "net_income": 1_469_000_000,
                "total_revenue": None,  # Missing
                "operating_cash_flow": 1_083_000_000,
            },
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, "TEST")
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        if q4:
            # Metrics with None in any period should be None
            assert q4["net_income"] == 488_000_000  # All present
            assert q4["total_revenue"] is None  # Some missing
            assert q4["operating_cash_flow"] is None  # Some missing

    def test_negative_values(self):
        """Test derivation with negative values (losses)."""
        quarters_data = [
            {
                "fiscal_year": 2024,
                "fiscal_period": "Q1",
                "period_end": "2023-09-27",
                "net_income": -184_000_000,
            },
            {
                "fiscal_year": 2024,
                "fiscal_period": "Q2",
                "period_end": "2023-12-27",
                "net_income": -19_000_000,
            },
            {
                "fiscal_year": 2024,
                "fiscal_period": "Q3",
                "period_end": "2024-03-27",
                "net_income": 25_000_000,
            },
            {
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "period_end": "2024-06-27",
                "net_income": 335_000_000,
            },
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, "TEST")
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        if q4:
            # Q4 = 335 - (-184 + -19 + 25) = 335 - (-178) = 513
            assert q4["net_income"] == 513_000_000

    def test_shares_outstanding_preserved(self):
        """Test that shares outstanding is preserved from FY entry."""
        expected_shares = 250_000_000

        quarters_data = [
            {
                "fiscal_year": 2025,
                "fiscal_period": "Q1",
                "period_end": "2024-09-27",
                "net_income": 305_000_000,
                "shares_outstanding": 220_000_000,
                "weighted_average_diluted_shares_outstanding": 225_000_000,
            },
            {
                "fiscal_year": 2025,
                "fiscal_period": "Q2",
                "period_end": "2024-12-27",
                "net_income": 336_000_000,
                "shares_outstanding": 222_000_000,
                "weighted_average_diluted_shares_outstanding": 227_000_000,
            },
            {
                "fiscal_year": 2025,
                "fiscal_period": "Q3",
                "period_end": "2025-03-27",
                "net_income": 340_000_000,
                "shares_outstanding": 224_000_000,
                "weighted_average_diluted_shares_outstanding": 229_000_000,
            },
            {
                "fiscal_year": 2025,
                "fiscal_period": "FY",
                "period_end": "2025-06-27",
                "net_income": 1_469_000_000,
                "shares_outstanding": 212_000_000,
                "weighted_average_diluted_shares_outstanding": expected_shares,
            },
        ]

        result = self.tool._derive_missing_q4_quarters(quarters_data, "TEST")
        q4 = next((q for q in result if q["fiscal_period"] == "Q4"), None)

        if q4:
            # Should use weighted average from FY entry
            assert q4["weighted_average_diluted_shares_outstanding"] == expected_shares
            assert q4["shares_outstanding"] == expected_shares


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

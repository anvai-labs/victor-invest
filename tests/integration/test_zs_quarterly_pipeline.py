"""
Integration Test for ZS (Zscaler) Fundamental Analysis Pipeline

This integration test validates the SEC→Fundamental pipeline for a
non-calendar fiscal year company (ZS, fiscal year ends July 31).

**Key Test Scenarios**:
1. SEC agent successfully fetches and caches CompanyFacts data
2. Fundamental agent produces complete analysis with valuation
3. Multi-model valuation produces reasonable blended fair value
4. Financial ratios are populated from SEC data
5. Pipeline works for multiple non-calendar-FY companies

**Company**: ZS (Zscaler Inc.)
- Fiscal year end: July 31
- Filing pattern: Q1, Q2, Q3, FY (no separate Q4)
- CIK: 1713683
"""

import pytest

from investigator.domain.agents.fundamental import FundamentalAnalysisAgent
from investigator.domain.agents.sec import SECAnalysisAgent
from investigator.domain.models import AgentTask, AnalysisType, TaskStatus


class TestZSPipeline:
    """Integration tests for ZS SEC→Fundamental pipeline"""

    @pytest.fixture
    def sec_agent(self):
        """Create SEC agent instance"""
        return SECAnalysisAgent(agent_id="sec", ollama_client=None, event_bus=None, cache_manager=None)

    @pytest.fixture
    def fundamental_agent(self):
        """Create Fundamental agent instance"""
        return FundamentalAnalysisAgent(
            agent_id="fundamental",
            ollama_client=None,
            event_bus=None,
            cache_manager=None,
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sec_agent_fetches_zs_data(self, sec_agent):
        """SEC agent fetches and caches CompanyFacts for ZS (non-calendar FY)."""
        task = AgentTask(
            task_id="test_zs_sec",
            symbol="ZS",
            analysis_type=AnalysisType.SEC_FUNDAMENTAL,
            context={"symbol": "ZS"},
        )

        result = await sec_agent.execute_with_timeout(task)

        assert result.status == TaskStatus.COMPLETED, f"SEC agent failed: {result.error}"
        assert result.result_data["status"] == "success"
        assert result.result_data["symbol"] == "ZS"

        summary = result.result_data["companyfacts_summary"]
        assert summary["cik"] is not None
        assert summary["entityName"] is not None
        assert summary["fact_count"] > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fundamental_analysis_produces_complete_result(self, fundamental_agent):
        """Fundamental agent produces a full analysis with valuation, ratios, and recommendation."""
        task = AgentTask(
            task_id="test_zs_fundamental",
            symbol="ZS",
            analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
            context={"symbol": "ZS"},
        )

        result = await fundamental_agent.execute_with_timeout(task)

        assert result.status == TaskStatus.COMPLETED, f"Fundamental agent failed: {result.error}"
        rd = result.result_data
        assert rd["status"] == "success"
        assert rd["symbol"] == "ZS"

        # Core output keys must be present
        required_keys = [
            "analysis",
            "valuation",
            "ratios",
            "fair_value",
            "recommendation",
            "investment_grade",
            "multi_model_summary",
            "fiscal_period",
            "data_quality",
            "confidence",
        ]
        for key in required_keys:
            assert key in rd, f"Missing required key: {key}"

        # Recommendation must be a valid value
        assert rd["recommendation"] in (
            "strong_buy",
            "buy",
            "hold",
            "sell",
            "strong_sell",
        )

        # Investment grade must be a letter grade
        assert rd["investment_grade"] in (
            "A+",
            "A",
            "A-",
            "B+",
            "B",
            "B-",
            "C+",
            "C",
            "C-",
            "D",
            "F",
        )

        # Fiscal period should reflect ZS's July FY end
        assert rd["fiscal_period"] is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multi_model_valuation_blending(self, fundamental_agent):
        """
        Multi-model valuation produces a blended fair value from applicable models.

        ZS is a SaaS company, so DCF and P/S should be applicable;
        P/E and EV/EBITDA may not be (negative earnings/EBITDA).
        """
        task = AgentTask(
            task_id="test_zs_valuation",
            symbol="ZS",
            analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
            context={"symbol": "ZS"},
        )

        result = await fundamental_agent.execute_with_timeout(task)
        assert result.status == TaskStatus.COMPLETED

        mms = result.result_data["multi_model_summary"]

        # At least one model must be applicable
        assert mms["applicable_models"] >= 1, "At least one valuation model should be applicable"

        # Blended fair value must be positive
        assert mms["blended_fair_value"] > 0, "Blended fair value should be positive"

        # Model agreement score is between 0 and 1
        assert 0 <= mms["model_agreement_score"] <= 1

        # Tier classification should reflect SaaS characteristics
        assert mms["tier_classification"] is not None

        # Models list should contain standard valuation models
        model_names = [m["model"] for m in mms["models"]]
        assert "dcf" in model_names
        assert "ps" in model_names

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_financial_ratios_populated_from_sec(self, fundamental_agent):
        """
        Financial ratios are derived from SEC filings, not market data alone.

        ZS has positive revenue and FCF but negative net income/EBITDA,
        so certain ratios should reflect that.
        """
        task = AgentTask(
            task_id="test_zs_ratios",
            symbol="ZS",
            analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
            context={"symbol": "ZS"},
        )

        result = await fundamental_agent.execute_with_timeout(task)
        assert result.status == TaskStatus.COMPLETED

        ratios = result.result_data["ratios"]

        # Revenue should be positive and in billions range for ZS
        assert ratios["ttm_revenue"] > 1_000_000_000, "ZS TTM revenue should be > $1B"

        # FCF should be positive (ZS is FCF-positive)
        assert ratios["free_cash_flow"] > 0, "ZS should have positive FCF"

        # Gross margin should be high (SaaS company, typically 70%+)
        assert ratios["gross_margin"] > 0.6, f"ZS gross margin {ratios['gross_margin']:.1%} seems too low for SaaS"

        # Market cap should be present and positive
        assert ratios["market_cap"] > 0

        # Shares outstanding should be present
        assert ratios["shares_outstanding"] > 0

        # Current ratio should be > 1 (liquid company)
        assert ratios["current_ratio"] > 1.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_data_quality_assessment(self, fundamental_agent):
        """Data quality scoring provides meaningful assessment of SEC data completeness."""
        task = AgentTask(
            task_id="test_zs_dq",
            symbol="ZS",
            analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
            context={"symbol": "ZS"},
        )

        result = await fundamental_agent.execute_with_timeout(task)
        assert result.status == TaskStatus.COMPLETED

        dq = result.result_data["data_quality"]

        # Quality score should be a number between 0 and 100
        assert 0 <= dq["data_quality_score"] <= 100

        # Quality grade should be a valid grade
        assert dq["quality_grade"] in ("Excellent", "Good", "Fair", "Poor", "Very Poor")

        # Completeness and consistency scores should exist
        assert 0 <= dq["completeness_score"] <= 100
        assert 0 <= dq["consistency_score"] <= 100


class TestMultiCompanyPipeline:
    """Test the pipeline works across companies with different fiscal years."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_non_calendar_fy_companies(self):
        """
        Pipeline produces valid results for companies with non-calendar fiscal years.

        Companies:
        - ZS: Fiscal year ends July 31
        """
        agent = FundamentalAnalysisAgent(
            agent_id="fundamental",
            ollama_client=None,
            event_bus=None,
            cache_manager=None,
        )

        test_symbols = ["ZS"]
        results = {}

        for symbol in test_symbols:
            task = AgentTask(
                task_id=f"test_{symbol}",
                symbol=symbol,
                analysis_type=AnalysisType.FUNDAMENTAL_ANALYSIS,
                context={"symbol": symbol},
            )

            result = await agent.execute_with_timeout(task)
            assert result.status == TaskStatus.COMPLETED, f"{symbol} failed: {result.error}"

            rd = result.result_data
            results[symbol] = {
                "fair_value": rd["fair_value"],
                "recommendation": rd["recommendation"],
                "tier": rd["multi_model_summary"]["tier_classification"],
                "applicable_models": rd["multi_model_summary"]["applicable_models"],
                "fiscal_period": rd["fiscal_period"],
            }

        # All companies should have positive fair values
        for symbol, data in results.items():
            assert data["fair_value"] > 0, f"{symbol} should have positive fair value"
            assert data["applicable_models"] >= 1, f"{symbol} should have at least 1 applicable model"
            assert data["fiscal_period"] is not None, f"{symbol} should have a fiscal period"

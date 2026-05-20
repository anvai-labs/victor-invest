import asyncio

import pytest

from investigator.domain.services.unified_valuation_executor import UnifiedValuationExecutor


def test_unified_executor_renormalizes_applied_model_weights():
    executor = UnifiedValuationExecutor.__new__(UnifiedValuationExecutor)
    executor.symbol = "AAPL"
    executor.current_price = 100.0
    executor.quarterly_metrics = [{"total_revenue": 1}]
    executor.multi_year_data = [{"total_revenue": 1}]

    class Metadata:
        def get_sector_industry(self, symbol):
            return "Technology", "Consumer Electronics"

    class Weighting:
        def determine_weights(self, **kwargs):
            return {"dcf": 50.0, "pe": 30.0, "ps": 20.0}, "test_tier", None

    async def run_models():
        return {
            "dcf": {"success": True, "output": {"fair_value_per_share": 120.0}},
            "pe": {"success": True, "output": {"fair_value_per_share": 90.0}},
            "ps": {"success": False, "error": "not applicable"},
        }

    executor.metadata_service = Metadata()
    executor.weighting_service = Weighting()
    executor._run_all_models = run_models
    executor._build_financials_dict = lambda: {}
    executor._build_ratios_dict = lambda: {}

    result = asyncio.run(executor.run_comprehensive_valuation())

    assert result["consensus_fair_value"] == 108.75
    assert result["consensus_upside"] == pytest.approx(8.75)
    assert result["weights_applied"] == {"dcf": 50.0, "pe": 30.0}

import asyncio
import sys
from types import ModuleType, SimpleNamespace

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


def test_unified_executor_helpers_build_financials_ratios_and_enterprise_value():
    executor = UnifiedValuationExecutor.__new__(UnifiedValuationExecutor)
    executor.symbol = "AAPL"
    executor.current_price = 100.0
    executor.quarterly_metrics = [
        {
            "net_income": 10,
            "total_revenue": 100,
            "stockholders_equity": 50,
            "shares_outstanding": 1_000,
        },
        {"net_income": 11, "revenue": 101},
        {"net_income": 12, "total_revenue": 102},
        {"net_income": 13, "revenue": 103},
    ]

    financials = executor._build_financials_dict()
    ratios = executor._build_ratios_dict()

    assert financials == {
        "net_income": 46,
        "revenue": 406,
        "shareholders_equity": 50,
        "market_cap": 100_000.0,
    }
    assert ratios["roe"] == 92.0
    assert executor._extract_metric({"a": 0, "b": 2}, ["a", "b"]) == 2
    assert executor._extract_metric({"a": 0}, ["a"]) is None
    assert (
        executor._calculate_enterprise_value({"market_cap": 1000, "total_debt": 300, "cash_and_equivalents": 50})
        == 1250
    )
    assert executor._calculate_enterprise_value({"total_debt": 300}) is None


def test_unified_executor_returns_error_when_no_models_are_available():
    executor = UnifiedValuationExecutor.__new__(UnifiedValuationExecutor)
    executor.symbol = "EMPTY"
    executor.current_price = 100.0
    executor.quarterly_metrics = [{"revenue": 1}]
    executor.multi_year_data = [{"revenue": 1}]

    class Metadata:
        def get_sector_industry(self, symbol):
            return "Unknown", "Unknown"

    async def no_models():
        return {}

    executor.metadata_service = Metadata()
    executor._run_all_models = no_models

    result = asyncio.run(executor.run_comprehensive_valuation())

    assert result["error"] == "No valuation models could be applied"
    assert result["models_applied"] == []
    assert result["consensus_fair_value"] is None


def test_unified_executor_uses_simple_average_when_weights_filter_models():
    executor = UnifiedValuationExecutor.__new__(UnifiedValuationExecutor)
    executor.symbol = "AVG"
    executor.current_price = 100.0
    executor.quarterly_metrics = [{"revenue": 1}]
    executor.multi_year_data = [{"revenue": 1}]

    class Metadata:
        def get_sector_industry(self, symbol):
            return "Technology", "Software"

    class Weighting:
        def determine_weights(self, **kwargs):
            return {"dcf": 0.0, "pe": 0.0}, "zero_weight", {"fallback": False}

    async def run_models():
        return {
            "dcf": {"success": True, "output": {"fair_value_per_share": 120.0}},
            "pe": {"success": True, "output": {"fair_value_per_share": 80.0}},
        }

    executor.metadata_service = Metadata()
    executor.weighting_service = Weighting()
    executor._run_all_models = run_models
    executor._build_financials_dict = lambda: {}
    executor._build_ratios_dict = lambda: {}

    result = asyncio.run(executor.run_comprehensive_valuation())

    assert result["consensus_fair_value"] == 100.0
    assert result["consensus_upside"] == 0.0
    assert result["weights_applied"] == {"dcf": 0.0, "pe": 0.0}


def test_run_all_models_executes_success_and_failure_paths(monkeypatch):
    executor = UnifiedValuationExecutor.__new__(UnifiedValuationExecutor)
    executor.symbol = "MODEL"
    executor.current_price = 100.0
    executor.quarterly_metrics = [{"revenue": 1}]
    executor.multi_year_data = [{"revenue": 1}]

    class Metadata:
        def get_sector_industry(self, symbol):
            return "Technology", "Software"

    executor.metadata_service = Metadata()

    class FakeDCF:
        def __init__(self, **kwargs):
            pass

        def calculate_dcf_valuation(self):
            return {"fair_value_per_share": 130.0}

    class FakeGGM:
        def __init__(self, **kwargs):
            pass

        def calculate(self):
            return SimpleNamespace(fair_value=90.0)

    class FakePE:
        def __init__(self, **kwargs):
            pass

        def calculate(self):
            return SimpleNamespace(fair_value=110.0)

    class FakePS:
        def __init__(self, **kwargs):
            pass

        def calculate(self):
            return "not applicable"

    class FakePB:
        def __init__(self, **kwargs):
            pass

        def calculate(self):
            raise RuntimeError("pb failed")

    class FakeEV:
        def __init__(self, **kwargs):
            pass

        def calculate(self):
            return SimpleNamespace(fair_value=140.0)

    class FakeTTM:
        @staticmethod
        def calculate_ttm_eps(quarterly_data, shares_outstanding=None):
            return 5.0

        @staticmethod
        def calculate_ttm_revenue(quarterly_data):
            return 1000.0

        @staticmethod
        def calculate_ttm_ebitda(quarterly_data):
            return 250.0

    class FakeSectorMultiples:
        @staticmethod
        def get_sector_multiples(sector, industry):
            return {"pe": 20.0, "ps": 5.0, "pb": 4.0, "ev_ebitda": 12.0}

    class FakeBookValueService:
        def calculate_book_value(self, quarterly_data):
            return 10.0

    class FakeMarketDataService:
        async def get_market_data(self, symbol):
            return {"market_cap": 1000.0, "total_debt": 200.0, "cash_and_equivalents": 100.0}

    monkeypatch.setattr("investigator.domain.services.valuation.DCFValuation", FakeDCF)
    monkeypatch.setattr("investigator.domain.services.valuation.models.GordonGrowthModel", FakeGGM, raising=False)
    monkeypatch.setattr("investigator.domain.services.valuation.models.PERatioModel", FakePE, raising=False)
    monkeypatch.setattr("investigator.domain.services.valuation.models.PSRatioModel", FakePS, raising=False)
    monkeypatch.setattr("investigator.domain.services.valuation.models.PBRatioModel", FakePB, raising=False)
    monkeypatch.setattr("investigator.domain.services.valuation.models.EVEBITDAModel", FakeEV)
    monkeypatch.setattr("investigator.domain.services.valuation.common.TTMMetrics", FakeTTM)
    monkeypatch.setattr("investigator.domain.services.valuation.common.SectorMultiples", FakeSectorMultiples)
    shared_module = ModuleType("investigator.domain.services.valuation.shared")
    book_value_module = ModuleType("investigator.domain.services.valuation.shared.book_value_service")
    market_data_module = ModuleType("investigator.domain.services.valuation.shared.market_data_service")
    book_value_module.BookValueService = FakeBookValueService
    market_data_module.MarketDataService = FakeMarketDataService
    monkeypatch.setitem(sys.modules, "investigator.domain.services.valuation.shared", shared_module)
    monkeypatch.setitem(
        sys.modules,
        "investigator.domain.services.valuation.shared.book_value_service",
        book_value_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "investigator.domain.services.valuation.shared.market_data_service",
        market_data_module,
    )

    result = asyncio.run(executor._run_all_models())

    assert result["dcf"]["output"]["fair_value_per_share"] == 130.0
    assert result["ggm"]["output"]["fair_value_per_share"] == 90.0
    assert result["pe"]["output"]["fair_value_per_share"] == 110.0
    assert "ps" not in result
    assert result["pb"]["success"] is False
    assert result["ev_ebitda"]["output"]["fair_value_per_share"] == 140.0

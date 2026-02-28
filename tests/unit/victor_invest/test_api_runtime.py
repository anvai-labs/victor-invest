import asyncio
import importlib
import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

import victor_invest.workflows as workflows_pkg
from victor_invest.workflows.state import AnalysisMode, AnalysisWorkflowState

api_module = importlib.import_module("victor_invest.api.app")


def test_api_runner_alias_targets_yaml_workflow_path():
    assert api_module.run_workflow_analysis is workflows_pkg.run_yaml_analysis


def test_analyze_symbol_uses_workflow_runner(monkeypatch):
    monkeypatch.setattr(api_module, "Agent", object())
    calls = {}

    async def fake_run_workflow_analysis(symbol, mode):
        calls["symbol"] = symbol
        calls["mode"] = mode
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            fundamental_analysis={"status": "success"},
            technical_analysis={"status": "success"},
            market_context={"status": "success"},
            synthesis={"recommendation": "BUY"},
            recommendation={"action": "BUY"},
            errors=[],
        )

    monkeypatch.setattr(api_module, "run_workflow_analysis", fake_run_workflow_analysis)

    request = api_module.AnalysisRequest(symbol="AAPL", mode="standard")
    response = asyncio.run(api_module.analyze_symbol("aapl", request))

    assert calls["symbol"] == "AAPL"
    assert calls["mode"] == AnalysisMode.STANDARD
    assert response.symbol == "AAPL"
    assert response.status == "completed"
    assert response.recommendation == {"action": "BUY"}


def test_run_batch_analysis_uses_workflow_runner(monkeypatch):
    calls = []

    async def fake_run_workflow_analysis(symbol, mode):
        calls.append((symbol, mode))
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            recommendation={"action": "HOLD"},
            errors=[],
        )

    monkeypatch.setattr(api_module, "run_workflow_analysis", fake_run_workflow_analysis)
    api_module.app.state.analysis_jobs = {
        "job-1": {
            "symbols": ["AAPL", "MSFT"],
            "mode": "quick",
            "status": "pending",
            "results": {},
            "submitted_at": "now",
        }
    }

    asyncio.run(api_module._run_batch_analysis("job-1", ["AAPL", "MSFT"], "quick"))

    assert sorted(calls) == [
        ("AAPL", AnalysisMode.QUICK),
        ("MSFT", AnalysisMode.QUICK),
    ]
    assert api_module.app.state.analysis_jobs["job-1"]["status"] == "completed"
    assert api_module.app.state.analysis_jobs["job-1"]["results"]["AAPL"]["status"] == "completed"
    assert api_module.app.state.analysis_jobs["job-1"]["results"]["MSFT"]["status"] == "completed"
    assert api_module.app.state.analysis_jobs["job-1"]["success_count"] == 2
    assert api_module.app.state.analysis_jobs["job-1"]["error_count"] == 0


def test_run_batch_analysis_marks_failed_for_invalid_mode(monkeypatch):
    async def should_not_run_workflow_analysis(symbol, mode):  # pragma: no cover - defensive
        raise AssertionError("run_workflow_analysis should not be called for invalid mode")

    monkeypatch.setattr(api_module, "run_workflow_analysis", should_not_run_workflow_analysis)
    api_module.app.state.analysis_jobs = {
        "job-invalid-mode": {
            "symbols": ["AAPL", "MSFT"],
            "mode": "invalid",
            "status": "pending",
            "results": {},
            "submitted_at": "now",
        }
    }

    asyncio.run(api_module._run_batch_analysis("job-invalid-mode", ["AAPL", "MSFT"], "invalid"))

    job = api_module.app.state.analysis_jobs["job-invalid-mode"]
    assert job["status"] == "failed"
    assert "Invalid mode" in job["error"]
    assert "completed_at" in job
    assert job["results"] == {}


def test_run_batch_analysis_marks_completed_with_errors(monkeypatch):
    async def fake_run_workflow_analysis(symbol, mode):
        if symbol == "MSFT":
            raise RuntimeError("boom")
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            recommendation={"action": "HOLD"},
            errors=[],
        )

    monkeypatch.setattr(api_module, "run_workflow_analysis", fake_run_workflow_analysis)
    api_module.app.state.analysis_jobs = {
        "job-partial": {
            "symbols": ["AAPL", "MSFT"],
            "mode": "quick",
            "status": "pending",
            "results": {},
            "submitted_at": "now",
        }
    }

    asyncio.run(api_module._run_batch_analysis("job-partial", ["AAPL", "MSFT"], "quick"))

    job = api_module.app.state.analysis_jobs["job-partial"]
    assert job["status"] == "completed_with_errors"
    assert job["results"]["AAPL"]["status"] == "completed"
    assert job["results"]["MSFT"]["status"] == "error"
    assert job["success_count"] == 1
    assert job["error_count"] == 1
    assert "completed_at" in job


def test_get_batch_parallelism_from_env(monkeypatch):
    monkeypatch.setenv("VICTOR_BATCH_MAX_PARALLEL", "8")
    assert api_module._get_batch_parallelism() == 8

    monkeypatch.setenv("VICTOR_BATCH_MAX_PARALLEL", "0")
    assert api_module._get_batch_parallelism() == 1

    monkeypatch.setenv("VICTOR_BATCH_MAX_PARALLEL", "not-an-int")
    assert api_module._get_batch_parallelism() == api_module.BATCH_ANALYSIS_MAX_PARALLEL

    monkeypatch.delenv("VICTOR_BATCH_MAX_PARALLEL", raising=False)
    assert api_module._get_batch_parallelism() == api_module.BATCH_ANALYSIS_MAX_PARALLEL


def test_warm_cache_uses_supported_market_data_action(monkeypatch):
    import victor_invest.tools as tools_module

    market_calls = []
    sec_calls = []

    class FakeSECTool:
        async def execute(self, **kwargs):
            sec_calls.append(kwargs)

    class FakeMarketTool:
        async def execute(self, **kwargs):
            market_calls.append(kwargs)

    monkeypatch.setattr(tools_module, "SECFilingTool", FakeSECTool)
    monkeypatch.setattr(tools_module, "MarketDataTool", FakeMarketTool)

    asyncio.run(api_module._warm_cache_for_symbols(["aapl"]))

    assert sec_calls[0]["symbol"] == "AAPL"
    assert market_calls[0]["symbol"] == "AAPL"
    assert market_calls[0]["action"] == "get_history"
    assert market_calls[0]["days"] == 365


def test_safe_float_normalizes_nan_and_inf():
    assert api_module._safe_float(float("nan")) is None
    assert api_module._safe_float(float("inf")) is None
    assert api_module._safe_float(float("-inf")) is None
    assert api_module._safe_float("123.45") == 123.45


def test_series_to_float_list_normalizes_non_finite_values():
    series = [1.0, float("nan"), float("inf"), float("-inf"), None]
    assert api_module._series_to_float_list(series) == [1.0, None, None, None, None]


def test_extract_ui_view_from_compact_includes_forward_horizon_and_guidance():
    payload = {
        "schema_version": "analysis.compact.v1",
        "symbol": "TRV",
        "price": {"current": 297.43, "target": 300.28, "expected_return_pct": 0.96},
        "recommendation": {
            "action": "hold",
            "confidence_score": 70.01,
            "investment_grade": "B",
        },
        "quality": {"data_quality_score": 68.1, "quality_grade": "Fair"},
        "valuation": {
            "basis": "forward",
            "forward_horizon": "1y",
            "blended_fair_value": 300.28,
            "models": {
                "pe": {
                    "assumptions": {
                        "valuation_basis": "forward",
                        "forward_horizon": "1y",
                    }
                }
            },
        },
        "sec": {
            "entity_name": "Travelers Companies, Inc.",
            "forward_guidance": {"source_form": "10-Q", "confidence_score": 0.55},
        },
    }

    view = api_module._extract_ui_view_from_payload(payload)

    assert view["summary"]["valuation_basis"] == "forward"
    assert view["summary"]["forward_horizon"] == "1y"
    assert view["summary"]["guidance_source_form"] == "10-Q"
    assert view["fundamental"]["forward_guidance"]["source_form"] == "10-Q"


def test_extract_ui_view_from_compact_derives_guidance_from_model_assumptions():
    payload = {
        "schema_version": "analysis.compact.v1",
        "symbol": "TRV",
        "valuation": {
            "basis": "forward",
            "models": {
                "pe": {
                    "assumptions": {
                        "valuation_basis": "forward",
                        "forward_horizon": "2q",
                        "guidance_applied": True,
                        "guidance_source_form": "8-K",
                        "guidance_confidence_score": 0.72,
                        "guidance_revenue_growth_used": 0.08,
                    }
                }
            },
        },
        "sec": {"entity_name": "Travelers Companies, Inc."},
    }

    view = api_module._extract_ui_view_from_payload(payload)
    guidance = view["fundamental"]["forward_guidance"]

    assert view["summary"]["forward_horizon"] == "2q"
    assert guidance["source"] == "valuation_model_assumptions"
    assert guidance["source_model"] == "pe"
    assert guidance["source_form"] == "8-K"
    assert guidance["revenue_growth_guidance"] == 0.08


def test_build_rankings_payload_returns_overall_and_sector_views():
    now_epoch = datetime.utcnow().timestamp()
    entries = [
        {
            "symbol": "AAA",
            "sector": "Technology",
            "expected_return_pct": 18.5,
            "data_quality_score": 82.0,
            "model_agreement_score": 0.6,
            "dispersion_ratio": 0.3,
            "valuation_basis": "forward",
            "forward_horizon": "1y",
            "cached_at_epoch": now_epoch,
        },
        {
            "symbol": "BBB",
            "sector": "Technology",
            "expected_return_pct": -12.0,
            "data_quality_score": 75.0,
            "model_agreement_score": 0.55,
            "dispersion_ratio": 0.4,
            "valuation_basis": "forward",
            "forward_horizon": "1y",
            "cached_at_epoch": now_epoch,
        },
        {
            "symbol": "CCC",
            "sector": "Financials",
            "expected_return_pct": 7.0,
            "data_quality_score": 66.0,
            "model_agreement_score": 0.35,
            "dispersion_ratio": 0.5,
            "valuation_basis": "forward",
            "forward_horizon": "1y",
            "cached_at_epoch": now_epoch,
        },
    ]

    payload = api_module._build_rankings_payload(
        entries,
        limit=2,
        per_sector=1,
        min_quality=50.0,
        max_age_hours=1000.0,
        min_model_agreement=0.0,
        max_dispersion=2.0,
        basis="forward",
        forward_horizon="1y",
        require_positive_target=False,
    )

    assert payload["universe"]["cached_symbols"] == 3
    assert payload["universe"]["eligible_symbols"] == 3
    assert payload["overall"]["longs"][0]["symbol"] == "AAA"
    assert payload["overall"]["shorts"][0]["symbol"] == "BBB"
    assert any(sector_row["sector"] == "Technology" for sector_row in payload["sectors"])
    assert payload["pairs"][0]["long"]["symbol"] == "AAA"
    assert payload["pairs"][0]["short"]["symbol"] == "BBB"
    assert payload["portfolio_preview"]["legs"]["longs"] >= 1
    assert payload["portfolio_preview"]["legs"]["shorts"] >= 1


def test_build_rankings_payload_filters_concentrated_and_low_confidence_names():
    now_epoch = datetime.utcnow().timestamp()
    entries = [
        {
            "symbol": "RISKY",
            "sector": "Technology",
            "expected_return_pct": -85.0,
            "confidence_score": 40.0,
            "data_quality_score": 80.0,
            "model_agreement_score": 0.5,
            "dispersion_ratio": 0.4,
            "weighted_model_count": 1,
            "max_model_weight": 0.95,
            "valuation_basis": "forward",
            "forward_horizon": "1y",
            "cached_at_epoch": now_epoch,
        },
        {
            "symbol": "ROBUST",
            "sector": "Technology",
            "expected_return_pct": -22.0,
            "confidence_score": 72.0,
            "data_quality_score": 82.0,
            "model_agreement_score": 0.6,
            "dispersion_ratio": 0.35,
            "weighted_model_count": 3,
            "max_model_weight": 0.5,
            "valuation_basis": "forward",
            "forward_horizon": "1y",
            "cached_at_epoch": now_epoch,
        },
    ]

    payload = api_module._build_rankings_payload(
        entries,
        limit=5,
        per_sector=2,
        min_quality=50.0,
        max_age_hours=1000.0,
        min_model_agreement=0.25,
        max_dispersion=0.8,
        basis="forward",
        forward_horizon="1y",
        min_confidence=55.0,
        require_model_agreement=True,
        require_dispersion=True,
        max_single_model_weight=0.8,
        require_multi_model=True,
        require_positive_target=False,
    )

    assert payload["universe"]["eligible_symbols"] == 1
    assert payload["overall"]["shorts"][0]["symbol"] == "ROBUST"
    assert payload["overall"]["longs"] == []


def test_ui_rankings_endpoint_reads_cache_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_module, "UI_CACHE_DIR", tmp_path)

    def _write(symbol: str, expected_return: float, sector: str, quality: float):
        payload = {
            "schema_version": "analysis.compact.v1",
            "symbol": symbol,
            "price": {
                "current": 100.0,
                "target": 100.0 + expected_return,
                "expected_return_pct": expected_return,
            },
            "recommendation": {
                "action": "hold",
                "confidence_score": 60.0,
                "investment_grade": "B",
            },
            "quality": {"data_quality_score": quality, "quality_grade": "Good"},
            "valuation": {
                "basis": "forward",
                "forward_horizon": "1y",
                "blended_fair_value": 100.0 + expected_return,
                "overall_confidence": 0.72,
                "model_agreement_score": 0.6,
                "dispersion_ratio": 0.4,
                "models": {
                    "pe": {
                        "weight": 0.5,
                        "fair_value_per_share": 110.0,
                        "applicable": 1.0,
                    },
                    "ps": {
                        "weight": 0.5,
                        "fair_value_per_share": 108.0,
                        "applicable": 1.0,
                    },
                },
            },
            "market": {"sector": sector, "market_regime": "risk_off"},
        }
        record = {
            "symbol": symbol,
            "cached_at": datetime.utcnow().isoformat(),
            "source": "test",
            "payload": payload,
        }
        (tmp_path / f"{symbol}.json").write_text(json.dumps(record), encoding="utf-8")

    _write("AAPL", 12.0, "Technology", 80.0)
    _write("MSFT", 6.0, "Technology", 76.0)
    _write("XOM", -8.0, "Energy", 72.0)

    client = TestClient(api_module.app)
    response = client.get("/ui/api/rankings?limit=2&per_sector=1&min_quality=0&max_age_hours=1000")

    assert response.status_code == 200
    data = response.json()
    assert data["universe"]["cached_symbols"] == 3
    assert data["overall"]["longs"][0]["symbol"] == "AAPL"
    assert data["overall"]["shorts"][0]["symbol"] == "XOM"
    assert isinstance(data["sectors"], list)
    assert "pairs" in data
    assert "portfolio_preview" in data


def test_ui_rankings_export_csv(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_module, "UI_CACHE_DIR", tmp_path)

    payload = {
        "schema_version": "analysis.compact.v1",
        "symbol": "AAPL",
        "price": {"current": 100.0, "target": 112.0, "expected_return_pct": 12.0},
        "recommendation": {
            "action": "buy",
            "confidence_score": 70.0,
            "investment_grade": "B",
        },
        "quality": {"data_quality_score": 80.0, "quality_grade": "Good"},
        "valuation": {
            "basis": "forward",
            "forward_horizon": "1y",
            "blended_fair_value": 112.0,
            "overall_confidence": 0.74,
            "model_agreement_score": 0.58,
            "dispersion_ratio": 0.3,
            "models": {
                "pe": {
                    "weight": 0.55,
                    "fair_value_per_share": 111.0,
                    "applicable": 1.0,
                },
                "ps": {
                    "weight": 0.45,
                    "fair_value_per_share": 113.0,
                    "applicable": 1.0,
                },
            },
        },
        "market": {"sector": "Technology", "market_regime": "risk_off"},
    }
    record = {
        "symbol": "AAPL",
        "cached_at": datetime.utcnow().isoformat(),
        "source": "test",
        "payload": payload,
    }
    (tmp_path / "AAPL.json").write_text(json.dumps(record), encoding="utf-8")

    client = TestClient(api_module.app)
    response = client.get("/ui/api/rankings/export.csv?export_type=overall&limit=5&min_quality=0&max_age_hours=1000")

    assert response.status_code == 200
    assert "text/csv" in (response.headers.get("content-type") or "")
    assert "side,rank,symbol,sector" in response.text
    assert "AAPL" in response.text

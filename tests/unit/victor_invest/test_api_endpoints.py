import importlib

from fastapi.testclient import TestClient

from victor_invest.workflows.state import AnalysisMode, AnalysisWorkflowState

api_module = importlib.import_module("victor_invest.api.app")


def test_analyze_endpoint_returns_workflow_result(monkeypatch):
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
    client = TestClient(api_module.app)

    response = client.post("/analyze/aapl", json={"symbol": "AAPL", "mode": "standard"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["status"] == "completed"
    assert payload["recommendation"] == {"action": "BUY"}
    assert calls == {"symbol": "AAPL", "mode": AnalysisMode.STANDARD}


def test_analyze_endpoint_api_alias_returns_workflow_result(monkeypatch):
    monkeypatch.setattr(api_module, "Agent", object())
    calls = {}

    async def fake_run_workflow_analysis(symbol, mode):
        calls["symbol"] = symbol
        calls["mode"] = mode
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            recommendation={"action": "BUY"},
            errors=[],
        )

    monkeypatch.setattr(api_module, "run_workflow_analysis", fake_run_workflow_analysis)
    client = TestClient(api_module.app)

    response = client.post("/api/analyze/aapl", json={"symbol": "AAPL", "mode": "standard"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["status"] == "completed"
    assert calls == {"symbol": "AAPL", "mode": AnalysisMode.STANDARD}


def test_analyze_endpoint_rejects_invalid_mode(monkeypatch):
    monkeypatch.setattr(api_module, "Agent", object())
    client = TestClient(api_module.app)

    response = client.post("/analyze/aapl", json={"symbol": "AAPL", "mode": "invalid"})

    assert response.status_code == 400
    assert "Invalid mode" in response.json()["error"]


def test_analyze_endpoint_rejects_symbol_mismatch(monkeypatch):
    monkeypatch.setattr(api_module, "Agent", object())
    client = TestClient(api_module.app)

    response = client.post("/analyze/aapl", json={"symbol": "MSFT", "mode": "standard"})

    assert response.status_code == 400
    assert "Symbol mismatch" in response.json()["error"]


def test_analyze_endpoint_normalizes_mode_case_and_whitespace(monkeypatch):
    monkeypatch.setattr(api_module, "Agent", object())
    calls = {}

    async def fake_run_workflow_analysis(symbol, mode):
        calls["symbol"] = symbol
        calls["mode"] = mode
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            recommendation={"action": "HOLD"},
            errors=[],
        )

    monkeypatch.setattr(api_module, "run_workflow_analysis", fake_run_workflow_analysis)
    client = TestClient(api_module.app)

    response = client.post("/analyze/aapl", json={"symbol": "AAPL", "mode": " STANDARD "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "standard"
    assert calls == {"symbol": "AAPL", "mode": AnalysisMode.STANDARD}


def test_batch_endpoint_rejects_invalid_mode():
    client = TestClient(api_module.app)

    response = client.post("/batch", json={"symbols": ["AAPL"], "mode": "invalid"})

    assert response.status_code == 400
    assert "Invalid mode" in response.json()["error"]


def test_batch_endpoint_normalizes_symbols_and_mode(monkeypatch):
    calls = {}

    async def fake_run_batch_analysis(job_id, symbols, mode):
        calls["job_id"] = job_id
        calls["symbols"] = symbols
        calls["mode"] = mode

    monkeypatch.setattr(api_module, "_run_batch_analysis", fake_run_batch_analysis)
    client = TestClient(api_module.app)

    response = client.post(
        "/batch",
        json={"symbols": [" aapl ", "AAPL", " msft ", " "], "mode": " QUICK "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["submitted"] == 2
    assert payload["status"] == "pending"

    job = api_module.app.state.analysis_jobs[payload["job_id"]]
    assert job["symbols"] == ["AAPL", "MSFT"]
    assert job["mode"] == "quick"
    assert calls["symbols"] == ["AAPL", "MSFT"]
    assert calls["mode"] == "quick"


def test_batch_endpoint_rejects_empty_normalized_symbols():
    client = TestClient(api_module.app)

    response = client.post("/batch", json={"symbols": ["  ", ""], "mode": "standard"})

    assert response.status_code == 400
    assert response.json()["error"] == "No valid symbols provided"


def test_protected_endpoints_require_bearer_token_when_configured(monkeypatch):
    monkeypatch.setenv("VICTOR_API_BEARER_TOKEN", "secret-token")
    monkeypatch.setattr(api_module, "Agent", object())
    client = TestClient(api_module.app)

    analyze_response = client.post("/analyze/aapl", json={"symbol": "AAPL", "mode": "standard"})
    batch_response = client.post("/batch", json={"symbols": ["AAPL"], "mode": "standard"})
    refresh_response = client.post("/ui/api/analysis/AAPL/refresh", json={"mode": "quick"})

    assert analyze_response.status_code == 401
    assert batch_response.status_code == 401
    assert refresh_response.status_code == 401


def test_protected_endpoints_accept_configured_bearer_token(monkeypatch):
    monkeypatch.setenv("VICTOR_API_BEARER_TOKEN", "secret-token")
    monkeypatch.setattr(api_module, "Agent", object())
    calls = {}

    async def fake_run_workflow_analysis(symbol, mode):
        calls["symbol"] = symbol
        calls["mode"] = mode
        return AnalysisWorkflowState(
            symbol=symbol,
            mode=mode,
            recommendation={"action": "BUY"},
            errors=[],
        )

    monkeypatch.setattr(api_module, "run_workflow_analysis", fake_run_workflow_analysis)
    client = TestClient(api_module.app)

    response = client.post(
        "/analyze/aapl",
        json={"symbol": "AAPL", "mode": "standard"},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert calls == {"symbol": "AAPL", "mode": AnalysisMode.STANDARD}


def test_health_endpoint_remains_unprotected_with_bearer_auth_enabled(monkeypatch):
    monkeypatch.setenv("VICTOR_API_BEARER_TOKEN", "secret-token")
    client = TestClient(api_module.app)

    response = client.get("/ui/api/health")

    assert response.status_code == 200


def test_dashboard_redirect_preserves_query_string():
    client = TestClient(api_module.app)

    response = client.get("/dashboard?symbol=AAPL", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui?symbol=AAPL"


def test_ui_analysis_history_returns_cache_derived_entries(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_load_ui_cache",
        lambda symbol: {
            "payload": {
                "schema_version": "analysis.compact.v1",
                "symbol": symbol,
                "price": {"current": 190.12},
                "recommendation": {"action": "buy", "confidence_score": 82.5},
            },
            "cached_at": "2026-03-15T10:00:00",
            "source": "ui_cache",
        },
    )
    monkeypatch.setattr(api_module, "_candidate_log_files", lambda symbol: [])
    client = TestClient(api_module.app)

    response = client.get("/ui/api/analysis/aapl/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "symbol": "AAPL",
            "timestamp": "2026-03-15T10:00:00",
            "action": "buy",
            "composite_score": 82.5,
            "price": 190.12,
            "source": "ui_cache",
        }
    ]

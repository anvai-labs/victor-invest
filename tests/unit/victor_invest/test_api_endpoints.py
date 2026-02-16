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

import importlib

from fastapi.testclient import TestClient

import victor_invest.workflows as workflows_pkg

api_module = importlib.import_module("victor_invest.api.app")


class _FakeWorkflowResult:
    def __init__(self, context):
        self.success = True
        self.context = context
        self.error = None


def test_analyze_endpoint_executes_yaml_provider_path_for_all_modes(monkeypatch):
    monkeypatch.setattr(api_module, "Agent", object())
    calls = []

    class FakeProvider:
        async def run_workflow_with_handlers(self, workflow_name, context):
            calls.append((workflow_name, dict(context)))
            return _FakeWorkflowResult(
                {
                    "fundamental_analysis": {"status": "success"},
                    "technical_analysis": {"status": "success"},
                    "market_context": {"status": "success"},
                    "synthesis": {"recommendation": "BUY", "confidence": "HIGH"},
                }
            )

    monkeypatch.setattr(workflows_pkg, "InvestmentWorkflowProvider", FakeProvider)

    client = TestClient(api_module.app)
    for mode in ("quick", "standard", "comprehensive"):
        response = client.post("/analyze/aapl", json={"symbol": "AAPL", "mode": mode})
        assert response.status_code == 200
        payload = response.json()
        assert payload["symbol"] == "AAPL"
        assert payload["mode"] == mode
        assert payload["recommendation"]["action"] == "BUY"

    assert calls == [
        ("quick", {"symbol": "AAPL"}),
        ("standard", {"symbol": "AAPL"}),
        ("comprehensive", {"symbol": "AAPL"}),
    ]

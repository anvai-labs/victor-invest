import json
from datetime import UTC, datetime

from investigator.infrastructure.database.valuation_run_repository import (
    ValuationModelOutputRecord,
    ValuationRunRecord,
    ValuationRunRepository,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Connection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        if "RETURNING valuation_run_id" in str(statement):
            return _Result(101)
        return _Result(None)


class _BeginContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self):
        self.conn = _Connection()

    def begin(self):
        return _BeginContext(self.conn)


def test_insert_run_writes_run_and_model_outputs():
    engine = _Engine()
    repo = ValuationRunRepository(engine)

    run_id = repo.insert_run(
        ValuationRunRecord(
            symbol="AAPL",
            analysis_mode="comprehensive",
            run_started_at=datetime(2026, 5, 20, tzinfo=UTC),
            run_completed_at=datetime(2026, 5, 20, 1, tzinfo=UTC),
            valuation_basis="ttm",
            forward_horizon="1y",
            current_price=100.0,
            blended_fair_value=125.0,
            expected_return_pct=25.0,
            data_quality_score=88.0,
            model_agreement_score=0.72,
            dispersion_ratio=0.28,
            applicable_models=3,
            decision_action="STRONG_BUY",
            decision_confidence="HIGH",
            decision_score=75.0,
            guardrails_triggered=[],
            source_freshness={"sec": "fresh"},
            input_snapshot={"price": 100.0},
            output_snapshot={"fair_value": 125.0},
            model_outputs=[
                ValuationModelOutputRecord(
                    model_name="dcf",
                    applicable=True,
                    fair_value_per_share=130.0,
                    weight=0.5,
                    confidence=0.8,
                    assumptions={"wacc": 0.09},
                    notes=["primary model"],
                ),
                ValuationModelOutputRecord(
                    model_name="pe",
                    applicable=True,
                    fair_value_per_share=120.0,
                    weight=0.5,
                    confidence=0.7,
                ),
            ],
        )
    )

    assert run_id == 101
    assert len(engine.conn.calls) == 3
    run_sql, run_params = engine.conn.calls[0]
    assert "INSERT INTO valuation_runs" in run_sql
    assert run_params["symbol"] == "AAPL"
    assert run_params["decision_action"] == "STRONG_BUY"
    assert json.loads(run_params["source_freshness_json"]) == {"sec": "fresh"}

    model_sql, model_params = engine.conn.calls[1]
    assert "INSERT INTO valuation_model_outputs" in model_sql
    assert model_params["valuation_run_id"] == 101
    assert model_params["model_name"] == "dcf"
    assert json.loads(model_params["assumptions_json"]) == {"wacc": 0.09}
    assert json.loads(model_params["notes_json"]) == ["primary model"]


def test_insert_run_allows_empty_model_outputs():
    engine = _Engine()
    repo = ValuationRunRepository(engine)

    run_id = repo.insert_run(
        ValuationRunRecord(
            symbol="MSFT",
            analysis_mode="standard",
            decision_action="REVIEW",
            decision_confidence="LOW",
            guardrails_triggered=["missing_fair_value"],
        )
    )

    assert run_id == 101
    assert len(engine.conn.calls) == 1
    assert json.loads(engine.conn.calls[0][1]["guardrails_triggered"]) == ["missing_fair_value"]

"""Repository for auditable valuation run persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ValuationModelOutputRecord:
    model_name: str
    applicable: bool
    fair_value_per_share: float | None = None
    weight: float | None = None
    confidence: float | None = None
    assumptions: dict[str, Any] = field(default_factory=dict)
    notes: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ValuationRunRecord:
    symbol: str
    analysis_mode: str
    run_started_at: datetime | None = None
    run_completed_at: datetime | None = None
    valuation_basis: str | None = None
    forward_horizon: str | None = None
    current_price: float | None = None
    blended_fair_value: float | None = None
    expected_return_pct: float | None = None
    data_quality_score: float | None = None
    model_agreement_score: float | None = None
    dispersion_ratio: float | None = None
    applicable_models: int | None = None
    decision_action: str | None = None
    decision_confidence: str | None = None
    decision_score: float | None = None
    guardrails_triggered: list[str] = field(default_factory=list)
    source_freshness: dict[str, Any] = field(default_factory=dict)
    input_snapshot: dict[str, Any] = field(default_factory=dict)
    output_snapshot: dict[str, Any] = field(default_factory=dict)
    model_outputs: list[ValuationModelOutputRecord] = field(default_factory=list)


class ValuationRunRepository:
    """Persist valuation run audit records and per-model outputs."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def insert_run(self, record: ValuationRunRecord) -> int:
        """Insert a valuation run and its model outputs, returning run id."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO valuation_runs (
                        symbol,
                        run_started_at,
                        run_completed_at,
                        analysis_mode,
                        valuation_basis,
                        forward_horizon,
                        current_price,
                        blended_fair_value,
                        expected_return_pct,
                        data_quality_score,
                        model_agreement_score,
                        dispersion_ratio,
                        applicable_models,
                        decision_action,
                        decision_confidence,
                        decision_score,
                        guardrails_triggered,
                        source_freshness_json,
                        input_snapshot_json,
                        output_snapshot_json
                    ) VALUES (
                        :symbol,
                        COALESCE(:run_started_at, now()),
                        :run_completed_at,
                        :analysis_mode,
                        :valuation_basis,
                        :forward_horizon,
                        :current_price,
                        :blended_fair_value,
                        :expected_return_pct,
                        :data_quality_score,
                        :model_agreement_score,
                        :dispersion_ratio,
                        :applicable_models,
                        :decision_action,
                        :decision_confidence,
                        :decision_score,
                        CAST(:guardrails_triggered AS jsonb),
                        CAST(:source_freshness_json AS jsonb),
                        CAST(:input_snapshot_json AS jsonb),
                        CAST(:output_snapshot_json AS jsonb)
                    )
                    RETURNING valuation_run_id
                    """
                ),
                self._run_params(record),
            )
            valuation_run_id = int(result.scalar_one())

            for model_output in record.model_outputs:
                conn.execute(
                    text(
                        """
                        INSERT INTO valuation_model_outputs (
                            valuation_run_id,
                            model_name,
                            applicable,
                            fair_value_per_share,
                            weight,
                            confidence,
                            assumptions_json,
                            notes_json
                        ) VALUES (
                            :valuation_run_id,
                            :model_name,
                            :applicable,
                            :fair_value_per_share,
                            :weight,
                            :confidence,
                            CAST(:assumptions_json AS jsonb),
                            CAST(:notes_json AS jsonb)
                        )
                        """
                    ),
                    self._model_params(valuation_run_id, model_output),
                )

        return valuation_run_id

    @staticmethod
    def _run_params(record: ValuationRunRecord) -> dict[str, Any]:
        return {
            "symbol": record.symbol.upper(),
            "run_started_at": record.run_started_at,
            "run_completed_at": record.run_completed_at,
            "analysis_mode": record.analysis_mode,
            "valuation_basis": record.valuation_basis,
            "forward_horizon": record.forward_horizon,
            "current_price": record.current_price,
            "blended_fair_value": record.blended_fair_value,
            "expected_return_pct": record.expected_return_pct,
            "data_quality_score": record.data_quality_score,
            "model_agreement_score": record.model_agreement_score,
            "dispersion_ratio": record.dispersion_ratio,
            "applicable_models": record.applicable_models,
            "decision_action": record.decision_action,
            "decision_confidence": record.decision_confidence,
            "decision_score": record.decision_score,
            "guardrails_triggered": json.dumps(record.guardrails_triggered),
            "source_freshness_json": json.dumps(record.source_freshness),
            "input_snapshot_json": json.dumps(record.input_snapshot),
            "output_snapshot_json": json.dumps(record.output_snapshot),
        }

    @staticmethod
    def _model_params(valuation_run_id: int, record: ValuationModelOutputRecord) -> dict[str, Any]:
        return {
            "valuation_run_id": valuation_run_id,
            "model_name": record.model_name,
            "applicable": record.applicable,
            "fair_value_per_share": record.fair_value_per_share,
            "weight": record.weight,
            "confidence": record.confidence,
            "assumptions_json": json.dumps(record.assumptions),
            "notes_json": json.dumps(record.notes),
        }

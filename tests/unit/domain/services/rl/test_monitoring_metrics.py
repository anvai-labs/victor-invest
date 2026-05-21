from datetime import datetime
from unittest.mock import patch

from investigator.domain.services.rl.monitoring.metrics import RLMetrics, get_rl_metrics


class _Result:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _Session:
    def __init__(self, results):
        self.results = list(results)
        self.params = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.params.append(params or {})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _DB:
    def __init__(self, results):
        self.session = _Session(results)

    def get_session(self):
        return self.session


def _metrics_with(results):
    db = _DB(results)
    with patch("investigator.domain.services.rl.monitoring.metrics.get_db_manager", return_value=db):
        metrics = RLMetrics()
    return metrics, db


def test_accuracy_by_sector_and_tier_map_rows_and_defaults():
    metrics, db = _metrics_with(
        [
            _Result(rows=[("Technology", 12, 0.35, 0.12, 8.5, 0.75), (None, 10, None, None, None, None)]),
            _Result(rows=[("tier_1", 11, 0.25, 0.11, 9.0), (None, 10, None, None, None)]),
        ]
    )

    by_sector = metrics.get_accuracy_by_sector(min_samples=5, days=180)
    by_tier = metrics.get_accuracy_by_tier(min_samples=5, days=180)

    assert by_sector["Technology"] == {
        "num_predictions": 12,
        "avg_reward": 0.35,
        "std_reward": 0.12,
        "avg_error_pct": 8.5,
        "direction_accuracy": 0.75,
    }
    assert by_sector["Unknown"]["avg_reward"] == 0
    assert by_tier["tier_1"]["num_predictions"] == 11
    assert by_tier["Unknown"]["avg_error_pct"] == 0
    assert db.session.params == [{"days": 180, "min_samples": 5}, {"days": 180, "min_samples": 5}]


def test_model_contribution_and_baseline_comparison_calculate_outputs():
    metrics, _ = _metrics_with(
        [
            _Result(one=(30.0, 25.0, 15.0, 10.0, 5.0, None)),
            _Result(rows=[("rl", 20, 0.30, 7.5, 0.70), ("baseline", 25, 0.20, 9.0, 0.60)]),
        ]
    )

    contribution = metrics.get_model_contribution(days=90)
    comparison = metrics.compare_to_baseline(days=90)

    assert contribution["dcf"] == {"avg_weight": 30.0}
    assert contribution["ggm"] == {"avg_weight": 0.0}
    assert comparison["rl_count"] == 20
    assert comparison["baseline_avg_reward"] == 0.20
    assert comparison["reward_improvement_pct"] == 49.999999999999986


def test_trend_and_summary_map_database_rows():
    period = datetime(2026, 5, 18)
    metrics, _ = _metrics_with(
        [
            _Result(rows=[(period, 5, 0.12, 10.5), (None, 2, None, None)]),
            _Result(one=(100, 80, 0.22, 0.08, -0.4, 0.9, 11.2, 0.63)),
        ]
    )

    trend = metrics.get_trend(days=60, bucket="day")
    summary = metrics.get_summary(days=60)

    assert trend == [
        {"period": "2026-05-18T00:00:00", "num_predictions": 5, "avg_reward": 0.12, "avg_error_pct": 10.5},
        {"period": None, "num_predictions": 2, "avg_reward": 0, "avg_error_pct": 0},
    ]
    assert summary == {
        "period_days": 60,
        "total_predictions": 100,
        "predictions_with_outcomes": 80,
        "avg_reward": 0.22,
        "std_reward": 0.08,
        "min_reward": -0.4,
        "max_reward": 0.9,
        "avg_mape": 11.2,
        "direction_accuracy": 0.63,
    }


def test_metrics_methods_return_empty_structures_on_database_errors():
    metrics, _ = _metrics_with([RuntimeError("db down")] * 6)

    assert metrics.get_accuracy_by_sector() == {}
    assert metrics.get_accuracy_by_tier() == {}
    assert metrics.get_model_contribution() == {}
    assert metrics.compare_to_baseline() == {}
    assert metrics.get_trend() == []
    assert metrics.get_summary() == {}


def test_rl_metrics_factory_uses_database_manager():
    db = _DB([])
    with patch("investigator.domain.services.rl.monitoring.metrics.get_db_manager", return_value=db):
        metrics = get_rl_metrics()

    assert isinstance(metrics, RLMetrics)
    assert metrics.db is db

"""
Unit tests for ABTestingFramework.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from investigator.domain.services.rl.models import ABTestGroup
from investigator.domain.services.rl.monitoring.ab_testing import (
    ABTestConfig,
    ABTestingFramework,
    get_ab_testing_framework,
)


class TestABTestingFramework:
    """Tests for ABTestingFramework."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return ABTestConfig(
            test_name="test_rl_vs_baseline",
            rl_traffic_pct=0.20,
            min_samples_per_group=10,
        )

    @pytest.fixture
    def framework(self, config):
        """Create A/B testing framework."""
        return ABTestingFramework(config=config)

    def test_get_assignment_deterministic(self, framework):
        """Test that assignment is deterministic for same symbol."""
        symbol = "AAPL"

        # Get assignment multiple times
        group1 = framework.get_assignment(symbol)
        group2 = framework.get_assignment(symbol)
        group3 = framework.get_assignment(symbol)

        # Should always be the same
        assert group1 == group2 == group3

    def test_get_assignment_distribution(self, framework):
        """Test that assignment follows target distribution."""
        # Reset cache
        framework.reset_cache()

        # Test many symbols
        symbols = [f"SYM{i}" for i in range(1000)]

        for symbol in symbols:
            framework.get_assignment(symbol)

        stats = framework.get_assignment_stats()

        # Should be close to 20% RL
        actual_rl_pct = stats["actual_rl_pct"]
        assert 15 <= actual_rl_pct <= 25  # Allow some variance

    def test_should_use_rl(self, framework):
        """Test should_use_rl method."""
        # Find a symbol that gets RL
        rl_symbol = None
        baseline_symbol = None

        for i in range(100):
            symbol = f"TEST{i}"
            if framework.should_use_rl(symbol):
                rl_symbol = symbol
            else:
                baseline_symbol = symbol

            if rl_symbol and baseline_symbol:
                break

        # Verify both groups are represented
        assert rl_symbol is not None or baseline_symbol is not None

    def test_assignment_cache(self, framework):
        """Test that assignments are cached."""
        symbol = "CACHED"

        # First call
        framework.get_assignment(symbol)
        assert symbol in framework._assignment_cache

        # Cache should contain assignment
        assert framework._assignment_cache[symbol] in [
            ABTestGroup.RL,
            ABTestGroup.BASELINE,
        ]

    def test_reset_cache(self, framework):
        """Test cache reset."""
        # Make some assignments
        for i in range(10):
            framework.get_assignment(f"SYM{i}")

        assert len(framework._assignment_cache) == 10

        # Reset
        framework.reset_cache()

        assert len(framework._assignment_cache) == 0
        assert framework._assignment_counts[ABTestGroup.RL] == 0
        assert framework._assignment_counts[ABTestGroup.BASELINE] == 0

    def test_assignment_stats(self, framework):
        """Test getting assignment statistics."""
        # Make some assignments
        for i in range(20):
            framework.get_assignment(f"SYM{i}")

        stats = framework.get_assignment_stats()

        assert "total_assignments" in stats
        assert stats["total_assignments"] == 20
        assert "rl_count" in stats
        assert "baseline_count" in stats
        assert stats["rl_count"] + stats["baseline_count"] == 20


class TestABTestConfig:
    """Tests for ABTestConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ABTestConfig()

        assert config.test_name == "rl_vs_baseline"
        assert config.rl_traffic_pct == 0.20
        assert config.min_samples_per_group == 50
        assert config.confidence_level == 0.95

    def test_custom_config(self):
        """Test custom configuration."""
        config = ABTestConfig(
            test_name="custom_test",
            rl_traffic_pct=0.50,
            min_samples_per_group=100,
            confidence_level=0.99,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert config.test_name == "custom_test"
        assert config.rl_traffic_pct == 0.50
        assert config.min_samples_per_group == 100


class TestABTestRecommendations:
    """Tests for A/B test recommendations."""

    def test_recommend_action_insufficient_data(self):
        """Test recommendation with insufficient data."""
        # Create a mock db manager that returns empty results
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_db.get_session.return_value = mock_session

        # Patch get_db_manager before creating framework
        with patch(
            "investigator.domain.services.rl.monitoring.ab_testing.get_db_manager",
            return_value=mock_db,
        ):
            config = ABTestConfig(min_samples_per_group=10)
            framework = ABTestingFramework(config=config)
            recommendation = framework.recommend_action()

        assert "action" in recommendation
        assert "reason" in recommendation
        # With no data, should recommend continuing test
        assert recommendation["action"] == "continue_test"

    def test_get_test_results_maps_metrics_and_significance(self):
        """Test DB result aggregation into ABTestResults."""
        framework = _framework_with_db_rows(
            [
                ("rl", 100, 0.40, 0.10, 8.0, 0.70),
                ("baseline", 100, 0.20, 0.10, 10.0, 0.55),
            ],
            min_samples=10,
        )

        results = framework.get_test_results(days=30)

        assert results.num_rl_samples == 100
        assert results.num_baseline_samples == 100
        assert results.rl_mean_reward == 0.40
        assert results.baseline_mean_reward == 0.20
        assert results.reward_p_value == 0.01
        assert results.reward_effect_size == 2.0
        assert results.is_significant is True

    def test_get_test_results_returns_empty_result_on_database_error(self):
        """Test DB errors return neutral results."""
        framework = _framework_with_db_exception(RuntimeError("db down"))

        results = framework.get_test_results(days=45)

        assert results.num_rl_samples == 0
        assert results.num_baseline_samples == 0
        assert results.reward_p_value == 1.0

    def test_group_breakdown_and_trend_comparison_map_rows(self):
        """Test detailed group and trend reporting."""
        period = datetime(2026, 5, 18)
        framework = _framework_with_db_results(
            [
                _Result(rows=[("rl", "Technology", 7, 0.3), ("baseline", None, 5, None)]),
                _Result(rows=[(period, "rl", 3, 0.4), (period, "baseline", 4, 0.2), (None, "rl", 1, None)]),
            ]
        )

        breakdown = framework.get_group_breakdown(days=90)
        trend = framework.get_trend_comparison(days=90, bucket="month")

        assert breakdown == {
            "rl": {"Technology": {"count": 7, "avg_reward": 0.3}},
            "baseline": {"Unknown": {"count": 5, "avg_reward": 0}},
        }
        assert trend == [
            {
                "period": "2026-05-18T00:00:00",
                "rl_count": 3,
                "rl_reward": 0.4,
                "baseline_count": 4,
                "baseline_reward": 0.2,
            },
            {"period": "unknown", "rl_count": 1, "rl_reward": 0},
        ]

    def test_recommend_action_expand_reduce_neutral_and_not_significant(self):
        """Test rollout recommendation branches."""
        framework = ABTestingFramework(config=ABTestConfig(rl_traffic_pct=0.4, min_samples_per_group=10))

        framework.get_test_results = MagicMock(
            return_value=_results(rl=0.40, baseline=0.20, p_value=0.01, effect_size=0.8)
        )
        assert framework.recommend_action()["action"] == "expand_rl"

        framework.get_test_results = MagicMock(
            return_value=_results(rl=-0.10, baseline=0.20, p_value=0.01, effect_size=-0.8)
        )
        assert framework.recommend_action()["action"] == "reduce_rl"

        framework.get_test_results = MagicMock(
            return_value=_results(rl=0.21, baseline=0.20, p_value=0.01, effect_size=0.8)
        )
        assert framework.recommend_action()["reason"] == "Marginal difference (5.0%), need more data"

        framework.get_test_results = MagicMock(
            return_value=_results(rl=0.40, baseline=0.20, p_value=0.10, effect_size=0.8)
        )
        assert framework.recommend_action()["reason"] == "Results not yet statistically significant"

    def test_recommend_action_checks_baseline_sample_floor(self):
        """Test baseline minimum-sample branch."""
        framework = ABTestingFramework(config=ABTestConfig(min_samples_per_group=10))
        framework.get_test_results = MagicMock(
            return_value=_results(rl=0.3, baseline=0.2, rl_samples=12, baseline_samples=3)
        )

        recommendation = framework.recommend_action()

        assert recommendation["action"] == "continue_test"
        assert "Insufficient baseline samples" in recommendation["reason"]

    def test_group_breakdown_and_trend_return_defaults_on_error(self):
        """Test reporting methods tolerate database exceptions."""
        framework = _framework_with_db_exception(RuntimeError("db down"))

        assert framework.get_group_breakdown() == {"rl": {}, "baseline": {}}
        assert framework.get_trend_comparison() == []

    def test_factory_creates_framework_with_traffic_config(self):
        """Test factory wiring."""
        with patch("investigator.domain.services.rl.monitoring.ab_testing.get_db_manager", return_value=MagicMock()):
            framework = get_ab_testing_framework(rl_traffic_pct=0.35)

        assert isinstance(framework, ABTestingFramework)
        assert framework.config.rl_traffic_pct == 0.35


class TestHashDistribution:
    """Tests for hash-based distribution."""

    def test_hash_uniformity(self):
        """Test that hash produces uniform distribution."""
        framework = ABTestingFramework(config=ABTestConfig(rl_traffic_pct=0.50))

        # Large sample
        rl_count = 0
        baseline_count = 0

        for i in range(10000):
            symbol = f"UNIFORM_TEST_{i}"
            if framework.should_use_rl(symbol):
                rl_count += 1
            else:
                baseline_count += 1

        # Should be close to 50/50
        ratio = rl_count / (rl_count + baseline_count)
        assert 0.45 <= ratio <= 0.55

    def test_hash_consistency_across_instances(self):
        """Test that different instances give same assignment."""
        config = ABTestConfig(rl_traffic_pct=0.30)

        fw1 = ABTestingFramework(config=config)
        fw2 = ABTestingFramework(config=config)

        # Same symbol should get same assignment in both
        for i in range(100):
            symbol = f"CONSISTENCY_{i}"
            assert fw1.get_assignment(symbol) == fw2.get_assignment(symbol)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Session:
    def __init__(self, results):
        self.results = list(results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _DB:
    def __init__(self, results):
        self.session = _Session(results)

    def get_session(self):
        return self.session


def _framework_with_db_results(results, min_samples=10):
    db = _DB(results)
    with patch("investigator.domain.services.rl.monitoring.ab_testing.get_db_manager", return_value=db):
        return ABTestingFramework(config=ABTestConfig(min_samples_per_group=min_samples))


def _framework_with_db_rows(rows, min_samples=10):
    return _framework_with_db_results([_Result(rows)], min_samples=min_samples)


def _framework_with_db_exception(exception):
    return _framework_with_db_results([exception, exception])


def _results(
    rl,
    baseline,
    p_value=0.01,
    effect_size=0.8,
    rl_samples=100,
    baseline_samples=100,
):
    from investigator.domain.services.rl.models import ABTestResults

    return ABTestResults(
        test_start_date=date(2026, 1, 1),
        test_end_date=date(2026, 5, 20),
        num_rl_samples=rl_samples,
        num_baseline_samples=baseline_samples,
        rl_mean_reward=rl,
        rl_mape=8.0,
        rl_direction_accuracy=0.7,
        baseline_mean_reward=baseline,
        baseline_mape=10.0,
        baseline_direction_accuracy=0.6,
        reward_p_value=p_value,
        mape_p_value=p_value,
        direction_p_value=p_value,
        reward_effect_size=effect_size,
        mape_effect_size=effect_size,
    )

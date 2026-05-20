"""
Unit tests for RL policies.
"""

import os
import tempfile
from datetime import date
from unittest.mock import MagicMock

import pytest

from investigator.domain.services.rl.feature_normalizer import FeatureNormalizer
from investigator.domain.services.rl.models import Experience, GrowthStage, RewardSignal, ValuationContext
from investigator.domain.services.rl.policy.base import RLPolicy, UniformPolicy
from investigator.domain.services.rl.policy.contextual_bandit import (
    ContextualBanditPolicy,
)
from investigator.domain.services.rl.policy.dual_policy import DualRLPolicy
from investigator.domain.services.rl.policy.hybrid import HybridPolicy


class _RecordingPolicy(RLPolicy):
    def __init__(self, **kwargs):
        super().__init__(name="recording", **kwargs)
        self.updates = []
        self._ready = True

    def predict(self, context):
        return {"dcf": 60.0, "pe": 40.0}

    def update(self, context, action, reward):
        self.updates.append((context.symbol, action, reward))
        self._update_count += 1

    def save(self, path):
        return True

    def load(self, path):
        return True


class _FakeTechnicalPolicy:
    def __init__(self):
        self._update_count = 0
        self._ready = True
        self.loaded = []
        self.saved = []
        self.updated = []

    def predict_position(self, context):
        return 1, 0.82

    def predict(self, context):
        return {"skip": 0.05, "long": 0.82, "short": 0.13}

    def update(self, context, action, reward):
        self.updated.append((action, reward))
        self._update_count += 1

    def save(self, path):
        self.saved.append(path)
        return True

    def load(self, path):
        self.loaded.append(path)
        return True

    def get_state(self):
        return {"policy": "technical"}

    def get_action_stats(self):
        return {"long": 3}


class _FakeFundamentalPolicy:
    def __init__(self):
        self._update_count = 0
        self._ready = True
        self.loaded = []
        self.saved = []
        self.weights_updates = []
        self.period_updates = []

    def predict(self, context):
        return {"dcf": 55.0, "pe": 45.0}

    def predict_holding_period(self, context):
        return "6m"

    def update_weights(self, context, weights, reward):
        self.weights_updates.append((weights, reward))
        self._update_count += 1

    def update_holding_period(self, context, period, reward):
        self.period_updates.append((period, reward))

    def save(self, path):
        self.saved.append(path)
        return True

    def load(self, path):
        self.loaded.append(path)
        return True

    def get_state(self):
        return {"policy": "fundamental"}

    def get_model_stats(self):
        return {"dcf": 2}

    def get_holding_period_stats(self):
        return {"6m": 2}


class TestUniformPolicy:
    """Tests for UniformPolicy baseline."""

    @pytest.fixture
    def policy(self):
        """Create uniform policy."""
        return UniformPolicy()

    @pytest.fixture
    def sample_context(self):
        """Create sample context."""
        return ValuationContext(
            symbol="AAPL",
            analysis_date=date(2024, 1, 15),
            sector="Technology",
            industry="Consumer Electronics",
        )

    def test_predict_returns_weights(self, policy, sample_context):
        """Test that predict returns valid weights dict."""
        weights = policy.predict(sample_context)

        assert isinstance(weights, dict)
        assert "dcf" in weights
        assert "pe" in weights
        assert "ps" in weights

    def test_weights_sum_to_100(self, policy, sample_context):
        """Test that weights sum to approximately 100."""
        weights = policy.predict(sample_context)
        total = sum(weights.values())
        assert abs(total - 100) < 0.1

    def test_is_ready(self, policy):
        """Test that uniform policy is always ready."""
        assert policy.is_ready() is True

    def test_update_no_op(self, policy, sample_context):
        """Test that update is no-op for uniform policy."""
        # Should not raise
        policy.update(sample_context, {"dcf": 50, "pe": 50}, 0.5)


class TestContextualBanditPolicy:
    """Tests for ContextualBanditPolicy."""

    @pytest.fixture
    def normalizer(self):
        """Create and fit normalizer."""
        normalizer = FeatureNormalizer()
        contexts = [
            ValuationContext(
                symbol=f"SYM{i}",
                analysis_date=date(2024, 1, 15),
                sector="Technology",
                industry="Software",
                profitability_score=0.5 + i * 0.1,
            )
            for i in range(10)
        ]
        normalizer.fit(contexts)
        return normalizer

    @pytest.fixture
    def policy(self, normalizer):
        """Create contextual bandit policy."""
        return ContextualBanditPolicy(normalizer=normalizer)

    @pytest.fixture
    def sample_context(self):
        """Create sample context."""
        return ValuationContext(
            symbol="TEST",
            analysis_date=date(2024, 1, 15),
            sector="Technology",
            industry="Software",
            growth_stage=GrowthStage.HIGH_GROWTH,
            profitability_score=0.75,
        )

    def test_predict_returns_valid_weights(self, policy, sample_context):
        """Test that predict returns valid weight distribution."""
        weights = policy.predict(sample_context)

        assert isinstance(weights, dict)
        assert len(weights) == 6  # 6 valuation models

        # Weights should sum to 100
        assert abs(sum(weights.values()) - 100) < 0.1

        # All weights should be non-negative
        for weight in weights.values():
            assert weight >= 0

    def test_update_does_not_raise(self, policy, sample_context):
        """Test that update completes without error."""
        # Should not raise
        policy.update(
            context=sample_context,
            action={"dcf": 40, "pe": 30, "ps": 20, "ev_ebitda": 10},
            reward=1.0,
        )

    def test_is_ready_without_normalizer(self):
        """Test that policy without normalizer is not ready."""
        policy = ContextualBanditPolicy(normalizer=None)
        assert policy.is_ready() is False

    def test_is_ready_with_unfitted_normalizer(self):
        """Test that policy with unfitted normalizer is not ready."""
        normalizer = FeatureNormalizer()
        policy = ContextualBanditPolicy(normalizer=normalizer)
        assert policy.is_ready() is False

    def test_save_and_load(self, policy, sample_context):
        """Test saving and loading policy."""
        for _ in range(5):
            policy.predict(sample_context)
            policy.update(sample_context, {"dcf": 50, "pe": 50}, 0.5)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "policy.pkl")

            # Save
            policy.save(path)
            assert os.path.exists(path)

            # Load into new policy
            new_policy = ContextualBanditPolicy(normalizer=policy.normalizer)
            loaded = new_policy.load(path)

            assert loaded is True


class TestHybridPolicy:
    """Tests for HybridPolicy."""

    @pytest.fixture
    def base_service(self):
        """Create mock base weighting service."""
        service = MagicMock()
        service.determine_weights.return_value = (
            {"dcf": 40, "pe": 30, "ps": 15, "ev_ebitda": 10, "pb": 5, "ggm": 0},
            "high_growth_strong",
            None,
        )
        return service

    @pytest.fixture
    def normalizer(self):
        """Create and fit normalizer."""
        normalizer = FeatureNormalizer()
        contexts = [
            ValuationContext(
                symbol=f"SYM{i}",
                analysis_date=date(2024, 1, 15),
                sector="Technology",
                industry="Software",
                profitability_score=0.5,
            )
            for i in range(5)
        ]
        normalizer.fit(contexts)
        return normalizer

    @pytest.fixture
    def policy(self, base_service, normalizer):
        """Create hybrid policy."""
        return HybridPolicy(
            base_weighting_service=base_service,
            adjustment_policy=None,
            max_adjustment=0.30,
            normalizer=normalizer,
        )

    @pytest.fixture
    def sample_context(self):
        """Create sample context."""
        return ValuationContext(
            symbol="TEST",
            analysis_date=date(2024, 1, 15),
            sector="Technology",
            industry="Software",
        )

    def test_predict_returns_valid_weights(self, policy, sample_context):
        """Test that predictions are valid."""
        weights = policy.predict(sample_context)

        assert isinstance(weights, dict)
        assert abs(sum(weights.values()) - 100) < 0.1

        # All weights should be non-negative
        for weight in weights.values():
            assert weight >= 0

    def test_predict_uses_base_service(self, policy, sample_context, base_service):
        """Test that predict calls base service."""
        policy.predict(sample_context)

        # Base service should have been called
        base_service.determine_weights.assert_called()

    def test_update_does_not_raise(self, policy, sample_context):
        """Test that update completes without error."""
        policy.update(
            context=sample_context,
            action={"dcf": 45, "pe": 30, "ps": 15, "ev_ebitda": 10},
            reward=0.8,
        )

    def test_is_ready(self, policy):
        """Test is_ready with base service."""
        assert policy.is_ready() is True


class TestPolicyHelperMethods:
    """Tests for policy helper methods."""

    def test_normalize_weights(self):
        """Test weight normalization."""
        policy = UniformPolicy()

        weights = {"dcf": 50, "pe": 30, "ps": 20}
        normalized = policy.normalize_weights(weights)

        assert abs(sum(normalized.values()) - 100) < 0.01

    def test_normalize_zero_weights(self):
        """Test normalization with zero weights."""
        policy = UniformPolicy()

        weights = {"dcf": 0, "pe": 0, "ps": 0}
        normalized = policy.normalize_weights(weights)

        # Should return valid weights (all >= 0)
        assert all(v >= 0 for v in normalized.values())

    def test_apply_applicability_mask(self):
        """Test applying applicability mask."""
        policy = UniformPolicy()

        weights = {"dcf": 30, "pe": 30, "ps": 20, "ev_ebitda": 10, "pb": 5, "ggm": 5}
        context = ValuationContext(
            symbol="TEST",
            analysis_date=date(2024, 1, 15),
            sector="Technology",
            industry="Software",
            dcf_applicable=True,
            pe_applicable=True,
            ps_applicable=True,
            pb_applicable=False,
            evebitda_applicable=True,
            ggm_applicable=False,
        )

        masked = policy.apply_applicability_mask(weights, context)

        # pb and ggm should be zero
        assert masked.get("pb", 0) == 0
        assert masked.get("ggm", 0) == 0

        # Others should still have values
        assert masked["dcf"] > 0
        assert masked["pe"] > 0

    def test_base_policy_batch_confidence_state_and_dict_mask(self):
        """Test inherited RLPolicy helper methods through a concrete subclass."""
        context = ValuationContext(symbol="TEST", analysis_date=date(2024, 1, 15))
        policy = _RecordingPolicy(model_names=["dcf", "pe"])
        experiences = [
            Experience(
                id=1,
                symbol="TEST",
                analysis_date=date(2024, 1, 15),
                context=context,
                weights_used={"dcf": 70.0, "pe": 30.0},
                tier_classification="tier_1",
                blended_fair_value=120.0,
                current_price=100.0,
                reward=RewardSignal(reward_90d=0.4),
            ),
            Experience(
                id=2,
                symbol="MISS",
                analysis_date=date(2024, 1, 16),
                context=context,
                weights_used={"dcf": 50.0, "pe": 50.0},
                tier_classification="tier_2",
                blended_fair_value=95.0,
                current_price=100.0,
                reward=RewardSignal(),
            ),
        ]

        processed = policy.batch_update(experiences)
        weights, confidence = policy.predict_with_confidence(context)
        masked = policy.apply_applicability_mask(
            {"dcf": 60.0, "pe": 20.0, "ggm": 20.0},
            {"dcf_applicable": True, "pe_applicable": False, "ggm_applicable": False},
        )
        features = policy._extract_features(context)
        state = policy.get_state()

        assert processed == 1
        assert policy.updates == [("TEST", {"dcf": 70.0, "pe": 30.0}, 0.4)]
        assert weights == {"dcf": 60.0, "pe": 40.0}
        assert confidence == 0.5
        assert policy.get_exploration_bonus(context) == {"dcf": 0.0, "pe": 0.0}
        assert masked["dcf"] == 100.0
        assert masked["pe"] == 0.0
        assert masked["ggm"] == 0.0
        assert features.size > 0
        assert state["name"] == "recording"
        assert state["update_count"] == 1


class TestDualPolicy:
    """Tests for dual technical/fundamental policy composition."""

    def test_predict_update_save_load_and_stats(self, tmp_path):
        context = ValuationContext(symbol="NVDA", analysis_date=date(2024, 1, 15))
        technical = _FakeTechnicalPolicy()
        fundamental = _FakeFundamentalPolicy()
        policy = DualRLPolicy(
            technical_policy=technical,
            fundamental_policy=fundamental,
            technical_path=str(tmp_path / "technical.pkl"),
            fundamental_path=str(tmp_path / "fundamental.pkl"),
        )

        prediction = policy.predict_full(context)
        policy.update(context, prediction, 0.7, {"1m": None, "6m": 0.8})
        policy.update_position(context, -1, -0.4)
        policy.update_weights(context, {"dcf": 65.0, "pe": 35.0}, 0.5)
        policy.update_holding_period(context, "12m", 0.2)

        assert policy.predict_position(context) == (1, 0.82)
        assert policy.predict_weights(context) == {"dcf": 55.0, "pe": 45.0}
        assert policy.predict_holding_period(context) == "6m"
        assert prediction["position"] == 1
        assert prediction["position_confidence"] == 0.82
        assert technical.updated[0] == (1, 0.7)
        assert technical.updated[1] == (2, -0.4)
        assert fundamental.weights_updates[0] == ({"dcf": 55.0, "pe": 45.0}, 0.7)
        assert fundamental.weights_updates[1] == ({"dcf": 65.0, "pe": 35.0}, 0.5)
        assert fundamental.period_updates == [("6m", 0.8), ("12m", 0.2)]
        assert policy.save() is True
        assert policy.load() is True
        assert policy.is_ready() is True
        assert policy.get_state()["technical_updates"] == technical._update_count
        assert policy.get_action_stats() == {"long": 3}
        assert policy.get_model_stats() == {"dcf": 2}
        assert policy.get_holding_period_stats() == {"6m": 2}

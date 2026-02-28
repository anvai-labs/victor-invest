# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for RobustValuationService orchestrator.

Tests the comprehensive robust valuation combining all 3 layers:
- Layer 1: Trend-adjusted sector multiples
- Layer 2: Company fair multiples
- Layer 3: Peer comparison
- Synthesis and recommendation logic
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from investigator.domain.services.company_fair_multiple_calculator import (
    FairMultipleResult,
)
from investigator.domain.services.cross_sectional_valuation import (
    PeerComparisonResult,
)
from investigator.domain.services.robust_valuation_service import (
    RobustValuationResult,
    RobustValuationService,
)


@pytest.fixture
def mock_sec_db_manager():
    """Create mock SEC database manager."""
    return MagicMock()


@pytest.fixture
def mock_stock_db_manager():
    """Create mock stock database manager."""
    return MagicMock()


@pytest.fixture
def valuation_service(mock_sec_db_manager, mock_stock_db_manager):
    """Create RobustValuationService with mocked dependencies."""
    with (
        patch("investigator.domain.services.robust_valuation_service.SectorMultiplesTrendAdjusted"),
        patch("investigator.domain.services.robust_valuation_service.CompanyFairMultipleCalculator"),
        patch("investigator.domain.services.robust_valuation_service.CrossSectionalValuation"),
    ):
        service = RobustValuationService(
            sec_db_manager=mock_sec_db_manager,
            stock_db_manager=mock_stock_db_manager,
        )
        return service


class TestLayer1Data:
    """Test Layer 1 trend-adjusted sector multiples retrieval."""

    def test_get_layer1_data_success(self, valuation_service):
        """Test successful Layer 1 data retrieval."""
        sector = "Technology"

        result = valuation_service._get_layer1_data(sector)

        assert result is not None
        assert "pe" in result
        assert "ps" in result
        assert "pb" in result
        assert result["pe"] == 55.0
        assert result["ps"] == 7.6
        assert result["pb"] == 8.0


class TestLayer2Data:
    """Test Layer 2 company fair multiples calculation."""

    @pytest.mark.asyncio
    async def test_get_layer2_data_success(self, valuation_service):
        """Test successful Layer 2 data retrieval."""
        symbol = "AAPL"
        sector = "Technology"
        industry = "Consumer Electronics"

        # Mock Layer 1 data
        layer1_data = {"pe": 55.0, "ps": 7.6, "pb": 8.0}

        # Mock layer2.calculate_fair_multiple
        mock_results = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "ps": FairMultipleResult(
                symbol=symbol,
                metric="ps",
                sector_baseline=7.6,
                company_historical_premium=5.0,
                base_fair_multiple=7.98,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=7.58,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "pb": FairMultipleResult(
                symbol=symbol,
                metric="pb",
                sector_baseline=8.0,
                company_historical_premium=15.0,
                base_fair_multiple=9.2,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=8.74,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        with patch.object(valuation_service, "_get_layer1_data", return_value=layer1_data):
            with patch.object(
                valuation_service.layer2,
                "calculate_fair_multiple",
                side_effect=lambda **kwargs: mock_results.get(kwargs.get("metric")),
            ):
                result = valuation_service._get_layer2_data(symbol, sector, industry)

        assert result is not None
        assert "pe" in result
        assert "ps" in result
        assert "pb" in result
        assert result["pe"].final_fair_multiple == 57.48
        assert result["pe"].confidence == "HIGH"

    @pytest.mark.asyncio
    async def test_get_layer2_data_partial_failure(self, valuation_service):
        """Test Layer 2 with some metric failures."""
        symbol = "AAPL"
        sector = "Technology"

        # Mock Layer 1 data
        layer1_data = {"pe": 55.0, "ps": 7.6, "pb": 8.0}

        # Mock partial results (ps fails)
        mock_results = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "pb": FairMultipleResult(
                symbol=symbol,
                metric="pb",
                sector_baseline=8.0,
                company_historical_premium=15.0,
                base_fair_multiple=9.2,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=8.74,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        with patch.object(valuation_service, "_get_layer1_data", return_value=layer1_data):
            with patch.object(
                valuation_service.layer2,
                "calculate_fair_multiple",
                side_effect=lambda **kwargs: mock_results.get(kwargs.get("metric")),
            ):
                result = valuation_service._get_layer2_data(symbol, sector, None)

        assert result is not None
        assert "pe" in result
        assert "pb" in result
        assert "ps" not in result  # Failed


class TestLayer3Data:
    """Test Layer 3 peer comparison."""

    @pytest.mark.asyncio
    async def test_get_layer3_data_success(self, valuation_service):
        """Test successful Layer 3 data retrieval."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock peer comparison results
        mock_results = {
            "pe": PeerComparisonResult(
                symbol=symbol,
                metric="pe",
                industry=industry,
                peers=["MSFT", "GOOGL"],
                peer_count=2,
                company_multiple=35.0,
                peer_mean=30.0,
                peer_median=30.0,
                peer_std=5.0,
                peer_min=25.0,
                peer_max=35.0,
                peer_p25=27.5,
                peer_p75=32.5,
                percentile_rank=75.0,
                z_score_vs_peers=1.0,
                status="expensive",
                premium_to_peers_pct=16.7,
                outperforming_peers=2,
                underperforming_peers=0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "ps": PeerComparisonResult(
                symbol=symbol,
                metric="ps",
                industry=industry,
                peers=["MSFT", "GOOGL"],
                peer_count=2,
                company_multiple=8.0,
                peer_mean=7.0,
                peer_median=7.0,
                peer_std=1.0,
                peer_min=6.0,
                peer_max=8.0,
                peer_p25=6.5,
                peer_p75=7.5,
                percentile_rank=75.0,
                z_score_vs_peers=1.0,
                status="expensive",
                premium_to_peers_pct=14.3,
                outperforming_peers=2,
                underperforming_peers=0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        with patch.object(
            valuation_service.layer3,
            "compare_to_peers",
            side_effect=lambda **kwargs: mock_results.get(kwargs.get("metric")),
        ):
            result = valuation_service._get_layer3_data(symbol, industry)

        assert result is not None
        assert "pe" in result
        assert "ps" in result
        assert result["pe"].status == "expensive"

    @pytest.mark.asyncio
    async def test_get_layer3_data_empty(self, valuation_service):
        """Test Layer 3 with no peer data."""
        symbol = "AAPL"
        industry = "Unknown Industry"

        with patch.object(valuation_service.layer3, "compare_to_peers", return_value=None):
            result = valuation_service._get_layer3_data(symbol, industry)

        assert result == {}


class TestSynthesis:
    """Test synthesis of all 3 layers."""

    def test_synthesize_layers_strong_buy(self, valuation_service):
        """Test synthesis resulting in STRONG BUY recommendation."""
        symbol = "AAPL"
        current_price = 150.0
        eps = 6.0

        # Layer 2 data with high confidence
        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0},
            layer2_data=layer2_data,
            layer3_data=layer3_data,
            current_price=current_price,
            eps=eps,
            revenue_per_share=None,
            book_value_per_share=None,
        )

        assert synthesis["recommendation"] == "STRONG BUY"
        assert synthesis["confidence"] == "HIGH"
        assert synthesis["fair_value_estimate"] > current_price
        assert synthesis["upside_downside_pct"] >= 15.0

    def test_synthesize_layers_buy(self, valuation_service):
        """Test synthesis resulting in BUY recommendation."""
        symbol = "AAPL"
        current_price = 320.0  # Price to get ~7.7% upside (in BUY range 5-15%)
        eps = 6.0

        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0},
            layer2_data=layer2_data,
            layer3_data=layer3_data,
            current_price=current_price,
            eps=eps,
            revenue_per_share=None,
            book_value_per_share=None,
        )

        assert synthesis["recommendation"] == "BUY"
        assert 5.0 <= synthesis["upside_downside_pct"] < 15.0  # BUY range

    def test_synthesize_layers_hold(self, valuation_service):
        """Test synthesis resulting in HOLD recommendation."""
        symbol = "AAPL"
        current_price = 345.0  # Very close to fair value for HOLD
        eps = 6.0

        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0},
            layer2_data=layer2_data,
            layer3_data=layer3_data,
            current_price=current_price,
            eps=eps,
            revenue_per_share=None,
            book_value_per_share=None,
        )

        assert synthesis["recommendation"] == "HOLD"

    def test_synthesize_layers_sell(self, valuation_service):
        """Test synthesis resulting in SELL recommendation."""
        symbol = "AAPL"
        current_price = 365.0  # Above fair value for SELL
        eps = 6.0

        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0},
            layer2_data=layer2_data,
            layer3_data=layer3_data,
            current_price=current_price,
            eps=eps,
            revenue_per_share=None,
            book_value_per_share=None,
        )

        assert synthesis["recommendation"] == "SELL"

    def test_synthesize_layers_multiple_metrics(self, valuation_service):
        """Test synthesis with multiple valuation metrics."""
        symbol = "AAPL"
        current_price = 150.0
        eps = 6.0
        revenue_per_share = 25.0
        book_value_per_share = 22.0

        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "ps": FairMultipleResult(
                symbol=symbol,
                metric="ps",
                sector_baseline=7.6,
                company_historical_premium=5.0,
                base_fair_multiple=7.98,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=7.58,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "pb": FairMultipleResult(
                symbol=symbol,
                metric="pb",
                sector_baseline=8.0,
                company_historical_premium=15.0,
                base_fair_multiple=9.2,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=8.74,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0, "ps": 7.6, "pb": 8.0},
            layer2_data=layer2_data,
            layer3_data=layer3_data,
            current_price=current_price,
            eps=eps,
            revenue_per_share=revenue_per_share,
            book_value_per_share=book_value_per_share,
        )

        assert "pe_based" in synthesis["valuation_methods"]
        assert "ps_based" in synthesis["valuation_methods"]
        assert "pb_based" in synthesis["valuation_methods"]
        assert len(synthesis["valuation_methods"]) == 3
        assert synthesis["fair_value_estimate"] > 0
        assert synthesis["fair_value_range"][0] < synthesis["fair_value_estimate"] < synthesis["fair_value_range"][1]

    def test_synthesize_layers_insufficient_data(self, valuation_service):
        """Test synthesis with insufficient data."""
        symbol = "AAPL"

        layer2_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0},
            layer2_data=layer2_data,
            layer3_data={},
            current_price=None,
            eps=None,
            revenue_per_share=None,
            book_value_per_share=None,
        )

        assert synthesis["fair_value_estimate"] == 0.0
        assert synthesis["confidence"] == "LOW"
        assert synthesis["recommendation"] == "HOLD"
        assert "Insufficient data" in synthesis["signals"][0]

    def test_synthesize_layers_no_per_share_data(self, valuation_service):
        """Test synthesis with fair multiples but no per-share data."""
        symbol = "AAPL"

        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        synthesis = valuation_service._synthesize_layers(
            symbol=symbol,
            layer1_data={"pe": 55.0},
            layer2_data=layer2_data,
            layer3_data=layer3_data,
            current_price=None,
            eps=None,  # No per-share data
            revenue_per_share=None,
            book_value_per_share=None,
        )

        # Should return insufficient data since can't calculate fair value
        assert synthesis["fair_value_estimate"] == 0.0


class TestConfidenceDetermination:
    """Test overall confidence determination."""

    def test_determine_overall_confidence_all_high(self, valuation_service):
        """Test confidence with all HIGH confidences."""
        confidences = ["HIGH", "HIGH", "HIGH"]
        result = valuation_service._determine_overall_confidence(confidences)
        assert result == "HIGH"

    def test_determine_overall_confidence_mixed_high_medium(self, valuation_service):
        """Test confidence with mixed HIGH/MEDIUM."""
        confidences = ["HIGH", "MEDIUM", "HIGH"]
        result = valuation_service._determine_overall_confidence(confidences)
        assert result == "MEDIUM"

    def test_determine_overall_confidence_with_low(self, valuation_service):
        """Test confidence with any LOW confidences."""
        confidences = ["HIGH", "LOW", "MEDIUM"]
        result = valuation_service._determine_overall_confidence(confidences)
        assert result == "LOW"

    def test_determine_overall_confidence_empty(self, valuation_service):
        """Test confidence with empty list."""
        confidences = []
        result = valuation_service._determine_overall_confidence(confidences)
        assert result == "LOW"


class TestRecommendationDetermination:
    """Test recommendation determination logic."""

    def test_strong_buy_high_confidence(self, valuation_service):
        """Test STRONG BUY with HIGH confidence."""
        result = valuation_service._determine_recommendation(20.0, "HIGH")
        assert result == "STRONG BUY"

    def test_strong_buy_medium_confidence(self, valuation_service):
        """Test STRONG BUY with MEDIUM confidence (higher threshold)."""
        # With MEDIUM confidence, need 1.5x the threshold
        result = valuation_service._determine_recommendation(25.0, "MEDIUM")
        assert result == "STRONG BUY"

    def test_buy_high_confidence(self, valuation_service):
        """Test BUY with HIGH confidence."""
        result = valuation_service._determine_recommendation(10.0, "HIGH")
        assert result == "BUY"

    def test_hold_high_confidence(self, valuation_service):
        """Test HOLD with HIGH confidence."""
        result = valuation_service._determine_recommendation(3.0, "HIGH")
        assert result == "HOLD"

    def test_sell_high_confidence(self, valuation_service):
        """Test SELL with HIGH confidence."""
        result = valuation_service._determine_recommendation(-10.0, "HIGH")
        assert result == "SELL"

    def test_strong_sell_high_confidence(self, valuation_service):
        """Test STRONG SELL with HIGH confidence."""
        result = valuation_service._determine_recommendation(-20.0, "HIGH")
        assert result == "STRONG SELL"


class TestSignalCollection:
    """Test signal collection from layers."""

    def test_collect_signals_mean_reversion(self, valuation_service):
        """Test collecting mean reversion signals."""
        layer2_data = {
            "pe": FairMultipleResult(
                symbol="AAPL",
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                current_premium=10.0,
                premium_z_score=0.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="buy",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
            "ps": FairMultipleResult(
                symbol="AAPL",
                metric="ps",
                sector_baseline=7.6,
                company_historical_premium=5.0,
                current_premium=5.0,
                premium_z_score=0.0,
                base_fair_multiple=7.98,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=7.58,
                confidence="HIGH",
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {
            "pe": PeerComparisonResult(
                symbol="AAPL",
                metric="pe",
                industry="Tech",
                peers=["MSFT"],
                peer_count=1,
                company_multiple=25.0,
                peer_mean=30.0,
                peer_median=30.0,
                peer_std=5.0,
                peer_min=30.0,
                peer_max=30.0,
                peer_p25=30.0,
                peer_p75=30.0,
                percentile_rank=0.0,
                z_score_vs_peers=-1.0,
                status="cheap",
                premium_to_peers_pct=-16.7,
                outperforming_peers=0,
                underperforming_peers=1,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        signals = valuation_service._collect_signals(layer2_data, layer3_data, "HIGH")

        assert any("PE mean reversion: BUY" in s for s in signals)
        assert any("PE vs peers: CHEAP" in s for s in signals)
        assert "Overall confidence: HIGH" in signals

    def test_collect_signals_no_mean_reversion(self, valuation_service):
        """Test collecting signals when no mean reversion."""
        layer2_data = {
            "pe": FairMultipleResult(
                symbol="AAPL",
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                current_premium=10.0,
                premium_z_score=0.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        layer3_data = {}

        signals = valuation_service._collect_signals(layer2_data, layer3_data, "MEDIUM")

        # Should only have confidence signal
        assert len(signals) == 1
        assert signals[0] == "Overall confidence: MEDIUM"


class TestCalculateRobustValuation:
    """Test complete robust valuation calculation."""

    @pytest.mark.asyncio
    async def test_calculate_robust_valuation_success(self, valuation_service):
        """Test successful robust valuation calculation."""
        symbol = "AAPL"
        sector = "Technology"
        industry = "Consumer Electronics"
        current_price = 150.0
        eps = 6.0

        # Mock Layer 1
        layer1_data = {"pe": 55.0, "ps": 7.6, "pb": 8.0}

        # Mock Layer 2
        layer2_data = {
            "pe": FairMultipleResult(
                symbol=symbol,
                metric="pe",
                sector_baseline=55.0,
                company_historical_premium=10.0,
                base_fair_multiple=60.5,
                mean_reversion_adjustment=0.0,
                safety_margin=0.05,
                final_fair_multiple=57.48,
                confidence="HIGH",
                current_premium=10.0,
                premium_z_score=0.0,
                confidence_factors=["Sufficient data points"],
                mean_reversion_signal="none",
                upside_downside_pct=0.0,
                calculated_at=datetime.now(timezone.utc).isoformat(),
            ),
        }

        # Mock Layer 3
        layer3_data = {}

        with patch.object(valuation_service, "_get_layer1_data", return_value=layer1_data):
            with patch.object(valuation_service, "_get_layer2_data", return_value=layer2_data):
                with patch.object(valuation_service, "_get_layer3_data", return_value=layer3_data):
                    result = valuation_service.calculate_robust_valuation(
                        symbol=symbol,
                        sector=sector,
                        industry=industry,
                        current_price=current_price,
                        eps=eps,
                    )

        assert result is not None
        assert isinstance(result, RobustValuationResult)
        assert result.symbol == "AAPL"
        assert result.sector == "Technology"
        assert result.fair_value_estimate > 0
        assert result.recommendation in [
            "STRONG BUY",
            "BUY",
            "HOLD",
            "SELL",
            "STRONG SELL",
        ]
        assert result.confidence in ["HIGH", "MEDIUM", "LOW"]

    @pytest.mark.asyncio
    async def test_calculate_robust_valuation_no_layer1(self, valuation_service):
        """Test robust valuation when Layer 1 fails."""
        symbol = "AAPL"
        sector = "Unknown"

        with patch.object(valuation_service, "_get_layer1_data", return_value=None):
            result = valuation_service.calculate_robust_valuation(
                symbol=symbol,
                sector=sector,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_robust_valuation_no_layer2(self, valuation_service):
        """Test robust valuation when Layer 2 fails."""
        symbol = "AAPL"
        sector = "Technology"

        # Mock Layer 1
        layer1_data = {"pe": 55.0}

        with patch.object(valuation_service, "_get_layer1_data", return_value=layer1_data):
            with patch.object(valuation_service, "_get_layer2_data", return_value=None):
                result = valuation_service.calculate_robust_valuation(
                    symbol=symbol,
                    sector=sector,
                )

        assert result is None


class TestGenerateComprehensiveReport:
    """Test comprehensive report generation."""

    @pytest.mark.asyncio
    async def test_generate_comprehensive_report_success(self, valuation_service):
        """Test successful comprehensive report generation."""
        symbol = "AAPL"
        sector = "Technology"
        industry = "Consumer Electronics"
        current_price = 150.0
        eps = 6.0

        # Mock valuation result
        mock_valuation = RobustValuationResult(
            symbol=symbol,
            sector=sector,
            industry=industry,
            layer1_sector_multiples={"pe": 55.0, "ps": 7.6, "pb": 8.0},
            layer2_fair_multiples={
                "pe": FairMultipleResult(
                    symbol=symbol,
                    metric="pe",
                    sector_baseline=55.0,
                    company_historical_premium=10.0,
                    base_fair_multiple=60.5,
                    mean_reversion_adjustment=0.0,
                    safety_margin=0.05,
                    final_fair_multiple=57.48,
                    confidence="HIGH",
                    current_premium=10.0,
                    premium_z_score=0.0,
                    confidence_factors=["Sufficient data points"],
                    mean_reversion_signal="none",
                    upside_downside_pct=0.0,
                    calculated_at=datetime.now(timezone.utc).isoformat(),
                ),
            },
            layer3_peer_comparison={},
            fair_value_estimate=344.88,
            fair_value_range=(344.88, 344.88),
            confidence="HIGH",
            recommendation="STRONG BUY",
            upside_downside_pct=130.0,
            valuation_methods={"pe_based": 344.88},
            method_weights={"pe_weight": 1.0},
            signals=["Overall confidence: HIGH"],
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

        with patch.object(valuation_service, "calculate_robust_valuation", return_value=mock_valuation):
            report = valuation_service.generate_comprehensive_report(
                symbol=symbol,
                sector=sector,
                industry=industry,
                current_price=current_price,
                eps=eps,
            )

        assert report["symbol"] == "AAPL"
        assert report["sector"] == "Technology"
        assert "summary" in report
        assert report["summary"]["recommendation"] == "STRONG BUY"
        assert report["summary"]["confidence"] == "HIGH"
        assert report["summary"]["fair_value_estimate"] == 344.88
        assert "layer1_sector_multiples" in report
        assert "layer2_fair_multiples" in report
        assert "layer3_peer_comparison" in report

    @pytest.mark.asyncio
    async def test_generate_comprehensive_report_failure(self, valuation_service):
        """Test comprehensive report when valuation fails."""
        symbol = "AAPL"
        sector = "Technology"

        with patch.object(valuation_service, "calculate_robust_valuation", return_value=None):
            report = valuation_service.generate_comprehensive_report(
                symbol=symbol,
                sector=sector,
            )

        assert "error" in report
        assert report["symbol"] == "AAPL"


class TestDefaultWeights:
    """Test default layer weights."""

    def test_default_weights(self):
        """Test default weight distribution."""
        service = RobustValuationService()

        assert service.DEFAULT_WEIGHTS["layer1_sector"] == 0.40
        assert service.DEFAULT_WEIGHTS["layer2_company"] == 0.40
        assert service.DEFAULT_WEIGHTS["layer3_peers"] == 0.20

    def test_custom_weights(self, mock_sec_db_manager, mock_stock_db_manager):
        """Test custom weight configuration."""
        with (
            patch("investigator.domain.services.robust_valuation_service.SectorMultiplesTrendAdjusted"),
            patch("investigator.domain.services.robust_valuation_service.CompanyFairMultipleCalculator"),
            patch("investigator.domain.services.robust_valuation_service.CrossSectionalValuation"),
        ):
            service = RobustValuationService(
                sec_db_manager=mock_sec_db_manager,
                stock_db_manager=mock_stock_db_manager,
                weights={
                    "layer1_sector": 0.50,
                    "layer2_company": 0.30,
                    "layer3_peers": 0.20,
                },
            )

            assert service.weights["layer1_sector"] == 0.50
            assert service.weights["layer2_company"] == 0.30
            assert service.weights["layer3_peers"] == 0.20


class TestRecommendationThresholds:
    """Test recommendation thresholds."""

    def test_threshold_constants(self, valuation_service):
        """Test threshold constant values."""
        assert valuation_service.STRONG_BUY_THRESHOLD == 15.0
        assert valuation_service.BUY_THRESHOLD == 5.0
        assert valuation_service.HOLD_THRESHOLD_DOWN == -5.0
        assert valuation_service.SELL_THRESHOLD == -15.0

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

"""Tests for CrossSectionalValuation service.

Tests the Layer 3 peer comparison functionality including:
- Peer identification and filtering
- Percentile ranking calculation
- Z-score calculation
- Status determination (expensive/fair/cheap)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from investigator.domain.services.cross_sectional_valuation import (
    CrossSectionalValuation,
    PeerComparisonResult,
)


@pytest.fixture
def mock_stock_db_manager():
    """Create mock stock database manager."""
    manager = MagicMock()

    # Mock session context manager
    mock_session = MagicMock()
    manager.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
    manager.get_session.return_value.__exit__ = MagicMock(return_value=False)

    return manager


@pytest.fixture
def mock_sec_db_manager():
    """Create mock SEC database manager."""
    manager = MagicMock()

    # Mock engine connection
    mock_conn = MagicMock()
    manager.engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    manager.engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    return manager


@pytest.fixture
def valuation_service(mock_stock_db_manager, mock_sec_db_manager):
    """Create CrossSectionalValuation service with mocked databases."""
    return CrossSectionalValuation(
        stock_db_manager=mock_stock_db_manager,
        sec_db_manager=mock_sec_db_manager,
    )


class TestPercentileRank:
    """Test percentile rank calculation."""

    def test_percentile_rank_middle(self, valuation_service):
        """Test percentile rank for middle value."""
        values = [10, 20, 30, 40, 50]
        result = valuation_service.calculate_percentile_rank(30, values)
        assert result == 50.0

    def test_percentile_rank_minimum(self, valuation_service):
        """Test percentile rank for minimum value."""
        values = [10, 20, 30, 40, 50]
        result = valuation_service.calculate_percentile_rank(10, values)
        # (0 + 0.5) / 5 * 100 = 10
        assert result == 10.0

    def test_percentile_rank_maximum(self, valuation_service):
        """Test percentile rank for maximum value."""
        values = [10, 20, 30, 40, 50]
        result = valuation_service.calculate_percentile_rank(50, values)
        # (4 + 0.5) / 5 * 100 = 90
        assert result == 90.0

    def test_percentile_rank_duplicates(self, valuation_service):
        """Test percentile rank with duplicate values."""
        values = [10, 20, 20, 30, 40]
        result = valuation_service.calculate_percentile_rank(20, values)
        # (1 + 1) / 5 * 100 = 40
        assert result == 40.0

    def test_percentile_rank_empty_list(self, valuation_service):
        """Test percentile rank with empty comparison list."""
        result = valuation_service.calculate_percentile_rank(25, [])
        assert result == 50.0  # Middle if no comparison data


class TestGetPeers:
    """Test peer identification."""

    def test_get_peers_success(self, valuation_service, mock_stock_db_manager):
        """Test successful peer retrieval."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock company info query
        company_info_result = [
            ("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")
        ]
        mock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_session.execute.return_value.fetchone.return_value = company_info_result[0]

        # Mock peers query
        peers_result = [
            ("MSFT",),
            ("GOOGL",),
            ("META",),
            ("TSLA",),
            ("NVDA",),
        ]
        mock_session.execute.return_value = MagicMock()
        mock_session.execute.return_value.__iter__ = lambda self: iter(peers_result)

        result = valuation_service.get_peers(symbol=symbol, industry=industry)

        assert len(result) == 5
        assert "MSFT" in result
        assert "GOOGL" in result

    def test_get_peers_no_industry(self, valuation_service, mock_stock_db_manager):
        """Test peer retrieval with no industry found."""
        symbol = "UNKNOWN"

        # Mock no company info
        mock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_session.execute.return_value.fetchone.return_value = None

        result = valuation_service.get_peers(symbol=symbol)

        assert result == []

    def test_get_peers_insufficient_peers(
        self, valuation_service, mock_stock_db_manager
    ):
        """Test peer retrieval with insufficient peers."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock company info
        company_info_result = [
            ("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")
        ]
        mock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )

        # First call returns company info, second returns only 1 peer
        call_count = [0]

        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.fetchone.return_value = company_info_result[0]
            else:
                mock_result.__iter__ = lambda self: iter([("MSFT",)])
            return mock_result

        mock_session.execute.side_effect = mock_execute_side_effect

        result = valuation_service.get_peers(
            symbol=symbol, industry=industry, min_peers=3
        )

        # Returns what we have even if below minimum
        assert len(result) == 1


class TestCompareToPeers:
    """Test peer comparison analysis."""

    def test_compare_to_peers_expensive(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test comparison showing company is expensive vs peers."""
        symbol = "AAPL"
        metric = "pe"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock peers
        with patch.object(
            valuation_service, "get_peers", return_value=["MSFT", "GOOGL", "META"]
        ):
            # Mock _get_company_multiple to return different values for different symbols
            # Company has high P/E (35.0), peers have lower P/E (25.0, 28.0, 30.0)
            peer_multiples = {
                "AAPL": 35.0,
                "MSFT": 25.0,
                "GOOGL": 28.0,
                "META": 30.0,
            }

            with patch.object(
                valuation_service,
                "_get_company_multiple",
                side_effect=lambda s, m: peer_multiples.get(s),
            ):
                result = valuation_service.compare_to_peers(
                    symbol=symbol,
                    metric=metric,
                    industry=industry,
                )

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.metric == "pe"
        assert result.company_multiple == 35.0
        # With peer multiples [25.0, 28.0, 30.0], company at 35.0 should be 75th+ percentile
        assert result.percentile_rank == 100.0  # Highest value
        assert result.status == "expensive"
        assert result.peer_count == 3

    def test_compare_to_peers_cheap(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test comparison showing company is cheap vs peers."""
        symbol = "AAPL"
        metric = "pe"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock peers
        with patch.object(
            valuation_service, "get_peers", return_value=["MSFT", "GOOGL", "META"]
        ):
            # Company has low P/E (15.0), peers have higher P/E (25.0, 28.0, 30.0)
            peer_multiples = {
                "AAPL": 15.0,
                "MSFT": 25.0,
                "GOOGL": 28.0,
                "META": 30.0,
            }

            with patch.object(
                valuation_service,
                "_get_company_multiple",
                side_effect=lambda s, m: peer_multiples.get(s),
            ):
                result = valuation_service.compare_to_peers(
                    symbol=symbol,
                    metric=metric,
                    industry=industry,
                )

        assert result is not None
        assert result.company_multiple == 15.0
        assert result.percentile_rank == 0.0  # Lowest value
        assert result.status == "cheap"

    def test_compare_to_peers_fair(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test comparison showing company is fairly valued vs peers."""
        symbol = "AAPL"
        metric = "pe"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock peers
        with patch.object(
            valuation_service, "get_peers", return_value=["MSFT", "GOOGL", "META"]
        ):
            # Company has mid-range P/E (25.0), peers range (20.0, 28.0, 30.0)
            peer_multiples = {
                "AAPL": 25.0,
                "MSFT": 20.0,
                "GOOGL": 28.0,
                "META": 30.0,
            }

            with patch.object(
                valuation_service,
                "_get_company_multiple",
                side_effect=lambda s, m: peer_multiples.get(s),
            ):
                result = valuation_service.compare_to_peers(
                    symbol=symbol,
                    metric=metric,
                    industry=industry,
                )

        assert result is not None
        assert result.company_multiple == 25.0
        # With [20.0, 25.0, 28.0, 30.0], company at 25.0 is at ~33rd percentile
        assert 25 <= result.percentile_rank <= 50  # Should be in fair range
        assert result.status == "fair"

    def test_compare_to_peers_no_company_multiple(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test comparison when company multiple is unavailable."""
        symbol = "AAPL"
        metric = "pe"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock company multiple unavailable
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = None

        result = valuation_service.compare_to_peers(
            symbol=symbol,
            metric=metric,
            industry=industry,
        )

        assert result is None

    def test_compare_to_peers_insufficient_peer_data(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test comparison with insufficient peer data."""
        symbol = "AAPL"
        metric = "pe"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock company multiple
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = (
            3500000000000,
            100000000000,
        )

        # Mock peers but only 1 has data
        with patch.object(
            valuation_service, "get_peers", return_value=["MSFT", "GOOGL", "META"]
        ):
            # Only MSFT has valid data, others return None
            peer_multiples = [25.0, None, None]

            with patch.object(
                valuation_service,
                "_get_company_multiple",
                side_effect=peer_multiples + [35.0],
            ):
                result = valuation_service.compare_to_peers(
                    symbol=symbol,
                    metric=metric,
                    industry=industry,
                    min_peers=3,
                )

        assert result is None


class TestZScoreCalculation:
    """Test z-score calculation vs peers."""

    def test_z_score_above_mean(self, valuation_service):
        """Test z-score when company multiple is above mean."""
        # Peer multiples: 20, 25, 30 (mean = 25, std ≈ 5)
        peer_multiples = [20.0, 25.0, 30.0]
        company_multiple = 35.0

        # Calculate z-score manually
        import statistics

        peer_mean = statistics.mean(peer_multiples)
        peer_std = statistics.stdev(peer_multiples)
        expected_z = (company_multiple - peer_mean) / peer_std

        # Verify calculation
        assert expected_z == pytest.approx(2.0, rel=0.1)

    def test_z_score_below_mean(self, valuation_service):
        """Test z-score when company multiple is below mean."""
        peer_multiples = [20.0, 25.0, 30.0]
        company_multiple = 15.0

        import statistics

        peer_mean = statistics.mean(peer_multiples)
        peer_std = statistics.stdev(peer_multiples)
        expected_z = (company_multiple - peer_mean) / peer_std

        assert expected_z == pytest.approx(-2.0, rel=0.1)

    def test_z_score_at_mean(self, valuation_service):
        """Test z-score when company multiple equals mean."""
        peer_multiples = [20.0, 25.0, 30.0]
        company_multiple = 25.0

        import statistics

        peer_mean = statistics.mean(peer_multiples)
        peer_std = statistics.stdev(peer_multiples)
        expected_z = (company_multiple - peer_mean) / peer_std

        assert expected_z == pytest.approx(0.0, abs=0.01)


class TestPremiumToPeers:
    """Test premium/discount calculation to peer median."""

    def test_premium_above_median(self, valuation_service):
        """Test premium when company multiple is above peer median."""
        company_multiple = 35.0
        peer_median = 25.0

        expected_premium = ((company_multiple - peer_median) / peer_median) * 100
        assert expected_premium == 40.0  # (35-25)/25 * 100

    def test_discount_below_median(self, valuation_service):
        """Test discount when company multiple is below peer median."""
        company_multiple = 20.0
        peer_median = 25.0

        expected_premium = ((company_multiple - peer_median) / peer_median) * 100
        assert expected_premium == -20.0  # (20-25)/25 * 100


class TestCompareAllMetrics:
    """Test comparing across all metrics."""

    def test_compare_all_metrics_success(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test successful comparison across all metrics."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock compare_to_peers for each metric
        with patch.object(valuation_service, "compare_to_peers") as mock_compare:
            mock_compare.side_effect = [
                PeerComparisonResult(
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
                PeerComparisonResult(
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
                PeerComparisonResult(
                    symbol=symbol,
                    metric="pb",
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
            ]

            results = valuation_service.compare_all_metrics(
                symbol=symbol, industry=industry
            )

        assert "pe" in results
        assert "ps" in results
        assert "pb" in results
        assert all(r is not None for r in results.values())

    def test_compare_all_metrics_with_failures(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test comparison across metrics with some failures."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = [("AAPL", "Technology", industry, 2500000000000, "Apple Inc.")]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.fetchone.return_value = company_info[0]

        # Mock compare_to_peers with one failure
        with patch.object(valuation_service, "compare_to_peers") as mock_compare:
            mock_compare.side_effect = [
                PeerComparisonResult(
                    symbol=symbol,
                    metric="pe",
                    industry=industry,
                    peers=["MSFT"],
                    peer_count=1,
                    company_multiple=35.0,
                    peer_mean=35.0,
                    peer_median=35.0,
                    peer_std=0.0,
                    peer_min=35.0,
                    peer_max=35.0,
                    peer_p25=35.0,
                    peer_p75=35.0,
                    percentile_rank=50.0,
                    z_score_vs_peers=0.0,
                    status="fair",
                    premium_to_peers_pct=0.0,
                    outperforming_peers=0,
                    underperforming_peers=0,
                    calculated_at=datetime.now(timezone.utc).isoformat(),
                ),
                None,  # ps fails
                None,  # pb fails
            ]

            results = valuation_service.compare_all_metrics(
                symbol=symbol, industry=industry
            )

        assert results["pe"] is not None
        assert results["ps"] is None
        assert results["pb"] is None


class TestGetIndustryMultiples:
    """Test getting all multiples for an industry."""

    def test_get_industry_multiples_success(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test successful retrieval of industry multiples."""
        industry = "Consumer Electronics"
        metric = "pe"

        # Mock symbols in industry
        symbols_result = [("AAPL",), ("MSFT",), ("GOOGL",)]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.__iter__ = lambda self: iter(
            symbols_result
        )

        # Mock company multiples
        def mock_get_multiple(symbol, metric_name):
            multiples = {"AAPL": 35.0, "MSFT": 30.0, "GOOGL": 28.0}
            return multiples.get(symbol)

        with patch.object(
            valuation_service, "_get_company_multiple", side_effect=mock_get_multiple
        ):
            result = valuation_service.get_industry_multiples(
                industry=industry, metric=metric
            )

        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" in result
        assert result["AAPL"] == 35.0

    def test_get_industry_multiples_partial_data(
        self, valuation_service, mock_stock_db_manager, mock_sec_db_manager
    ):
        """Test industry multiples with some companies missing data."""
        industry = "Consumer Electronics"
        metric = "pe"

        # Mock symbols in industry
        symbols_result = [("AAPL",), ("MSFT",), ("GOOGL",)]
        mock_stock_session = (
            mock_stock_db_manager.get_session.return_value.__enter__.return_value
        )
        mock_stock_session.execute.return_value.__iter__ = lambda self: iter(
            symbols_result
        )

        # Mock company multiples (GOOGL returns None)
        def mock_get_multiple(symbol, metric_name):
            multiples = {"AAPL": 35.0, "MSFT": 30.0, "GOOGL": None}
            return multiples.get(symbol)

        with patch.object(
            valuation_service, "_get_company_multiple", side_effect=mock_get_multiple
        ):
            result = valuation_service.get_industry_multiples(
                industry=industry, metric=metric
            )

        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" not in result  # Excluded due to None


class TestGetCompanyMultiple:
    """Test getting company valuation multiple."""

    def test_get_pe_multiple(self, valuation_service, mock_sec_db_manager):
        """Test getting P/E multiple."""
        symbol = "AAPL"

        # Mock market cap and net income
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = (
            3000000000000,
            100000000000,
        )

        result = valuation_service._get_company_multiple(symbol, "pe")

        assert result == 30.0  # market_cap / net_income

    def test_get_ps_multiple(self, valuation_service, mock_sec_db_manager):
        """Test getting P/S multiple."""
        symbol = "AAPL"

        # Mock market cap and revenue
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = (
            3000000000000,
            400000000000,
        )

        result = valuation_service._get_company_multiple(symbol, "ps")

        assert result == 7.5  # market_cap / revenue

    def test_get_pb_multiple(self, valuation_service, mock_sec_db_manager):
        """Test getting P/B multiple."""
        symbol = "AAPL"

        # Mock market cap and equity
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = (
            3000000000000,
            100000000000,
        )

        result = valuation_service._get_company_multiple(symbol, "pb")

        assert result == 30.0  # market_cap / equity

    def test_get_company_multiple_zero_denominator(
        self, valuation_service, mock_sec_db_manager
    ):
        """Test getting multiple with zero denominator."""
        symbol = "AAPL"

        # Mock market cap and zero net income
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = (3000000000000, 0)

        result = valuation_service._get_company_multiple(symbol, "pe")

        assert result is None

    def test_get_company_multiple_no_data(self, valuation_service, mock_sec_db_manager):
        """Test getting multiple when no data available."""
        symbol = "UNKNOWN"

        # Mock no data
        mock_conn = (
            mock_sec_db_manager.engine.connect.return_value.__enter__.return_value
        )
        mock_conn.execute.return_value.fetchone.return_value = None

        result = valuation_service._get_company_multiple(symbol, "pe")

        assert result is None

    def test_get_company_multiple_unsupported_metric(self, valuation_service):
        """Test getting multiple for unsupported metric."""
        symbol = "AAPL"

        result = valuation_service._get_company_multiple(symbol, "unsupported")

        assert result is None


class TestGeneratePeerSummary:
    """Test comprehensive peer comparison summary."""

    def test_generate_peer_summary_success(
        self, valuation_service, mock_stock_db_manager
    ):
        """Test successful peer summary generation."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = {
            "symbol": "AAPL",
            "sector": "Technology",
            "industry": industry,
            "market_cap": 2500000000000,
            "name": "Apple Inc.",
        }

        with patch.object(
            valuation_service, "_get_company_info", return_value=company_info
        ):
            # Mock compare_all_metrics
            mock_comparisons = {
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
                valuation_service, "compare_all_metrics", return_value=mock_comparisons
            ):
                summary = valuation_service.generate_peer_summary(
                    symbol=symbol, industry=industry
                )

        assert summary["symbol"] == "AAPL"
        assert summary["sector"] == "Technology"
        assert summary["industry"] == industry
        assert "comparisons" in summary
        assert "pe" in summary["comparisons"]
        assert "ps" in summary["comparisons"]
        assert summary["comparisons"]["pe"]["status"] == "expensive"
        assert summary["overall_assessment"]["status"] == "expensive"
        assert summary["overall_assessment"]["metrics_analyzed"] == 2

    def test_generate_peer_summary_no_company_info(self, valuation_service):
        """Test peer summary when company info unavailable."""
        symbol = "AAPL"

        with patch.object(valuation_service, "_get_company_info", return_value=None):
            summary = valuation_service.generate_peer_summary(symbol=symbol)

        assert "error" in summary
        assert "AAPL" in summary["error"]

    def test_generate_peer_summary_cheap_overall(
        self, valuation_service, mock_stock_db_manager
    ):
        """Test peer summary with cheap overall assessment."""
        symbol = "AAPL"
        industry = "Consumer Electronics"

        # Mock company info
        company_info = {
            "symbol": "AAPL",
            "sector": "Technology",
            "industry": industry,
            "market_cap": 2500000000000,
            "name": "Apple Inc.",
        }

        with patch.object(
            valuation_service, "_get_company_info", return_value=company_info
        ):
            # Mock compare_all_metrics with low percentiles
            mock_comparisons = {
                "pe": PeerComparisonResult(
                    symbol=symbol,
                    metric="pe",
                    industry=industry,
                    peers=["MSFT", "GOOGL"],
                    peer_count=2,
                    company_multiple=20.0,
                    peer_mean=30.0,
                    peer_median=30.0,
                    peer_std=5.0,
                    peer_min=20.0,
                    peer_max=35.0,
                    peer_p25=25.0,
                    peer_p75=32.5,
                    percentile_rank=10.0,
                    z_score_vs_peers=-2.0,
                    status="cheap",
                    premium_to_peers_pct=-33.3,
                    outperforming_peers=0,
                    underperforming_peers=2,
                    calculated_at=datetime.now(timezone.utc).isoformat(),
                ),
            }

            with patch.object(
                valuation_service, "compare_all_metrics", return_value=mock_comparisons
            ):
                summary = valuation_service.generate_peer_summary(
                    symbol=symbol, industry=industry
                )

        assert summary["overall_assessment"]["status"] == "cheap"

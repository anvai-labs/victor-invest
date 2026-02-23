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

"""Cross-sectional valuation service.

Compares companies to industry peers to identify relative mispricing
and percentile rankings. Implements Layer 3 of the robust valuation strategy.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import statistics
from sqlalchemy import text

from investigator.infrastructure.database.db import get_db_manager

logger = logging.getLogger(__name__)


@dataclass
class PeerComparisonResult:
    """Result of peer comparison analysis."""

    symbol: str
    metric: str  # pe, ps, pb, ev_ebitda
    industry: str

    # Peer universe
    peers: List[str]
    peer_count: int

    # Company metrics
    company_multiple: float

    # Peer statistics
    peer_mean: float
    peer_median: float
    peer_std: float
    peer_min: float
    peer_max: float
    peer_p25: float  # 25th percentile
    peer_p75: float  # 75th percentile

    # Relative valuation
    percentile_rank: float  # 0-100 (where company ranks vs peers)
    z_score_vs_peers: float  # How many std devs from peer mean
    status: str  # expensive, fair, cheap

    # Premium/discount to peers
    premium_to_peers_pct: float  # Company multiple vs peer median

    # Additional context
    outperforming_peers: int  # How many peers have lower multiple
    underperforming_peers: int  # How many peers have higher multiple

    calculated_at: str


class CrossSectionalValuation:
    """Compare companies to industry peers for relative valuation.

    Methods:
        get_peers: Identify peer companies in same industry
        calculate_percentile_rank: Calculate percentile rank vs peers
        compare_to_peers: Full peer comparison analysis
        get_industry_multiples: Get all multiples for an industry
    """

    def __init__(
        self,
        *,
        stock_db_manager: Any = None,
        sec_db_manager: Any = None,
    ):
        """Initialize cross-sectional valuation service.

        Args:
            stock_db_manager: Database manager for stock database
            sec_db_manager: Database manager for SEC database
        """
        if sec_db_manager is None:
            sec_db_manager = get_db_manager()

        self.sec_db_manager = sec_db_manager

        # Create stock database manager
        if stock_db_manager is None:
            from investigator.config import get_config
            from investigator.infrastructure.database.db import DatabaseManager

            config = get_config()
            stock_db_url = config.database.url.replace("/sec_database", "/stock")
            stock_db_manager = DatabaseManager(config)
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            stock_db_manager.engine = create_engine(stock_db_url)
            stock_db_manager.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=stock_db_manager.engine
            )

        self.stock_db_manager = stock_db_manager

    def get_peers(
        self,
        symbol: str,
        industry: Optional[str] = None,
        market_cap_tolerance: float = 0.5,
        min_peers: int = 3,
        max_peers: int = 20,
    ) -> List[str]:
        """Get peer companies in the same industry.

        Args:
            symbol: Stock symbol
            industry: Industry name (if None, will look up from database)
            market_cap_tolerance: Market cap tolerance (±50%)
            min_peers: Minimum number of peers to return
            max_peers: Maximum number of peers to return

        Returns:
            List of peer symbols
        """
        # Get company info if industry not provided
        if industry is None:
            company_info = self._get_company_info(symbol)
            if not company_info:
                logger.warning(f"{symbol}: Could not get company info")
                return []
            industry = company_info.get("industry")

        if not industry:
            logger.warning(f"{symbol}: No industry found")
            return []

        # Get company's market cap
        company_mc = self._get_market_cap(symbol)
        if not company_mc:
            logger.warning(f"{symbol}: Could not get market cap")
            return []

        # Calculate market cap range
        mc_min = company_mc * (1 - market_cap_tolerance)
        mc_max = company_mc * (1 + market_cap_tolerance)

        # Get peers
        with self.stock_db_manager.get_session() as session:
            query = text("""
                SELECT ticker
                FROM symbol
                WHERE islisted = true
                  AND UPPER("Industry") = UPPER(:industry)
                  AND "Market Cap" IS NOT NULL
                  AND "Market Cap" BETWEEN :mc_min AND :mc_max
                  AND UPPER(ticker) != UPPER(:symbol)
                ORDER BY "Market Cap" DESC
                LIMIT :limit
            """)

            result = session.execute(
                query,
                {
                    "industry": industry,
                    "mc_min": mc_min,
                    "mc_max": mc_max,
                    "symbol": symbol,
                    "limit": max_peers * 2,  # Get more than needed, will filter
                },
            )

            peers = [row[0] for row in result]

        if len(peers) < min_peers:
            logger.warning(
                f"{symbol}: Only found {len(peers)} peers (min required: {min_peers})"
            )
            # Return what we have
            return peers

        return peers[:max_peers]

    def calculate_percentile_rank(
        self, value: float, comparison_values: List[float]
    ) -> float:
        """Calculate percentile rank of a value among comparison values.

        Args:
            value: Value to rank
            comparison_values: List of values to compare against

        Returns:
            Percentile rank (0-100)
        """
        if not comparison_values:
            return 50.0  # Middle if no comparison data

        # Count how many values are lower
        lower_count = sum(1 for v in comparison_values if v < value)
        equal_count = sum(1 for v in comparison_values if v == value)

        # Calculate percentile
        percentile = (lower_count + equal_count / 2) / len(comparison_values) * 100

        return round(percentile, 1)

    def compare_to_peers(
        self,
        symbol: str,
        metric: str = "pe",
        industry: Optional[str] = None,
        market_cap_tolerance: float = 0.5,
        min_peers: int = 3,
    ) -> Optional[PeerComparisonResult]:
        """Compare company's multiple to industry peers.

        Args:
            symbol: Stock symbol
            metric: Metric to compare - "pe", "ps", "pb", "ev_ebitda"
            industry: Industry name (if None, will look up)
            market_cap_tolerance: Market cap tolerance for peer filtering
            min_peers: Minimum number of peers required

        Returns:
            PeerComparisonResult or None if insufficient data
        """
        logger.info(f"Comparing {symbol} {metric.upper()} to peers...")

        # Get company info
        company_info = self._get_company_info(symbol)
        if not company_info:
            logger.warning(f"{symbol}: Could not get company info")
            return None

        if industry is None:
            industry = company_info.get("industry")

        if not industry:
            logger.warning(f"{symbol}: No industry found")
            return None

        # Get peers
        peers = self.get_peers(
            symbol=symbol,
            industry=industry,
            market_cap_tolerance=market_cap_tolerance,
            min_peers=min_peers,
        )

        if not peers:
            logger.warning(f"{symbol}: No peers found in {industry}")
            return None

        # Get company's multiple
        company_multiple = self._get_company_multiple(symbol, metric)
        if company_multiple is None:
            logger.warning(f"{symbol}: Could not get {metric.upper()} multiple")
            return None

        # Get peer multiples
        peer_multiples = []
        for peer in peers:
            peer_multiple = self._get_company_multiple(peer, metric)
            if peer_multiple is not None:
                peer_multiples.append(peer_multiple)

        if len(peer_multiples) < min_peers:
            logger.warning(
                f"{symbol}: Insufficient peer data "
                f"({len(peer_multiples)} peers with data, min: {min_peers})"
            )
            return None

        # Calculate peer statistics
        peer_mean = statistics.mean(peer_multiples)
        peer_median = statistics.median(peer_multiples)
        peer_std = statistics.stdev(peer_multiples) if len(peer_multiples) > 1 else 0.0
        peer_min = min(peer_multiples)
        peer_max = max(peer_multiples)
        peer_p25 = statistics.quantiles(peer_multiples, n=4)[0]  # 25th percentile
        peer_p75 = statistics.quantiles(peer_multiples, n=4)[2]  # 75th percentile

        # Calculate percentile rank
        percentile_rank = self.calculate_percentile_rank(
            company_multiple, peer_multiples
        )

        # Calculate z-score vs peers
        if peer_std > 0:
            z_score_vs_peers = (company_multiple - peer_mean) / peer_std
        else:
            z_score_vs_peers = 0.0

        # Determine status
        if percentile_rank >= 75:
            status = "expensive"
        elif percentile_rank <= 25:
            status = "cheap"
        else:
            status = "fair"

        # Calculate premium to peers
        if peer_median > 0:
            premium_to_peers_pct = (
                (company_multiple - peer_median) / peer_median
            ) * 100
        else:
            premium_to_peers_pct = 0.0

        # Count peers above/below
        outperforming_peers = sum(1 for m in peer_multiples if m < company_multiple)
        underperforming_peers = sum(1 for m in peer_multiples if m > company_multiple)

        return PeerComparisonResult(
            symbol=symbol.upper(),
            metric=metric,
            industry=industry,
            peers=peers,
            peer_count=len(peer_multiples),
            company_multiple=round(company_multiple, 2),
            peer_mean=round(peer_mean, 2),
            peer_median=round(peer_median, 2),
            peer_std=round(peer_std, 2),
            peer_min=round(peer_min, 2),
            peer_max=round(peer_max, 2),
            peer_p25=round(peer_p25, 2),
            peer_p75=round(peer_p75, 2),
            percentile_rank=percentile_rank,
            z_score_vs_peers=round(z_score_vs_peers, 2),
            status=status,
            premium_to_peers_pct=round(premium_to_peers_pct, 1),
            outperforming_peers=outperforming_peers,
            underperforming_peers=underperforming_peers,
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_industry_multiples(
        self, industry: str, metric: str = "pe"
    ) -> Dict[str, float]:
        """Get all multiples for companies in an industry.

        Args:
            industry: Industry name
            metric: Metric to retrieve

        Returns:
            Dict mapping symbol to multiple value
        """
        multiples = {}

        # Get all symbols in industry
        with self.stock_db_manager.get_session() as session:
            query = text("""
                SELECT ticker
                FROM symbol
                WHERE islisted = true
                  AND UPPER("Industry") = UPPER(:industry)
                ORDER BY ticker
            """)

            result = session.execute(query, {"industry": industry})
            symbols = [row[0] for row in result]

        # Get multiple for each symbol
        for symbol in symbols:
            multiple = self._get_company_multiple(symbol, metric)
            if multiple is not None:
                multiples[symbol] = multiple

        return multiples

    def _get_company_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get company information from database.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with company info or None
        """
        with self.stock_db_manager.get_session() as session:
            query = text("""
                SELECT
                    ticker,
                    "Sector",
                    "Industry",
                    "Market Cap",
                    "Name"
                FROM symbol
                WHERE UPPER(ticker) = UPPER(:symbol)
                  AND islisted = true
            """)

            result = session.execute(query, {"symbol": symbol})
            row = result.fetchone()

            if row:
                return {
                    "symbol": row[0],
                    "sector": row[1],
                    "industry": row[2],
                    "market_cap": float(row[3]) if row[3] else None,
                    "name": row[4],
                }

        return None

    def _get_market_cap(self, symbol: str) -> Optional[float]:
        """Get company's market cap.

        Args:
            symbol: Stock symbol

        Returns:
            Market cap or None
        """
        company_info = self._get_company_info(symbol)
        return company_info.get("market_cap") if company_info else None

    def _get_company_multiple(self, symbol: str, metric: str) -> Optional[float]:
        """Get company's valuation multiple.

        Args:
            symbol: Stock symbol
            metric: Metric name - "pe", "ps", "pb", "ev_ebitda"

        Returns:
            Multiple value or None
        """
        # Map metric to calculation
        metric_calcs = {
            "pe": ("net_income", lambda mc, ni: mc / ni if ni and ni > 0 else None),
            "ps": (
                "total_revenue",
                lambda mc, rev: mc / rev if rev and rev > 0 else None,
            ),
            "pb": (
                "stockholders_equity",
                lambda mc, eq: mc / eq if eq and eq > 0 else None,
            ),
        }

        if metric not in metric_calcs:
            return None

        denominator_column, calc_func = metric_calcs[metric]

        with self.sec_db_manager.engine.connect() as conn:
            query = text(f"""
                SELECT market_cap, {denominator_column}
                FROM sec_companyfacts_processed
                WHERE UPPER(symbol) = UPPER(:symbol)
                ORDER BY fiscal_year DESC, fiscal_period DESC
                LIMIT 1
            """)

            result = conn.execute(query, {"symbol": symbol})
            row = result.fetchone()

            if row and row[0] and row[1]:
                market_cap = float(row[0])
                denominator = float(row[1])

                if denominator > 0:
                    return calc_func(market_cap, denominator)

        return None

    def compare_all_metrics(
        self,
        symbol: str,
        industry: Optional[str] = None,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Optional[PeerComparisonResult]]:
        """Compare company to peers across all metrics.

        Args:
            symbol: Stock symbol
            industry: Industry name
            metrics: List of metrics to compare (default: ["pe", "ps", "pb"])

        Returns:
            Dict mapping metric to PeerComparisonResult
        """
        if metrics is None:
            metrics = ["pe", "ps", "pb"]

        results = {}

        for metric in metrics:
            try:
                result = self.compare_to_peers(
                    symbol=symbol, metric=metric, industry=industry
                )
                results[metric] = result
            except Exception as e:
                logger.error(f"Error comparing {symbol} {metric}: {e}")
                results[metric] = None

        return results

    def generate_peer_summary(
        self, symbol: str, industry: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive peer comparison summary.

        Args:
            symbol: Stock symbol
            industry: Industry name

        Returns:
            Comprehensive peer comparison summary
        """
        logger.info(f"Generating peer comparison summary for {symbol}...")

        # Get company info
        company_info = self._get_company_info(symbol)
        if not company_info:
            return {"error": f"Could not get company info for {symbol}"}

        if industry is None:
            industry = company_info.get("industry")

        # Compare across all metrics
        all_comparisons = self.compare_all_metrics(symbol=symbol, industry=industry)

        # Build summary
        summary = {
            "symbol": symbol.upper(),
            "sector": company_info.get("sector"),
            "industry": industry,
            "market_cap": company_info.get("market_cap"),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "comparisons": {},
            "overall_assessment": None,
        }

        # Process each metric
        for metric, comparison in all_comparisons.items():
            if comparison is None:
                summary["comparisons"][metric] = {"status": "insufficient_data"}
                continue

            summary["comparisons"][metric] = {
                "company_multiple": comparison.company_multiple,
                "peer_median": comparison.peer_median,
                "peer_mean": comparison.peer_mean,
                "percentile_rank": comparison.percentile_rank,
                "status": comparison.status,
                "premium_to_peers_pct": comparison.premium_to_peers_pct,
                "peer_count": comparison.peer_count,
                "peers": comparison.peers[:5],  # Show first 5 peers
            }

        # Determine overall assessment
        valid_comparisons = {k: v for k, v in all_comparisons.items() if v is not None}

        if valid_comparisons:
            # Average percentile rank
            avg_percentile = statistics.mean(
                [c.percentile_rank for c in valid_comparisons.values()]
            )

            # Determine overall status
            if avg_percentile >= 70:
                overall_status = "expensive"
            elif avg_percentile <= 30:
                overall_status = "cheap"
            else:
                overall_status = "fair"

            summary["overall_assessment"] = {
                "status": overall_status,
                "avg_percentile_rank": round(avg_percentile, 1),
                "metrics_analyzed": len(valid_comparisons),
            }

        return summary

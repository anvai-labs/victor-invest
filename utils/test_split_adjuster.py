#!/usr/bin/env python3
"""
Test script for Stock Split Adjuster

Run this script to verify split-adjusted EPS calculations and generate
comprehensive analysis for all major tech symbols.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class StockSplit:
    """Represents a stock split event"""

    symbol: str
    split_date: date
    split_ratio: float
    description: Optional[str] = None


@dataclass
class EPSAnalysis:
    """Result of EPS analysis with split adjustment"""

    symbol: str
    year: int
    raw_eps: float
    split_adjusted_eps: float
    adjustment_factor: float
    splits_between: List[StockSplit]


class SplitAnalyzer:
    """Analyzes EPS with split adjustments"""

    def __init__(self):
        db_url = f"postgresql://{os.environ['SEC_DB_USER']}:{os.environ['SEC_DB_PASSWORD']}@{os.environ['SEC_DB_HOST']}:5432/{os.environ['SEC_DB_NAME']}"
        self.engine = create_engine(db_url)

    def get_splits(self, symbol: str) -> List[StockSplit]:
        """Get all splits for a symbol"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT split_date, split_ratio, description FROM stock_splits WHERE symbol = :symbol ORDER BY split_date"
                ),
                {"symbol": symbol},
            )
            return [
                StockSplit(
                    symbol=symbol,
                    split_date=row[0],
                    split_ratio=float(row[1]),
                    description=row[2],
                )
                for row in result
            ]

    def calculate_adjustment_factor(self, symbol: str, from_year: int, to_year: int) -> float:
        """Calculate cumulative split adjustment factor between two years"""
        splits = self.get_splits(symbol)
        factor = 1.0

        # Simple logic: apply all splits that occurred between the two fiscal years
        for split in splits:
            # Split affects adjustment if it's after the source year and before/end of target year
            if from_year < split.split_date.year <= to_year:
                factor *= split.split_ratio

        return factor

    def get_eps_data(self, symbol: str, start_year: int, end_year: int) -> Dict[int, float]:
        """Get raw EPS data for a symbol"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT fiscal_year,
                           ROUND((net_income / NULLIF(shares_outstanding, 0))::numeric, 2) as eps
                    FROM sec_companyfacts_processed
                    WHERE symbol = :symbol
                        AND fiscal_year BETWEEN :start_year AND :end_year
                        AND fiscal_period = 'FY'
                        AND shares_outstanding IS NOT NULL
                        AND shares_outstanding > 0
                    ORDER BY fiscal_year
                """),
                {"symbol": symbol, "start_year": start_year, "end_year": end_year},
            )
            return {row[0]: float(row[1]) for row in result}

    def analyze_symbol(self, symbol: str, start_year: int = 2016, end_year: int = 2024) -> Optional[Dict]:
        """Comprehensive analysis of a symbol with split adjustments"""
        eps_data = self.get_eps_data(symbol, start_year, end_year)

        if not eps_data:
            logger.warning(f"No EPS data found for {symbol}")
            return None

        splits = self.get_splits(symbol)

        # Calculate split-adjusted EPS for each year
        adjusted_data = {}
        for year, raw_eps in eps_data.items():
            factor = self.calculate_adjustment_factor(symbol, year, end_year)
            adjusted_eps = raw_eps / factor
            adjusted_data[year] = {
                "raw_eps": raw_eps,
                "split_adjusted_eps": adjusted_eps,
                "adjustment_factor": factor,
            }

        # Calculate growth rates
        if start_year in eps_data and end_year in eps_data:
            raw_growth = ((eps_data[end_year] / eps_data[start_year]) - 1) * 100
            adjusted_growth = (
                (adjusted_data[end_year]["split_adjusted_eps"] / adjusted_data[start_year]["split_adjusted_eps"]) - 1
            ) * 100
        else:
            raw_growth = None
            adjusted_growth = None

        return {
            "symbol": symbol,
            "splits": splits,
            "eps_data": adjusted_data,
            "raw_growth": raw_growth,
            "adjusted_growth": adjusted_growth,
            "start_year": start_year,
            "end_year": end_year,
        }

    def print_analysis(self, analysis: Dict):
        """Print formatted analysis"""
        symbol = analysis["symbol"]
        splits = analysis["splits"]
        eps_data = analysis["eps_data"]

        print(f"\n{'=' * 90}")
        print(f"STOCK SPLIT ANALYSIS: {symbol}")
        print(f"{'=' * 90}\n")

        # Split history
        if splits:
            print("Stock Split History:")
            print("-" * 90)
            for split in splits:
                print(f"  {split.split_date.strftime('%Y-%m-%d')}: {split.split_ratio}x split - {split.description}")
        else:
            print("Stock Split History: No splits recorded")
        print()

        # EPS table
        print(f"EPS Analysis ({analysis['start_year']}-{analysis['end_year']}):")
        print("-" * 90)
        print(f"{'Year':<6} {'Raw EPS':>12} {'Adj EPS':>12} {'Factor':>10} {'Status'}")
        print("-" * 90)

        for year in sorted(eps_data.keys()):
            data = eps_data[year]
            status = ""
            if data["adjustment_factor"] > 1.0:
                status = f"Split-adjusted ({data['adjustment_factor']:.1f}x)"

            print(
                f"{year:<6} ${data['raw_eps']:>10.2f} ${data['split_adjusted_eps']:>10.2f} {data['adjustment_factor']:>9.2f}x  {status}"
            )

        # Growth comparison
        print()
        print("Growth Rate Comparison:")
        print("-" * 90)
        if analysis["raw_growth"] is not None and analysis["adjusted_growth"] is not None:
            raw = analysis["raw_growth"]
            adj = analysis["adjusted_growth"]

            print(f"  Raw EPS Growth:        {raw:>8.1f}%")
            print(f"  Split-Adjusted Growth: {adj:>8.1f}%")

            diff = abs(adj - raw)
            if diff > 10:
                print("  ⚠️  WARNING: Raw growth is misleading due to splits!")
                print(f"     Difference: {diff:.1f} percentage points")
            elif diff > 1:
                print(f"  ℹ️  Note: Small difference due to splits ({diff:.1f} pp)")
        else:
            print("  Insufficient data for growth comparison")


def main():
    """Run comprehensive split adjustment analysis"""
    analyzer = SplitAnalyzer()

    # Major tech symbols to analyze
    symbols = ["GOOGL", "AAPL", "NVDA", "META", "AMZN", "MSFT", "TSLA"]

    # Summary table
    print(f"\n{'=' * 130}")
    print("SPLIT-ADJUSTED EPS GROWTH SUMMARY (2016-2024)")
    print(f"{'=' * 130}\n")

    summary_data = []

    for symbol in symbols:
        analysis = analyzer.analyze_symbol(symbol)
        if analysis:
            summary_data.append(analysis)
            analyzer.print_analysis(analysis)

    # Print summary comparison table
    print(f"\n{'=' * 130}")
    print("COMPARATIVE SUMMARY: All Symbols")
    print(f"{'=' * 130}\n")

    print(f"{'Symbol':<10} {'Splits':<20} {'Raw Growth':>15} {'Adj Growth':>15} {'Difference':>15} {'Status'}")
    print("-" * 130)

    for analysis in summary_data:
        symbol = analysis["symbol"]
        splits = analysis["splits"]
        raw = analysis["raw_growth"] or 0
        adj = analysis["adjusted_growth"] or 0
        diff = adj - raw

        splits_str = ", ".join(f"{s.split_date.year} ({s.split_ratio}x)" for s in splits) if splits else "None"

        if abs(diff) > 10:
            status = "⚠️ MISLEADING"
        elif abs(diff) > 1:
            status = "ℹ️ Minor"
        else:
            status = "✓ Accurate"

        print(f"{symbol:<10} {splits_str:<20} {raw:>13.1f}% {adj:>13.1f}% {diff:>13.1f}% {status}")

    print(f"\n{'=' * 130}")
    print("KEY FINDINGS:")
    print("-" * 130)
    print("1. Stock splits make raw EPS comparisons MISLEADING")
    print("2. Split-adjusted EPS shows TRUE earnings growth")
    print("3. Use split_adjusted_eps for all historical analysis")
    print("4. P/E ratios are less affected (price adjusts, but EPS needs adjustment)")
    print(f"{'=' * 130}\n")


if __name__ == "__main__":
    # Load environment
    try:
        with open("/Users/vijaysingh/.investigator/env") as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    key, value = line.strip().split("=", 1)
                    if key.startswith("export "):
                        key = key[7:]
                    os.environ[key] = value.strip('"').strip("'")
    except FileNotFoundError:
        pass

    main()

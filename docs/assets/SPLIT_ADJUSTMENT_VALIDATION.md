# Stock Split Adjustment Validation Framework

## Executive Summary

This document provides **practical methods to validate** that our stock split adjustments are working correctly. It includes test cases, SQL queries, and validation scripts.

---

## Part 1: The Validation Equation

### The Mathematical Check

```
P/E from Aggregates  MUST EQUAL  P/E from Per-Share

Market Cap / Net Income  ≈  Price / EPS

(Price × Shares) / (EPS × Shares)  =  Price / EPS
```

**If these don't match → Split adjustment issue**

---

## Part 2: SQL Validation Queries

### Query 1: Find Potential Split Adjustment Issues

```sql
-- Find companies where P/E(aggregate) ≠ P/E(per-share)
-- This indicates split adjustment problems

WITH company_metrics AS (
    SELECT
        p.symbol,
        p.fiscal_year,
        p.fiscal_period,
        p.market_cap,
        p.net_income,
        p.total_revenue,
        p.weighted_average_diluted_shares_outstanding as shares,
        p.net_income / NULLIF(p.weighted_average_diluted_shares_outstanding, 0) as computed_eps,
        p.market_cap / p.total_revenue as ps_aggregate,
        CASE WHEN p.net_income > 0
             THEN p.market_cap / p.net_income
             ELSE NULL
        END as pe_aggregate
    FROM sec_companyfacts_processed p
    WHERE p.fiscal_period = 'FY'
      AND p.fiscal_year >= 2022
      AND p.market_cap > 0
      AND p.net_income > 0
      AND p.weighted_average_diluted_shares_outstanding > 0
),
per_share_multiples AS (
    SELECT
        symbol,
        fiscal_year,
        fiscal_period,
        -- These would come from price data (tickerdata)
        -- For this query, we'll use computed values
        computed_eps,
        market_cap,
        net_income
    FROM company_metrics
)
SELECT
    symbol,
    fiscal_year,
    pe_aggregate,
    computed_eps,
    market_cap / net_income as pe_recheck,
    -- If per-share EPS from SEC is used, compare:
    -- price / eps (from market data)
    -- For now, flag where our own computation is inconsistent
    CASE
        WHEN pe_aggregate IS NULL THEN 'Missing data'
        WHEN pe_aggregate > 500 THEN 'Implausibly high P/E'
        WHEN pe_aggregate < 0 THEN 'Negative P/E'
        ELSE 'OK'
    END as validation_status
FROM company_metrics
WHERE pe_aggregate IS NOT NULL
ORDER BY ABS(pe_aggregate - 50) DESC  -- Most extreme first
LIMIT 50;
```

### Query 2: Detect Unexplained Share Count Changes

```sql
-- Find sudden share count changes that might be unadjusted splits

WITH share_changes AS (
    SELECT
        symbol,
        fiscal_year,
        fiscal_period,
        period_end_date,
        weighted_average_diluted_shares_outstanding as shares,
        LEAD(weighted_average_diluted_shares_outstanding) OVER (
            PARTITION BY symbol
            ORDER BY period_end_date
        ) as next_period_shares,
        LEAD(period_end_date) OVER (
            PARTITION BY symbol
            ORDER BY period_end_date
        ) as next_period_date
    FROM sec_companyfacts_processed
    WHERE weighted_average_diluted_shares_outstanding > 0
      AND period_end_date IS NOT NULL
),
share_change_analysis AS (
    SELECT
        symbol,
        fiscal_year,
        fiscal_period,
        period_end_date,
        shares,
        next_period_shares,
        next_period_date,
        CASE WHEN next_period_shares IS NOT NULL
             THEN (next_period_shares - shares) / NULLIF(shares, 0)
             ELSE NULL
        END as share_change_pct
    FROM share_changes
)
SELECT
    symbol,
    fiscal_year,
    fiscal_period,
    period_end_date,
    shares,
    next_period_shares,
    ROUND(share_change_pct * 100, 1) as share_change_pct,
    CASE
        WHEN ABS(share_change_pct) >= 0.5 THEN '⚠️ Potential split or large offering'
        WHEN ABS(share_change_pct) >= 0.1 THEN '⚠️ Moderate change'
        ELSE '✓ Normal'
    END as flag
FROM share_change_analysis
WHERE share_change_pct IS NOT NULL
  AND ABS(share_change_pct) > 0.05  -- More than 5% change
ORDER BY ABS(share_change_pct) DESC;
```

### Query 3: Validate Split-Adjusted Market Cap

```sql
-- For companies with known splits, validate market cap calculation

WITH split_companies AS (
    -- Companies with recorded splits
    SELECT DISTINCT
        symbol,
        split_ratio,
        split_date
    FROM stock_splits
    WHERE split_date >= '2020-01-01'
),
company_before_split AS (
    SELECT
        p.symbol,
        p.market_cap,
        p.weighted_average_diluted_shares_outstanding as shares,
        p.period_end_date
    FROM sec_companyfacts_processed p
    INNER JOIN split_companies s ON p.symbol = s.symbol
    WHERE p.period_end_date <= s.split_date
      AND p.fiscal_period = 'FY'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY p.symbol
        ORDER BY ABS(p.period_end_date - s.split_date) ASC
    ) = 1
),
company_after_split AS (
    SELECT
        p.symbol,
        p.market_cap,
        p.weighted_average_diluted_shares_outstanding as shares,
        p.period_end_date
    FROM sec_companyfacts_processed p
    INNER JOIN split_companies s ON p.symbol = s.symbol
    WHERE p.period_end_date > s.split_date
      AND p.fiscal_period = 'FY'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY p.symbol
        ORDER BY ABS(p.period_end_date - s.split_date) ASC
    ) = 1
)
SELECT
    b.symbol,
    s.split_ratio,
    b.market_cap as market_cap_before,
    a.market_cap as market_cap_after,
    b.shares as shares_before,
    a.shares as shares_after,
    ROUND((a.shares / b.shares), 2) as actual_share_ratio,
    ROUND((b.market_cap / a.market_cap), 2) as market_cap_ratio,
    CASE
        -- After split, shares should increase by split ratio
        WHEN ABS((a.shares / b.shares) - s.split_ratio) > 0.1
        THEN '⚠️ Share ratio mismatch'
        -- Market cap should be relatively stable
        WHEN ABS(b.market_cap - a.market_cap) / b.market_cap > 0.3
        THEN '⚠️ Market cap changed significantly'
        ELSE '✓ Valid'
    END as validation_status
FROM company_before_split b
INNER JOIN split_companies s ON b.symbol = s.symbol
INNER JOIN company_after_split a ON a.symbol = s.symbol
ORDER BY b.symbol;
```

---

## Part 3: Python Validation Script

### Complete Validation Suite

```python
#!/usr/bin/env python3
"""
Stock Split Adjustment Validation Script

Validates that our split adjustment logic is working correctly by:
1. Checking P/E consistency (aggregates vs per-share)
2. Detecting unexplained share count changes
3. Validating against known split events
4. Testing market cap calculations

Usage:
    python scripts/validate_split_adjustments.py --symbol AAPL
    python scripts/validate_split_adjustments.py --all
"""

import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from investigator.infrastructure.database.db import get_database_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SplitAdjustmentValidator:
    """Validates stock split adjustments in our data."""

    def __init__(self, engine: Optional[Engine] = None):
        self.engine = engine or get_database_engine()

    def validate_pe_consistency(
        self,
        symbol: str,
        tolerance: float = 0.10,
    ) -> Dict[str, any]:
        """
        Validate P/E calculated from aggregates matches per-share calculation.

        P/E = Market Cap / Net Income
        P/E = Price / EPS

        These should be approximately equal (within tolerance).

        Returns:
            Dict with validation results
        """
        query = """
        SELECT
            p.symbol,
            p.fiscal_year,
            p.fiscal_period,
            p.market_cap,
            p.net_income,
            p.total_revenue,
            p.weighted_average_diluted_shares_outstanding as shares,
            t.close as price
        FROM sec_companyfacts_processed p
        LEFT JOIN tickerdata_daily t ON (
            UPPER(p.symbol) = UPPER(t.symbol)
            AND t.date >= p.period_end_date - INTERVAL '7 days'
            AND t.date <= p.period_end_date + INTERVAL '7 days'
        )
        WHERE UPPER(p.symbol) = UPPER(:symbol)
          AND p.fiscal_year >= 2022
          AND p.market_cap > 0
          AND p.weighted_average_diluted_shares_outstanding > 0
        ORDER BY p.period_end_date DESC
        LIMIT 20
        """

        with self.engine.connect() as conn:
            df = pd.read_sql(
                sa.text(query),
                conn,
                params={"symbol": symbol}
            )

        if df.empty:
            return {
                "symbol": symbol,
                "status": "no_data",
                "issues": [],
            }

        results = []
        for _, row in df.iterrows():
            # Calculate P/E from aggregates (split-immune)
            pe_aggregate = row["market_cap"] / row["net_income"] if row["net_income"] > 0 else None

            # Calculate P/E from per-share (split-sensitive)
            if row["price"] and row["shares"] and row["shares"] > 0:
                computed_eps = row["net_income"] / row["shares"]
                pe_per_share = row["price"] / computed_eps if computed_eps > 0 else None
            else:
                pe_per_share = None

            # Validate
            issue = None
            if pe_aggregate and pe_per_share:
                diff_pct = abs(pe_aggregate - pe_per_share) / pe_aggregate
                if diff_pct > tolerance:
                    issue = {
                        "fiscal_year": row["fiscal_year"],
                        "fiscal_period": row["fiscal_period"],
                        "pe_aggregate": pe_aggregate,
                        "pe_per_share": pe_per_share,
                        "diff_pct": diff_pct * 100,
                        "issue": f"P/E mismatch: {diff_pct*100:.1f}% difference"
                    }

            results.append({
                "fiscal_year": row["fiscal_year"],
                "fiscal_period": row["fiscal_period"],
                "market_cap": row["market_cap"],
                "net_income": row["net_income"],
                "shares": row["shares"],
                "price": row["price"],
                "pe_aggregate": pe_aggregate,
                "pe_per_share": pe_per_share,
                "issue": issue,
            })

        issues = [r["issue"] for r in results if r["issue"] is not None]

        return {
            "symbol": symbol,
            "status": "pass" if len(issues) == 0 else "fail",
            "total_periods": len(results),
            "issues_found": len(issues),
            "issues": issues,
        }

    def detect_share_count_anomalies(
        self,
        symbol: str,
        threshold: float = 0.20,
    ) -> Dict[str, any]:
        """
        Detect unexplained share count changes that might be unadjusted splits.

        Args:
            symbol: Stock symbol
            threshold: Minimum change percentage to flag (default 20%)

        Returns:
            Dict with anomaly detection results
        """
        query = """
        SELECT
            symbol,
            fiscal_year,
            fiscal_period,
            period_end_date,
            weighted_average_diluted_shares_outstanding as shares,
            market_cap
        FROM sec_companyfacts_processed
        WHERE UPPER(symbol) = UPPER(:symbol)
          AND weighted_average_diluted_shares_outstanding > 0
          AND period_end_date IS NOT NULL
        ORDER BY period_end_date DESC
        LIMIT 20
        """

        with self.engine.connect() as conn:
            df = pd.read_sql(
                sa.text(query),
                conn,
                params={"symbol": symbol}
            )

        if len(df) < 2:
            return {"symbol": symbol, "status": "insufficient_data"}

        df = df.sort_values("period_end_date")
        anomalies = []

        for i in range(len(df) - 1):
            current = df.iloc[i]
            next_row = df.iloc[i + 1]

            share_change = (next_row["shares"] - current["shares"]) / current["shares"]

            if abs(share_change) > threshold:
                # Check if there's a corresponding split event
                split_query = """
                SELECT split_ratio, split_date
                FROM stock_splits
                WHERE UPPER(symbol) = UPPER(:symbol)
                  AND split_date BETWEEN :start_date AND :end_date
                """

                with self.engine.connect() as conn:
                    split_df = pd.read_sql(
                        sa.text(split_query),
                        conn,
                        params={
                            "symbol": symbol,
                            "start_date": current["period_end_date"],
                            "end_date": next_row["period_end_date"],
                        }
                    )

                if split_df.empty:
                    # Unexplained change - potential issue
                    anomalies.append({
                        "from_date": current["period_end_date"],
                        "to_date": next_row["period_end_date"],
                        "shares_before": current["shares"],
                        "shares_after": next_row["shares"],
                        "change_pct": share_change * 100,
                        "issue": f"Unexplained {share_change*100:.1f}% share change",
                    })

        return {
            "symbol": symbol,
            "status": "pass" if len(anomalies) == 0 else "warning",
            "anomalies_found": len(anomalies),
            "anomalies": anomalies,
        }

    def validate_known_splits(
        self,
        symbol: str,
    ) -> Dict[str, any]:
        """
        Validate that our data correctly handles known split events.

        For companies with recorded splits, verify:
        1. Share count changes by approximately the split ratio
        2. Market cap remains relatively stable
        3. P/E remains consistent before/after

        Returns:
            Dict with split validation results
        """
        # Get known splits for this symbol
        split_query = """
        SELECT split_ratio, split_date
        FROM stock_splits
        WHERE UPPER(symbol) = UPPER(:symbol)
          AND split_date >= '2020-01-01'
        ORDER BY split_date DESC
        """

        with self.engine.connect() as conn:
            splits_df = pd.read_sql(
                sa.text(split_query),
                conn,
                params={"symbol": symbol}
            )

        if splits_df.empty:
            return {"symbol": symbol, "status": "no_splits_recorded"}

        results = []
        for _, split in splits_df.iterrows():
            split_date = split["split_date"]
            split_ratio = split["split_ratio"]

            # Get data before and after split
            data_query = """
            WITH ranked_data AS (
                SELECT
                    fiscal_year,
                    fiscal_period,
                    period_end_date,
                    market_cap,
                    net_income,
                    weighted_average_diluted_shares_outstanding as shares,
                    CASE WHEN period_end_date < :split_date
                         THEN 'before'
                         ELSE 'after'
                    END as timing,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            CASE WHEN period_end_date < :split_date THEN 'before' ELSE 'after' END
                        ORDER BY ABS(period_end_date - :split_date) ASC
                    ) as rn
                FROM sec_companyfacts_processed
                WHERE UPPER(symbol) = UPPER(:symbol)
                  AND period_end_date BETWEEN :split_date - INTERVAL '2 years'
                  AND :split_date + INTERVAL '1 year'
                  AND weighted_average_diluted_shares_outstanding > 0
            )
            SELECT *
            FROM ranked_data
            WHERE rn = 1
            """

            with self.engine.connect() as conn:
                data_df = pd.read_sql(
                    sa.text(data_query),
                    conn,
                    params={"symbol": symbol, "split_date": split_date}
                )

            if len(data_df) < 2:
                continue

            before = data_df[data_df["timing"] == "before"].iloc[0]
            after = data_df[data_df["timing"] == "after"].iloc[0]

            # Validate
            share_ratio = after["shares"] / before["shares"]
            expected_ratio = split_ratio

            pe_before = before["market_cap"] / before["net_income"] if before["net_income"] > 0 else None
            pe_after = after["market_cap"] / after["net_income"] if after["net_income"] > 0 else None

            mcap_change = abs(after["market_cap"] - before["market_cap"]) / before["market_cap"]

            issues = []
            if abs(share_ratio - expected_ratio) > 0.1:
                issues.append(f"Share ratio mismatch: expected {expected_ratio}, got {share_ratio:.2f}")

            if mcap_change > 0.20:
                issues.append(f"Large market cap change: {mcap_change*100:.1f}%")

            if pe_before and pe_after:
                pe_change = abs(pe_after - pe_before) / pe_before
                if pe_change > 0.10:
                    issues.append(f"P/E changed: {pe_before:.1f}x → {pe_after:.1f}x ({pe_change*100:.1f}%)")

            results.append({
                "split_date": str(split_date),
                "split_ratio": split_ratio,
                "shares_before": before["shares"],
                "shares_after": after["shares"],
                "actual_share_ratio": share_ratio,
                "market_cap_before": before["market_cap"],
                "market_cap_after": after["market_cap"],
                "pe_before": pe_before,
                "pe_after": pe_after,
                "issues": issues,
                "status": "pass" if len(issues) == 0 else "fail",
            })

        return {
            "symbol": symbol,
            "splits_tested": len(results),
            "results": results,
            "overall_status": "pass" if all(r["status"] == "pass" for r in results) else "fail",
        }

    def run_full_validation(
        self,
        symbol: str,
    ) -> Dict[str, any]:
        """Run all validation checks for a symbol."""
        logger.info(f"Running full validation for {symbol}")

        results = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "validations": {},
        }

        # 1. P/E Consistency Check
        logger.info("  Checking P/E consistency...")
        results["validations"]["pe_consistency"] = self.validate_pe_consistency(symbol)

        # 2. Share Count Anomalies
        logger.info("  Checking for share count anomalies...")
        results["validations"]["share_anomalies"] = self.detect_share_count_anomalies(symbol)

        # 3. Known Splits Validation
        logger.info("  Validating known split events...")
        results["validations"]["known_splits"] = self.validate_known_splits(symbol)

        # Overall status
        all_pass = all(
            v.get("status") == "pass"
            for v in results["validations"].values()
            if isinstance(v, dict) and "status" in v
        )

        results["overall_status"] = "pass" if all_pass else "fail"

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate stock split adjustments"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        help="Stock symbol to validate"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all symbols (slow!)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        help="Multiple symbols to validate"
    )

    args = parser.parse_args()

    validator = SplitAdjustmentValidator()

    if args.symbol:
        results = validator.run_full_validation(args.symbol)
        print(f"\n{'='*60}")
        print(f"Validation Results for {args.symbol}")
        print(f"{'='*60}")
        print(f"Overall Status: {results['overall_status'].upper()}")
        print(f"\nDetailed Results:")

        for check_name, check_result in results["validations"].items():
            status = check_result.get("status", "unknown")
            print(f"\n  {check_name}: {status.upper()}")

            if check_result.get("issues"):
                print(f"    Issues found: {len(check_result['issues'])}")
                for issue in check_result["issues"][:3]:  # Show first 3
                    if isinstance(issue, dict):
                        print(f"      - {issue.get('issue', str(issue))}")
                    else:
                        print(f"      - {issue}")

    elif args.symbols:
        for symbol in args.symbols:
            results = validator.run_full_validation(symbol)
            print(f"{symbol}: {results['overall_status']}")
            if results["overall_status"] == "fail":
                for check_name, check_result in results["validations"].items():
                    if check_result.get("status") == "fail":
                        print(f"  ❌ {check_name}: {check_result.get('issues_found', 'issues')} issues")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

---

## Part 4: Known Split Test Cases

### Reference Splits to Validate Against

| Symbol | Date | Split Ratio | Validation Check |
|--------|------|-------------|------------------|
| **AAPL** | Aug 31, 2020 | 4-for-1 | Shares ×4, Price ÷4, P/E unchanged |
| **NVDA** | Jul 20, 2021 | 4-for-1 | Shares ×4, Price ÷4, P/E unchanged |
| **NVDA** | May 27, 2000 | 3-for-2 | Shares ×1.5, Price ÷1.5 |
| **TSLA** | Aug 31, 2020 | 5-for-1 | Shares ×5, Price ÷5 |
| **AMZN** | Jun 6, 2022 | 20-for-1 | Shares ×20, Price ÷20 |
| **GOOGL** | Jul 18, 2022 | 20-for-1 | Shares ×20, Price ÷20 |
| **SHOP** | Jun 28, 2022 | 10-for-1 | Shares ×10, Price ÷10 |

### Test Case: AAPL 4-for-1 Split (Aug 2020)

```python
# Expected validation results:

Before Split (Q3 2020):
├─ Shares: ~4.4B
├─ Market Cap: ~$2.0T
├─ Net Income: ~$11B
└─ P/E: ~180x

After Split (Q4 2020):
├─ Shares: ~17.6B (×4)
├─ Market Cap: ~$2.2T (similar)
├─ Net Income: ~$12B
└─ P/E: ~180x (should match!)

Validation:
✓ P/E before ≈ P/E after (within 10%)
✓ Shares after ≈ Shares before × 4
✓ Market cap stable (<30% change)
```

---

## Part 5: Manual Validation Steps

### Step 1: Visual Chart Validation

```python
# Create a chart showing P/E before/after known splits
# P/E should be continuous across split events

import matplotlib.pyplot as plt
import pandas as pd

def plot_pe_with_split_markers(symbol: str):
    """Plot P/E over time with split markers."""

    # Get P/E data
    query = """
    SELECT
        p.period_end_date,
        p.market_cap / NULLIF(p.net_income, 0) as pe_ratio,
        p.fiscal_year
    FROM sec_companyfacts_processed p
    WHERE UPPER(p.symbol) = UPPER(:symbol)
      AND p.net_income > 0
      AND p.market_cap > 0
    ORDER BY p.period_end_date
    """

    # Get split dates
    split_query = """
    SELECT split_date, split_ratio
    FROM stock_splits
    WHERE UPPER(symbol) = UPPER(:symbol)
    ORDER BY split_date
    """

    # Plot
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot P/E line
    ax.plot(df["period_end_date"], df["pe_ratio"], marker='o', label='P/E')

    # Add vertical lines for splits
    for _, split in splits_df.iterrows():
        ax.axvline(split["split_date"], color='red', linestyle='--', alpha=0.5)
        ax.text(
            split["split_date"],
            ax.get_ylim()[1],
            f"{split['split_ratio']} split",
            rotation=90,
            verticalalignment='top'
        )

    ax.set_title(f"{symbol} P/E Ratio with Stock Split Markers")
    ax.set_ylabel("P/E Ratio")
    ax.legend()
    plt.show()

    # VALIDATION: P/E line should be continuous (no jumps) at split markers
```

### Step 2: Manual Calculation Spot-Check

For a random company and period:

```
1. Get SEC data:
   - Market Cap: $100B
   - Net Income: $5B
   - Shares Outstanding: 1B

2. Get market data:
   - Current Price: $100

3. Calculate:
   P/E (aggregate) = $100B / $5B = 20x
   P/E (per-share) = $100 / ($5B / 1B) = $100 / $5 = 20x

4. VALIDATE: 20x ≈ 20x ✓
```

### Step 3: Historical Consistency Check

```
Pick a company with a known split (e.g., AAPL 2020):

Check 3 periods before split:
  Q1 2020: P/E = X
  Q2 2020: P/E = Y
  Q3 2020: P/E = Z

Check 3 periods after split:
  Q4 2020: P/E = A (should ≈ Z, X, Y trend)
  Q1 2021: P/E = B (should follow trend)
  Q2 2021: P/E = C (should follow trend)

VALIDATION: No artificial jump at split date
```

---

## Part 6: Automated Validation Pipeline

### GitHub Actions / CI Integration

```yaml
# .github/workflows/validate-split-adjustments.yml

name: Validate Stock Split Adjustments

on:
  schedule:
    - cron: '0 0 * * 1'  # Weekly
  workflow_dispatch:

jobs:
  validate:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pandas sqlalchemy psycopg2-binary

      - name: Run validation script
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          python scripts/validate_split_adjustments.py \
            --symbols AAPL NVDA TSLA AMZN GOOGL

      - name: Report results
        if: failure()
        run: |
          echo "Split adjustment validation failed!"
          echo "Check logs for details."
```

---

## Part 7: Common Issues and Fixes

### Issue 1: P/E Mismatch > 10%

**Symptoms:**
```
P/E (aggregate) = 25x
P/E (per-share) = 50x
```

**Possible Causes:**
1. EPS not split-adjusted, price is split-adjusted
2. Shares outstanding from wrong source
3. Legacy data mixed with split-adjusted data

**Fix:**
```python
# Check EPS source
# SEC data: split-adjusted ✓
# Legacy data: may need adjustment

# Validate:
assert market_cap ≈ price × shares
assert net_income ≈ eps × shares
```

### Issue 2: Sudden Share Count Jump

**Symptoms:**
```
Q1 2023: 100M shares
Q2 2023: 200M shares
No split recorded in stock_splits table
```

**Possible Causes:**
1. Unrecorded split
2. Large equity offering
3. Data error

**Fix:**
```sql
-- Check for stock offerings in the period
SELECT * FROM SEC_offerings
WHERE symbol = 'XXX'
  AND offering_date BETWEEN '2023-03-31' AND '2023-06-30';

-- If no offering, flag as potential unrecorded split
```

### Issue 3: Reverse Split Not Flagged

**Symptoms:**
```
Shares: 100M → 10M (90% decrease)
Price: $1 → $10 (10x increase)
No special handling
```

**Fix:**
```python
# Detect reverse splits
if share_change < -0.5:  # More than 50% decrease
    flag_as_reverse_split()
    apply_distress_adjustment()
```

---

## Part 8: Validation Checklist

### Pre-Production Checklist

- [ ] Run P/E consistency check on top 100 stocks
- [ ] Validate against all known splits in `stock_splits` table
- [ ] Confirm no anomalies in share count changes
- [ ] Manual spot-check on 10 random companies
- [ ] Visual inspection of P/E charts at split dates
- [ ] Test reverse split handling separately
- [ ] Confirm aggregate calculations used in production

### Ongoing Monitoring

- [ ] Weekly automated validation on subset of symbols
- [ ] Flag new splits as they occur
- [ ] Monitor P/E mismatch rate (should be <5%)
- [ ] Review flagged anomalies monthly
- [ ] Update known splits table regularly

---

## Part 9: Quick Validation Commands

```bash
# Validate a single symbol
python scripts/validate_split_adjustments.py --symbol AAPL

# Validate multiple symbols
python scripts/validate_split_adjustments.py --symbols AAPL NVDA TSLA

# Run all validations (slow!)
python scripts/validate_split_adjustments.py --all

# Check SQL for specific company
psql -d sec_database -c "
SELECT
    symbol,
    fiscal_year,
    market_cap / NULLIF(net_income, 0) as pe_ratio,
    market_cap,
    net_income,
    weighted_average_diluted_shares_outstanding as shares
FROM sec_companyfacts_processed
WHERE UPPER(symbol) = 'AAPL'
  AND net_income > 0
ORDER BY period_end_date DESC
LIMIT 10;
"
```

---

## Summary

**Key Validation Principle:**
```
P/E (aggregates) MUST EQUAL P/E (per-share)
Market Cap / Net Income ≈ Price / EPS

If they don't match → Split adjustment issue
```

**Three Validation Levels:**
1. **Mathematical**: P/E consistency check
2. **Historical**: Known split validation
3. **Anomaly Detection**: Unexplained share changes

**Automate This:**
- Run weekly on top stocks
- Alert on failures
- Investigate and fix data quality issues

**Documentation Version:** 1.0
**Last Updated:** 2026-02-21

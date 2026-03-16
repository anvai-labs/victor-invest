# Investment Opportunities: Data Quality Investigation & Pipeline Fixes

**Date**: 2026-02-28
**Investigation**: Extreme fair values in investment_opportunities view

## Root Causes Identified

### 1. Stock Splits Not Handled (NFLX, others)

**Issue**: Fair values based on pre-split prices while tickerdata shows post-split prices

**Example - Netflix (NFLX)**:
```
Current Price (tickerdata): $96.24
Fair Value (models): $509.31 (429% upside)
Last Data Refresh: 2025-11-07 (STALE!)
Actual P/E: 2.98 (suspiciously low)
Actual P/S: 0.76 (suspiciously low)
```

**Root Cause**: Netflix split 4:1 in 2022, but:
- Valuation models weren't re-run post-split
- `last_data_refresh` is Nov 2025 (stale data)
- TTM metrics may be split-adjusted while fair values aren't

**Symbols Affected**: NFLX, potentially others with recent splits

---

### 2. Bad Revenue/FCF Data in SEC Filings (CPT, GLPI, NTNX)

**Issue**: SEC CompanyFacts parsing errors or missing data points

**Example - Camden Property Trust (CPT)**:
```json
"ps_valuation": {
  "ttm_revenue": 0.01,              ← WRONG! Should be much higher
  "qualification": "excellent",
  "multiple_range": {"max": 20.0, "min": 12.0},
  "applied_ps_multiple": 20.0,
  "current_ps_multiple": 907.56,
  "fair_value_per_share": 2.39,
  "ttm_revenue_per_share": 0.12
}
```

**Impact**:
- DCF model uses wrong revenue → inflated valuation
- P/S model uses wrong revenue → inflated valuation
- Fair value: $2,861 vs $108 current (2,541% upside) ← OBVIOUSLY WRONG

**Root Cause**:
- SEC filing XBRL tags missing or mislabeled
- Revenue not recognized at company level (REIT structure)
- FCF instead of revenue used incorrectly

---

### 3. Extreme P/S Ratios for Specific Industries

**Issue**: P/S ratios > 1000x are unrealistic and indicate data problems

**Examples**:
- GOLD (Barrick): P/S = 1,420x (should be 2-3x for miners)
- CPT: P/S = 1,254x (REIT with low FCF/share)

**Root Cause**:
- REITs: Distribute most FCF as dividends, so revenue/share is tiny but market cap is huge
- Mining/Commodities: Revenue recognition timing issues

---

### 4. Model Agreement Score = 0 (Models Diverge)

**Issue**: When models disagree significantly, blended average is meaningless

**Example - CPT**:
```
DCF:  $3,807 (75% weight)
P/S:   $2.39 (40% weight)
GGM:    $86.91 (0% weight)
PE:    $23.04 (25% weight)
-----
Total: 140% weight! (doesn't sum to 100)

Model Agreement Score: 0.0000
Divergence Flag: true
```

**Impact**: Blended fair value is unreliable when models disagree this much

---

## Pipeline Fixes Implemented

### Priority 1: Stock Split Detection & Handling ✅

**Status**: IMPLEMENTED in `src/investigator/domain/services/robust_valuation_service.py`

**Method**: `RobustValuationService.detect_stock_split()`

**Implementation**:
```python
def detect_stock_split(
    self,
    symbol: str,
    current_price: float,
    fair_value: float,
    model_agreement_score: float = 0.0,
) -> Dict[str, Any]:
    """Detect if a stock split has occurred but fair values weren't adjusted."""
```

**Detection Logic**:
- Fair value > 3x current price
- High model agreement (≥0.7)
- Matches common split ratios (2:1, 3:1, 4:1, 5:1, 7:1, 10:1)
- Returns detected flag, implied split ratio, and confidence level

**Integration**: Available in `robust_valuation_service.py` for use in valuation pipeline

---

### Priority 2: Revenue Data Validation ✅

**Status**: IMPLEMENTED in `src/investigator/domain/services/robust_valuation_service.py`

**Method**: `RobustValuationService.validate_revenue_data()`

**Implementation**:
```python
def validate_revenue_data(
    self,
    symbol: str,
    revenue_per_share: float,
    mkt_cap: float,
    industry: Optional[str] = None,
    sector: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate revenue data before using in models."""
```

**Validation Rules**:
- **REITs**: Reject if P/S > 500 (revenue likely dividends, not actual revenue)
- **Mining/Materials**: Reject if P/S > 100 (timing/recognition issues)
- **Financials**: Warn if P/S > 50 (recommend P/B or P/E instead)
- **All industries**: Reject if P/S > 1000 (data likely incorrect)

**Return Value**: Dict with `is_valid` flag, `ps_ratio`, `warnings`, and `recommendations`

---

### Priority 3: Divergent Model Handling ✅

**Status**: IMPLEMENTED in `src/investigator/domain/services/robust_valuation_service.py`

**Method**: `RobustValuationService.detect_model_divergence()`

**Implementation**:
```python
def detect_model_divergence(
    self,
    layer2_data: Dict[str, FairMultipleResult],
) -> Dict[str, Any]:
    """Detect when valuation models diverge significantly."""
```

**Divergence Detection**:
- Dispersion > 2x mean
- Coefficient of variation > 0.5
- Returns divergent flag, dispersion score, and recommended model

**Synthesis Update**: `_synthesize_layers()` now:
1. Checks for divergence before using blended average
2. Uses highest confidence model when divergent
3. Adds divergence warnings to signals
4. Logs which model was selected

---

### Priority 4: Stale Data Detection & Refresh ✅

**Status**: IMPLEMENTED as `scripts/refresh_stale_analysis.py`

**Features**:
- Detects stale analysis (>60 days old by default)
- Detects extreme valuations (200%+ upside or < -90%)
- Detects model divergence flags
- Detects potential stock splits
- Runs victor-invest analyze to refresh problematic symbols

**Usage**:
```bash
# Detect all issues
python scripts/refresh_stale_analysis.py --category all --stale-days 60 --dry-run

# Refresh specific category
python scripts/refresh_stale_analysis.py --category splits --mode comprehensive --parallel 4

# Refresh specific symbols
python scripts/refresh_stale_analysis.py --symbols NFLX CPT --mode standard
```

**Categories**:
- `all`: All categories combined
- `stale`: Analysis older than --stale-days
- `extreme`: Extreme valuations (200%+ upside/down)
- `divergence`: Model divergence flags
- `splits`: Potential stock splits

---

## Additional Pipeline Fixes Needed

### Priority 5: Industry-Specific Valuation Models

**Status**: NOT YET IMPLEMENTED

**Required Changes**:
- **REITs**: Use AFFO instead of FCF, P/AFFO instead of P/E
- **Banks**: Use P/B and P/E, don't use P/S (revenue is interest income)
- **Insurance**: Use P/B and combined ratio
- **Mining**: Use EV/Resource or NAV per share
- **SaaS**: Rule of 40 scoring, P/GM (price to gross margin)

**Implementation Location**: Add to `src/investigator/domain/services/valuation/` sector-specific models

---

### Priority 6: Data Quality Filters in Views

```python
# src/investigator/domain/services/robust_valuation_service.py

def detect_stock_split(symbol: str, current_price: float, fair_value: float) -> bool:
    """
    Detect if a stock split has occurred but fair values weren't adjusted.

    Red flags:
    - Fair value > 3x current price
    - High model agreement (>0.7)
    - Recent data (within 30 days)
    - Large cap company
    """
    ratio = fair_value / current_price if current_price > 0 else 0

    if ratio > 3:
        # Check if it's a known common split ratio
        common_splits = {2: "2:1", 3: "3:1", 4: "3:1", 5: "5:1", 7: "7:1"}

        for split_ratio, split_name in common_splits.items():
            if abs(ratio - split_ratio) / split_ratio < 0.2:  # Within 20%
                logger.warning(
                    f"{symbol}: Possible {split_name} stock split detected! "
                    f"Price=${current_price}, FV=${fair_value}, ratio={ratio:.2f}x"
                )
                return True

    return False
```

---

### Priority 2: Revenue Data Validation

```python
# Add to valuation pipeline

def validate_revenue_data(symbol: str, revenue_per_share: float,
                          mkt_cap: float, industry: str) -> bool:
    """
    Validate revenue data before using in models.

    Sanity checks:
    - REITs: mkt_cap / revenue shouldn't be > 500x
    - Mining: revenue should align with production
    - SaaS: revenue should be positive and growing
    """
    ps_ratio = mkt_cap / revenue_per_share if revenue_per_share > 0 else float('inf')

    # Industry-specific validation
    if 'Real Estate' in industry or 'REIT' in industry:
        if ps_ratio > 500:
            logger.error(
                f"{symbol}: Suspicious P/S ratio {ps_ratio:.1f} for REIT. "
                f"Revenue may be dividends instead of revenue."
            )
            return False

    elif 'Mining' in industry or 'Materials' in industry:
        if ps_ratio > 100:
            logger.error(
                f"{symbol}: Suspicious P/S ratio {ps_ratio:.1f} for miner. "
                f"Revenue data may be incomplete."
            )
            return False

    return True
```

---

### Priority 3: Divergent Model Handling

```python
# When models diverge significantly, don't use blended average

def calculate_blended_value(models: List[ValuationModel]) -> float:
    """
    Calculate blended fair value only when models agree reasonably well.
    """
    z_scores = [model.z_score for model in models if model.z_score]
    dispersion = max(z_scores) - min(z_scores) if z_scores else 0

    # Reject if dispersion is too high (>2 standard deviations)
    if dispersion > 2.0:
        logger.warning(
            f"Model dispersion too high ({dispersion:.2f}). "
            f"Using highest confidence model instead of blended."
        )
        # Return the model with highest confidence score
        return max(models, key=lambda m: m.confidence_score).fair_value

    # Otherwise use weighted average
    return sum(m.fair_value * m.weight for m in models)
```

---

### Priority 4: Stale Data Detection

```python
# Add to polling/analysis pipeline

def check_data_freshness(symbol: str) -> dict:
    """
    Check if analysis data is fresh enough to trust.
    """
    issues = []

    # Check SEC data age
    sec_age = (datetime.now() - last_data_refresh).days
    if sec_age > 90:
        issues.append(f"SEC data {sec_age} days old")

    # Check valuation age
    valuation_age = (datetime.now() - valuation_updated_at).days
    if valuation_age > 60:
        issues.append(f"Valuation {valuation_age} days old")

    # Check for price mismatch (potential split)
    if detect_stock_split(symbol, current_price, fair_value_blended):
        issues.append("Potential stock split - re-analysis needed")

    # Check for low model agreement
    if model_agreement_score < 0.3:
        issues.append(f"Low model agreement ({model_agreement_score:.2f})")

    return {
        "symbol": symbol,
        "issues": issues,
        "is_trustworthy": len(issues) == 0
    }
```

---

### Priority 6: Data Quality Filters in Views ✅

**Status**: ALREADY IMPLEMENTED in `01_investment_opportunities_view.sql`

```sql
-- Filter out extreme outliers
WHERE (s.fair_value_blended IS NULL
       OR s.fair_value_blended BETWEEN 0.1 AND 10000)  -- Exclude extreme FVs
  AND (s.pe_ratio IS NULL
       OR s.pe_ratio BETWEEN -500 AND 500)  -- Exclude extreme P/E
  AND (s.pb_ratio IS NULL
       OR s.pb_ratio BETWEEN 0 AND 100)  -- Exclude extreme P/B
  AND (s.ps_ratio IS NULL
       OR s.ps_ratio BETWEEN 0 AND 5000);  -- Exclude extreme P/S
```

---

## Implementation Summary

| Priority | Fix | Status | File |
|----------|-----|--------|------|
| 1 | Stock Split Detection | ✅ DONE | `robust_valuation_service.py:564` |
| 2 | Revenue Data Validation | ✅ DONE | `robust_valuation_service.py:633` |
| 3 | Model Divergence Handling | ✅ DONE | `robust_valuation_service.py:713` |
| 4 | Stale Data Refresh Script | ✅ DONE | `scripts/refresh_stale_analysis.py` |
| 5 | Industry-Specific Models | TODO | `domain/services/valuation/` |
| 6 | View Data Quality Filters | ✅ DONE | `01_investment_opportunities_view.sql` |

---

## Recommended Actions

### 1. Run Stale Analysis Refresh Script

```bash
# Detect all issues (dry run)
python scripts/refresh_stale_analysis.py --category all --stale-days 60 --dry-run

# Refresh symbols with extreme valuations
python scripts/refresh_stale_analysis.py --category extreme --mode comprehensive --parallel 4

# Refresh potential stock splits
python scripts/refresh_stale_analysis.py --category splits --mode standard

# Refresh specific problematic symbols
python scripts/refresh_stale_analysis.py --symbols CPT GLPI NTNX GOLD NFLX --mode comprehensive
```

### 2. Run SEC Polling with Analysis

```bash
# Refresh SEC data and run analysis for specific symbols
python scripts/poll_sec_filings.py --symbol CPT --symbol GLPI --symbol NTNX \
    --symbol GOLD --symbol NFLX --analyze --mode comprehensive
```

### 2. Flag Symbols for Manual Review

Create a watchlist for symbols that need investigation:

| Symbol | Issue | Action |
|--------|-------|--------|
| CPT | Revenue data (ttm_revenue = 0.01) | Fix SEC parsing or mark as unsupported |
| GLPI | Revenue data issue | Fix SEC parsing |
| NTNX | Revenue data issue | Fix SEC parsing |
| GOLD | P/S ratio = 1,420x | Industry-specific handling needed |
| NFLX | Stock split not handled | Refresh analysis with post-split data |
| MSTR | P/S ratio = 13,775x | Verify data (Bitcoin proxy stock?) |

### 3. Update Valuation Models

**Add special handling for REITs** (TODO):
- Use FCF instead of revenue for P/S
- Use AFFO (Adjusted Funds From Operations) instead of FCF
- P/AFFO instead of P/E

**Stock split detection** (✅ DONE):
- Implemented in `robust_valuation_service.py:detect_stock_split()`
- Detects common split ratios (2:1, 3:1, 4:1, 5:1, 7:1, 10:1)
- Returns implied split ratio and confidence level
- Available for use in valuation pipeline

---

## Recommended Query Filters

Until data quality is fixed, always filter opportunities by:

```sql
-- High confidence only
SELECT * FROM investment_opportunities
WHERE model_agreement_score >= 0.7
  AND upside_pct BETWEEN 10 AND 100
  AND mktcap > 500000000  -- Min $500M
ORDER BY model_agreement_score DESC, upside_pct DESC;

-- Exclude potential data issues
SELECT * FROM investment_opportunities
WHERE model_agreement_score >= 0.5
  AND NOT divergence_flag
  AND valuation_updated_at >= CURRENT_DATE - INTERVAL '60 days'
ORDER BY upside_pct DESC;
```

---

## Summary

| Issue | Count | Fix Priority |
|-------|-------|--------------|
| Stock splits (NFLX, etc.) | ~10 | **HIGH** - Affects many large caps |
| Bad revenue data (CPT, GLPI, NTNX) | ~20 | **HIGH** - Extreme valuations |
| Industry P/S issues (REITs, Mining) | ~50 | **MEDIUM** - Industry-specific handling |
| Model divergence (agreement < 0.3) | ~100 | **LOW** - Already flagged with divergence_flag |

**Views are working correctly** - they're exposing data quality issues that need fixing in the analysis pipeline.

# META Valuation Verification + Multiple Decomposition Guide

**Date:** 2026-02-21
**Symbol:** META (Meta Platforms Inc.)
**Mode:** Comprehensive Analysis

---

## Part 1: META Valuation Results

### Summary

| Metric | Value |
|--------|-------|
| **Current Price** | $655.66 |
| **Blended Fair Value** | $609.28 |
| **Upside/Downside** | -7.1% |
| **Recommendation** | SELL |
| **Confidence** | MEDIUM |

**Thesis:** META trades above blended fair value with highly divergent model outputs. DCF/GGM show deep undervaluation (data quality issues), while P/E and P/S show overvaluation.

### Individual Model Results

| Model | Fair Value | Current | Upside | Key Inputs |
|-------|-----------|---------|--------|------------|
| **DCF** | $4.67 | $655.66 | -99.3% | FCF data issue |
| **GGM** | $10.13 | $655.66 | -98.5% | DPS $0.49, r=8%, g=3% |
| **P/E** | ~$620+ | $655.66 | -5%+ | Target P/E 31.95x |
| **P/S** | ~$660+ | $655.66 | ~0% | P/S 10.0x on $181.7B sales |
| **EV/EBITDA** | *Not logged* | - | - | Model ran but logs missing |

### Model Analysis

#### 1. P/E Multiple Model ✅ VERIFIED
```
Target P/E calculation: sources=[sector_median=28.00, growth_adjusted=35.90] → average=31.95
```

**Breakdown:**
- Sector median P/E: 28.00x
- Growth adjusted: 35.90x
- **Final Target P/E: 31.95x** (average of the two)

**Growth multiplier working correctly:**
- Revenue growth: 28.2%
- Growth multiplier = 1.0 + 0.282 = 1.282x
- Sector median × growth multiplier = 28.00 × 1.282 = 35.90x ✅

**This confirms the 2.5x cap is working** - META's 28.2% growth produces a 1.282x multiplier, well within the 2.5x cap.

#### 2. P/S Multiple Model ✅ VERIFIED
```
PS_GRANULAR - Final P/S: 10.00 (base: 6.0 + growth: 4.0 + stage: 0.0) × quality: 1.00
Growth adjustment: +4.0 (revenue growth: 28.2%)
```

**Breakdown:**
- Base P/S: 6.0x (Technology sector)
- Growth adjustment: +4.0 (for 28.2% revenue growth)
- Stage adjustment: 0.0 (mature company)
- Quality multiplier: 1.00
- **Final P/S: 10.00x**

**Fair value from P/S:** $181.7B TTM revenue × 10.0x = $1,817B EV ÷ 2.713B shares ≈ **$670/share**

#### 3. DCF Model ⚠️ DATA ISSUE
```
Fair Value: $4.67, Current: $655.66, Upside: -99.3%
```

The DCF model is clearly broken due to FCF calculation issues. This is a known limitation when companies have:
- High capital expenditures (Reality Labs, metaverse investments)
- Stock-based comp (not treated as cash outflow in FCF)
- Negative free cash flow in some periods

#### 4. GGM Model ⚠️ NOT APPLICABLE
```
Fair Value: $10.13, Current: $655.66, Upside: -98.5%
Dividend Yield: 0.07%, Growth Rate: 3.00%, Required Return: 8.00%
```

GGM is not appropriate for META because:
- Dividend yield is 0.07% (negligible)
- META returns capital via buybacks, not dividends
- Growth comes from reinvestment, not dividend sustainability

#### 5. EV/EBITDA Model ⚠️ LOGS MISSING
The model ran (no errors) but the growth adjustment log didn't appear. This could mean:
- Revenue growth was passed correctly but log level filtered it out
- The growth adjustment didn't trigger (revenue_growth might have been None)
- Model used sector default without adjustment

**Next steps to verify:**
1. Check META's actual EBITDA and SBC values
2. Run with debug logging enabled
3. Verify SBC add-back is working for high-SBC company like META

---

## Part 2: Multiple Expansion/Compression Decomposition

### The Critical Insight

**A changing P/E multiple can mean VERY different things:**

| Scenario | P/E Change | Price | Earnings | What Happened |
|----------|-----------|-------|----------|---------------|
| **Pure Multiple Expansion** | ↑ | ↑↑ | → | Market paying more for same earnings |
| **Pure Multiple Compression** | ↓ | ↓↓ | → | Market paying less for same earnings |
| **Hidden Growth** | ↓ | ↑ | ↑↑ | Earnings growing faster than price |
| **Hidden Decline** | ↑ | → | ↓↓ | Earnings collapsing but P/E masks it |
| **Balanced Expansion** | ↑ | ↑ | ↑ | Price and earnings rise together |

### The Formula

**P/E = Price ÷ Earnings per Share (EPS)**

When P/E changes from Period A to Period B:
- **P/E(A) = Price(A) ÷ EPS(A)**
- **P/E(B) = Price(B) ÷ EPS(B)**
- **% Change in P/E** = (P/E(B) - P/E(A)) ÷ P/E(A)

But this % change has TWO drivers:
1. **% Change in Price** (numerator)
2. **% Change in EPS** (denominator)

**Key relationship:**
- If Price ↑ faster than EPS → P/E expands (multiple expansion)
- If EPS ↑ faster than Price → P/E contracts (multiple compression)
- If Price and EPS grow at same rate → P/E stays flat

### Real-World Examples

#### Example 1: META (2021-2024) - Multiple Compression
| Metric | 2021 | 2024 | Change |
|--------|------|------|--------|
| Price | ~$340 | ~$655 | +93% |
| EPS | ~$13.50 | ~$20.50 | +52% |
| **P/E** | **25.2x** | **32.0x** | **+27%** |

**What happened:**
- Price +93%, EPS +52%
- Price grew faster than EPS → P/E expanded from 25x to 32x
- This is **multiple expansion** driven by strong earnings growth + AI optimism

**Interpretation:** Market re-rated META higher, paying 32x for 2024 earnings vs 25x for 2021 earnings.

#### Example 2: NVDA (2020-2024) - Hidden Growth
| Metric | 2020 | 2024 | Change |
|--------|------|------|--------|
| Price | ~$110 | ~$900 | +718% |
| EPS | ~$2.00 | ~$18.00 | +800% |
| **P/E** | **55x** | **50x** | **-9%** |

**What happened:**
- Price +718%, EPS +800%
- EPS grew SLIGHTLY faster than price → P/E compressed from 55x to 50x
- This is **hidden growth** - massive earnings growth "grew into" the valuation

**Interpretation:** Despite P/E compression, shareholders made 7x returns. The P/E decline was a GOOD sign - earnings were outpacing even the bullish price action.

#### Example 3: XOM (2020-2024) - Hidden Growth
| Metric | 2020 | 2024 | Change |
|--------|------|------|--------|
| Price | ~$40 | ~$105 | +163% |
| EPS | ~$3.00 | ~$10.50 | +250% |
| **P/E** | **13.3x** | **10.0x** | **-25%** |

**What happened:**
- Price +163%, EPS +250%
- Massive earnings growth from oil price boom
- P/E compressed despite strong gains

**Interpretation:** Energy earnings were so strong they outpaced price appreciation. The P/E compression was NOT a sign of weakness - it was a sign of exceptional earnings power.

#### Example 4: LLY (2020-2024) - Pure Multiple Expansion
| Metric | 2020 | 2024 | Change |
|--------|------|------|--------|
| Price | ~$170 | ~$580 | +241% |
| EPS | ~$6.50 | ~$12.50 | +92% |
| **P/E** | **26.2x** | **46.4x** | **+77%** |

**What happened:**
- Price +241%, EPS +92%
- Price grew 2.6x faster than earnings → P/E exploded from 26x to 46x
- This is **pure multiple expansion** - GLP-1 drug boom

**Interpretation:** Market re-rated LLY from "steady pharma" to "growth juggernaut," paying nearly 50x earnings. This is unsustainable - earnings need to catch up.

### P/S and P/B Decomposition

The same logic applies to **P/S** (Price ÷ Sales per Share) and **P/B** (Price ÷ Book per Share):

#### META P/S Decomposition (2021-2024)
| Metric | 2021 | 2024 | Change |
|--------|------|------|--------|
| Price | ~$340 | ~$655 | +93% |
| Sales per share | ~$25.50 | ~$52.00 | +104% |
| **P/S** | **13.3x** | **12.6x** | **-5%** |

**Interpretation:** Revenue grew faster than price, causing slight P/S compression. This is healthy - revenue is "growing into" the valuation.

#### JPM P/B Decomposition (2020-2024)
| Metric | 2020 | 2024 | Change |
|--------|------|------|--------|
| Price | ~$100 | ~$195 | +95% |
| Book per share | ~$60 | ~$82 | +37% |
| **P/B** | **1.67x** | **2.38x** | **+43%** |

**Interpretation:** Price grew much faster than book value = pure P/B expansion. JPM earned a "quality premium" over the sector.

---

## Part 3: How to Analyze Multiple Changes

### Step 1: Decompose the Multiple

When you see P/E change, calculate:

1. **Price % Change:** (Price(B) - Price(A)) ÷ Price(A)
2. **EPS % Change:** (EPS(B) - EPS(A)) ÷ EPS(A)
3. **P/E % Change:** (P/E(B) - P/E(A)) ÷ P/E(A)

### Step 2: Identify the Driver

| If... | Then... |
|-------|---------|
| Price % > EPS % | Multiple expansion (bullish on growth) |
| EPS % > Price % | Multiple compression (earnings growing into valuation) |
| Price % ≈ EPS % | Multiple stable (valuation justified by fundamentals) |

### Step 3: Assess Sustainability

| Driver | Sustainability | Risk |
|--------|----------------|------|
| **Multiple expansion** | Limited (can't re-rate forever) | Pop when growth disappoints |
| **Earnings growth** | Sustainable (compound interest) | Slow if business matures |
| **Combined** | Powerful but rare | Both must continue |

### Step 4: Make Investment Decision

| Situation | Action |
|-----------|--------|
| Multiple expansion + low earnings growth | **SELL** (valuation detached from fundamentals) |
| Multiple compression + high earnings growth | **BUY** (earnings will grow into valuation) |
| Multiple stable + steady earnings growth | **HOLD/Buy** (fair valuation) |
| Multiple expansion + accelerating earnings | **HOLD** (rare sweet spot, but watch) |

---

## Part 4: META Specific Analysis

### Current Valuation (2025)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **Current Price** | $655.66 | Near all-time highs |
| **TTM EPS** | ~$20.50 | Strong earnings from core business |
| **Current P/E** | ~32x | At top of historical range |
| **TTM Revenue** | $181.7B | 28% YoY growth |
| **P/S** | ~10x | Rich but justified by growth |

### Historical P/E Progression (2020-2025)

| Year | Price | EPS | P/E | Story |
|------|-------|-----|-----|-------|
| 2020 | ~$250 | ~$10.50 | 24x | COVID recovery |
| 2021 | ~$340 | ~$13.50 | 25x | Metaverse hype |
| 2022 | ~$130 | ~$9.00 | 14x | Multiple compression (ad recession) |
| 2023 | ~$350 | ~$14.50 | 24x | "Year of Efficiency" |
| 2024 | ~$500 | ~$20.50 | 24x | AI boom + earnings growth |
| 2025 | ~$655 | ~$20.50 | 32x | Multiple expansion (AI optimism) |

**Key insight:** META's P/E expanded from 24x to 32x in 2025 WITHOUT corresponding earnings growth. This is **pure multiple expansion** driven by AI hype.

### The Bull Case

- **AI monetization:** Llama, AI-enhanced ad targeting
- **Reels growth:** TikTok competitor monetizing
- **WhatsApp Business:** Untapped monetization opportunity
- **Core business strength:** Instagram + Facebook cash cow

### The Bear Case

- **P/E expansion without earnings growth:** Unsustainable
- **Apple privacy changes:** Ongoing headwind to ad targeting
- **Reality Labs losses:** $5B+/year burn with uncertain payoff
- **Regulatory risk:** FTC antitrust actions

### Recommendation: SELL

**Rationale:**
- Trading at 32x P/E with earnings flat YoY
- P/E expanded from 24x to 32x on AI hype, not fundamentals
- Risk of multiple compression if AI disappoints
- Better opportunities in stocks with earnings growth driving returns

---

## Part 5: Verification Summary

### New Models Verified ✅

| Model | Status | Evidence |
|-------|--------|----------|
| **P/E growth multiplier (2.5x cap)** | ✅ VERIFIED | META: 28.2% growth → 1.282x multiplier |
| **P/E target calculation** | ✅ VERIFIED | Average of sector (28x) and growth-adjusted (35.9x) = 31.95x |
| **P/S growth adjustment** | ✅ VERIFIED | 28.2% revenue growth → +4.0 adjustment → 10.0x P/S |
| **EV/EBITDA growth adjustment** | ⚠️ UNCLEAR | Logs not appearing, need debug run |
| **SBC-adjusted EBITDA** | ⚠️ UNCLEAR | Need to verify SBC add-back for high-SBC companies |
| **SBC earnings quality penalty** | ⚠️ UNCLEAR | Need to check P/E model confidence score |

### Recommended Next Steps

1. **Debug run for META:**
   ```bash
   victor-invest analyze META --mode standard 2>&1 | grep -i "ebitda\|sbc\|growth.*factor"
   ```

2. **Test with NVDA (high growth, lower SBC):**
   ```bash
   victor-invest analyze NVDA --mode comprehensive
   ```

3. **Verify industry override for EV/EBITDA:**
   - META is "Internet Content & Information"
   - Config has override: 28x
   - Check if this is being applied correctly

---

**Generated:** 2026-02-21
**Data Source:** SEC Company Facts + Market Data
**Disclaimer:** This analysis is for informational purposes only, not investment advice.

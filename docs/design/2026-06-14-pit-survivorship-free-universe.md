# Design Scope — Point-in-Time, Survivorship-Free Backtest Universe (Finding C)

**Date:** 2026-06-14
**Status:** Scoping / design (no implementation)
**Related:** `docs/audits/2026-06-14-rl-backtest-and-convergence-audit.md` finding C; the interim
`survivorship_flag` mitigation already shipped (migration 012 + workflow/tool/tracker plumbing).

---

## 1. Problem & why it matters

The RL backtest draws its universe from **currently-listed** names only and cannot represent a
company that delisted, was acquired, or went bankrupt during the lookback window. Two compounding
biases result:

- **Survivorship bias (selection):** the universe is conditioned on companies that survived to
  today, systematically inflating realized forward returns — especially for LONG rows.
- **Delisting bias (missing terminal outcome):** when a name's `tickerdata` rows stop, the future
  price resolves to `None` and the observation is silently dropped. The worst outcomes
  (bankruptcies, –100% moves — exactly the SHORT-correct / LONG-wrong cases) vanish from training.

Together these teach the policy an over-optimistic, long-biased view of the market. This is one of
the two remaining "disqualifying for a defensible backtest" items from the audit (the other,
lookahead bias, was fixed in P0).

**Bottom line:** this is fundamentally a **data-acquisition** project. The code changes are modest
and mostly already scaffolded; the hard, expensive part is sourcing trustworthy historical
constituent membership and delisting events.

---

## 2. Goals / non-goals

**Goals**
- A canonical universe selector: `get_universe(as_of_date, index=..., top_n=...)` returning the names
  that were actually members/listed **as of** that date, including names later delisted.
- Delisting modeled as a **terminal, loss-bearing exit** in price/reward logic (not a dropped row).
- Recorded outcomes legitimately set `survivorship_flag = False` when sourced from a PIT universe.

**Non-goals (for this effort)**
- Tick-level or intraday accuracy; corporate-action chains beyond splits (already handled) and
  delistings. Spin-offs/mergers acquirer-mapping are a later refinement.
- Replacing the live (current-snapshot) universe used by the production `analyze`/screener paths —
  those legitimately want today's universe. PIT is for backtesting only.

---

## 3. Current state (grounded)

**Exists / leverage:**
- `tickerdata` (OHLCV history) — the price spine; row presence is the de-facto liveness signal.
- `stock_splits` table + `cumulative_split_ratios` view (`schema/migrations/008_add_stock_splits_table.sql`)
  — **the precedent to copy**: event-dated rows, `UNIQUE(symbol, date)`, `source` provenance, helper views.
- Consumer-side survivorship scaffolding is **already built end-to-end**: `valuation_outcomes.survivorship_flag`
  (migration 012), threaded through `RLBacktestWorkflowState`, `RLBacktestTool._record_prediction`,
  `OutcomeTracker.record_prediction_with_outcomes`, and `get_training_ready_experiences(exclude_survivorship=...)`.
- SEC EDGAR integration (`src/investigator/infrastructure/sec/sec_api.py`) — can fetch submissions/filings,
  which is the realistic free source for **delisting** signals (Form 25 / Form 15 / last-filing).
- `mktcap` / `stockid` rank for cap-based selection.

**Missing (the gaps):**
1. Historical index-constituent membership with effective/removal dates — **no table, no feed**.
   Index flags (`sp500`, `russell1000`, …) are current booleans on the `symbol` FDW foreign table.
2. Delisting events (date, reason, last price) — only implicit from absent `tickerdata` rows; today
   there is **no way to distinguish "delisted" from "stale/missing data."**
3. PIT listing/IPO/first-trade/last-trade dates (`symbol` has only current `islisted`).
4. A canonical universe module that accepts `as_of_date` — selection is duplicated across ≥5 call
   sites (`scripts/rl_backtest_workflow.py:82-117`, `tools/options_screen.py:154-196`,
   `symbol_repository.py:90-127`, `scripts/batch_warm_sec_cache.py`, `api/app.py:2433`).
5. `as_of_date` on `SymbolMetadataService.get_metadata` (current-snapshot only).

**Note / cleanup:** `survivorship_flag` defaults inconsistently — `True` in `RLBacktestWorkflowState`
(`workflows/rl_backtest.py:107`) vs `False` in the tool signature (`tools/rl_backtest.py`). Reconcile
during this work (PIT-sourced ⇒ False; legacy/current-snapshot ⇒ True).

---

## 4. Proposed design

### 4.1 New tables (local Postgres, modeled on `stock_splits`)

```sql
-- Historical index membership (point-in-time constituents).
CREATE TABLE index_membership (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20) NOT NULL,
    index_name   VARCHAR(32) NOT NULL,        -- 'sp500','russell1000','nasdaq100',...
    effective_date DATE NOT NULL,             -- added to index
    removal_date   DATE,                      -- NULL = still a member
    source       VARCHAR(64) NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, index_name, effective_date)
);
-- "members as of D": WHERE effective_date <= D AND (removal_date IS NULL OR removal_date > D)

-- Delisting / terminal events.
CREATE TABLE delisting_events (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20) NOT NULL,
    delist_date  DATE NOT NULL,
    reason       VARCHAR(64),                 -- 'bankruptcy','acquired','compliance','voluntary','unknown'
    last_price   NUMERIC(12,2),               -- last traded price before delisting
    recovery_assumption NUMERIC(5,4),         -- fraction of last_price realized (0 = total loss)
    acquirer_symbol VARCHAR(20),              -- for mergers (future use)
    source       VARCHAR(64) NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, delist_date)
);
```

Both follow the `stock_splits` shape (event-dated, `source` provenance, idempotent migration with
`IF NOT EXISTS` guards). Add a `members_as_of(index, date)` SQL view/helper mirroring
`cumulative_split_ratios`.

### 4.2 Canonical universe service

New `src/investigator/domain/services/market_data/universe_service.py`:

```python
class UniverseService:
    def get_universe(self, as_of_date, index=None, top_n=None,
                     include_delisted=True) -> list[UniverseMember]: ...
    # UniverseMember: symbol, stockid, sec_sector, mktcap_as_of, survivorship_safe: bool
```

- `index` set ⇒ PIT membership query against `index_membership`.
- `top_n` ⇒ cap-rank as of date (best-effort: needs PIT mktcap; see §5 risk).
- `survivorship_safe=True` only when the result is sourced from `index_membership` (real PIT) and
  delistings are available; sets `survivorship_flag=False` downstream.
- Refactor the ≥5 duplicated snapshot queries to call this service (back-compat: a `live` mode that
  returns today's snapshot for the production `analyze`/screener paths).

### 4.3 Delisting-aware price / reward

- `PriceService`: add `get_terminal_price(symbol, as_of_date)` returning `(price, date, is_delisting)`
  by joining `delisting_events`. When a holding-period target date falls **after** `delist_date`,
  the realized exit is `last_price * recovery_assumption` (default 0 for bankruptcy, ~1 for
  acquisition at last price), not `None`.
- `RLBacktestTool._get_multi_period_data` / `_calculate_rewards`: when the symbol delists mid-horizon,
  substitute the terminal value so the reward reflects the real (often catastrophic) outcome instead
  of dropping the row. This is the single highest-value behavioral fix.

### 4.4 Metadata PIT

Add optional `as_of_date` to `SymbolMetadataService.get_metadata` and surface delisting status; when
`as_of_date` is set and the symbol delisted before it, return the last-known metadata + a `delisted`
marker rather than current-snapshot values.

---

## 5. Data-sourcing strategy (the critical path)

No integrated feed provides historical constituents or delistings. Options, in priority order:

**A. Delistings first (highest value, cheapest) — recommended MVP.**
- Source from **SEC EDGAR** (already integrated): Form **25** (notification of delisting) and Form
  **15** (deregistration) give a delist date per CIK; the last `tickerdata` row gives `last_price`.
  Reason can be coarsely inferred (bankruptcy via Chapter 11 8-K / Form 15 cause; acquisition via
  merger 8-K / DEFM14A). Build an extractor under `infrastructure/sec/` that walks submissions for
  Form 25/15 and writes `delisting_events`. Default `recovery_assumption`: 0.0 (bankruptcy/compliance),
  pending refinement.
- Backfill `last_price` from the final `tickerdata` close before `delist_date`.

**B. Index constituent history (harder; pick one):**
1. **Paid feed (gold standard):** CRSP (academic), Norgate Data, or **Sharadar SEP/TICKERS via Nasdaq
   Data Link** (most cost-effective, includes delisted tickers + historical index membership). One-time
   loader populates `index_membership` + `delisting_events`. Strongly recommended if budget allows —
   removes the reconstruction risk entirely.
2. **Free / scrappy reconstruction (MVP fallback):** historical S&P 500 change lists (Wikipedia
   "List of S&P 500 companies" revision history / public change CSVs) give add/remove dates back ~20y;
   Russell reconstitution is annual (June) and partially published. Lower fidelity; document the
   limitation and keep `survivorship_safe=False` for indices we can't reconstruct cleanly.
3. **`tickerdata`-presence proxy (weakest):** treat "had price rows in [D-1y, D]" as the universe as
   of D. Captures delisted names that still have history but **not** membership; over-includes
   micro-caps. Use only as a stopgap and never claim `survivorship_safe`.

**Recommendation:** ship **A (EDGAR delistings)** + the terminal-exit reward path first — it fixes the
worst bias with data we can already get. Then pursue **B.1 (Sharadar)** for true PIT membership; fall
back to **B.2** if no budget.

---

## 6. Validation strategy

- **Bias quantification:** run the same backtest window (a) current-snapshot universe vs (b) PIT
  universe-with-delistings; report the delta in mean reward / win-rate / LONG-vs-SHORT skew. A
  material drop in LONG reward and appearance of large-negative SHORT-correct outcomes confirms the
  bias was real and is now captured.
- **Spot-check delistings:** assert known bankruptcies (e.g. Lehman, Bed Bath & Beyond, SVB) appear
  in `delisting_events` with a terminal loss and produce a strongly negative LONG / positive SHORT
  reward at the spanning horizon.
- **Significance:** feed PIT results through the P3 `evaluate_reward_significance` (Newey-West +
  block bootstrap + effective N + mirror dedup) and compare significance with/without survivors.
- **Coverage report:** `log()` how many universe members had no price/metadata (silent drops) so
  truncation is never mistaken for completeness.

---

## 7. Phased implementation plan

| Phase | Deliverable | Effort | Risk |
|---|---|---|---|
| C1 | `delisting_events` table + migration + SEC Form 25/15 extractor + `last_price` backfill + tests | M | Low (EDGAR available) |
| C2 | Delisting-aware terminal-exit in `PriceService` + `RLBacktestTool` reward path + tests | S–M | Low |
| C3 | `index_membership` table + migration + loader (Sharadar paid **or** reconstruction) + tests | M–L | **High (data sourcing/budget)** |
| C4 | `UniverseService.get_universe(as_of_date,...)`; refactor ≥5 call sites; set `survivorship_flag` correctly; reconcile the True/False default | M | Med (blast radius) |
| C5 | `SymbolMetadataService` `as_of_date` + delisting surface | S | Low |
| C6 | Validation harness (bias quantification + spot-checks + significance) | S | Low |

Sequencing: **C1 → C2** deliver most of the value independently of the expensive C3. C3/C4 depend on
the data-sourcing decision; gate them on that.

---

## 8. Risks & open questions

- **Data budget (blocking for true PIT membership):** is there budget for Sharadar/Norgate/CRSP? If
  not, C3 is reconstruction-only and `survivorship_safe` stays partial. **Decision needed.**
- **PIT market cap for `top_n`:** cap-rank as of a past date needs historical shares × price; shares
  are available point-in-time via SEC (`shares_service` already supports `as_of_date`), price via
  `tickerdata` — so PIT cap is computable but adds cost. Confirm acceptable.
- **`recovery_assumption` calibration:** 0 for bankruptcy is conservative; acquisitions should use the
  deal price. Start coarse, refine with reason.
- **FDW constraint:** `symbol` is a read-only foreign table; new tables are **local** Postgres (like
  `stock_splits`) — fine, no FDW writes needed.
- **Acquirer mapping / spin-offs:** out of scope now; `acquirer_symbol` column reserved for later.

---

## 9. Summary

The consumer side (flag + filter) is done. The work is: (1) **get delisting data from EDGAR** and make
the reward path treat delisting as a terminal loss (C1–C2, high value, low risk, no budget needed);
then (2) **acquire/reconstruct PIT index membership** and route all universe selection through one
as-of-date service (C3–C4, gated on a data-sourcing decision). Validate by quantifying the
survivorship delta and running it through the P3 significance toolkit.
</content>

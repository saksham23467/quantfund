# Assumptions, Biases, and Limitations

This document records research assumptions. **None of the default cost or slippage values are claims of exact current broker or exchange charges.**

---

## Phase 1 — Data correctness (prominent)

### DEVELOPMENT vs RESEARCH datasets

| Kind | Meaning |
|------|---------|
| **DEVELOPMENT DATASET** | Pipeline / exploratory use. May use yfinance + Stage A universes. |
| **DEVELOPMENT_DATA** | Free/public NSE-related OHLCV pipeline (`src/quantfund/data/development/`). Explicit `data_class=DEVELOPMENT_DATA`. |
| **RESEARCH DATASET** | Reserved for exchange/paid-grade sources with PIT (or better) membership. |

**Phase 1 yfinance + `current_snapshot_only` MUST be:**

- `source_grade = non_exchange`
- `dataset_status = development`
- `research_eligibility = development_only`

**`DEVELOPMENT_DATA` invariant (hard lock):**

```text
DEVELOPMENT_DATA → DEVELOPMENT_ONLY → research/paper/live eligible = false → real_orders = 0
```

Quality PASS does **not** promote eligibility. PIT / CA / delisted gaps are recorded, never fabricated.  
See `docs/DEVELOPMENT_DATA.md`.

These datasets may be used for infrastructure and exploration.  
They are **NOT suitable for final strategy validation.**

### Survivorship (Stage A)

Universe completeness is `current_snapshot_only`.

**NOT POINT-IN-TIME. UNSUITABLE FOR FINAL STRATEGY EVALUATION.**

Membership queries return `TRUE` / `FALSE` / `UNKNOWN`.  
For Stage A, any date other than the snapshot `as_of_date` returns **UNKNOWN**.  
Stage A does **not** solve survivorship bias.

### RAW vs ADJUSTED prices

| Series | Use |
|--------|-----|
| **RAW OHLC** | As-traded session prices. **Never overwritten.** Used for **execution simulation**. |
| **ADJUSTED OHLC** | Derived continuity series under an explicit `AdjustmentPolicy`. Research only. |

Default `AdjustmentPolicy` (`split_bonus_v1`):

- Split adjusted (backward cumulative)
- Bonus adjusted (backward cumulative)
- Dividends tracked separately (`dividends.json`)
- Dividends **excluded** from adjusted OHLC

Math for split/bonus factor \(r\) with ex-date \(T\):

\[
C(t)=\prod_{\text{ex}>t} r,\quad P^{adj}(t)=P^{raw}(t)/C(t)
\]

Mergers/demergers: schema only; **no automatic price reconstruction**.

### Calendar (Phase 1.5)

`CalendarProvider` is independent of `DataProvider`. Weekends/holidays are **expected absences**, not missing-data errors. Never forward-fill weekends or holidays.

**Verified NSE calendar (preferred):**
- `calendar_id = NSE_EQ`
- `calendar_version = nse_eq_v2023_2025_r1` (default; prior `nse_eq_v2024_2025_r1` remains immutable)
- Curated from NSE Capital Market holiday circulars (2024: NSE/CMTR/59722; 2025: NSE/CMTR/65587)
- Coverage: 2024-01-01 … 2025-12-31 (`Asia/Kolkata`)
- Muhurat Trading days are OPEN special sessions
- `calendar_verified = true`

**Unverified proxy (must not be treated as NSE):**
- `ExchangeCalendarsProvider` uses `exchange-calendars` **XBOM** (BSE)
- `calendar_id = XBOM_PROXY_UNVERIFIED`
- `calendar_verified = false`
- Any dataset using an unverified calendar is forced to `research_eligibility = development_only`

### yfinance

Transitional / development source only. Incomplete corporate actions, possible errors, not exchange-grade.

### Historical local CF-CA equities (user-supplied)

Ingested via `historical_local_ca` as **non_exchange / DEVELOPMENT_ONLY**.

- Improves development CA infrastructure (classify, parse, as-of, coverage metrics).
- Does **not** become research-grade because the file is large or historical.
- As-of visibility uses **ex_date** (announcement dates are absent — not invented).
- Mergers/demergers remain manual; RAW OHLC never modified.
- See `DATA_LICENSE.md` (redistribution rights unknown unless established).

---

## Execution model (unchanged from Milestone 1)

- **Signal at bar close** using information available at or before that close.
- **Order scheduled for next bar open only.**
- **Same-bar execution is disabled.**
- Fill price = next open ± slippage; then transaction costs are applied.
- Long-only: **no short selling.**
- Execution uses **RAW** prices from the dataset reader.

---

## Cost model (equity delivery)

Configurable research assumptions (not exact broker schedules):

| Component | Default research assumption |
|-----------|-----------------------------|
| Brokerage | 3 bps of turnover |
| STT | 0 on buy; 10 bps on sell turnover |
| Exchange charges | 0.00297% of turnover |
| GST | 18% on (brokerage + exchange) |
| Stamp duty | 1.5 bps on buy turnover; 0 on sell |
| SEBI charges | 0.0001% of turnover |

---

## Slippage model

- Fixed adverse slippage (default **5 bps**).
- Not a market-impact model.

---

## Data lineage

```
source → raw download → normalize → CA policy → universe version
       → calendar version → dataset version → backtest experiment
```

Experiments record `dataset_id`, `dataset_version`, eligibility, and warnings.

---

## Known biases and gaps

| Issue | Status |
|-------|--------|
| Look-ahead (execution) | Mitigated by next-bar open + history slicing + as-of reader |
| Survivorship | **Stage A only — NOT solved** |
| Corporate actions completeness | Source-dependent; mergers not auto-handled |
| Calendar NSE vs BSE proxy | Possible minor mismatch |
| yfinance quality | Non-exchange / development |
| Intraday | Not implemented |
| Live trading | Not implemented |

---

## Capital

- Default initial capital: **₹100,000** (`QUANTFUND_INITIAL_CAPITAL`).
- Backtests / research only. **Not connected to live automated trading.**

---

## Phase 4 — AI Strategy Factory

- AI may generate **structured StrategySpec JSON only** (currently `MockStrategyGenerator`).
- Generator ≠ evaluator. AI cannot accept itself or access sealed TEST during generation.
- No LLM SDK/API in Phase 4. No arbitrary code execution from AI output.
- Strategies evaluated on `DEVELOPMENT_ONLY` data remain **not accepted** for validation pipelines.
- See `docs/AI_SAFETY.md` and `docs/STRATEGY_DSL.md`.

## Phase 7 — Research package acquisition

- A configured `QUANTFUND_RESEARCH_PACKAGE` is validated fail-closed before ingest.
- Synthetic fixtures and yfinance remain permanently non–research-eligible.
- Delisted coverage is measurable (`none` / `partial` / `complete`); partial is never promoted to full merely because the active universe looks complete.
- PIT membership import never invents intervals; UNKNOWN stays UNKNOWN.
- Certification `facts_hash` is reproducible from validated facts; package booleans are not trusted.
- Phase 7 does **not** promise profitable strategies or that this environment has a licensed exchange package.

## Phase 8 — Paper trading kernel

- Paper sessions use **simulated capital only**; `quantfund.execution/` remains live-empty.
- `DEVELOPMENT_ONLY` datasets always yield `paper_eligible=false`.
- Infrastructure sandbox may exercise the kernel without claiming paper eligibility.
- Campaign acceptance alone never implies paper eligibility.
- Deterministic replay requires stable config + event stream + strategy; paper IDs are deterministic.
- No profitability claims from the Phase 8 demo.

## Phase 9 — Execution gateway (DRY_RUN / Mock only)

- `ExecutionGateway` + `MockBrokerAdapter` + `DRY_RUN` only.
- **Real orders sent: always 0.** No real broker SDK or network order path.
- `LiveTradingEligibilityGate`: `DEVELOPMENT_ONLY` → `LIVE_BLOCKED`.
- Research acceptance ≠ paper eligibility ≠ live authorization.
- Kill switch is **freeze only** (no automatic flatten).
- See `docs/PHASE9_EXECUTION_SAFETY.md`.

## Phase 10 — Research-to-paper validation

- `StrategyAcceptanceRecord` is the only acceptance evidence; strategies cannot self-accept.
- Paper eligibility requires RESEARCH_ELIGIBLE + acceptance record + sealed TEST + robustness + walk-forward + DSR/trials + operator paper session.
- `DEVELOPMENT_ONLY` / synthetic / yfinance remain non–research-eligible.
- Research→paper ladder (`PaperEligibilityGate`) still requires research-grade data.
- `paper_policy_v1` may yield `LIVE_ELIGIBILITY_CANDIDATE`; **live trading remains disabled**.
- Research acceptance ≠ profitability guarantee; paper pass ≠ live authorization.
- See `docs/PHASE10_ARCHITECTURE.md`, `docs/PAPER_VALIDATION.md`, `docs/RESEARCH_ACCEPTANCE.md`.

## Phase 10.5 — Research package readiness audit

- Documents and audits existing RESEARCH_ELIGIBLE gates; does not weaken them.
- `make audit-research-package` certifies the configured package or the synthetic pilot fixture.
- Expected without a licensed package: `RESEARCH_ELIGIBLE = FALSE`.
- See `docs/RESEARCH_PACKAGE_REQUIREMENTS.md`.

## Research package integration (post–10.5)

- Prefer package-local `universe/membership.json|csv` for PIT; never invent membership.
- `LocalResearchPackageProvider` remains vendor-neutral; vendor parsing stays in import helpers.
- Certification derives eligibility from recomputed facts/`facts_hash` only.
- `make certify-research-package` for `QUANTFUND_RESEARCH_PACKAGE`.
- CI synthetic fixtures remain `DEVELOPMENT_ONLY`.

## Phase 12 — Controlled simulation paper

- Separate from the research→paper ladder: `controlled_paper_eligible` may be TRUE with
  `research_eligibility=DEVELOPMENT_ONLY` only after explicit human `PaperActivationRecord`
  (`LIVE_TRADING=FALSE`) and Phase 12 safety gates.
- yfinance / fixtures remain `source_grade=non_exchange` and never become `RESEARCH_ELIGIBLE`.
- Simulated orders/fills use `PaperExecutionAdapter` only (next-bar-open, RAW prices).
- Live broker order submission remains impossible on the Phase 12 path.
- See `docs/PHASE12_ARCHITECTURE.md`, `docs/PHASE12_PAPER_TRADING.md`, `docs/PHASE12_SAFETY.md`.

## Phase 13 — Controlled historical paper validation

- Multi-day yfinance-labeled historical replay through Phase 12 paper gates.
- Backtest ↔ paper drift expected `NONE` for identical inputs.
- Mode: `CONTROLLED_HISTORICAL_SIMULATION` (not live paper trading).
- See `docs/PHASE13_ARCHITECTURE.md`, `docs/PHASE13_PAPER_VALIDATION.md`, `docs/PHASE13_SAFETY.md`.

## Phase 14 — Real-time paper / shadow

- Live-data-shaped stream (simulated in CI) → paper or shadow modes.
- Fills only via `PaperExecutionAdapter`; shadow records `WOULD_*` only.
- yfinance provider remains `non_exchange` / not research-eligible.
- See `docs/PHASE14_ARCHITECTURE.md`, `docs/PHASE14_REALTIME_PAPER.md`, `docs/PHASE14_SAFETY.md`.

## Phase 15 — Real market data + read-only broker shadow

- Market-data adapter with capabilities/provenance; simulated fallback when unconfigured.
- Read-only broker adapter only (`place_order` / cancel / modify forbidden; fail-closed).
- Shadow produces `WOULD_ORDER` / optional `SIMULATED_ORDER`; `REAL_ORDER` impossible.
- Bad data → `DATA_BLOCKED`; reconciliation mismatch blocks new shadow decisions.
- See `docs/PHASE15_ARCHITECTURE.md`, `docs/REAL_MARKET_DATA.md`, `docs/BROKER_READ_ONLY.md`, `docs/PHASE15_SAFETY.md`, `docs/PHASE15_OPERATIONS.md`.

## Phase 16A — Real broker integration + live readiness

- Zerodha/Kite **read-only** adapter on `ReadOnlyBrokerAdapter` + GuardTransport.
- Live-readiness preflight always ends `LIVE_TRADING_DISABLED`.
- Order submission NOT IMPLEMENTED; write capabilities fail closed.
- See `docs/PHASE16A_ARCHITECTURE.md`, `docs/PHASE16A_BROKER.md`, `docs/PHASE16A_SAFETY.md`.

## Phase 16B — Controlled live canary

- Gated canary path extending Phase 16A Zerodha adapter; demos/CI use MOCK only.
- Real `place_order` only when LIVE_TRADING + ActivationRecord + all gates pass.
- No unrestricted autonomy; no auto scale; research eligibility unchanged.
- See `docs/PHASE16B_ARCHITECTURE.md`, `docs/PHASE16B_LIVE_CANARY.md`, `docs/PHASE16B_SAFETY.md`.

## Out of scope (still)

- Unrestricted autonomous live trading / portfolio-wide automation
- LLM API integration / autonomous strategy evolution / genetic search
- Options / futures strategies
- PostgreSQL, Redis, FastAPI, Docker, MLflow
- Automated capital deployment / automatic canary→full-live promotion
- Final strategy validation on development datasets
- Phase 17 (not started)

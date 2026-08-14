# Phase 8 Architecture — Paper Trading Infrastructure

**Status:** Approved (C8-1…C8-D, C8-A) and implemented. Live brokers remain out of scope.

Phase 7 established research-package contracts and eligibility certification. No licensed package is configured; synthetic/yfinance datasets remain `DEVELOPMENT_ONLY`. Phase 8 adds a **broker-independent paper-trading kernel** as a strict extension of Phases 0–7.

---

## 1. Non-negotiable constraints

| Constraint | Implication |
|------------|-------------|
| Do not weaken `ResearchEligibilityChecker` | Paper cannot invent research eligibility |
| `DEVELOPMENT_ONLY` → never paper acceptance claims | Demo: `paper_eligible = false` |
| No live trading / broker SDKs | `quantfund.execution/` stays empty of live adapters |
| No LLM / genetic / new generators | Reuse existing Strategy / StrategySpec only |
| Preserve next-bar-open in backtester | Paper may share fill *policy* IDs; must not alter `BacktestEngine` defaults |
| Preserve RAW-price execution | Paper marks/fills use RAW OHLC only |
| Strategy ↔ execution separation | Strategy never sees credentials, transport, or fill factory |
| Simulated capital only | No real money path |
| Deterministic replay | Same config + event stream → identical state |
| No `eval` / `exec` / dynamic imports / network from StrategySpec | Unchanged AI safety |
| No Postgres / Redis / Kafka / Ray / MLflow / Spark | SQLite + JSON/JSONL (+ Parquet if needed) |

---

## 2. Objective

Build a broker-independent paper kernel:

```
MarketDataEvent
      ↓
MarketDataValidator
      ↓
Strategy  (existing Strategy / StrategySpec → Signal / Order intents)
      ↓
OrderIntent  (paper-validated intent; maps to trading.Order)
      ↓
RiskEngine  (extended; never bypassed)
      ↓
PaperExecutionAdapter
      ↓
SimulatedOrder  (lifecycle state machine)
      ↓
SimulatedFill
      ↓
PositionLedger + CashLedger
      ↓
Portfolio / P&L
      ↓
Reconciliation + Audit
```

Paper trading is **not** research acceptance and **not** live trading.

```
research acceptance evidence
        ↓
paper eligibility gate
        ↓
paper session  (simulated capital)
        ↓
[FUTURE] live execution  (Phase N — out of scope)
```

---

## 3. Inventory of existing contracts (must reuse)

| Asset | Path | Reuse rule |
|-------|------|------------|
| `Signal`, `Order`, `Fill`, `Position` | `trading/models.py` | Canonical lifecycle types; do not fork parallel trade types for the same concepts |
| `Strategy`, `StrategyContext` | `strategies/base.py` | Only strategy I/O surface |
| `StrategySpec` / interpreter / validator | `strategies/spec/*` | Untrusted JSON → interpreter only |
| `RiskEngine`, `RiskConfig` | `risk/limits.py` | Independent risk; extend, do not bypass |
| `Portfolio` | `backtest/portfolio.py` | Accounting reference; paper ledgers must reconcile to same invariants |
| `BrokerSimulator`, costs, slippage | `backtest/broker_sim.py`, `costs.py` | Fill math reference; paper adapter may wrap/share models |
| `resolve_execution_models` | `research/execution_models.py` | Fail-closed cost/slippage IDs |
| `ResearchEligibilityChecker` | `data/eligibility.py` | Unchanged meanings |
| `CampaignAcceptancePolicy` | `research/acceptance.py` | `accepted_research_candidate` ≠ paper-eligible |
| `ExperimentRegistry` | `storage/registry.py` | SQLite + JSON (+ parquet) patterns |
| `CalendarProvider` / NSE calendar | `data/calendar/*` | Session open/closed |
| Quality / OHLC / identity checks | `data/quality/*`, `data/validate.py` | Event validation semantics |
| Dataset certification facts | `data/certification.py`, `data/policy.py` | Gate inputs |
| Package stub | `paper/__init__.py` | **Fill this package** — do not create a second paper namespace |
| Live stub | `execution/__init__.py` | Remains non-live in Phase 8 |

---

## 4. Conflicts with existing contracts (must resolve before coding)

### C8-1 — Order lifecycle vocabulary mismatch

**Existing (`OrderStatus`):**  
`PENDING → ACCEPTED → SCHEDULED → FILLED | REJECTED | CANCELLED`

**Requested Phase 8 example:**  
`CREATED → VALIDATED → ACCEPTED → PARTIALLY_FILLED → FILLED`  
(+ `REJECTED`, `CANCELLED`, `EXPIRED`)

**Conflict:** Renaming/replacing `OrderStatus` would break `BacktestEngine` and `RiskEngine`.

**Resolution (proposed):**

1. Keep `trading.OrderStatus` for backtest unchanged.
2. Introduce paper-only `PaperOrderStatus` in `paper/orders.py` with the richer state machine.
3. Maintain an explicit mapping table (see §7).
4. `SCHEDULED` in backtest ≡ paper `ACCEPTED` waiting for next-bar open event (paper may use `ACCEPTED` + `scheduled_execution_time` without inventing a second “scheduled” enum if `ACCEPTED` already means venue-accepted pending fill).

**Decision required:** Approve paper-local enum + mapping (recommended) vs. expanding shared `OrderStatus` (higher blast radius).

---

### C8-2 — `OrderIntent` vs existing `Order`

Strategies already emit `Order` intents (`strategies/base.py`: “intended Orders only”).

**Resolution (proposed):**

- `OrderIntent` = validated paper DTO wrapping / constructed from `trading.Order` plus paper metadata (`session_id`, `intent_id`, `validation_status`).
- Strategy continues to produce `Signal` / `Order` only.
- Paper kernel converts `Order → OrderIntent` after structural validation; strategy never constructs `SimulatedFill`.

---

### C8-3 — Who creates fills?

**Existing contract:** “Only the broker simulator may create Fill objects.”

**Resolution (proposed):**

- `PaperExecutionAdapter` is the **sole** fill factory in paper mode (analogous to `BrokerSimulator`).
- Prefer constructing frozen `trading.Fill` (or a thin `SimulatedFill` that embeds/aliases `Fill` fields) so portfolio accounting stays compatible.
- Strategies and risk must never import the fill factory.

---

### C8-4 — `BrokerSimulator` vs `PaperExecutionAdapter`

**Conflict:** Two simulators could diverge on slippage/costs/next-bar semantics.

**Resolution (proposed):**

- Extract shared fill policy functions **or** have `PaperExecutionAdapter` delegate next-bar-open MARKET fills to the same cost/slippage models used by research (`equity_delivery_v1`, `fixed_bps_*`).
- Do **not** put paper under `quantfund.execution` (reserved for future live brokers).
- Do **not** change `BacktestEngine` defaults.

---

### C8-5 — Kill switch exists but is incomplete

`RiskConfig.kill_switch: bool` already rejects all orders. Missing: auditable activation, explicit reset, session-scoped persistence.

**Resolution (proposed):**

- New `paper/kill_switch.py` owns state + audit events.
- `RiskEngine` / paper risk layer reads kill state (fail-closed).
- Reset requires explicit `KillSwitch.reset(reason, actor)` audited event — not a silent flag flip.
- Extend `RiskConfig` usage for paper sessions; do not remove the existing boolean (backtests may still set it).

---

### C8-6 — Determinism vs `uuid4` order/fill IDs

`Order.order_id` and `Fill.fill_id` default to `uuid4().hex` → non-replayable.

**Resolution (proposed):**

- Paper session injects deterministic IDs:  
  `hash(session_id, event_seq, symbol, side, quantity, signal_ts)` (or sequential counters from the event stream).
- Replay forbids relying on default factories.
- Backtest path may keep uuid defaults (out of Phase 8 scope) unless a later phase unifies.

---

### C8-7 — Partial fills

Existing `BrokerSimulator` is effectively all-or-nothing at next open.

**Resolution (proposed):**

- Paper fill policy enum: `all_or_nothing` (default, backtest-compatible) | `allow_partial` with explicit `max_fill_ratio` / liquidity stub.
- Partial fills require `PARTIALLY_FILLED` in paper state machine.
- Never silent ideal full fill when policy says partial.

---

### C8-8 — Portfolio / ledger duplication

`backtest.Portfolio` already tracks cash, positions, realized/unrealized PnL, fills.

**Resolution (proposed):**

- `PositionLedger` / `CashLedger` are paper append-only journals (event-sourced).
- `Portfolio` (or a paper facade) is the materialized view.
- Reconciliation compares journals ↔ materialization ↔ fills.
- Do not maintain a second conflicting PnL formula; reuse portfolio math or call into it.

---

### C8-9 — Risk limit vocabulary

| Phase 8 ask | Existing |
|-------------|----------|
| max position quantity | not present (value-based only) |
| max position notional | `max_position_value` |
| max order notional | `max_order_value` |
| max gross exposure | `max_total_exposure` |
| max daily loss | placeholder, **not enforced** |
| max turnover | absent |
| max number of orders | absent |

**Resolution (proposed):** Extend paper `PaperRiskConfig` (session-scoped) that **composites** `RiskEngine` checks and adds quantity/turnover/order-count/daily-loss. Platform ceilings are `min(strategy preference, platform config)` — risk may only reduce.

---

### C8-10 — Research acceptance ≠ paper eligibility

`CampaignAcceptancePolicy` yields `accepted_research_candidate` on research-eligible data. Docs already say accepted ≠ live.

**Resolution (proposed):** New gate `PaperEligibilityGate` in `paper/eligibility.py`:

```
requires ALL of:
  - dataset certified_eligibility ∈ {research_eligible, production_candidate}
  - ResearchEligibilityChecker would still pass on frozen facts_hash
  - strategy has acceptance evidence artifact (campaign acceptance record) OR explicit human paper-authorization record
  - paper config references those artifact IDs / hashes
  - strategy code/spec hash matches acceptance evidence
  - no DEVELOPMENT_ONLY / exploratory_development purpose
```

**Hard rule:** If dataset is `development_only` → `paper_eligible = false` regardless of backtest score.

Phase 8 demo dataset is synthetic → **must** print `Paper eligible: false`.

---

### C8-11 — Audit persistence: SQLite vs JSONL

Phase 6 uses append-only SQLite `campaign_events`. Phase 8 asks for JSON/JSONL audit.

**Resolution (proposed):**

- Primary paper audit: **JSONL** file per session (`sessions/{session_id}/audit.jsonl`) — append-only, hash-chained optional.
- Optional SQLite index table for query (`paper_sessions`, `paper_session_events` metadata) following registry philosophy.
- No DB server.

---

### C8-12 — AI_SAFETY / docs currently forbid paper

`docs/AI_SAFETY.md` and several phase docs state paper trading is forbidden / not started.

**Resolution (proposed):** On implementation, update docs to:

- Allow **kernel paper trading** under `quantfund.paper` with eligibility gate.
- Keep forbidding: AI-initiated paper sessions, live brokers, capital deployment.
- AI still cannot accept strategies or place orders.

---

### C8-13 — Multi-symbol / streaming scope

`BacktestEngine` is single-symbol M1 with supersede-pending behavior.

**Resolution (proposed):** Phase 8 v1 paper session supports **multi-symbol event stream** but demo may run one symbol. Document supersede/cancel policy per symbol. No intraday L2 book.

---

### C8-14 — Naming: “ledger”

Corporate-action ledger / terminal ledger / campaign trial ledger already use “ledger”.

**Resolution:** Use `PositionLedger` / `CashLedger` inside `paper/` only; avoid bare `Ledger` exports at package root.

---

## 5. Package layout (target)

```
src/quantfund/paper/
  __init__.py          # public exports; no broker imports
  models.py            # MarketDataEvent, session config, enums
  session.py           # PaperSession orchestration
  market_data.py       # MarketDataValidator
  orders.py            # OrderIntent, PaperOrderStatus state machine
  execution.py         # PaperExecutionAdapter (sim only)
  fills.py             # fill policy + SimulatedFill helpers
  portfolio.py         # ledgers + valuation facade
  risk.py              # PaperRiskConfig / PaperRiskEngine wrapping RiskEngine
  kill_switch.py       # auditable kill switch
  reconciliation.py    # fail-closed reconciler
  audit.py             # append-only JSONL (+ optional sqlite index)
  replay.py            # deterministic replay engine
  eligibility.py       # research → paper gate
```

Tests: `tests/unit/test_phase8_*.py` (≥50) + `scripts/run_phase8_demo.py` + `make phase8-demo`.

---

## 6. Component design

### 6.1 MarketDataEvent

Immutable event (bar-oriented v1):

| Field | Notes |
|-------|-------|
| `event_id` | Deterministic in recorded streams |
| `seq` | Monotonic per session stream |
| `timestamp` | Timezone-aware; Asia/Kolkata for NSE |
| `instrument_id` / `symbol` | Must resolve via instrument master when provided |
| `open, high, low, close, volume` | RAW |
| `session_date` | Calendar date |
| `source` | e.g. `replay`, `dataset_reader` |

No invented prices. Missing fields → reject event.

### 6.2 MarketDataValidator

Reject (fail-closed):

- unknown instruments (when master configured)
- duplicate `event_id` / `(symbol, timestamp)` 
- out-of-order `seq` or timestamps where ordering required
- stale events (`timestamp` older than watermark / max lag policy)
- events on closed calendar sessions
- invalid OHLC relationships / non-positive prices
- missing required fields

Uses existing `CalendarProvider` + OHLC rules aligned with `data/quality/checks.py` (do not weaken dataset quality; paper may be stricter on live-ish streams).

### 6.3 Strategy boundary

Unchanged:

```
StrategyContext → Signal → list[Order]
```

Paper session builds `StrategyContext` exactly as research does (history ≤ t, membership TRUE/FALSE/UNKNOWN).  
`UNKNOWN` / `FALSE` membership → no new risk-increasing orders (parity with SpecInterpretedStrategy).

Strategy modules must not import:

- `quantfund.paper.execution`
- `quantfund.paper.fills`
- `quantfund.execution`
- credentials / env broker keys

Enforced by architecture + tests (import linter or boundary unit tests).

### 6.4 OrderIntent + validation

Pipeline:

1. Structural validate `Order` (qty > 0, known side/type, symbol).
2. Wrap as `OrderIntent` with `CREATED`.
3. Transition → `VALIDATED` or `REJECTED`.
4. Risk → `ACCEPTED` or `REJECTED` (`risk_rejected` audit).
5. Execution adapter owns later transitions.

### 6.5 Paper order state machine

```
CREATED
  → VALIDATED
  → ACCEPTED
  → PARTIALLY_FILLED
  → FILLED

CREATED → REJECTED
VALIDATED → REJECTED
ACCEPTED → CANCELLED
ACCEPTED → EXPIRED
PARTIALLY_FILLED → FILLED
PARTIALLY_FILLED → CANCELLED   # residual cancel only; filled qty sticks
PARTIALLY_FILLED → EXPIRED
```

Invalid transitions raise / reject closed (no silent coerce).

Mapping to backtest statuses (documentation only):

| Paper | Backtest analogue |
|-------|-------------------|
| CREATED | PENDING |
| VALIDATED | PENDING (post structural) |
| ACCEPTED | ACCEPTED / SCHEDULED |
| PARTIALLY_FILLED | (new; N/A in M1 sim) |
| FILLED | FILLED |
| REJECTED | REJECTED |
| CANCELLED | CANCELLED |
| EXPIRED | CANCELLED + reason |

### 6.6 PaperExecutionAdapter + fill model

Configurable `PaperFillConfig`:

| Knob | Default |
|------|---------|
| `execution_mode` | `next_bar_open` |
| `slippage_model_id` | via `resolve_execution_models` (fail closed) |
| `cost_model_id` | via `resolve_execution_models` (fail closed) |
| `partial_fill_policy` | `all_or_nothing` |
| `reject_on_insufficient_cash` | true |
| `reject_on_insufficient_position` | true |
| `reject_on_market_closed` | true |
| `reject_on_stale_data` | true |

Never silently assume ideal fills.  
Market-closed / stale-data → reject with audited reason.

### 6.7 Position / cash / PnL

- **PositionLedger:** append `position_changed` records (delta, reason_fill_id).
- **CashLedger:** append cash deltas from fills (gross, costs, net).
- **Valuation:** mark at last validated RAW close (or explicit mark event).
- **Realized / unrealized:** same semantics as `backtest.Portfolio` (long-only).

### 6.8 Risk layer

`PaperRiskEngine`:

1. Query kill switch (reject all if active).
2. Delegate notional checks to existing `RiskEngine` where overlapping.
3. Enforce additional paper ceilings (qty, turnover, order count, daily loss).
4. May clip/reject only — never raise platform limits because strategy asked.

### 6.9 Kill switch

States: `ARMED` | `TRIGGERED`.

- `TRIGGERED`: all new orders → `REJECTED` / `risk_rejected` + `kill_switch_activated` (once) / subsequent `order_rejected`.
- Reset: explicit API with reason + actor; audit `kill_switch_reset`.
- Fail-closed on corrupted kill-switch store.

### 6.10 Reconciliation

Compare:

- sum(fill qty by symbol/side) vs position ledger deltas  
- cash ledger vs fill `net_cash_delta`  
- no negative cash if prohibited  
- no duplicate `fill_id` application  
- portfolio equity == cash + Σ mark·qty (within epsilon)

Failures → `reconciliation_failed` audit + session halt (fail closed).

### 6.11 Audit (append-only)

Required event types:

- `session_started`, `session_stopped`
- `market_event`
- `signal_generated`
- `order_created`, `order_rejected`, `order_accepted`
- `fill_generated`
- `position_changed`
- `risk_rejected`
- `kill_switch_activated` (+ `kill_switch_reset`)
- `reconciliation_failed`

Each record: `session_id`, `seq`, `ts`, `type`, `payload`, optional `prev_hash`.  
Files are append-only; mutation APIs absent.

### 6.12 Research → paper eligibility gate

```
Strategy artifact
    → load acceptance evidence (campaign decision / authorization)
    → load dataset certification (facts_hash, eligibility)
    → PaperEligibilityGate.evaluate()
    → allow PaperSession.start() only if paper_eligible
```

Scores alone never open a session.  
Synthetic Phase 8 demo: gate returns `paper_eligible=false`; demo still runs kernel **infrastructure** paths on a **sandbox mode** flag:

**Important product rule (decision C8-A):**

- **Production paper sessions** require `paper_eligible=true`.
- **Infra demo / CI** may run `PaperSession(mode="infrastructure_sandbox")` that exercises kernel, replay, risk, kill switch, reconciliation **without** claiming paper eligibility or acceptance.

Demo output must still show:

```
Research eligibility: DEVELOPMENT_ONLY
Paper eligible: false
```

Sandbox mode must be loud in audit (`session_mode=infrastructure_sandbox`) and cannot set `paper_eligible=true`.

### 6.13 Replay

```
recorded market events (JSONL)
    → ReplayEngine
    → identical signals / intents / fills / portfolio snapshot
```

Equality checked on canonical state hash (orders, fills, positions, cash, PnL).  
Non-determinism sources banned: wall-clock IDs, unordered dict iteration in hashed payloads, random slippage.

### 6.14 Persistence

| Artifact | Store |
|----------|-------|
| Session metadata | SQLite (`paper_sessions`) under registry root or `data/paper/` |
| Audit / events | JSONL |
| Final snapshot | JSON |
| Optional equity curve | Parquet only if bulk |

---

## 7. Interaction with BacktestEngine

| Concern | Rule |
|---------|------|
| next-bar-open | Paper default `execution_mode=next_bar_open` mirrors engine; engine code path unchanged |
| RAW prices | Paper marks/fills from RAW fields only |
| Costs/slippage | Shared model IDs; fail closed |
| Strategy API | Shared |
| Risk | Shared core + paper extensions |
| Eligibility | Dataset gate unchanged; paper gate additional |

Phase 8 must **not** refactor BacktestEngine into the paper session (avoid big-bang). Parallel kernel with shared models is intentional.

---

## 8. Demo contract

```
make phase8-demo
```

Expected console contract:

```
Paper trading kernel: PASS
Replay deterministic: true
Reconciliation: PASS
Risk controls: PASS
Kill switch: PASS
Research eligibility: DEVELOPMENT_ONLY
Paper eligible: false
Live trading: DISABLED
Broker: NONE
```

No profitability claims. No fabricated `RESEARCH_ELIGIBLE` or `paper_eligible=true`.

---

## 9. Test plan (≥50)

| Area | Examples |
|------|----------|
| Order state machine | Valid path; every invalid transition fails closed |
| Market data | Session closed; stale; duplicate; out-of-order; bad OHLC; unknown instrument |
| Risk | Each ceiling; clip/reject only reduces |
| Kill switch | Blocks orders; audit; reset required |
| Fills | Slippage; costs; partial; insufficient cash/position; market closed; stale |
| Accounting | Position/cash/realized/unrealized |
| Reconciliation | Mismatch cases; duplicate fills |
| Audit | Append-only; required event set |
| Replay | Bitwise/canonical equality |
| Eligibility | DEVELOPMENT_ONLY → false; high score irrelevant |
| Separation | Strategy cannot import execution/fills |
| Fail-closed | Exceptions → reject/halt, not silent continue |

---

## 10. Implementation order (after approval only)

1. Resolve §26 decisions  
2. `paper/models.py` + `orders.py` state machine  
3. `market_data.py` validator  
4. `kill_switch.py` + `risk.py`  
5. `fills.py` + `execution.py`  
6. `portfolio.py` ledgers  
7. `reconciliation.py` + `audit.py`  
8. `eligibility.py` gate  
9. `session.py` orchestration  
10. `replay.py`  
11. ≥50 tests  
12. `scripts/run_phase8_demo.py` + Makefile  
13. Doc updates (README, ASSUMPTIONS, AI_SAFETY)  

**Stop after Phase 8.** No live brokers.

---

## 11. Non-goals

- Broker SDKs / order routing / credentials  
- Live or paper *broker* accounts  
- LLM / genetic search  
- Weakening eligibility or fabricating research-grade data  
- Changing FeatureEngine / StrategySpec DSL semantics  
- Distributed infra  
- Claiming strategy profitability  

---

## 12. Risks

| Risk | Mitigation |
|------|------------|
| Dual simulators diverge | Shared cost/slippage IDs + parity tests |
| Pressure to paper-trade synthetic | Hard `paper_eligible=false`; sandbox mode labeled |
| UUID non-determinism | Deterministic ID policy in paper |
| Strategy reaches into execution | Import boundary tests |
| Silent ideal fills | Explicit fill policy; reject paths tested |
| Kill switch reset accidents | Audited reset with reason/actor |
| Scope creep into live `execution/` | Package remains empty of brokers |

---

## 26. Approval decisions required

Before implementation, please decide:

| ID | Decision | Recommendation |
|----|----------|----------------|
| **C8-1** | Paper-local `PaperOrderStatus` + mapping vs expand shared `OrderStatus` | **Paper-local + mapping** |
| **C8-2** | `OrderIntent` as wrapper around `trading.Order` | **Yes** |
| **C8-3** | Fill factory ownership | **`PaperExecutionAdapter` only** (reuse `trading.Fill` fields) |
| **C8-4** | Share cost/slippage model IDs with research | **Yes** — fail closed via `resolve_execution_models` |
| **C8-5** | Kill switch module + audited reset | **Yes** |
| **C8-6** | Deterministic paper IDs | **Yes** (hash/counter; no uuid defaults in paper path) |
| **C8-7** | Partial-fill policy in v1 | **Support both; default `all_or_nothing`** |
| **C8-8** | Ledgers event-source + Portfolio materialization | **Yes** |
| **C8-9** | Extend paper risk with qty/turnover/order-count/daily-loss | **Yes** |
| **C8-10** | Paper eligibility requires research-eligible dataset + acceptance evidence | **Yes**; scores never suffice |
| **C8-11** | Audit = JSONL (+ optional SQLite index) | **Yes** |
| **C8-A** | Infra sandbox demo may run kernel while `paper_eligible=false` | **Yes**, must be explicit in audit/output |
| **C8-B** | Touch `BacktestEngine`? | **No** functional changes in Phase 8 |
| **C8-C** | Multi-symbol session in v1 | **Yes** (events); demo may use one symbol |
| **C8-D** | Update AI_SAFETY to allow gated paper kernel (still ban AI order placement) | **Yes** on impl |

---

## 27. Stop conditions

This document is **design only**.

Do **not** implement Phase 8 until:

1. Conflicts C8-1 … C8-14 are accepted or amended, and  
2. Decisions C8-1 … C8-D / C8-A are explicitly approved.

Phase 8 implementation must end with the demo contract in §8 and **must not** start live trading.

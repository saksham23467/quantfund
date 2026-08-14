# Phase 9 Architecture — Live Trading Infrastructure (Broker Boundary)

**Status:** Approved (L1–L12, L5a–L5d recommended defaults) and implemented for **DRY_RUN + MockBroker only**. Real broker send remains forbidden.

Phase 8 delivered a broker-independent paper kernel with deterministic replay, reconciliation, risk, kill switch, and `PaperEligibilityGate`. Current datasets remain `DEVELOPMENT_ONLY`; `paper_eligible=false`; `broker=NONE`; `live trading=DISABLED`.

Phase 9 designs the **safe broker/execution boundary** for eventual controlled NSE equity live trading — without shipping a real broker SDK, real credentials, or real order submission in v1.

---

## 1. Non-negotiable constraints

| Constraint | Implication |
|------------|-------------|
| Do not weaken any Phase 0–8 eligibility gate | Research / paper meanings unchanged |
| `DEVELOPMENT_ONLY` → never live | `LiveTradingEligibilityGate` → `LIVE_BLOCKED` |
| Research acceptance ≠ live authorization | Separate evidence chain |
| Paper eligibility ≠ live authorization | Paper is necessary but not sufficient |
| Strategy never accesses a broker | No broker imports in strategy path |
| StrategySpec never contains broker ops | Spec validator remains allowlisted research ops |
| No credentials in Strategy / FeatureEngine / ResearchRunner / StrategySpec / Paper | Credentials only inside live adapter runtime |
| Paper and live share order/risk contract where practical | Same `OrderIntent` + risk composition pattern |
| Do not modify `BacktestEngine` for live | Parallel live session; backtest untouched |
| `PaperExecutionAdapter` remains available | Paper stays under `quantfund.paper` |
| No automatic paper → live | Explicit operator authorization artifact |
| No automatic capital scaling | Fixed ceilings; fail closed |
| No LLM / genetic search | Unchanged |
| No HFT / intraday stack unless already required | v1 remains daily / session-bar oriented like paper |
| No Postgres / Redis / Kafka / Ray / Spark | SQLite + JSON/JSONL |
| No real broker / real orders in Phase 9 v1 | `MockBrokerAdapter` + `DRY_RUN` only |

---

## 2. Objective

Design (and later implement, post-approval) an execution boundary:

```
              ACCEPTED STRATEGY ARTIFACT
                        │
                        ▼
               LiveTradingEligibilityGate
                        │
                        ▼
                 LiveSession (orchestrator)
                        │
            MarketDataEvent (normalized)
                        │
                        ▼
                 MarketDataValidator  (reuse Phase 8)
                        │
                        ▼
              Strategy → Signal → Order
                        │
                        ▼
                   OrderIntent
                        │
                        ▼
            LiveRiskEngine (wraps RiskEngine + KillSwitch)
                        │
                        ▼
               ExecutionGateway  (mode select only)
                  /            \
                 /              \
                ▼                ▼
    PaperExecutionAdapter    LiveBrokerAdapter
    (unchanged Phase 8)      (interface + Mock only in v1)
                                    │
                                    ▼
                            Broker / Exchange
                         (NOT in Phase 9 v1)
```

**Strategy must never know** which adapter is active. The gateway injects the adapter; strategy only sees `StrategyContext`.

Authorization ladder (never skip, never auto-promote):

```
dataset RESEARCH_ELIGIBLE / PRODUCTION_CANDIDATE
        ↓
accepted_research_candidate (+ sealed TEST evidence)
        ↓
paper_eligible + paper session evidence
        ↓
LiveTradingEligibilityGate → LIVE_AUTHORIZED | LIVE_BLOCKED
        ↓
operator approval artifact
        ↓
live session (DRY_RUN or — future — LIVE_SEND)
```

---

## 3. Inventory of existing contracts (must reuse)

| Asset | Path | Phase 9 rule |
|-------|------|--------------|
| `Signal`, `Order`, `Fill` | `trading/models.py` | Canonical internal models; translate broker DTOs ↔ these |
| `OrderStatus` (shared) | `trading/models.py` | **Do not expand** for live (Phase 8 lesson) |
| `PaperOrderStatus`, `OrderIntent` | `paper/orders.py` | Reuse intent + paper status machine; live adds broker-side projection |
| `RiskEngine` / `PaperRiskEngine` | `risk/limits.py`, `paper/risk.py` | Compose; never bypass |
| `KillSwitch` | `paper/kill_switch.py` | Extend triggers; shared fail-closed semantics |
| `PaperExecutionAdapter` | `paper/execution.py` | Remains paper-only fill factory |
| `PaperEligibilityGate` | `paper/eligibility.py` | Prerequisite evidence; not sufficient for live |
| `MarketDataEvent` / `MarketDataValidator` | `paper/models.py`, `paper/market_data.py` | Live MD adapter normalizes **into** these |
| `CalendarProvider` / NSE calendar | `data/calendar/*` | **Reuse only** — no second calendar |
| `CampaignAcceptancePolicy` | `research/acceptance.py` | Research accept ≠ live |
| `ResearchEligibilityChecker` | `data/eligibility.py` | Unchanged |
| `PaperAuditLog` | `paper/audit.py` | Extend event types; same append-only JSONL pattern |
| `execution/` stub | `execution/__init__.py` | **Home of live boundary** (interface + mock + dry-run) |
| `BacktestEngine` | `backtest/engine.py` | Untouched |

---

## 4. Conflicts with Phases 0–8 (must resolve before coding)

### P9-C1 — Package ownership: live vs paper

**Conflict:** Phase 8 reserved `quantfund.execution/` for live and kept paper under `quantfund.paper/`.

**Resolution (proposed):**  
- Live interfaces, gateway, mock broker, dry-run, live eligibility → `quantfund.execution/`  
- Paper kernel remains in `quantfund.paper/`  
- Shared types stay in `trading/`, `risk/`, `data/calendar/`  
- Do **not** put live broker code inside `paper/`

---

### P9-C2 — Dual order-status vocabularies

**Existing:** shared `OrderStatus` + paper-local `PaperOrderStatus` (approved C8-1).

**Live needs:** broker ack states including `UNKNOWN`, disconnect, etc.

**Resolution (proposed):** Introduce **live-local** `BrokerOrderState` (and optionally `LiveOrderProjection`) mapping:

| Internal (`PaperOrderStatus` / intent) | Broker projection |
|----------------------------------------|-------------------|
| CREATED / VALIDATED | LOCAL_ONLY |
| ACCEPTED (submitted) | SUBMITTED / ACK_PENDING |
| ACCEPTED (acked) | OPEN / WORKING |
| PARTIALLY_FILLED | PARTIALLY_FILLED |
| FILLED | FILLED |
| REJECTED | REJECTED |
| CANCELLED / EXPIRED | CANCELLED / EXPIRED |
| — | **UNKNOWN** (never mapped to FILLED) |

Do **not** modify shared `OrderStatus`.

---

### P9-C3 — Fill factory ownership (three modes)

**Existing docs:** historically “only BrokerSimulator”; Phase 8 extended to `PaperExecutionAdapter`.

**Resolution (proposed):** Document three mode-scoped factories:

| Mode | Sole fill / ack factory |
|------|-------------------------|
| Backtest | `BrokerSimulator` |
| Paper | `PaperExecutionAdapter` |
| Live | `LiveBrokerAdapter` (via gateway) |

Strategies never call any of them.

---

### P9-C4 — Determinism vs live broker IDs

**Conflict:** Paper IDs are deterministic hashes; broker IDs are external and non-replayable in the paper sense.

**Resolution (proposed):**  
- Internal `client_order_id` remains deterministic from stable inputs (session, intent, retry epoch).  
- Broker `broker_order_id` stored as correlation only.  
- Live “deterministic behavior” means: same mock scenario + config → same decisions; **not** bit-identical to paper replay across a real broker.  
- State hash for live recovery excludes secrets and wall-clock; includes internal IDs + last known broker projection.

---

### P9-C5 — Long-only / MARKET-only contract

**Existing:** shorts rejected; `OrderType.MARKET` only; float qty without lot-size.

**Resolution (proposed) for Phase 9 v1:**  
- Keep **long-only** and **MARKET-only** unless a later decision expands `OrderType`.  
- Capabilities declare `limit_orders=false`, `short_selling=false`.  
- Fractional qty: capability `fractional_quantity`; if broker false → fail closed (reject) rather than silent round unless an explicit lot-rounding policy is approved later.  
- NSE lot/tick rules: **out of v1** except as capability blockers.

---

### P9-C6 — Paper session membership hardcode

**Conflict:** `PaperSession` currently sets `membership="TRUE"`; research Spec path respects UNKNOWN.

**Resolution (proposed):** Live session design must pass real membership (TRUE/FALSE/UNKNOWN) into `StrategyContext`. UNKNOWN/FALSE → no risk-increasing orders (parity with SpecInterpretedStrategy). Fix paper parity in a separate non-weakening follow-up if needed — do not weaken live.

---

### P9-C7 — Kill switch: freeze vs flatten

**Conflict:** Phase 8 kill switch rejects **new** orders; does not liquidate.

**Resolution (proposed) — default for L12:**  
- Kill switch → **BLOCK new orders** + freeze (no automatic emergency flatten in v1).  
- Emergency flatten is a **separate, explicitly authorized** procedure (not auto on kill).  
- Documented in L12; do not implement auto-liquidation without approval.

---

### P9-C8 — Documentation / AI_SAFETY currently forbid live

**Resolution (proposed):** On implementation approval, update README / ASSUMPTIONS / AI_SAFETY parallel to Phase 8: allow **gated** live boundary with Mock + DRY_RUN; forbid AI-initiated live, real credentials in repo, and real send in Phase 9 v1 demo.

---

### P9-C9 — `ExecutionGateway` vs second orchestrator

**Risk:** Gateway becomes a competing `PaperSession`.

**Resolution (proposed):**  
- `LiveSession` owns orchestration (mirror `PaperSession` shape).  
- `ExecutionGateway` is a **thin adapter selector + submit/cancel façade** after risk acceptance — not a second strategy loop.  
- Shared helpers may be extracted later; **do not** refactor `BacktestEngine` into the gateway.

---

### P9-C10 — Credentials vs config files

**Conflict:** Experiment configs / campaign JSON are persisted; must never hold secrets.

**Resolution:** Credential provider interface reads env / OS secret store only inside live adapter process. Config may hold `credential_ref` names (e.g. env var keys), never secret values.

---

## 5. Target package layout (post-approval implementation)

```
src/quantfund/execution/
  __init__.py
  gateway.py              # ExecutionGateway (paper | live | dry_run)
  broker_adapter.py       # BrokerAdapter Protocol + request/response models
  capabilities.py         # BrokerCapabilities
  live_orders.py          # BrokerOrderState, client_order_id, idempotency store
  live_risk.py            # LiveRiskConfig / LiveRiskEngine (compose PaperRiskEngine)
  live_kill_switch.py     # extended triggers (or extend paper KillSwitch)
  live_eligibility.py     # LiveTradingEligibilityGate
  live_session.py         # LiveSession orchestrator
  market_data_live.py     # LiveMarketDataAdapter → MarketDataEvent
  reconciliation_live.py  # broker vs internal reconcile
  recovery.py             # restart / reconcile / BLOCKED
  dry_run.py              # DRY_RUN transport (validate, do not send)
  mock_broker.py          # MockBrokerAdapter
  credentials.py          # CredentialProvider (env); redaction helpers
  audit_live.py           # extend audit event types (or reuse PaperAuditLog)
```

Tests: `tests/unit/test_phase9_*.py` (≥60)  
Demo: `scripts/run_phase9_demo.py` + `make phase9-demo`  
**Real broker SDK: forbidden in Phase 9 v1.**

---

## 6. Component design

### 6.1 BrokerAdapter interface

```text
BrokerAdapter
  connect() -> BrokerHealth
  disconnect() -> None
  health() -> BrokerHealth
  submit_order(SubmitOrderRequest) -> SubmitOrderResponse
  cancel_order(CancelOrderRequest) -> CancelOrderResponse
  get_order(GetOrderRequest) -> BrokerOrderView
  get_open_orders(GetOpenOrdersRequest) -> list[BrokerOrderView]
  get_positions() -> list[BrokerPositionView]
  get_cash() -> BrokerCashView
  reconcile(ReconcileRequest) -> BrokerReconcileSnapshot
```

**Rules:**
- Request/response models are internal Pydantic/dataclass types.
- Never return raw SDK objects.
- Map broker enums → `BrokerOrderState` / internal fills.
- Unsupported capability → fail closed (`CapabilityError`), never silent emulate.

### 6.2 Canonical request/response (sketch)

| Model | Key fields |
|-------|------------|
| `SubmitOrderRequest` | `client_order_id`, `symbol`, `instrument_id`, `side`, `quantity`, `order_type`, `session_id`, `intent_id`, `idempotency_key` |
| `SubmitOrderResponse` | `client_order_id`, `broker_order_id?`, `state`, `reject_reason?`, `raw_ref_hash?` (no secrets) |
| `BrokerOrderView` | ids, state, filled_qty, avg_price?, updated_at |
| `BrokerPositionView` | symbol / instrument_id, qty, avg_price? |
| `BrokerCashView` | cash, currency, as_of |
| `BrokerHealth` | connected, degraded, reason, server_time? |

### 6.3 BrokerCapabilities

```text
BrokerCapabilities
  market_orders: bool
  limit_orders: bool
  cancel_orders: bool
  partial_fills: bool
  fractional_quantity: bool
  short_selling: bool
  order_status_stream: bool
  position_query: bool
  cash_query: bool
  idempotency: bool
```

Phase 9 v1 Mock defaults: market_orders=true, cancel=true, partial_fills=true, position/cash query=true, idempotency=true; limit/short/fractional=false (match platform long-only MARKET contract unless later approved).

Gateway checks capabilities **before** submit.

### 6.4 Order state reconciliation

Triangulation:

```
OrderIntent (internal)
    ↔ BrokerOrderView (broker)
    ↔ Fill records (internal)
    ↔ PositionLedger / broker positions
    ↔ CashLedger / broker cash
```

Rules:
- `UNKNOWN` / disconnected **≠ FILLED**
- `ACK_PENDING` after timeout → **do not resubmit** until `get_order` / reconcile resolves
- Unexpected fill → kill switch candidate + BLOCK
- Position/cash mismatch → BLOCK new orders

### 6.5 Idempotency (mandatory)

Problem:

```
submit → timeout → unknown if accepted → naive retry → duplicate live order
```

Design:

1. Every live submit has deterministic `client_order_id` =  
   `hash(session_id, intent_id, submit_epoch)`  
   where `submit_epoch` increments only after a **terminal** local decision that the prior attempt is confirmed absent/rejected.
2. Persist local idempotency record **before** network call:  
   `{client_order_id, intent_id, state: PENDING_SUBMIT|SUBMITTED|ACKED|FAILED, broker_order_id?}`.
3. On timeout / disconnect:  
   - Query `get_order(client_order_id)` / open orders  
   - If found → adopt broker id; never second submit  
   - If confirmed absent → may open new epoch **only** after explicit reconcile policy  
   - If still UNKNOWN → **BLOCK** (no blind retry)
4. Brokers without idempotency capability → **LIVE_BLOCKED** for send mode (DRY_RUN may still exercise validation).

### 6.6 Credentials

```
Strategy / Research / Paper / Spec / Features  →  ❌ credentials
CredentialProvider (env / secret store)       →  ✅ only into LiveBrokerAdapter runtime
```

- Config may reference `QUANTFUND_BROKER_API_KEY_ENV=...` style refs.
- Never commit secrets; never log; never put in audit payloads, experiment JSON, or campaign artifacts.
- Redaction helper mandatory for any debug dumps.
- Phase 9 v1 Mock uses **no live credentials**; dry-run must not require real secrets.

### 6.7 LiveTradingEligibilityGate

Produces:

```text
LIVE_AUTHORIZED | LIVE_BLOCKED
+ machine-readable blockers[]
```

**Required evidence (all must pass for AUTHORIZED):**

| Evidence | Notes |
|----------|-------|
| Research eligibility | `research_eligible` or `production_candidate` via certification facts / checker |
| Accepted research experiment | acceptance evidence id + sealed TEST (exactly-once semantics from Phase 6) |
| Robustness | campaign robustness requirements satisfied (reuse acceptance policy fields) |
| Paper-trading evidence | prior paper session artifact ids / reconciliation PASS / not sandbox-only claim of “paper eligible” without evidence |
| `paper_eligible` historical truth | cannot jump research → live skipping paper evidence |
| Broker configuration | adapter id, capabilities meet platform minimum |
| Risk configuration | live ceilings ≤ platform safety limits |
| Operator approval | signed/recorded approval artifact (human); not AI |
| Kill-switch readiness | armed, reset procedure documented, triggers configured |
| Mode | `DRY_RUN` may run mock path while still `LIVE_BLOCKED` for real send; **real send** requires AUTHORIZED + `LIVE_SEND` flag (future; disabled in Phase 9 v1) |

**Hard blockers:**

- `certified_eligibility=development_only` → always `LIVE_BLOCKED`
- Missing sealed TEST / acceptance evidence → BLOCKED
- Paper eligibility failure / missing paper evidence → BLOCKED
- Research acceptance alone → BLOCKED
- Infrastructure sandbox / demo mode → cannot claim LIVE_AUTHORIZED for real send

No scores, PnL, or AI output may authorize live.

### 6.8 Capital limits (hierarchy)

```
strategy preference
      ≤
session limit (live/paper config)
      ≤
account limit (broker/account policy)
      ≤
platform safety limit (hardcoded / ops config)
```

Strategy can never raise any ceiling. Risk may only reduce.

Ceilings (live session):

- max order notional  
- max position notional  
- max gross exposure  
- max daily loss  
- max turnover  
- max number of orders  
- max capital allocation (session notional / cash at risk)

Compose with existing `RiskEngine` + paper-style extensions (`LiveRiskEngine`).

### 6.9 Kill switch (extended)

Reuse Phase 8 auditable ARMED / TRIGGERED + explicit reset.

**Additional automatic trigger candidates (design):**

| Trigger | Default action |
|---------|----------------|
| Manual operator | TRIGGERED |
| Daily loss breach | TRIGGERED |
| Stale market data | TRIGGERED |
| Broker disconnect | TRIGGERED |
| Reconciliation failure | TRIGGERED |
| Unexpected position | TRIGGERED |
| Unexpected fill | TRIGGERED |
| Risk-engine failure / exception | TRIGGERED |
| Repeated order rejection | TRIGGERED (threshold) |
| Clock / session failure | TRIGGERED |

Once TRIGGERED: **new orders = BLOCKED**.

**Position policy (v1 recommendation — L12):** freeze only; **no automatic emergency flatten**. Flattening requires separate approved playbook + operator command in a later phase.

### 6.10 Live market-data boundary

`LiveMarketDataAdapter` (interface + mock feed in v1):

- Normalize vendor ticks/bars → `MarketDataEvent`
- Validate via existing `MarketDataValidator` + `CalendarProvider`
- Reject: bad timestamp, unknown symbol, closed session, bad OHLC, stale, duplicate, out-of-order, halt/closed
- Never invent prices
- Trading halt → BLOCK new orders (kill or session halt)

No second calendar implementation.

### 6.11 Clock and session safety

- Reuse verified NSE calendar for holidays / weekends / special sessions  
- Reject pre-open / post-close submissions per session rules  
- Detect clock drift vs broker/server time when available (threshold → BLOCK)  
- Timezone: Asia/Kolkata for NSE session dates  
- Unexpected early close: treat as session closure; cancel/expire working intents per policy; BLOCK new

### 6.12 Position / cash / order reconciliation

**Before enabling new live orders** (and on a schedule / reconnect):

```
internal positions  ↔ broker positions
internal cash       ↔ broker cash
internal open intents ↔ broker open orders
```

Any unexplained difference → `reconciliation_failed` + kill/BLOCK.

### 6.13 Failure modes (default: uncertainty → stop)

| Failure | Behavior |
|---------|----------|
| Broker timeout on submit | Mark ACK_PENDING; query; no blind retry |
| Broker rejects | Intent REJECTED; audit; count toward repeated-reject trigger |
| Connection lost after submit | Disconnect trigger; reconcile on reconnect |
| Stale order status | BLOCK until resolved |
| Duplicate broker response | Idempotent apply; detect double-fill |
| Partial fill | Update projection; ledger once per fill id |
| Unknown order | BLOCK; never assume FILLED |
| Unexpected fill | TRIGGER kill; BLOCK |
| Position / cash mismatch | BLOCK |
| Market-data outage | TRIGGER / halt |
| Process / machine restart | Recovery protocol (§6.14) |
| SQLite / audit corruption | BLOCK; fail closed; no silent repair |

### 6.14 Restart / recovery

```
process dies
   ↓
restart
   ↓
load local session + idempotency store + ledgers
   ↓
connect broker (or mock)
   ↓
reconcile positions / cash / open orders
   ↓
match client_order_id ↔ broker_order_id
   ↓
RECOVERED (armed) OR remain BLOCKED
```

Never assume previous orders/fills were absent. Resume trading only after reconcile PASS + kill switch ARMED + (if required) operator ack.

### 6.15 Audit (append-only; no secrets)

Extend Phase 8 JSONL audit with at least:

- `live_session_started` / `live_session_stopped`
- `authorization_granted` / `authorization_denied`
- `broker_connected` / `broker_disconnected`
- `order_submitted` / `broker_acknowledged` / `broker_rejected`
- `fill_received`
- `reconciliation_started` / `reconciliation_failed` / `reconciliation_passed`
- `kill_switch_activated`
- (retain Phase 8 signal/order/risk events as applicable)

Payloads: ids, states, notionals, reasons — **never** credentials, tokens, or raw secret-bearing headers.

### 6.16 DRY_RUN mode (mandatory)

Distinct from Phase 8 paper simulation:

| Mode | Meaning |
|------|---------|
| Paper (`PaperExecutionAdapter`) | Simulated fills; no broker protocol |
| `DRY_RUN` | Build real `SubmitOrderRequest`s; validate capabilities/risk/idempotency; **transport suppressed**; mock may optionally echo |
| `LIVE_SEND` | Real network submit — **disabled / unimplemented in Phase 9 v1** |

Demo and CI use DRY_RUN + Mock only. `Real Orders Sent: 0` is a hard assertion.

### 6.17 MockBrokerAdapter

Supports scripted:

- deterministic fills  
- rejection  
- timeout / ACK_PENDING  
- partial fills  
- disconnect  
- unknown order state  
- reconciliation mismatches  

No real broker SDK/API dependency in Phase 9 v1.

---

## 7. Strategy / Spec isolation (tests must enforce)

Forbidden imports from strategy / Spec interpreter path:

- `quantfund.execution.broker_adapter`
- `quantfund.execution.mock_broker`
- `quantfund.execution.credentials`
- any live transport

StrategySpec schema must not gain broker fields (`broker`, `api_key`, `submit_order`, etc.).

---

## 8. Demo contract (implementation phase)

```
make phase9-demo
```

Expected:

```
Phase 9 Architecture: PASS
Mock Broker: PASS
Dry Run: PASS
Idempotency: PASS
Reconciliation: PASS
Kill Switch: PASS
Authorization Gate: PASS
Research Eligibility: DEVELOPMENT_ONLY
Live Authorization: BLOCKED
Real Broker: NONE
Real Orders Sent: 0
Claims: NONE
```

No profitability claims. No real orders.

---

## 9. Test plan (≥60) — for post-approval implementation

| Area | Cases |
|------|-------|
| Adapter contract | connect/disconnect/health/submit/cancel/get_* |
| Capabilities | unsupported → fail closed |
| Idempotency | timeout → no duplicate; epoch rules |
| Unknown state | ≠ FILLED |
| Reconciliation | position/cash/order mismatch → BLOCK |
| Market data | stale/duplicate/OOO/bad OHLC/closed session |
| Session/clock | holiday/weekend/pre-open/post-close |
| Kill switch | each trigger class; new orders blocked |
| Capital hierarchy | strategy cannot raise ceilings |
| Restart recovery | recover vs BLOCKED |
| Credential isolation | strategy/research/paper cannot read secrets; audit redaction |
| Dry-run | requests built; send count 0 |
| Mock broker | reject/timeout/partial/disconnect/mismatch |
| Authorization | DEVELOPMENT_ONLY → BLOCKED; paper fail → BLOCKED; accept alone → BLOCKED |
| Separation | strategy cannot import broker |
| Fail-closed | exceptions → BLOCK |

---

## 10. Implementation order (after L1–L12 approval only)

1. Models: capabilities, broker DTOs, `BrokerOrderState`, idempotency store  
2. `BrokerAdapter` protocol + `MockBrokerAdapter`  
3. `DRY_RUN` transport  
4. `LiveTradingEligibilityGate`  
5. `ExecutionGateway` + wire to existing paper adapter for paper mode  
6. `LiveRiskEngine` + kill-switch trigger matrix (freeze-only)  
7. Live MD adapter → existing validator/calendar  
8. Live reconciliation + recovery  
9. `LiveSession`  
10. Audit extensions  
11. ≥60 tests  
12. `make phase9-demo`  
13. Doc updates (README, ASSUMPTIONS, AI_SAFETY)  

**Stop after Phase 9.** Do not start real broker integration (Phase 10+) without a new design approval.

---

## 11. Explicit non-goals (Phase 9 v1)

- Real broker SDK / exchange connection / real order submission  
- Real credentials / live capital  
- Automatic strategy promotion or capital scaling  
- LLM / genetic search  
- Options / futures  
- Shorting (unless a later decision changes long-only — **not** Phase 9 v1)  
- Limit-order productization  
- HFT / L2 / intraday microarchitecture  
- Automatic emergency liquidation  
- Distributed infra  

---

## 12. Risks

| Risk | Mitigation |
|------|------------|
| Pressure to “just wire Zerodha/IB” | v1 Mock + DRY_RUN only; demo asserts 0 real orders |
| Blind retries | Idempotency store + UNKNOWN → BLOCK |
| Paper/live semantic drift | Shared OrderIntent + risk composition; parity tests |
| Secret leakage | CredentialProvider + audit redaction tests |
| Auto-flatten disasters | L12 freeze-only default |
| Eligibility collapse | Separate Live gate; DEVELOPMENT_ONLY hard block |
| Gateway god-object | Thin façade; LiveSession owns loop |

---

## 26. Approval decisions required (L1–L12)

Before any Phase 9 implementation, please decide:

| ID | Decision | Recommendation |
|----|----------|----------------|
| **L1** | Broker interface shape (`connect/submit/cancel/get_*/reconcile`) as in §6.1 | **Approve as specified** |
| **L2** | `BrokerCapabilities` fail-closed (no silent emulate) | **Yes** |
| **L3** | Idempotency via deterministic `client_order_id` + pre-submit local record; no blind retry on UNKNOWN | **Yes** |
| **L4** | Credentials only via env/secret provider inside live adapter; never in Spec/research/paper/artifacts/logs | **Yes** |
| **L5** | Separate `LiveTradingEligibilityGate`; research accept ≠ paper ≠ live; DEVELOPMENT_ONLY → LIVE_BLOCKED | **Yes** |
| **L6** | Capital hierarchy strategy ≤ session ≤ account ≤ platform; strategy cannot raise | **Yes** |
| **L7** | Kill switch extended triggers; new orders BLOCKED | **Yes** |
| **L8** | Reconciliation of positions/cash/open orders before enabling new orders; mismatch → BLOCK | **Yes** |
| **L9** | Restart recovery: load local → query broker → reconcile → RECOVERED or BLOCKED | **Yes** |
| **L10** | Mandatory `DRY_RUN` distinct from paper sim; Phase 9 demo never sends real orders | **Yes** |
| **L11** | Phase 9 v1 implements `BrokerAdapter` + `MockBrokerAdapter` only (no real SDK) | **Yes** |
| **L12** | Emergency flattening on kill switch | **Freeze only in v1 — no automatic flatten** (separate future approval for flatten playbook) |

Additional scoped defaults (call out if rejecting):

| ID | Topic | Recommendation |
|----|-------|----------------|
| **L5a** | Live session home package | `quantfund.execution/` |
| **L5b** | Order status approach | Live-local `BrokerOrderState`; do not modify shared `OrderStatus` |
| **L5c** | Order types in v1 | MARKET + long-only only |
| **L5d** | `LIVE_SEND` | Disabled / unimplemented in Phase 9 v1 |

---

## 27. Stop conditions

This document is **design only**.

Do **not** implement Phase 9 until **L1–L12** (and L5a–L5d if contested) are explicitly approved.

Do **not** add real broker SDKs, real credentials, or real order submission under the guise of “just a spike.”

Phase 9 implementation (when approved) must end with the demo contract in §8 and **Real Orders Sent: 0**.

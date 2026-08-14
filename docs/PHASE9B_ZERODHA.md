# Phase 9B — Zerodha Kite Connect Integration

**Status:** Broker adapter + safe execution testing layer.  
**Not in scope:** Unrestricted live trading, research-eligibility promotion, Strategy/AI broker access, Phase 10.

## Architecture

```text
Strategy  →  RiskEngine  →  ExecutionIntent  →  ExecutionRouter
                                              ├── PaperExecutionAdapter  (unchanged)
                                              └── ZerodhaExecutionAdapter
                                                        ↓
                                                   Kite Connect
```

- Strategy never knows paper vs Zerodha.
- StrategySpec / AI / ResearchRunner must not import `quantfund.brokers`.
- Existing Phase 9 `ExecutionGateway` remains **DRY_RUN + MockBroker only**.
- Phase 9B Zerodha path is a **separate** guarded router (`ExecutionRouter`).

## Four separate gates

| Gate | Question |
|------|----------|
| Research eligibility | Can this historical dataset support trustworthy research? |
| Broker connectivity | Can QuantFund talk to Zerodha? |
| Paper eligibility | Can a validated strategy run in paper? |
| Live eligibility | Has a human explicitly authorized real-money execution? |

**Broker connectivity must NEVER promote `DEVELOPMENT_ONLY → RESEARCH_ELIGIBLE`.**

## Execution modes

| Mode | Default | Behavior |
|------|---------|----------|
| `OFF` | **YES** | No broker send path |
| `SIMULATION` | no | Paper / mock only |
| `BROKER_SANDBOX` | no | Sandbox credentials only; guarded sends |
| `BROKER_LIVE` | no | Requires multi-gate human confirmation |

Never use a single `LIVE=true` switch.

`BROKER_LIVE` requires **all** of:

1. `QUANTFUND_EXECUTION_MODE=BROKER_LIVE`
2. `QUANTFUND_LIVE_TRADING_CONFIRM=I_UNDERSTAND_REAL_MONEY`
3. Risk limits configured
4. Kill switch initialized (not triggered)
5. Broker health OK
6. Strategy explicitly broker-approved
7. `ZERODHA_ENV=production` with production credentials only

## Environment variables

| Variable | Purpose |
|----------|---------|
| `ZERODHA_API_KEY` | API key (never logged) |
| `ZERODHA_API_SECRET` | API secret (never logged / never git) |
| `ZERODHA_ACCESS_TOKEN` | Session access token (never logged) |
| `ZERODHA_ENV` | `sandbox` \| `production` |
| `QUANTFUND_EXECUTION_MODE` | `OFF` \| `SIMULATION` \| `BROKER_SANDBOX` \| `BROKER_LIVE` |
| `QUANTFUND_LIVE_TRADING_CONFIRM` | Must equal `I_UNDERSTAND_REAL_MONEY` for live |

Sandbox credentials must not be used when `ZERODHA_ENV=production` and vice versa.

## Authentication

Official Kite flow: `api_key` → login → `request_token` → checksum/token exchange → `access_token`.

Access tokens are never written to Git, SQLite research DBs, experiment artifacts, logs, or reports unless an explicitly encrypted secret store is introduced (not in Phase 9B).

## Order lifecycle

Internal broker states (do **not** change `trading.OrderStatus`):

`CREATED → SUBMITTED → OPEN → PARTIALLY_FILLED → FILLED`  
also: `CANCEL_PENDING`, `CANCELLED`, `REJECTED`, `EXPIRED`, `UNKNOWN`

- Successful `place_order` ≠ fill.
- Fills created only from broker trade/order responses.
- Partial / multi-chunk trades preserved.
- Unknown Kite statuses → `UNKNOWN` → reconciliation required.

Supported initially: NSE equity, BUY/SELL, MARKET/LIMIT, CNC, DAY.  
Unsupported (fail closed): derivatives, GTT, multi-leg.

## Idempotency

Every intent has `execution_intent_id`. Before submit, check for an existing broker order for that intent. If present, **never** submit again. Persist intent ↔ broker_order_id ↔ trade ids.

## Reconciliation

`BrokerReconciler` compares local expected vs Zerodha actual:

`MATCH | LOCAL_MISSING | BROKER_MISSING | QUANTITY_MISMATCH | PRICE_MISMATCH | STATUS_MISMATCH | UNKNOWN`

Mismatches are visible and **never** silently repaired.

## LiveExecutionGuard

Before every broker order:

1. Connection healthy  
2. Kill switch OFF  
3. Instrument allowed  
4. Quantity / notional / daily order count / daily loss / turnover / position limits  
5. Duplicate intent blocked  
6. Session valid  
7. Mode is `BROKER_SANDBOX` or (fully gated) `BROKER_LIVE`

Any failure → **do not send**.

## Market data vs research

`ZerodhaMarketDataAdapter` (instruments, LTP, quote, ticks, daily candles) is **not** a substitute for `DatasetReader`. Broker market data does not certify research packages.

## Tick recording & paper replay

Immutable append-only recordings under `data/live_recordings/` with checksums.  
`BrokerReplaySource` feeds recordings into `PaperExecutionAdapter` for no-money stack tests.

## Failure modes & recovery

| Failure | Response |
|---------|----------|
| Network timeout after place | Do not retry blindly; reconcile by intent id |
| UNKNOWN status | Block new submits for intent; reconcile |
| Credential mismatch env | Fail closed |
| Kill switch | Block all sends |
| Reconcile mismatch | Surface; do not auto-fix |

## Emergency shutdown

1. Activate kill switch (`LiveExecutionGuard` / paper `KillSwitch`)  
2. Set `QUANTFUND_EXECUTION_MODE=OFF`  
3. Disconnect adapter  
4. Run reconciliation (read-only)  
5. Do **not** auto-cancel/rebook without human review  

## Demo contract

`make phase9b-demo`:

- Default mode `OFF`
- Live trading `DISABLED`
- Research eligibility `DEVELOPMENT_ONLY`
- Paper eligibility `FALSE`
- Claims `NONE`
- May perform **read-only** calls if credentials configured
- **Never** places a real-money order from the demo

## Broker limitations (Kite)

- Async order state changes; place ≠ execute  
- Multi-trade fills possible  
- Sandbox ≠ production behavior  
- Rate limits / session expiry apply  

Do **not** document a procedure for automatically enabling unrestricted live trading.

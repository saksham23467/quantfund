# Phase 14 — Real-Time Paper vs Shadow

## PAPER (`REAL_TIME_PAPER`)

1. Receive bar
2. Compute features ≤ T
3. Strategy signal
4. Risk check
5. Simulated order via paper path
6. Next-bar-open simulated fill
7. Portfolio / P&L update
8. Journal + reconcile

## SHADOW

1–4 same as paper  
5. Record `WOULD_ORDER` / `WOULD_REJECT`  
6. Optionally record `WOULD_FILL` estimate  
7. **No** cash/position mutation  
8. **No** broker calls

## Session states

`PRE_MARKET → OPEN → TRADING → CLOSING → CLOSED` (+ `HALTED`)

Executable paper orders only in allowed trading windows derived from the
existing calendar + NSE equity session hours (Asia/Kolkata).

## Freshness

If `data_age > max_staleness`: `allows_new_orders = false`.

## Eligibility

Research eligibility remains `DEVELOPMENT_ONLY` for yfinance/simulation feeds.
Controlled paper eligibility may be TRUE under Phase 12 gates.
Live trading remains DISABLED.

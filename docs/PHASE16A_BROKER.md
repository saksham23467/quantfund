# Phase 16A — Broker (Zerodha / Kite, read-only)

## Implemented (read-only)

- Authentication / session validation
- Account identity (hashed in snapshots)
- Funds / margins read
- Positions / holdings read
- Orders / trades read
- Instrument metadata lookup

## Explicitly NOT implemented

- `place_order`
- `modify_order`
- `cancel_order`
- GTT / basket / any write endpoint

Write attempts raise `BrokerWriteForbidden`. Capability construction with write
flags fails closed.

## Credentials

Environment only:

- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- `ZERODHA_ACCESS_TOKEN`
- `ZERODHA_ENV` (`sandbox` / `production`)

Never hardcoded. Never logged. CI uses `FakeKiteTransport` (MOCK).

## Capability declarations

Enabled: `READ_ACCOUNT`, `READ_POSITIONS`, `READ_ORDERS`, `READ_TRADES`,
`READ_MARKET_DATA`, `READ_HOLDINGS`.

Disabled forever in 16A: `WRITE_PLACE_ORDER`, `WRITE_CANCEL_ORDER`,
`WRITE_MODIFY_ORDER`.

# Phase 12 — Operations

## Commands

```bash
make phase12-preflight   # config + gates; no trading
make phase12-demo        # deterministic fixture; orders>0, fills>0, live=0
make phase12-paper       # controlled paper session (fixture/yfinance)
make phase12-replay      # A==B hash comparison
make phase12-report      # performance + drift + safety report
```

## Start a paper session

1. Ensure risk config + cost/slippage model IDs are set.
2. Create a `PaperActivationRecord` (`I_CONFIRM_CONTROLLED_PAPER_ACTIVATION`).
3. Enable a specific `strategy_id` / `strategy_version`.
4. Provide market data (offline fixture recommended; yfinance optional).
5. Run `make phase12-paper` or call `ControlledPaperEngine.run(...)`.

## Stop

Engine transitions to STOPPING → reconcile → COMPLETED/FAILED.
Kill switch may be triggered to reject new orders without clearing positions.

## Inspect

- Journal JSONL (append-only events)
- Session report JSON/TXT (`paper_orders`, `paper_fills`, P&L, costs)
- Drift report vs research backtest (if provided)

## Restart / recovery

1. Load journal + state snapshot
2. Verify integrity
3. Restore kill-switch + risk counters + positions/cash
4. Reconcile; refuse trading if untrusted

Never start with a clean portfolio unless creating a **new** session_id.

## Why this is not live trading

- Execution adapter is paper-only
- Activation record forbids live
- No credentials required for demo
- Live order count is always zero by construction

## Why DEVELOPMENT_ONLY remains

yfinance / fixtures are non-exchange. Research eligibility is decided by the
existing certification machinery and is not promoted by paper success.

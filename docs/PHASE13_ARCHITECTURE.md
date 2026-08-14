# Phase 13 — Controlled Paper-Trading Validation

## Purpose

Validate that controlled historical paper simulation (Phase 12) behaves
consistently with the existing backtest engine over multi-day yfinance /
fixture streams labeled **simulation-only**.

This is **not** live trading and **not** “live paper trading”.

Mode label: `CONTROLLED_HISTORICAL_SIMULATION`

## Status quo reused

| Layer | Reuse |
|-------|--------|
| Paper kernel | `PaperSession` + `PaperExecutionAdapter` (next-bar-open) |
| Controlled eligibility | Phase 12 `ControlledSimulationPaperGate` + `PaperActivationRecord` |
| Research eligibility | Unchanged; yfinance/fixtures stay `DEVELOPMENT_ONLY` |
| Costs / slippage | `equity_delivery_v1` / `fixed_bps_5` via `resolve_execution_models` |
| Strategies | Existing baselines + `BuyAndHoldStrategy` + StrategySpec interpreter |
| CA model | Existing `CorporateAction` + Phase 12 `build_paper_ca_context` |
| Calendar | Verified `FakeCalendarProvider` / NSE calendar providers |

## Flow

```
Historical bars (yfinance-labeled / fixture)
  → quality checks (fail closed on impossible OHLC / duplicates)
  → chronological MarketDataEvent stream (per-symbol seq)
  → PaperSession (features via history only ≤ T)
  → Signal → Risk → Order → PaperExecutionAdapter → Fill
  → Portfolio / CA accounting
  → Phase13 journal + reconciliation
  → BacktestEngine on same bars → drift compare
  → Report
```

## Package

```
src/quantfund/phase13/
  replay.py           # chronological bar → event feed
  session_runner.py   # multi-day validation session orchestration
  journal.py          # append-only validation journal
  portfolio.py        # accounting + CA position/cash updates
  reconciliation.py   # strict session integrity
  drift.py            # backtest ↔ paper semantic drift
  recovery.py         # restart / checkpoint recovery
  report.py           # session report
  demo.py             # offline demo harness
```

## Safety

- No broker `place_order`, no live activation, no LLM generation
- yfinance never upgraded to research-eligible
- Strategies never create fills
- Kill switch / risk / reconciliation remain fail-closed
- Claims: NONE

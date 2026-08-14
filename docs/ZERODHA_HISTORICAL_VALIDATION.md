# Zerodha Historical Data Validation

## Prominence

This phase is **DATA VALIDATION ONLY**.

- No live trading
- No `place_order` / cancel / modify
- Research eligibility is **not** auto-promoted for Zerodha
- yfinance remains non_exchange / development-only

## Credentials

Use environment variables only:

```
ZERODHA_API_KEY=
ZERODHA_API_SECRET=
ZERODHA_ACCESS_TOKEN=
ZERODHA_ENV=production   # or sandbox
QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1   # required for real network fetch
```

Never commit secrets. Rotate any key that was pasted into chat or tickets.

## Commands

```bash
make zerodha-auth-check        # credentials present? (no order)
make zerodha-historical-test   # mock by default; real if allow flag + token
make zerodha-data-quality
make zerodha-research
make zerodha-compare           # optional vs yfinance
make zerodha-demo              # full validation report
```

CI uses `FakeKiteTransport` unless explicitly opted into network fetch.

## Price policy

Kite historical OHLC is recorded as `price_policy=unknown` until adjustment
semantics are proven. RAW execution prices stay RAW. Research adjustments use
the existing corporate-action infrastructure separately — never invent adjusted OHLC.

## Dataset packages

Immutable packages land under `data/research/zerodha/<dataset_id>/<vN>/`
(`manifest.json`, `bars.parquet`, CA/instrument metadata, quality + provenance).
Re-download creates `vN+1`; overwrite of an existing version is refused.

## Safety proof

- `WRITE_ORDERS=false` on the historical provider
- AST scan forbids broker write-module imports
- Demo / validation report: `orders_submitted=0`, `place_order_called=0`,
  `live_trading=DISABLED`, `kill_switch=ARMED`
- Eligibility remains `DEVELOPMENT_ONLY` unless the existing certification stack
  independently promotes a package (no Zerodha shortcut)

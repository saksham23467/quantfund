# DEVELOPMENT_DATA

```text
DEVELOPMENT_DATA IS FOR ENGINEERING AND RESEARCH DEVELOPMENT ONLY.
IT DOES NOT CONSTITUTE RESEARCH-GRADE MARKET DATA.
IT CANNOT AUTHORIZE PAPER OR LIVE TRADING.
```

## 1. What it is

`DEVELOPMENT_DATA` is a free/public Indian equity market-data pipeline for:

- strategy development and debugging
- backtester / feature / campaign engineering
- paper-engine infrastructure testing

It is **not** a licensed research package and is permanently classified:

```text
DEVELOPMENT_DATA → DEVELOPMENT_ONLY
→ research_eligible = false
→ paper_eligible = false
→ live_eligible = false
→ real_orders = 0
```

## 2. Why it exists

Engineers need real-looking NSE OHLCV without waiting for a licensed research package.
Quality of development data **cannot** promote eligibility.

## 3. Supported sources

| Mode | How |
|------|-----|
| Offline fixture | Default `make development-data` uses `tests/fixtures/development/sample_ohlcv` |
| Offline import | `FILE=/path/to.csv` or `FILE=/path/to/bars_dir` |
| Optional network | `ALLOW_NETWORK_FETCH=1` uses existing yfinance adapter — still `DEVELOPMENT_DATA` |

Sources are recorded as `source_grade=development`, `research_grade=false`, `exchange_authority=false`.

Do **not** treat yfinance / public CSV as licensed research data.

## 4. How to ingest

```bash
make development-data
make ingest-development-data FILE=/path/to/file_or_dir
```

## 5. Normalization

Maps common OHLCV / bhavcopy-style columns into `MarketBar`:

`timestamp/date, symbol, open, high, low, close, volume`

No forward-fill, no invented volume, no silent OHLC repair.

## 6. Known limitations

| Area | Development status |
|------|--------------------|
| PIT NIFTY50 | `unavailable` / `CURRENT_SNAPSHOT` only |
| Corporate actions | `none` unless explicitly supplied (not fabricated) |
| Delisted coverage | `none` |
| License | `unknown_or_public_source` |

## 7. Why not research eligible

`ResearchEligibilityChecker` hard-blocks `data_class=DEVELOPMENT_DATA` and `source_grade=development`, independent of quality, PIT, or CA completeness. Manifest booleans are not trusted.

## 8. Why not paper eligible

Phase 8/10 `PaperEligibilityGate` requires `research_eligible` / `production_candidate`. Development datasets fail that rung.

## 9. Why not live

Phase 9 live ladder requires research acceptance + paper evidence. Development data never clears those rungs. `LIVE_SEND` remains disabled.

## 10. Transition to licensed research later

1. Acquire a package meeting `docs/RESEARCH_PACKAGE_REQUIREMENTS.md`
2. `export QUANTFUND_RESEARCH_PACKAGE=/path/to/package`
3. `make audit-research-package` / `make certify-research-package`
4. Only then may `RESEARCH_ELIGIBLE` become true — via existing gates, not this pipeline

Storage layout:

```text
data/development/india_eq/<dataset_id>/<dataset_version>/
    manifest.json
    instruments.json
    bars/
    metadata/
```

Never store development data inside a licensed research-package directory.

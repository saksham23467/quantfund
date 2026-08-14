# Phase 7 Architecture — Research-Grade Indian Market Data Acquisition

Phase 7 builds the **ingestion, validation, identity, coverage, and certification** path for a licensed research package. It does **not** guarantee that any environment becomes `RESEARCH_ELIGIBLE`.

## Principle

```
Provider → Raw Package → Validation → Normalization → Identity → Calendar
  → Corporate Actions → PIT Universe → Delisted Coverage → Dataset Manifest
  → Certification → Eligibility
```

Never:

```
Provider → "trust me" → RESEARCH_ELIGIBLE
```

Data acquisition and research eligibility are separate. Eligibility is **derived** from independently validated facts.

## What Phase 7 does not change

- `BacktestEngine`, next-bar-open execution, RAW execution prices
- `FeatureEngine` semantics, `StrategySpec` DSL, AI safety boundary
- `ResearchRunner`, `CampaignRunner`, sealed TEST
- DSR / trial accounting, risk limits, UNKNOWN membership handling
- Eligibility gate meanings (no weakening)

## Components

| Module | Role |
|--------|------|
| `data/packages/contract.py` | Versioned `package.json` contract |
| `data/packages/license.py` | License / provenance evidence model |
| `data/packages/ingest.py` | `QUANTFUND_RESEARCH_PACKAGE` resolution |
| `data/providers/package_validator.py` | Fail-closed package validator |
| `data/instruments/coverage.py` | Measurable delisted coverage |
| `data/universe/membership_audit.py` | PIT overlap / gap / duplicate audit |
| `data/certification.py` | `DatasetCertification` artifact |
| `scripts/run_phase7_demo.py` | Demo (no fabrication) |

## Environment

```bash
export QUANTFUND_RESEARCH_PACKAGE=/path/to/QUANTFUND_RESEARCH_PACKAGE
make phase7-demo
```

If unset: demo reports `Package: NOT CONFIGURED`, `Eligibility: DEVELOPMENT_ONLY`, blocker `research_package_not_configured`.

## Non-goals

- No brokers / broker SDKs
- No live or paper trading
- No LLM
- No genetic search
- No Phase 8
- No fabricated exchange-grade data to pass certification

## Demo contract

`make phase7-demo` must succeed without a licensed package, remaining `DEVELOPMENT_ONLY`.

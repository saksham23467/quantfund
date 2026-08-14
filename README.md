# QuantFund

Research and backtesting platform for systematic strategies on Indian markets.

**Current status:** Phases 0–16B. **Phase 16B** adds a gated **live canary** path; normal demos/CI/paper/shadow never submit real orders (`make phase16b-demo` → `CANARY_SIMULATION`, live orders `0`). Real submission requires explicit activation gates. yfinance remains non-exchange / simulation-only. Research eligibility remains `DEVELOPMENT_ONLY` without a licensed package.  
There is **no live trading**, **no LLM API**, and **no automated capital deployment**.

AI may only emit structured `StrategySpec` JSON. Output is untrusted and must pass validator → interpreter → `ResearchRunner`. See `docs/AI_SAFETY.md`.

Initial research capital (configuration default): ₹100,000 — backtests only.

---

## Critical Phase 1 warning

Datasets built from **yfinance** with **Stage A** (`current_snapshot_only`) universes are:

- `source_grade = non_exchange`
- `research_eligibility = development_only`

They are **DEVELOPMENT DATASETS**.  
They must **not** be treated as production-grade research data or as final strategy validation.

Universe Stage A is **NOT POINT-IN-TIME** and does **not** solve survivorship bias.

See `ASSUMPTIONS.md`.

---

## Architecture

```
SOURCE (DataProvider) → RAW (immutable) → VALIDATE → NORMALIZE
        → ADJUST (derived cols only) → DATASET (versioned Parquet)
        → Backtest (RAW execution, next-bar open) → Report + lineage
```

### Event flow (unchanged)

1. Signal at bar close (history ≤ t only)
2. Risk check
3. Schedule fill at **next bar open** (never same bar)
4. Slippage + costs → Fill → Portfolio

### Order lifecycle

`Signal` → `Order` → `Fill` → `Position` → `Portfolio`

---

## Setup

Requires Python 3.12+.

```bash
make setup
```

---

## Tests

```bash
make test
```

Includes Milestone 1 tests plus Phase 1 calendar, universe, corporate-action, dataset, and integration tests.

---

## Smoke backtest (M1)

```bash
make smoke
```

---

## Phase 2 research demo (offline, exploratory only)

```bash
make phase2-demo
```

Runs a deterministic momentum baseline through the research runner on synthetic
data. Status is forced to `exploratory_only` when `research_eligibility=development_only`.
TEST remains sealed. Not final strategy validation.

## Phase 1 development dataset (offline)

Builds a labeled **development_only** dataset from the synthetic fixture:

```bash
make phase1-dataset
```

Optional network ingest (still non-exchange / development):

```bash
.venv/bin/python scripts/ingest_yfinance_universe.py
```

## DEVELOPMENT_DATA pipeline (free public / offline)

Engineering-only Indian equity data for strategy debugging, features, campaigns, and infrastructure tests. Permanently `DEVELOPMENT_ONLY` — never research/paper/live eligible.

```bash
make development-data
make ingest-development-data FILE=/path/to/csv_or_bars_dir
```

See `docs/DEVELOPMENT_DATA.md`.

---

## Package layout (data / Phase 3)

| Path | Role |
|------|------|
| `src/quantfund/data/policy.py` | `DataQualityPolicy` + `DatasetEligibilityPolicy` |
| `src/quantfund/data/eligibility.py` | `ResearchEligibilityChecker` (central gate) |
| `src/quantfund/data/certification.py` | Certification facts + human-readable report |
| `src/quantfund/data/calendar/` | Verified `NSE_EQ` calendar versions + XBOM proxy |
| `src/quantfund/data/universe/` | Stage A + PIT `UniverseMembership`, TRUE/FALSE/UNKNOWN |
| `src/quantfund/data/identity.py` | Stable `instrument_id` / symbol-history helpers |
| `src/quantfund/data/corporate_actions/` | CA ledger + `AdjustmentPolicy` (RAW untouched) |
| `src/quantfund/data/quality/` | Expanded QualityReport ERROR/WARNING/INFO |
| `src/quantfund/data/providers/` | `DevelopmentProvider` / `ResearchProvider` roles |
| `src/quantfund/data/datasets/` | Manifest, builder, as-of reader, immutability |
| `scripts/certify_dataset.py` | Dataset certification CLI |
| `scripts/certify_research_dataset.py` | Phase 3.5 research certification report |
| `src/quantfund/data/providers/local_package.py` | Vendor-neutral `LocalResearchPackageProvider` |
| `src/quantfund/data/instruments/` | Instrument master + terminal/delisted events |
| `make phase3-demo` | Data-trust demo (development_only expected) |
| `make phase35-pilot` | Small synthetic pilot acquisition + certification |
| `src/quantfund/ai/` | Phase 4 generator / genealogy / research pipeline (no brokers) |
| `src/quantfund/strategies/spec/expr.py` | Additive Expr AST (value layer) |
| `make phase4-demo` | Mock AI factory demo (DEVELOPMENT_ONLY, accepted=0) |
| `docs/STRATEGY_DSL.md` / `docs/AI_SAFETY.md` | DSL + safety contract |
| `src/quantfund/data/providers/package_validator.py` | Phase 5 research package validation |
| `src/quantfund/data/universe/coverage.py` | PIT membership coverage metrics |
| `src/quantfund/data/corporate_actions/coverage.py` | Per-type CA coverage report |
| `make phase5-demo` | Evidence/certification demo (DEVELOPMENT_ONLY without licensed package) |
| `make validate-research-package` | Validate package.json / checksums / forge checks |
| `docs/PHASE5_ARCHITECTURE.md` / `docs/PHASE5_DATA_SOURCES.md` | Phase 5 design + source decision log |
| `src/quantfund/research/campaign_runner.py` | Phase 6 campaign orchestration (above ResearchRunner) |
| `make phase6-demo` | Campaign demo (DEVELOPMENT_ONLY, accepted=0, claims=NONE) |
| `docs/PHASE6_ARCHITECTURE.md` | Phase 6 campaign design |
| `src/quantfund/data/packages/` | Phase 7 research package contract / license / ingest |
| `make phase7-demo` | Package acquisition demo (`QUANTFUND_RESEARCH_PACKAGE` or NOT CONFIGURED) |
| `docs/PHASE7_ARCHITECTURE.md` / `PHASE7_DATA_CONTRACT.md` / `PHASE7_CERTIFICATION.md` | Phase 7 design + evidence gates |
| `src/quantfund/paper/` | Phase 8 broker-independent paper kernel (sandbox) |
| `make phase8-demo` | Paper kernel demo (`paper_eligible=false`, Broker: NONE) |
| `docs/PHASE8_ARCHITECTURE.md` | Phase 8 design (locked) |
| `src/quantfund/execution/` | Phase 9 gateway / MockBroker / DRY_RUN (no real brokers) |
| `make phase9-demo` | Execution gateway demo (`Real orders sent: 0`) |
| `docs/PHASE9_ARCHITECTURE.md` / `PHASE9_EXECUTION_SAFETY.md` | Phase 9 design + safety |
| `src/quantfund/research/acceptance_record.py` | Phase 10 immutable acceptance evidence |
| `src/quantfund/research/paper_policy.py` / `promotion.py` | Paper policy + promotion ladder |
| `make phase10-demo` | Research→paper demo (Mode A synthetic / Mode B package) |
| `docs/PHASE10_ARCHITECTURE.md` / `PAPER_VALIDATION.md` / `RESEARCH_ACCEPTANCE.md` | Phase 10 docs |
| `make audit-research-package` | Phase 10.5 readiness audit (RESEARCH_ELIGIBLE checklist) |
| `make certify-research-package` | Certify `QUANTFUND_RESEARCH_PACKAGE` (facts-derived eligibility) |
| `docs/RESEARCH_PACKAGE_REQUIREMENTS.md` | Vendor-neutral shopping list for research-grade NSE data |
| `src/quantfund/data/packages/membership.py` | Package-local PIT membership resolution |
| `src/quantfund/data/packages/vendor_import.py` | Vendor-neutral package materialization helpers |

---

## Principles

1. Backtests are hypotheses, not guarantees.
2. Know exactly what data was used and whether it can be trusted.
3. RAW prices never silently replaced by adjusted prices.
4. Risk is independent of strategy logic.
5. No look-ahead / no same-bar fills.
6. Secrets via environment variables only.

See `ASSUMPTIONS.md` before interpreting any result.

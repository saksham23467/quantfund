# Phase 9A — Research Data Upgrade Infrastructure

**Status:** Design + implementation (this phase).  
**Not in scope:** Phase 9 live trading, brokers, credentials, `LIVE_SEND`, LLM, genetic search, paper-kernel changes.

## Objective

Make QuantFund **production-ready to plug in a future licensed NSE research package**, while keeping yfinance / synthetic / historical CF-CA explicitly `DEVELOPMENT_ONLY`.

```text
External licensed package (future)
        ↓
validate-research-package
        ↓
certify-research-package  (facts-derived)
        ↓
ResearchEligibilityChecker  (authoritative)
        ↓
RESEARCH_ELIGIBLE or DEVELOPMENT_ONLY
```

## Non-negotiable

| Rule | Implication |
|------|-------------|
| Do not fabricate market data | Fixtures labeled `TEST_FIXTURE_ONLY` only |
| Do not weaken eligibility | Package booleans never authorize research |
| No brokers / live / LLM | `execution/` live path untouched; Phase 8 paper untouched |
| Reuse existing stacks | packages/, validator, certify, PIT, identity, CA, terminal |
| RAW OHLC immutable | CA identity wiring never mutates bars |

## Distinction

| Term | Meaning |
|------|---------|
| **RESEARCH_ELIGIBLE-CAPABLE** | Package declares `source_grade ∈ {exchange,paid}`, license evidence, capabilities that *can* satisfy the source bar |
| **ACTUALLY RESEARCH_ELIGIBLE** | Only after `ResearchEligibilityChecker` on independently measured facts |

## Reuse map

| Need | Existing module |
|------|-----------------|
| Contract | `data/packages/contract.py` |
| Validate CLI | `providers/package_validator.py` + `scripts/validate_research_package.py` |
| Certify | `research/certify_package.py` |
| PIT | `universe/membership.py` `was_member` TRUE/FALSE/UNKNOWN |
| Instrument master | `instruments/master.py` |
| Terminal/delisted | `instruments/delisted.py` |
| Historical CA | `corporate_actions/historical_local.py` |
| Readiness audit | `packages/readiness.py` |

## Phase 9A additions (thin)

1. **Instrument ↔ CA identity resolver** — resolve CF-CA symbols via instrument master (ISIN/history); ambiguous → UNKNOWN; never company-name-only.
2. **Terminal schema extensions** — `acquired`, `suspended`; optional `confidence`.
3. **Instrument fields** — `series`, `aliases`, predecessor/successor ids (backward compatible).
4. **`scripts/research_readiness.py`** — GREEN / YELLOW / RED traffic light (**GREEN ≠ RESEARCH_ELIGIBLE**).
5. **`make phase9a-demo`** — show real-world blockers + TEST_FIXTURE_ONLY structural path.
6. **TEST_FIXTURE_ONLY package** — structurally complete paid-grade *fixture* for CI gate tests; fabricated prices; never presented as real NSE data.
7. **Extended certification report** — PACKAGE / SOURCE / IDENTITY / UNIVERSE / CA / DELISTED / CALENDAR / ELIGIBILITY.

## Demo contract

Without `QUANTFUND_RESEARCH_PACKAGE` (real licensed data):

```text
RESEARCH_ELIGIBLE = FALSE
Claims = NONE
```

With TEST_FIXTURE_ONLY package path: structural certification may pass eligibility *for the fixture only*, still labeled TEST_FIXTURE_ONLY / not real market data.

## Stop conditions

Do not start Phase 9 live trading. Do not modify Phase 8 paper architecture. Do not modify BacktestEngine execution semantics.

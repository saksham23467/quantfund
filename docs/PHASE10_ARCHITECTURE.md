# Phase 10 — Research-to-Paper Validation

**Status:** Implemented (research → paper evidence pipeline).  
**Does not enable:** live trading, `LIVE_SEND`, real brokers, real credentials, Phase 11.

## Objective

Wire the evidence ladder:

```text
RESEARCH_ELIGIBLE
        ↓
Strategy ACCEPTED (StrategyAcceptanceRecord)
        ↓
PAPER_ELIGIBLE
        ↓
Paper Trading Evidence
        ↓
LIVE_ELIGIBILITY_CANDIDATE
```

Live trading remains **DISABLED**. Candidate ≠ authorization to send orders.

## Non-goals

- Real broker SDKs / network order paths
- Automatic paper → live promotion
- Automatic emergency flatten
- LLM / genetic strategy search
- Weakening `ResearchEligibilityChecker` for demos

## Components

| Module | Role |
|--------|------|
| `research/acceptance_record.py` | Immutable `StrategyAcceptanceRecord` |
| `research/certify_package.py` | Package → facts → certify (Phase 5/7 path) |
| `research/paper_policy.py` | Versioned `paper_policy_v1` |
| `research/paper_evidence.py` | Evidence from Phase 8 session artifacts |
| `research/paper_session_fsm.py` | Validation session state machine |
| `research/backtest_paper_compare.py` | BACKTEST vs PAPER divergence |
| `research/drift.py` | Drift monitoring (no strategy mutation) |
| `research/promotion.py` | End-to-end orchestration |
| `paper/eligibility.py` | Extended PRODUCTION paper gates |

## Invariants preserved

- Next-bar-open backtest / RAW execution
- Strategy ↔ broker separation
- Sealed TEST / DSR / score_policy_v1
- `DEVELOPMENT_ONLY` → never accepted, never paper-eligible
- Campaign acceptance alone ≠ paper eligibility
- Paper pass ≠ live authorization
- Phase 9 MockBroker + DRY_RUN only

## Demo

```bash
make phase10-demo
# Mode B:
QUANTFUND_RESEARCH_PACKAGE=/path/to/package make phase10-demo
```

See also `docs/PAPER_VALIDATION.md` and `docs/RESEARCH_ACCEPTANCE.md`.

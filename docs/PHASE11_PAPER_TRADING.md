# Phase 11 — Paper Trading Policy

## Paper eligibility policy

`RESEARCH_ELIGIBLE` alone does **not** imply `PAPER_ELIGIBLE`.

`PaperEligibilityGate` (Phase 8/10) remains authoritative. Phase 11 adds **additional** operational gates via `Phase11PaperCertificationGate`:

| Gate | Requirement |
|------|-------------|
| Research | `certified_eligibility ∈ {research_eligible, production_candidate}` |
| Acceptance | Strategy acceptance evidence present |
| PRODUCTION flags | sealed TEST, robustness, walk-forward, DSR, no leakage, no UNKNOWN membership traded |
| Risk / exec config | valid |
| Operator | operator-approved paper session |
| Calendar / CA / delisted | satisfied via certification facts (existing checker) |
| Kill switch | armed (not triggered) and functional |
| Reconciliation | clean (`allows_new_orders` true for paper local state) |
| Connectivity | healthy for chosen mode (SIMULATED or CONNECTED_READ_ONLY) |
| Mode | explicit PAPER; not LIVE |
| Strategy | explicitly enabled for paper |
| Activation | no live activation contamination |

### Non-research data mode

Infrastructure sandbox / DEVELOPMENT_ONLY datasets remain **non-paper-eligible**.  
There is no silent “demo paper eligible” override. CI may run **simulated paper machinery** for tests, but `paper_eligible` stays `FALSE` unless every gate genuinely passes.

## Execution invariants

- SIGNAL at T → next-bar-open fill
- RAW OHLC unmodified
- Deterministic IDs (`deterministic_id` / `make_fill_id`)
- PaperExecutionAdapter is the sole paper fill factory
- Execution mode label: `PAPER`

## Session FSM

`CREATED → PREFLIGHT → READY → RUNNING → PAUSED → STOPPING → RECONCILING → FINALIZED`  
Failure: `FAILED` from any non-terminal state.

RUNNING requires: paper eligibility, risk OK, kill switch OK, account state known, reconcile clean, strategy enabled, mode=PAPER.

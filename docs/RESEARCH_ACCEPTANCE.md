# Research Acceptance (Phase 10)

## Authority

Only the evaluator-owned campaign path may create acceptance evidence.

- Strategies / StrategySpec metadata must **not** self-accept
- Generators must not write acceptance flags
- Manual edits of acceptance JSON are detected via `artifact_digest`

## `StrategyAcceptanceRecord`

Immutable artifact with (at minimum):

- strategy / campaign / dataset identity
- config hash, selection criterion
- validation / walk-forward / robustness / TEST metrics
- DSR, n_trials, score
- acceptance policy version
- research eligibility
- sealed_test_ok / robustness_ok / walkforward_ok
- deterministic `acceptance_evidence_id` + `artifact_digest`

## Hard bans

| Condition | Accepted? |
|-----------|-----------|
| `DEVELOPMENT_ONLY` dataset | Never |
| Exploratory campaign purpose | Never |
| Unsealed / multi-shot TEST | Never |
| Missing acceptance evidence id | Paper blocked |
| Campaign accept without record | Paper blocked |

## Claims language

Accepted research candidates may be labeled research candidates only.

**Research acceptance ≠ profitability guarantee.**

Downstream paper/live gates are separate authorization ladders.

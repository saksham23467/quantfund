# AI Safety (Phase 4)

## Core principle

**AI output is untrusted data.**

```
LLM / Mock generator
      ↓ (untrusted JSON)
StrategySpec schema
      ↓
StrategySpecValidator
      ↓
Trusted interpreter (allowlisted ops only)
      ↓
ResearchRunner / scoring / registry
```

The generator is never the evaluator.

## Forbidden

- Real brokers, live order submission, live capital deployment
- AI-initiated paper or live sessions; AI access to `PaperExecutionAdapter`,
  `ExecutionGateway`, `MockBrokerAdapter`, or credential providers
- API credentials in the AI path, Spec, research artifacts, or audit logs
- Arbitrary Python execution from model output
- `eval`, `exec`, dynamic imports, subprocess, shell, sockets
- Generator access to sealed TEST results
- Generator modification of datasets, costs, slippage, risk ceilings, eligibility, scoring
- Self-acceptance fields on StrategySpec (`accepted`, `accepted_for_validation_pipeline`)
- Promoting `DEVELOPMENT_ONLY` datasets because an AI strategy “looks good”
- Claiming `paper_eligible=true` or `LIVE_AUTHORIZED` from AI output or scores

## Paper trading (Phase 8)

The broker-independent paper kernel under `quantfund.paper` may run in
`infrastructure_sandbox` for demos/tests. Production paper requires
`PaperEligibilityGate` (`paper_eligible=true`). AI must not place paper orders
or bypass the gate.

## Live execution boundary (Phase 9)

`quantfund.execution` provides `ExecutionGateway` with **MockBroker + DRY_RUN only**.
Real orders sent must remain **0**. `LiveTradingEligibilityGate` and operator
approval are mandatory before any execution rung; Phase 9 v1 still cannot
`LIVE_SEND`. See `docs/PHASE9_EXECUTION_SAFETY.md`.

## Research → paper promotion (Phase 10)

Acceptance evidence is evaluator-owned (`StrategyAcceptanceRecord`). Generators
must not self-accept. Paper policy may yield `LIVE_ELIGIBILITY_CANDIDATE` only;
**live trading remains disabled**. Research acceptance ≠ profitability;
paper pass ≠ live authorization.

## Required

- Structured StrategySpec only
- Validator before interpreter
- Deterministic interpretation
- Every evaluated candidate counted as a trial
- Failed / invalid candidates retained (not hidden)
- `DEVELOPMENT_ONLY` → never `accepted_for_validation_pipeline`

## Phase 4 generator

`MockStrategyGenerator` is deterministic and offline.

`LLMStrategyGenerator` is an **unconnected** stub. When a real LLM is added later, it must still pass the same validation pipeline — never execute model-generated code.

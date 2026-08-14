# Phase 4 Architecture — AI Strategy Factory

**Status:** Implemented (Steps 2–9). Mock generator only. No LLM SDK. No brokers.

## Flow

```
GenerationRequest
      ↓
StrategyGenerator (MockStrategyGenerator)
      ↓
StrategySpec[]          # untrusted structured data
      ↓
StrategySpecValidator   # structured VALID / INVALID
      ↓
canonical hash dedupe
      ↓
interpret_strategy_spec # trusted Expr/Rule dispatch
      ↓
ResearchRunner.evaluate # existing Phase 2 spine
      ↓
ExperimentRegistry      # trial accounting
```

## Package split

| Package | Responsibility |
|---------|----------------|
| `quantfund.ai` | GenerationRequest, generators, genealogy, pipeline orchestration |
| `quantfund.strategies.spec` | Expr, Rule, StrategySpec, validators, interpreter |

## DSL

- **Expr** — value expressions (`strategies/spec/expr.py`)
- **Rule** — boolean predicates (Phase 2 compatible; operands may be Expr)
- See `docs/STRATEGY_DSL.md` and `docs/AI_SAFETY.md`

## Compatibility

Existing Phase 2 Rule JSON and `validate_strategy_spec` / `interpret_strategy_spec` APIs remain.

## Non-goals (not in Phase 4)

LLM APIs, genetic search, hyperparameter optimization, paper/live trading, brokers.

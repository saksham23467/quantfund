# Strategy DSL

QuantFund strategies that come from AI (or humans) are **structured JSON**, never Python source.

## Layers

| Layer | Type | Role |
|-------|------|------|
| **Expr** | value expression → `float \| None` | arithmetic, feature refs, constants, `if` |
| **Rule** | boolean predicate → `bool` | comparisons + `and` / `or` / `not` |
| **StrategySpec** | strategy document | features, entry/exit rules, sizing, risk prefs |
| **Interpreter** | trusted runtime | explicit allowlisted dispatch only |

## Rule (Phase 2 — unchanged semantics)

Operators: `gt`, `gte`, `lt`, `lte`, `eq`, `and`, `or`, `not`

Legacy operands (still required to work):

```json
{"op": "gt", "left": "feature:sma_20", "right": "feature:sma_50"}
```

## Expr (Phase 4 — additive)

Operators: `constant`, `feature_ref`, `add`, `subtract`, `multiply`, `divide`, `abs`, `min`, `max`, `if`

```json
{
  "op": "gt",
  "left": {
    "op": "subtract",
    "args": [
      {"op": "feature_ref", "name": "sma_20"},
      {"op": "feature_ref", "name": "sma_50"}
    ]
  },
  "right": {"op": "constant", "value": 0}
}
```

Arithmetic ops are **not** valid `Rule.op` values.

## Safety

- No `eval` / `exec` / imports / filesystem / network
- Division by zero → invalid (`None`) → strategy HOLDs
- Missing features → HOLD
- Complexity limits enforce depth / nodes / rules / features

See `docs/AI_SAFETY.md`.

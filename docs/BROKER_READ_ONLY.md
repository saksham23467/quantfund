# Broker Read-Only (Phase 15)

## Allowed

- Connectivity / health
- Account metadata (if safely available)
- Funds / margins read
- Positions / holdings read
- Orders / trades history read

## Forbidden

- `place_order`, cancel, modify, bracket, GTT, basket, any write endpoint

## Capability model

```
BrokerCapabilities.place_order = FALSE
BrokerCapabilities.cancel_order = FALSE
BrokerCapabilities.modify_order = FALSE
can_place_orders = FALSE
```

Construction fails closed if a provider claims write capabilities.

## Credentials

Environment/configuration only. Never in source, tests, fixtures, logs,
registry, reports, or Git. Redact tokens/secrets everywhere.

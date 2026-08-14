# Phase 16B — Operations

## Safe commands

```bash
make phase16b-demo
make phase16b-preflight
```

## Dangerous command

```bash
LIVE_TRADING=true \
  .venv/bin/python scripts/run_phase16b_live_canary.py \
  --confirm I_CONFIRM_CONTROLLED_LIVE_CANARY \
  --activation path/to/activation.json
```

`make phase16b-live-canary` refuses unless `LIVE_TRADING=true` and all gates pass.
Any gate failure exits **without** calling `place_order`.

## Emergency stop

Kill switch activate → prevent new orders, keep position visibility, reconcile,
audit. Does **not** auto-liquidate unless separately configured.

## Session lifecycle

CREATED → ACTIVATION_REQUIRED → ACTIVATED → RUNNING → HALTED → RECONCILING → CLOSED

Failure → HALTED (never continue trading).

# PHASE 19 — Controlled Real-Time Paper Trading

## Status

Paper trading only. **Zero real Zerodha order submissions.**

## Activation

- Mode: `INFRASTRUCTURE_SANDBOX`
- Candidate: `p18_sha256:01863bbbd`
- Family: `mean_reversion`
- Research accepted: `False`
- Strategy hash: `97c2381b45b89db0`
- Parameter hash: `608c62ca29e261d7`
- Dataset/research hash: `sha256:588736f373856baf836c7d1a841a4057bef5675d33089d8409a562af50307a21`
- Code version: `0.2.0`
- Auto-graduate to live: **DISABLED**

## Session

- Duration: `{'duration': '1d', 'trading_days': 1, 'auto_graduate_to_live': False, 'description': 'Controlled paper session for 1 trading day(s); live graduation disabled.'}`
- Paper orders: 0
- Paper fills: 0
- Reconciliation: True

## Safety

- real_broker_orders = 0
- place_order_called = 0
- live_trading = DISABLED
- kill_switch = ARMED
- Execution adapter = PaperExecutionAdapter only

## EC2

See `deploy/systemd/quantfund-phase19-paper.service` for the systemd unit template.
Health: `GET /health` on loopback (default port 8719).

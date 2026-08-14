# PHASE 21 — EC2 Operations (Paper Only)

**LIVE_TRADING = DISABLED**  
**BROKER_WRITE = DISABLED**  
**PAPER_TRADING = ENABLED**  
**KILL_SWITCH = ARMED**

This service runs autonomous **paper** trading on real Zerodha **read-only** market data.
It never calls `place_order` / `cancel_order` / `modify_order` against Zerodha.

## Install

```bash
cd ~/quantfund
sudo cp deploy/systemd/quantfund-phase21-paper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quantfund-phase21-paper
```

Ensure `.env` contains Zerodha read credentials (`ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN`) and **does not** set live-trading flags.

Do **not** set `QUANTFUND_PHASE21_ALLOW_MOCK=1` on EC2 production paper.

## Start / Stop / Restart / Status

```bash
sudo systemctl start quantfund-phase21-paper
sudo systemctl stop quantfund-phase21-paper
sudo systemctl restart quantfund-phase21-paper
sudo systemctl status quantfund-phase21-paper
```

Make targets (from repo root):

```bash
make phase21-preflight
make phase21-start
make phase21-status
make phase21-report
make phase21-recovery
make phase21-stop
```

## Logs

```bash
journalctl -u quantfund-phase21-paper -f
ls -la experiments/phase21/journal/
ls -la experiments/phase21/audit/
```

## Heartbeat / runtime

```bash
cat experiments/phase21/runtime/heartbeat.json
cat experiments/phase21/runtime/status.json
```

## Recovery

After crash or EC2 reboot, systemd restarts the unit. State lives under:

- `experiments/phase21/checkpoints/`
- `experiments/phase21/journal/`
- `experiments/phase21/runtime/`

```bash
make phase21-recovery
```

Recovered cash/positions must match the last trusted checkpoint before new paper orders continue.

## Kill switch

Kill switch starts **ARMED**. If triggered (strategy mutation, reconciliation failure, operator STOP):

- no new paper orders
- service should be inspected before restart

Operator stop:

```bash
make phase21-stop
# or
touch experiments/phase21/runtime/STOP
sudo systemctl stop quantfund-phase21-paper
```

## Data health

- Provider: Zerodha Kite historical daily + optional quote poll
- Stale / malformed bars fail closed
- `source_grade=vendor_read_only`, `research_eligible=false`
- Never yfinance on the real-time path

## Paper status

```bash
make phase21-status
make phase21-report
cat reports/phase21_paper_qualification.json
```

Distinguish:

| Class | Meaning |
|-------|---------|
| `PAPER_ORDER` | Simulated via `PaperExecutionAdapter` |
| `LIVE_BROKER_ORDER` | Forbidden — must remain 0 |

## Final results

One of:

- `PAPER_QUALIFIED`
- `PAPER_BLOCKED`
- `PAPER_INSUFFICIENT_ACTIVITY`
- `PAPER_FAILED`

Do **not** enable live trading after Phase 21.

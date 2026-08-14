# QuantFund EC2 Deployment

Infrastructure migration only. Mac remains the development/control machine.
EC2 becomes the execution environment for research validation and Zerodha
**historical read-only** API calls.

```
Mac (develop / control)
        │
        │  git / rsync  (no secrets in git)
        ▼
EC2 Linux (execute)
        │
        │  QuantFund (.venv, make targets)
        ▼
Zerodha Historical API  (READ-ONLY)
```

**NO PAPER OR LIVE TRADING.**  
`place_order` is not enabled. Broker write capability remains **DISABLED**.

---

## Repository facts (do not duplicate)

| Item | Value |
|------|--------|
| Python | **≥ 3.12** (pinned tooling assumes 3.12) |
| Package manager | `pip` + `pyproject.toml` editable install |
| Lockfile | `requirements-lock.txt` |
| Tests | `make test` → `pytest` |
| Phase 17C | `make phase17c-demo` |
| Real Zerodha hist | `make zerodha-real-validation` |
| Data | `data/research/zerodha/` (immutable packages; gitignored) |
| Calendars | `data/calendars/` |
| Secrets | `.env` only (gitignored) |

Required env vars for REAL historical API (never commit values):

- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- `ZERODHA_ACCESS_TOKEN`
- `QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1`

Optional deployment env (on Mac control machine):

- `QUANTFUND_EC2_HOST` — EC2 public DNS/IP
- `QUANTFUND_EC2_USER` — default `ubuntu`
- `QUANTFUND_EC2_SSH_KEY` — path to `.pem` (chmod 400)
- `QUANTFUND_EC2_DIR` — default `~/quantfund`
- `QUANTFUND_EC2_SYNC_ENV=1` — copy `.env` once over SSH
- `QUANTFUND_EC2_SYNC_DATA=1` — sync research packages (default on)
- `QUANTFUND_EXPECTED_ZERODHA_IP` — Kite/Zerodha allowlisted egress IP
- `QUANTFUND_EXECUTION_ROLE=EC2` — force role label on EC2 if needed

---

## 1. Prepare EC2 (one-time)

Ubuntu 22.04/24.04 AMI recommended.

Security group:

- inbound SSH (22) from **your IP only**
- outbound HTTPS (443) to Zerodha / internet

On the instance (or via `scripts/deploy_to_ec2.sh` bootstrap):

```bash
sudo apt-get update -y
sudo apt-get install -y python3.12 python3.12-venv python3-pip \
  build-essential libffi-dev libssl-dev curl git rsync
```

---

## 2. Deploy from Mac

```bash
cd /path/to/Quant-fund

export QUANTFUND_EC2_HOST=ec2-XX-XX-XX-XX.compute-1.amazonaws.com
export QUANTFUND_EC2_USER=ubuntu
export QUANTFUND_EC2_SSH_KEY=$HOME/path/to/your-key.pem
export QUANTFUND_EXPECTED_ZERODHA_IP=x.x.x.x   # optional, for IP match check

# First deploy: also sync .env once (values never printed)
export QUANTFUND_EC2_SYNC_ENV=1
chmod +x scripts/deploy_to_ec2.sh
./scripts/deploy_to_ec2.sh
```

What gets synced:

- source, `pyproject.toml`, `requirements-lock.txt`, `Makefile`, `tests`, `docs`
- `data/calendars/`
- `data/research/zerodha/` with **`--ignore-existing`** (never overwrite immutable package files)
- optional `.env` only if `QUANTFUND_EC2_SYNC_ENV=1`

What does **not** go through git:

- `.env`, `*.pem`, research parquet packages (gitignored)

---

## 3. EC2 setup after sync

```bash
ssh -i $QUANTFUND_EC2_SSH_KEY $QUANTFUND_EC2_USER@$QUANTFUND_EC2_HOST
cd ~/quantfund
source .venv/bin/activate
export QUANTFUND_EXECUTION_ROLE=EC2

make environment-check
make ec2-preflight
```

`make environment-check` reports (never secrets):

- `execution_role` → **LOCAL** vs **EC2**
- `execution_host`, `execution_os`, `execution_architecture`
- `public_egress_ip`
- `expected_zerodha_ip_if_configured`
- `zerodha_ip_match`

---

## 4. Verify Zerodha IP allowlist

1. On EC2: `make environment-check` → note `public_egress_ip`
2. In Zerodha/Kite developer console, ensure that IP is allowlisted
3. Set `QUANTFUND_EXPECTED_ZERODHA_IP=<that-ip>` on EC2 `.env`
4. Re-run `make environment-check` → `zerodha_ip_match=MATCH`

Access tokens are often IP-bound. Prefer generating the token **from EC2**
after redirect/URL flows are adjusted, or use a login path that produces a
token valid for the EC2 egress IP.

---

## 5. Research regression on EC2

Do **not** redownload Phase 17B/17C packages. Hashes must remain identical.

```bash
make test
make phase17c-demo          # uses existing packages; may write new cert versions only if missing
make zerodha-real-validation  # REAL API; fails closed without credentials
```

Confirm:

- dataset `content_hash` unchanged for existing `v1`/`v2` dirs
- eligibility still `DEVELOPMENT_ONLY`
- leakage / reproducibility PASS
- `place_order_called=0`, `orders_submitted=0`

---

## 6. Update workflow

```bash
# On Mac after pulling/committing code changes:
export QUANTFUND_EC2_SYNC_ENV=0   # do not overwrite remote .env
./scripts/deploy_to_ec2.sh

# On EC2:
cd ~/quantfund && source .venv/bin/activate
pip install -r requirements-lock.txt
pip install -e ".[dev]"
make test
```

---

## 7. Rotate credentials

1. Revoke old Zerodha access token in Kite
2. On EC2, edit `~/quantfund/.env` (chmod 600) — never commit
3. Obtain new `ZERODHA_ACCESS_TOKEN` valid for EC2 egress IP
4. `make environment-check` then `make zerodha-auth-check`
5. Do not paste secrets into chat, tickets, or reports

---

## 8. Stop processes

QuantFund research commands are batch Make/Python processes, not a daemon.

```bash
# find leftover research/validation processes
pgrep -af 'phase17|zerodha|pytest|quantfund' || true
pkill -f 'run_phase17c|run_zerodha_real_validation' || true
```

There is no live trading service to stop.

---

## 9. Safety invariants

Always:

| Flag | Required |
|------|----------|
| `place_order_called` | `0` |
| `orders_submitted` | `0` |
| `broker_write_capability` | `DISABLED` |
| `live_trading` | `DISABLED` |
| `paper_trading` | `NOT_STARTED` |
| `kill_switch` | `ARMED` |

Deployment scripts and `src/quantfund/deploy/` must not call `place_order`.

---

## 10. Make targets

```bash
make environment-check   # LOCAL vs EC2 identity + egress IP
make ec2-preflight       # Linux/Python/deps/disk/mem/datasets/safety
make deploy-ec2          # wrapper → scripts/deploy_to_ec2.sh
```

#!/usr/bin/env bash
# Deploy QuantFund from Mac (control) → EC2 (execution).
# Never copies .env with secrets unless QUANTFUND_EC2_SYNC_ENV=1.
# Never enables live/paper trading.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${QUANTFUND_EC2_HOST:-}"
USER_NAME="${QUANTFUND_EC2_USER:-ubuntu}"
KEY="${QUANTFUND_EC2_SSH_KEY:-}"
REMOTE_DIR="${QUANTFUND_EC2_DIR:-~/quantfund}"
SYNC_ENV="${QUANTFUND_EC2_SYNC_ENV:-0}"
SYNC_DATA="${QUANTFUND_EC2_SYNC_DATA:-1}"

if [[ -z "$HOST" ]]; then
  echo "ERROR: QUANTFUND_EC2_HOST is required (EC2 public DNS or IP)."
  echo "Example:"
  echo "  export QUANTFUND_EC2_HOST=ec2-XX-XX-XX-XX.compute.amazonaws.com"
  echo "  export QUANTFUND_EC2_USER=ubuntu"
  echo "  export QUANTFUND_EC2_SSH_KEY=\$HOME/path/to/key.pem"
  exit 2
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes)
if [[ -n "$KEY" ]]; then
  chmod 400 "$KEY" 2>/dev/null || true
  SSH_OPTS+=(-i "$KEY")
fi

SSH=(ssh "${SSH_OPTS[@]}" "${USER_NAME}@${HOST}")
RSYNC_SSH="ssh ${SSH_OPTS[*]}"

echo "=== QuantFund deploy Mac → EC2 ==="
echo "host=${HOST} user=${USER_NAME} remote_dir=${REMOTE_DIR}"
echo "sync_env=${SYNC_ENV} sync_data=${SYNC_DATA}"
echo "(secrets are not printed)"

"${SSH[@]}" "mkdir -p ${REMOTE_DIR}"

# Code + lockfile (exclude secrets, venv, caches, large ignored noise)
rsync -az --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '*.pem' \
  --exclude '*.key' \
  --exclude 'experiments/' \
  --exclude 'reports/' \
  -e "$RSYNC_SSH" \
  "$ROOT/" "${USER_NAME}@${HOST}:${REMOTE_DIR}/"

# Optionally sync immutable research packages (no overwrite of newer remote-only versions
# is handled by rsync update semantics; we use --ignore-existing for package version dirs
# that already exist on remote to preserve immutability).
if [[ "$SYNC_DATA" == "1" ]]; then
  echo "=== Syncing research datasets (immutable; skip existing version dirs) ==="
  "${SSH[@]}" "mkdir -p ${REMOTE_DIR}/data/research/zerodha ${REMOTE_DIR}/data/calendars"
  # Calendars are small and versioned — sync fully
  rsync -az \
    -e "$RSYNC_SSH" \
    "$ROOT/data/calendars/" "${USER_NAME}@${HOST}:${REMOTE_DIR}/data/calendars/"
  # CA file if present
  if [[ -f "$ROOT/CF-CA-equities-01-01-2009-to-01-08-2026.csv" ]]; then
    rsync -az -e "$RSYNC_SSH" \
      "$ROOT/CF-CA-equities-01-01-2009-to-01-08-2026.csv" \
      "${USER_NAME}@${HOST}:${REMOTE_DIR}/"
  fi
  # Research packages: copy missing files only (never overwrite existing package files)
  if [[ -d "$ROOT/data/research/zerodha" ]]; then
    rsync -az --ignore-existing \
      -e "$RSYNC_SSH" \
      "$ROOT/data/research/zerodha/" \
      "${USER_NAME}@${HOST}:${REMOTE_DIR}/data/research/zerodha/"
  fi
fi

if [[ "$SYNC_ENV" == "1" ]]; then
  if [[ ! -f "$ROOT/.env" ]]; then
    echo "ERROR: QUANTFUND_EC2_SYNC_ENV=1 but local .env missing"
    exit 2
  fi
  echo "=== Syncing .env (presence only logged; values not printed) ==="
  rsync -az -e "$RSYNC_SSH" "$ROOT/.env" "${USER_NAME}@${HOST}:${REMOTE_DIR}/.env"
  "${SSH[@]}" "chmod 600 ${REMOTE_DIR}/.env"
else
  echo "=== Skipping .env sync (set QUANTFUND_EC2_SYNC_ENV=1 to copy once) ==="
fi

echo "=== Remote bootstrap (venv + pinned deps) ==="
"${SSH[@]}" "REMOTE_DIR=${REMOTE_DIR} bash -s" <<'REMOTE'
set -euo pipefail
cd "${REMOTE_DIR/#\~/$HOME}"
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3.12 python3.12-venv python3-pip build-essential \
    libffi-dev libssl-dev curl git
fi
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-lock.txt
python -m pip install -e ".[dev]"
export QUANTFUND_EXECUTION_ROLE=EC2
make environment-check
make ec2-preflight || true
REMOTE

echo "=== Deploy finished ==="
echo "Next on EC2:"
echo "  ssh ${USER_NAME}@${HOST}"
echo "  cd ${REMOTE_DIR} && source .venv/bin/activate"
echo "  make environment-check && make ec2-preflight"
echo "  make test && make phase17c-demo"
echo "  make zerodha-real-validation"
echo "NO PAPER OR LIVE TRADING WAS STARTED."

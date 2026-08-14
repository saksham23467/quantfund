#!/usr/bin/env bash
# Run the QuantFund Research Terminal API gateway.
# Uses the repository's existing virtualenv so the real quantfund package and
# numpy/pandas are available.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

# One-time: install the gateway's extra deps into the existing venv.
if ! "$VENV_PY" -c "import fastapi, sqlalchemy" >/dev/null 2>&1; then
  echo "Installing gateway dependencies (fastapi, uvicorn, sqlalchemy) into .venv ..."
  "$VENV_PY" -m pip install -r "$HERE/requirements.txt"
fi

# Seed demo-ready data on first boot (idempotent; skips if already seeded).
"$VENV_PY" "$HERE/seed.py" || echo "seed skipped/failed (continuing)"

cd "$HERE"
exec "$VENV_PY" -m uvicorn app.main:app --reload --port 8000

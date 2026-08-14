"""Gateway configuration (paths + safety posture + SaaS settings)."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports"
DOCS_DIR = REPO_ROOT / "docs"
TERMINAL_ROOT = Path(__file__).resolve().parents[2]  # quantfund_terminal/

# --- Multi-tenant SaaS datastores ------------------------------------------
# Default to a local SQLite file so v2 runs with zero infra. In production this
# is a Postgres URL (RDS). Set QFT_DATABASE_URL to override.
DATABASE_URL = os.environ.get(
    "QFT_DATABASE_URL", f"sqlite:///{TERMINAL_ROOT / 'quantfund_terminal.db'}"
)
# Redis is optional; when absent the gateway falls back to an in-process cache.
REDIS_URL = os.environ.get("QFT_REDIS_URL")  # e.g. redis://localhost:6379/0

# Billing is behind a provider interface; default is a no-op mock (no secrets).
BILLING_PROVIDER = os.environ.get("QFT_BILLING_PROVIDER", "mock")  # mock|stripe
STRIPE_WEBHOOK_SECRET = os.environ.get("QFT_STRIPE_WEBHOOK_SECRET", "")

# Immutable safety posture surfaced to every client. The terminal is read-only.
SAFETY_STATE = {
    "live_trading": "DISABLED",
    "paper_trading": "NOT_STARTED",
    "broker_write_capability": "DISABLED",
    "kill_switch": "ARMED",
    "orders_submitted": 0,
    "place_order_called": 0,
    "auto_graduate_to_live": False,
    "product_mode": "READ_ONLY_RESEARCH_TERMINAL",
}

# Certification is the moat: acceptance requires research_eligible datasets. This
# gateway never overrides it; it only reads and displays the verdict.
#
# CORS: defaults to localhost. On EC2/prod set QFT_CORS_ORIGINS to a comma-list of
# allowed browser origins (e.g. "http://<public-ip>:3000"), or "*" for an open demo.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("QFT_CORS_ORIGINS", _default_origins).split(",") if o.strip()
]

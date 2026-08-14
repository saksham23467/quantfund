"""QuantFund Research Terminal — backend (research_api gateway).

Ensures the repository root is importable so the gateway can call the REAL,
UNMODIFIED QuantFund research infrastructure (dataset certification, PIT
universe) read-only, alongside the terminal's analytics_engine and copilot.
"""

from __future__ import annotations

import sys
from pathlib import Path

# .../Quant-fund/quantfund_terminal/backend/app/__init__.py -> parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

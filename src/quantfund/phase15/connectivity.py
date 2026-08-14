"""Phase 15 read-only connectivity probes (no order submission)."""

from __future__ import annotations

from typing import Any

from quantfund.phase15.demo import run_phase15_connectivity


def probe_readonly_connectivity(env: dict[str, str] | None = None) -> dict[str, Any]:
    return run_phase15_connectivity(env=env)

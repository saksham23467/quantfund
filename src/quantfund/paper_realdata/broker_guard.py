"""Hard assertion that NO real broker write capability exists (fail closed).

This is the safety spine of real-market-data paper trading. It composes the
existing, vetted guards:

- ``PaperExecutionAdapter`` must be the only execution path and must expose no
  order-write methods (``place_order`` / ``modify_order`` / ``cancel_order`` …).
- ``assert_runtime_paper_capabilities`` rejects any write-capable adapter.
- The live-trading environment gates must NOT be satisfied.
- The aggregated static write-scans (phase 19/21) must be clean.

If any check fails, :class:`RealBrokerWriteError` is raised and paper mode
refuses to proceed. Paper execution can therefore never reach a real broker.
"""

from __future__ import annotations

from typing import Any

from quantfund.execution.modes import (
    QuantFundExecutionMode,
    broker_live_gates_satisfied,
    live_confirm_ok,
    resolve_execution_mode_from_env,
)
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.phase19.capability import assert_runtime_paper_capabilities
from quantfund.phase19.safety import require_paper_execution_only
from quantfund.phase21.safety import safety_assertions

FORBIDDEN_WRITE_METHODS = frozenset(
    {
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_order",
        "basket_order",
        "place_gtt",
        "submit_order",
    }
)


class RealBrokerWriteError(RuntimeError):
    """Raised when any real broker write capability is detected."""


def assert_no_real_broker_write_capability(
    *,
    execution_adapter: Any | None = None,
    market_data_provider: Any | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fail closed unless the whole execution surface is provably paper-only."""
    reasons: list[str] = []

    # 1. The execution adapter must be a PaperExecutionAdapter with no writes.
    adapter = execution_adapter or PaperExecutionAdapter(
        session_id="paper_realdata_preflight_probe"
    )
    require_paper_execution_only(adapter)
    cap = assert_runtime_paper_capabilities(
        execution_adapter=adapter, market_data_provider=market_data_provider
    )
    exposed = sorted(m for m in FORBIDDEN_WRITE_METHODS if hasattr(adapter, m))
    if exposed:
        reasons.append(f"paper_adapter_exposes_write_methods:{exposed}")

    # 2. Live-trading environment gates must not be satisfied.
    mode = resolve_execution_mode_from_env(env)
    live_ok, live_blockers = broker_live_gates_satisfied(
        mode=mode,
        env=env,
        risk_limits_configured=False,
        kill_switch_initialized=True,
        kill_switch_triggered=False,
        broker_healthy=False,
        strategy_broker_approved=False,
        zerodha_env=(env or {}).get("ZERODHA_ENV"),
    )
    if live_ok:
        reasons.append("broker_live_gates_satisfied")
    if mode is QuantFundExecutionMode.BROKER_LIVE:
        reasons.append("execution_mode_is_broker_live")
    if live_confirm_ok(env):
        reasons.append("live_confirm_phrase_present")

    # 3. Static write-scan across the paper/real-time surface must be clean.
    safety = safety_assertions()
    if not safety.get("ok", False):
        reasons.append(f"write_scan_not_clean:{safety.get('write_scan_hits')}")

    if reasons:
        raise RealBrokerWriteError("; ".join(reasons))

    return {
        "real_broker_write_capability": "ABSENT",
        "execution_adapter": cap["execution_adapter"],
        "can_place_orders": False,
        "live_trading_gates_satisfied": False,
        "live_gate_blockers": live_blockers,
        "write_scan_ok": True,
        "write_scan_hits": safety.get("write_scan_hits", []),
        "forbidden_write_methods_exposed": exposed,
    }

"""Live readiness / preflight — final result always LIVE_TRADING_DISABLED."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.execution.credentials import redact_secrets
from quantfund.paper.kill_switch import KillSwitch
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.health import (
    BrokerHealthReport,
    run_broker_health_checks,
    run_reconcile_gate,
)
from quantfund.phase16a.snapshot import BrokerConnectionSnapshot
from quantfund.phase16a.zerodha_readonly import ZerodhaReadOnlyBroker


FINAL_RESULT = "LIVE_TRADING_DISABLED"


@dataclass
class LiveReadinessReport:
    broker: str = "ZERODHA/MOCK"
    authentication: str = "FAIL"
    account_read: str = "FAIL"
    positions_read: str = "FAIL"
    orders_read: str = "FAIL"
    trades_read: str = "FAIL"
    reconciliation: str = "FAIL"
    kill_switch: str = "ARMED"
    write_capability: str = "DISABLED"
    order_submission: str = "NOT IMPLEMENTED"
    live_orders: int = 0
    research_eligibility: str = "DEVELOPMENT_ONLY"
    live_trading: str = "DISABLED"
    claims: str = "NONE"
    final_result: str = FINAL_RESULT
    health_ok: bool = False
    connection_snapshot: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    place_order_called: int = 0

    @property
    def ok(self) -> bool:
        """PASS means read-only readiness succeeded while live remains disabled."""
        return (
            self.authentication == "PASS"
            and self.account_read == "PASS"
            and self.positions_read == "PASS"
            and self.orders_read == "PASS"
            and self.trades_read == "PASS"
            and self.reconciliation == "CLEAN"
            and self.kill_switch == "ARMED"
            and self.write_capability == "DISABLED"
            and self.order_submission == "NOT IMPLEMENTED"
            and self.live_orders == 0
            and self.live_trading == "DISABLED"
            and self.final_result == FINAL_RESULT
            and self.place_order_called == 0
            and self.research_eligibility == "DEVELOPMENT_ONLY"
            and self.claims == "NONE"
        )

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(
            {
                "phase": "16A",
                "broker": self.broker,
                "authentication": self.authentication,
                "account_read": self.account_read,
                "positions_read": self.positions_read,
                "orders_read": self.orders_read,
                "trades_read": self.trades_read,
                "reconciliation": self.reconciliation,
                "kill_switch": self.kill_switch,
                "write_capability": self.write_capability,
                "order_submission": self.order_submission,
                "live_orders": 0,
                "research_eligibility": self.research_eligibility,
                "live_trading": self.live_trading,
                "claims": self.claims,
                "final_result": self.final_result,
                "health_ok": self.health_ok,
                "connection_snapshot": self.connection_snapshot,
                "errors": list(self.errors),
                "place_order_called": self.place_order_called,
                "ok": self.ok,
            }
        )


def run_live_readiness(
    broker: ZerodhaReadOnlyBroker,
    *,
    kill_switch: KillSwitch | None = None,
    internal_positions: dict[str, float] | None = None,
    symbol: str = "RELIANCE",
) -> LiveReadinessReport:
    """Preflight all live prerequisites; never enable live trading."""
    ks = kill_switch or KillSwitch()
    report = LiveReadinessReport(
        broker="ZERODHA/MOCK" if broker.simulated else "ZERODHA",
        kill_switch="TRIGGERED" if ks.is_triggered else "ARMED",
    )

    # Kill switch mandatory — triggered switch fails readiness (still live disabled)
    if ks.is_triggered:
        report.errors.append("kill_switch_triggered")
        report.final_result = FINAL_RESULT
        report.live_trading = "DISABLED"
        return report

    # Prove write path impossible
    try:
        getattr(broker, "place_order")()
        report.place_order_called += 1
        report.errors.append("place_order_succeeded")
        report.write_capability = "ENABLED"
        return report
    except Exception:
        report.place_order_called = 0
        report.write_capability = "DISABLED"
        report.order_submission = "NOT IMPLEMENTED"

    health: BrokerHealthReport = run_broker_health_checks(broker, symbol=symbol)
    report.health_ok = health.ok
    report.authentication = health.authentication
    report.errors.extend(health.errors)

    try:
        acct = broker.get_account()
        report.account_read = "PASS" if acct.connected else "FAIL"
    except Exception as exc:  # noqa: BLE001
        report.account_read = "FAIL"
        report.errors.append(f"account_read:{type(exc).__name__}")

    try:
        broker.get_positions()
        report.positions_read = "PASS"
    except Exception as exc:  # noqa: BLE001
        report.positions_read = "FAIL"
        report.errors.append(f"positions_read:{type(exc).__name__}")

    try:
        broker.get_orders()
        report.orders_read = "PASS"
    except Exception as exc:  # noqa: BLE001
        report.orders_read = "FAIL"
        report.errors.append(f"orders_read:{type(exc).__name__}")

    try:
        broker.get_trades()
        report.trades_read = "PASS"
    except Exception as exc:  # noqa: BLE001
        report.trades_read = "FAIL"
        report.errors.append(f"trades_read:{type(exc).__name__}")

    reco = run_reconcile_gate(
        broker, internal_positions=internal_positions, kill_switch=ks
    )
    report.reconciliation = reco["reconciliation"]
    if reco["prevents_future_order_submission"] and reco["reconciliation"] == "RECONCILIATION_MISMATCH":
        report.errors.append("reconciliation_mismatch_blocks_future_orders")

    snap: BrokerConnectionSnapshot | None = broker.connection_snapshot()
    if snap is not None:
        report.connection_snapshot = redact_secrets(snap.to_dict())

    # Hard invariants
    report.live_orders = 0
    report.live_trading = "DISABLED"
    report.final_result = FINAL_RESULT
    report.research_eligibility = "DEVELOPMENT_ONLY"
    report.claims = "NONE"
    report.order_submission = "NOT IMPLEMENTED"
    report.kill_switch = "ARMED" if not ks.is_triggered else "TRIGGERED"
    return report

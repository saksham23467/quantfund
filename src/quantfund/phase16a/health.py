"""Broker connectivity health checks for Phase 16A."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.execution.credentials import redact_secrets
from quantfund.paper.kill_switch import KillSwitch
from quantfund.phase15.reconcile import reconcile_positions
from quantfund.phase16a.zerodha_readonly import ZerodhaReadOnlyBroker


@dataclass
class BrokerHealthReport:
    authentication: str = "FAIL"
    api_reachability: str = "FAIL"
    account_identity: str = "FAIL"
    market_data_freshness: str = "FAIL"
    clock_time_sanity: str = "FAIL"
    position_retrieval: str = "FAIL"
    order_retrieval: str = "FAIL"
    trade_retrieval: str = "FAIL"
    holdings_retrieval: str = "FAIL"
    funds_retrieval: str = "FAIL"
    write_capability: str = "DISABLED"
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        checks = [
            self.authentication,
            self.api_reachability,
            self.account_identity,
            self.market_data_freshness,
            self.clock_time_sanity,
            self.position_retrieval,
            self.order_retrieval,
            self.trade_retrieval,
            self.holdings_retrieval,
            self.funds_retrieval,
        ]
        return all(c == "PASS" for c in checks) and self.write_capability == "DISABLED"

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "authentication": self.authentication,
                "api_reachability": self.api_reachability,
                "account_identity": self.account_identity,
                "market_data_freshness": self.market_data_freshness,
                "clock_time_sanity": self.clock_time_sanity,
                "position_retrieval": self.position_retrieval,
                "order_retrieval": self.order_retrieval,
                "trade_retrieval": self.trade_retrieval,
                "holdings_retrieval": self.holdings_retrieval,
                "funds_retrieval": self.funds_retrieval,
                "write_capability": self.write_capability,
                "ok": self.ok,
                "errors": list(self.errors),
            }
        )


def run_broker_health_checks(
    broker: ZerodhaReadOnlyBroker,
    *,
    symbol: str = "RELIANCE",
) -> BrokerHealthReport:
    report = BrokerHealthReport()
    try:
        if not broker.can_place_orders:
            report.write_capability = "DISABLED"
        else:
            report.write_capability = "ENABLED"
            report.errors.append("write_capability_must_be_disabled")
            return report

        if not broker.health().get("connected"):
            broker.connect()
        report.authentication = "PASS"
        report.api_reachability = "PASS"

        snap = broker.connection_snapshot()
        if snap and snap.account_id_hash:
            report.account_identity = "PASS"
        else:
            report.errors.append("account_identity_missing")

        fresh = broker.quote_freshness(symbol)
        report.market_data_freshness = "PASS" if not fresh.get("stale") else "FAIL"
        report.clock_time_sanity = "PASS" if fresh.get("clock_skew_ok") else "FAIL"
        if fresh.get("stale"):
            report.errors.append("stale_data")
        if not fresh.get("clock_skew_ok"):
            report.errors.append("clock_skew")

        _ = broker.get_positions()
        report.position_retrieval = "PASS"
        _ = broker.get_orders()
        report.order_retrieval = "PASS"
        _ = broker.get_trades()
        report.trade_retrieval = "PASS"
        _ = broker.get_holdings()
        report.holdings_retrieval = "PASS"
        margins = broker.get_margins()
        report.funds_retrieval = "PASS" if margins is not None else "FAIL"
    except Exception as exc:  # noqa: BLE001
        report.errors.append(type(exc).__name__)
        # leave failed fields as FAIL
    return report


def run_reconcile_gate(
    broker: ZerodhaReadOnlyBroker,
    *,
    internal_positions: dict[str, float] | None = None,
    kill_switch: KillSwitch | None = None,
) -> dict[str, Any]:
    """Reconciliation mismatch prevents future order submission."""
    ks = kill_switch or KillSwitch()
    broker_pos = broker.get_positions()
    reco = reconcile_positions(
        broker_positions=broker_pos,
        shadow_positions=internal_positions or {},
        enabled=True,
    )
    mismatch = reco.status == "RECONCILIATION_MISMATCH"
    return {
        "reconciliation": reco.status,
        # Phase 16A never enables live submission; mismatch hard-blocks future paths.
        "allows_future_order_submission": False,
        "blocks_future_orders": mismatch or ks.is_triggered,
        "prevents_future_order_submission": mismatch or ks.is_triggered,
        "kill_switch": "TRIGGERED" if ks.is_triggered else "ARMED",
        "live_orders": 0,
        "mismatches": reco.mismatches,
    }

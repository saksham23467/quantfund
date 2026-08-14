"""Fail-closed decision helpers for production order path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FailClosedDecision:
    allow_new_order: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_new_order": self.allow_new_order,
            "reason": self.reason,
        }


def decide_fail_closed(
    *,
    broker_timeout: bool = False,
    malformed_broker_response: bool = False,
    authentication_failure: bool = False,
    unknown_instrument: bool = False,
    stale_market_data: bool = False,
    stale_clock: bool = False,
    reconciliation_mismatch: bool = False,
    risk_config_missing: bool = False,
    duplicate_intent: bool = False,
    unknown_order_status: bool = False,
    unexpected_fill: bool = False,
    kill_switch: bool = False,
    corrupted_local_state: bool = False,
) -> FailClosedDecision:
    """Any failure ⇒ NO NEW ORDER."""
    checks = [
        ("broker_timeout", broker_timeout),
        ("malformed_broker_response", malformed_broker_response),
        ("authentication_failure", authentication_failure),
        ("unknown_instrument", unknown_instrument),
        ("stale_market_data", stale_market_data),
        ("stale_clock", stale_clock),
        ("reconciliation_mismatch", reconciliation_mismatch),
        ("risk_config_missing", risk_config_missing),
        ("duplicate_intent", duplicate_intent),
        ("unknown_order_status", unknown_order_status),
        ("unexpected_fill", unexpected_fill),
        ("kill_switch", kill_switch),
        ("corrupted_local_state", corrupted_local_state),
    ]
    for reason, hit in checks:
        if hit:
            return FailClosedDecision(False, reason)
    return FailClosedDecision(True, "ok")

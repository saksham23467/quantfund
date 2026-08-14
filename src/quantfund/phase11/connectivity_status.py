"""Broker connectivity states — never collapse SIMULATED / PAPER / LIVE."""

from __future__ import annotations

from enum import Enum


class BrokerConnectivityStatus(str, Enum):
    SIMULATED = "SIMULATED"
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    PAPER = "PAPER"
    LIVE = "LIVE"  # must never be selected by Phase 11 runners


def assert_not_live(status: BrokerConnectivityStatus) -> None:
    if status == BrokerConnectivityStatus.LIVE:
        raise ValueError("phase11_live_connectivity_forbidden")

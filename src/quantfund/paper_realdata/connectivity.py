"""Honest Zerodha market-data connectivity probe.

Attempts to build the REAL Zerodha paper data provider (read-only market data,
never a write broker). A mock/simulation transport is NEVER counted as a real
connection: if credentials are missing or the connection fails, the probe
reports ``zerodha_data_connected = false`` rather than fabricating connectivity.
"""

from __future__ import annotations

import os
from typing import Any


def check_zerodha_data_connectivity(
    *,
    symbols: list[str],
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Probe read-only Zerodha data connectivity. Fails closed to not-connected."""
    env = env if env is not None else dict(os.environ)
    detail = ""
    connected = False
    simulation_only = True
    try:
        from quantfund.phase21.market_data import build_zerodha_paper_provider

        provider = build_zerodha_paper_provider(
            symbols=symbols, env=env, force_mock=False
        )
        connect = getattr(provider, "connect", None)
        if callable(connect):
            connect()
        health = getattr(provider, "health", None)
        h = health() if callable(health) else None
        raw_connected = bool(getattr(h, "connected", False)) if h is not None else False
        # ``simulation_only`` on ProviderHealth is authoritative and true for any
        # mock/sandbox transport (the wrapper does not expose ``is_mock``).
        sim_flag = bool(getattr(h, "simulation_only", True)) if h is not None else True
        detail = getattr(h, "detail", "") if h is not None else "no_health"
        # A mock/simulation transport is never counted as a real connection.
        connected = raw_connected and not sim_flag
        simulation_only = sim_flag or not connected
    except Exception as exc:  # noqa: BLE001 — any failure ⇒ not connected (honest)
        detail = f"{type(exc).__name__}:{exc}"
        connected = False
        simulation_only = True

    return {
        "data_source": "ZERODHA",
        "zerodha_data_connected": connected,
        "simulation_only": simulation_only,
        "detail": detail,
        "symbols": list(symbols),
    }

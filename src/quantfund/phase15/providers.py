"""Phase 15 market-data providers with capability / provenance declarations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quantfund.phase14.market_data import (
    ProviderHealth,
    RealTimeBar,
    RealTimeMarketDataProvider,
    YFinanceSimulationMarketDataProvider,
)
from quantfund.phase15.capabilities import MarketDataCapabilities


YFINANCE_CAPS = MarketDataCapabilities(
    provider_id="yfinance_simulation",
    source_grade="non_exchange",
    exchange="NSE",
    timezone="Asia/Kolkata",
    timestamp_semantics="bar_close_ist_simulated",
    realtime_quotes=False,
    historical_bars=True,
    websocket=False,
    streaming=True,
    instrument_master=False,
    simulation_only=True,
    research_eligible=False,
    license_status="development_public_unlicensed",
)


@dataclass
class ProviderProvenance:
    provider_id: str
    source_grade: str
    simulation_only: bool
    research_eligible: bool
    license_status: str
    configured: bool
    mode: str  # SIMULATED | REAL_READ_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "source_grade": self.source_grade,
            "simulation_only": self.simulation_only,
            "research_eligible": self.research_eligible,
            "license_status": self.license_status,
            "configured": self.configured,
            "mode": self.mode,
        }


class CapableMarketDataProvider(RealTimeMarketDataProvider):
    """Decorator adding capability/provenance without changing stream semantics."""

    def __init__(
        self,
        inner: RealTimeMarketDataProvider,
        *,
        capabilities: MarketDataCapabilities,
        provenance: ProviderProvenance,
    ) -> None:
        self.inner = inner
        self._capabilities = capabilities
        self._provenance = provenance
        self._disconnect_forced = False

    def capabilities(self) -> MarketDataCapabilities:
        return self._capabilities

    def provenance(self) -> ProviderProvenance:
        return self._provenance

    def connect(self) -> None:
        if self._disconnect_forced:
            raise ConnectionError("provider_disconnected")
        self.inner.connect()

    def disconnect(self) -> None:
        self.inner.disconnect()

    def subscribe(self, symbols: list[str]) -> None:
        self.inner.subscribe(symbols)

    def next_bar(self) -> RealTimeBar | None:
        if self._disconnect_forced:
            return None
        return self.inner.next_bar()

    def health(self) -> ProviderHealth:
        h = self.inner.health()
        if self._disconnect_forced:
            h.connected = False
            h.detail = (h.detail or "") + ";disconnected"
        return h

    def last_update(self) -> datetime | None:
        return self.inner.last_update()

    def force_disconnect(self) -> None:
        self._disconnect_forced = True
        self.inner.disconnect()

    def reconnect(self) -> None:
        self._disconnect_forced = False
        self.inner.connect()


class RealReadOnlyMarketDataStub(RealTimeMarketDataProvider):
    """Configured real-data placeholder — no exchange-grade claims.

    Used when credentials/env mark a real feed as configured. Phase 15 demo
    still falls back to simulation unless a stream is injected for tests.
    """

    def __init__(self, *, stream: list[RealTimeBar] | None = None) -> None:
        self._sim = YFinanceSimulationMarketDataProvider(stream=stream or [])
        self._provider_id = "real_readonly_stub"

    def connect(self) -> None:
        self._sim.connect()

    def disconnect(self) -> None:
        self._sim.disconnect()

    def subscribe(self, symbols: list[str]) -> None:
        self._sim.subscribe(symbols)

    def next_bar(self) -> RealTimeBar | None:
        return self._sim.next_bar()

    def health(self) -> ProviderHealth:
        h = self._sim.health()
        h.source_grade = "vendor_read_only"
        h.simulation_only = False
        h.research_eligible = False
        h.detail = "real_readonly_stub_not_exchange_grade"
        return h

    def last_update(self) -> datetime | None:
        return self._sim.last_update()


REAL_READONLY_CAPS = MarketDataCapabilities(
    provider_id="real_readonly_stub",
    source_grade="vendor_read_only",
    exchange="NSE",
    timezone="Asia/Kolkata",
    timestamp_semantics="vendor_exchange_timestamp",
    realtime_quotes=True,
    historical_bars=True,
    websocket=False,
    streaming=True,
    instrument_master=False,
    simulation_only=False,
    research_eligible=False,
    license_status="operator_configured_unverified",
)


def real_provider_configured(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else dict(os.environ)
    return bool(
        env.get("QUANTFUND_REAL_MARKET_DATA") == "1"
        or env.get("PHASE15_REAL_MARKET_DATA") == "1"
    )


def build_market_data_provider(
    *,
    stream: list[RealTimeBar] | None = None,
    env: dict[str, str] | None = None,
    force_simulated: bool = False,
) -> CapableMarketDataProvider:
    """Prefer simulated fallback; real stub only when explicitly configured."""
    if force_simulated or not real_provider_configured(env):
        inner = (
            YFinanceSimulationMarketDataProvider(stream=stream)
            if stream is not None
            else YFinanceSimulationMarketDataProvider.from_fixture_bars()
        )
        return CapableMarketDataProvider(
            inner,
            capabilities=YFINANCE_CAPS,
            provenance=ProviderProvenance(
                provider_id=YFINANCE_CAPS.provider_id,
                source_grade=YFINANCE_CAPS.source_grade,
                simulation_only=True,
                research_eligible=False,
                license_status=YFINANCE_CAPS.license_status,
                configured=False,
                mode="SIMULATED",
            ),
        )
    inner = RealReadOnlyMarketDataStub(stream=stream)
    if stream is None:
        # still need bars for demo — wrap fixture under real provenance label only
        # when operator opted in; stream still comes from labeled fixture.
        base = YFinanceSimulationMarketDataProvider.from_fixture_bars()
        inner = RealReadOnlyMarketDataStub(stream=list(base._stream))
    return CapableMarketDataProvider(
        inner,
        capabilities=REAL_READONLY_CAPS,
        provenance=ProviderProvenance(
            provider_id=REAL_READONLY_CAPS.provider_id,
            source_grade=REAL_READONLY_CAPS.source_grade,
            simulation_only=False,
            research_eligible=False,
            license_status=REAL_READONLY_CAPS.license_status,
            configured=True,
            mode="REAL_READ_ONLY",
        ),
    )

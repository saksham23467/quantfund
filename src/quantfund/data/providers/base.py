"""Abstract market data provider interface.

Backtester depends only on this interface, never on a specific vendor SDK.
Future providers (NSEProvider, BrokerDataProvider, PaidMarketDataProvider)
should implement the same contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from quantfund.data.models import Instrument, MarketBar


class DataProvider(ABC):
    """Vendor-agnostic historical market data source."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used in experiment metadata."""

    @abstractmethod
    def get_instruments(self) -> list[Instrument]:
        """Return instruments known to this provider instance."""

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        """Return validated chronological OHLCV bars for ``symbol``.

        Bars are inclusive of start/end when those bounds are provided,
        subject to provider availability. Implementations must not mutate
        previously persisted raw downloads.
        """

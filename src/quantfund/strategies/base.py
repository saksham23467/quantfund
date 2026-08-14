"""Standard strategy interface.

A strategy produces Signals / intended Orders only.
It must never create Fills or access a broker.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from quantfund.data.models import MarketBar
from quantfund.trading.models import Order, OrderSide, Signal, SignalAction


@dataclass(frozen=True)
class StrategyMetadata:
    """Identity and versioning for reproducible experiments."""

    strategy_id: str
    strategy_name: str
    strategy_version: str
    parameters: dict[str, Any] = field(default_factory=dict)
    code_version: str = "0.1.0"
    description: str = ""
    required_features: list[str] = field(default_factory=list)
    parameter_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    """Information available to the strategy at simulation time t.

    Contains only bars with timestamp <= t. The engine constructs this;
    strategies must not reach outside it for market data.
    """

    timestamp: datetime
    symbol: str
    history: list[MarketBar]
    position_quantity: float
    cash: float
    # Phase 2 research fields (optional; absent in pure M1 backtests)
    features: dict[str, float | None] = field(default_factory=dict)
    membership: str | None = None  # TRUE | FALSE | UNKNOWN

    @property
    def current_bar(self) -> MarketBar | None:
        if not self.history:
            return None
        return self.history[-1]

    def feature(self, name: str) -> float | None:
        return self.features.get(name)


class Strategy(ABC):
    """Base class for deterministic executable strategies."""

    @abstractmethod
    def metadata(self) -> StrategyMetadata:
        """Return strategy identity, version, and parameters."""

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        """Optional preprocessing. Must not introduce look-ahead.

        Default: return bars unchanged.
        """
        return bars

    @abstractmethod
    def generate_signal(self, context: StrategyContext) -> Signal:
        """Produce a BUY / SELL / HOLD signal using only ``context``."""

    def generate_orders(self, signal: Signal, context: StrategyContext) -> list[Order]:
        """Convert a signal into intended orders.

        Default mapping:
        - BUY with target_quantity or full cash deployment intent via metadata
        - SELL flattens long position
        - HOLD → no orders
        """
        if signal.action == SignalAction.HOLD:
            return []

        if signal.action == SignalAction.BUY:
            qty = signal.target_quantity
            if qty is None or qty <= 0:
                return []
            return [
                Order(
                    timestamp=signal.timestamp,
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    quantity=float(qty),
                    signal_timestamp=signal.timestamp,
                )
            ]

        if signal.action == SignalAction.SELL:
            qty = signal.target_quantity
            if qty is None:
                qty = context.position_quantity
            if qty is None or qty <= 0:
                return []
            return [
                Order(
                    timestamp=signal.timestamp,
                    symbol=signal.symbol,
                    side=OrderSide.SELL,
                    quantity=float(qty),
                    signal_timestamp=signal.timestamp,
                )
            ]

        return []

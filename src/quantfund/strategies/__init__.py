"""Strategy definitions and interfaces. Strategies never access brokers."""

from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines import (
    MeanReversionStrategy,
    MomentumStrategy,
    MovingAverageCrossStrategy,
    VolatilityBreakoutStrategy,
)
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy

__all__ = [
    "Strategy",
    "StrategyContext",
    "StrategyMetadata",
    "BuyAndHoldStrategy",
    "MovingAverageCrossStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "VolatilityBreakoutStrategy",
]

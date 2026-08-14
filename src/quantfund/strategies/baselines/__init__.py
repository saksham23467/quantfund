"""Deterministic baseline strategies for research engine verification."""

from quantfund.strategies.baselines.ma_cross import MovingAverageCrossStrategy
from quantfund.strategies.baselines.mean_reversion import MeanReversionStrategy
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.strategies.baselines.vol_breakout import VolatilityBreakoutStrategy
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy

__all__ = [
    "BuyAndHoldStrategy",
    "MovingAverageCrossStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "VolatilityBreakoutStrategy",
]

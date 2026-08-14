"""Extensible transaction cost models.

Milestone 1 implements equity delivery only.
Values are configurable research assumptions — not exact current broker charges.
Do not treat defaults as production fee schedules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from quantfund.trading.models import OrderSide


class MarketSegment(str, Enum):
    """Future segments; only EQUITY_DELIVERY is implemented in M1."""

    EQUITY_DELIVERY = "equity_delivery"
    EQUITY_INTRADAY = "equity_intraday"
    FUTURES = "futures"
    OPTIONS = "options"


@dataclass(frozen=True)
class CostBreakdown:
    """Itemized transaction costs for a single fill."""

    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    stamp_duty: float
    sebi_charges: float

    @property
    def total(self) -> float:
        return (
            self.brokerage
            + self.stt
            + self.exchange_charges
            + self.gst
            + self.stamp_duty
            + self.sebi_charges
        )


class CostModel(ABC):
    """Abstract cost model interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier stored in experiment metadata."""

    @abstractmethod
    def compute(
        self,
        *,
        side: OrderSide,
        quantity: float,
        price: float,
        segment: MarketSegment = MarketSegment.EQUITY_DELIVERY,
    ) -> CostBreakdown:
        """Return itemized costs for a fill at ``price`` × ``quantity``."""


@dataclass(frozen=True)
class EquityDeliveryCostConfig:
    """Configurable research assumptions for equity delivery costs (INR / rates).

    All fields are research placeholders. Update deliberately and document
    changes in ASSUMPTIONS.md. These are NOT claims of exact live charges.
    """

    # Brokerage as fraction of turnover (e.g. 0.0003 = 3 bps)
    brokerage_rate: float = 0.0003
    brokerage_min: float = 0.0

    # STT on delivery: typically charged on sell side for delivery equities.
    # Research assumption: apply configured rate on sell turnover only.
    stt_sell_rate: float = 0.001  # 0.10% of sell turnover (assumption)
    stt_buy_rate: float = 0.0

    # Exchange transaction charges as fraction of turnover
    exchange_rate: float = 0.0000297

    # GST on (brokerage + exchange charges)
    gst_rate: float = 0.18

    # Stamp duty on buy turnover (state-dependent; research assumption)
    stamp_duty_buy_rate: float = 0.00015
    stamp_duty_sell_rate: float = 0.0

    # SEBI charges as fraction of turnover
    sebi_rate: float = 0.000001


class EquityDeliveryCostModel(CostModel):
    """Equity delivery cost model for Milestone 1."""

    def __init__(self, config: EquityDeliveryCostConfig | None = None) -> None:
        self.config = config or EquityDeliveryCostConfig()

    @property
    def name(self) -> str:
        return "equity_delivery_v1"

    def compute(
        self,
        *,
        side: OrderSide,
        quantity: float,
        price: float,
        segment: MarketSegment = MarketSegment.EQUITY_DELIVERY,
    ) -> CostBreakdown:
        if segment != MarketSegment.EQUITY_DELIVERY:
            raise NotImplementedError(
                f"Segment {segment} not implemented in Milestone 1; "
                "only equity_delivery is supported."
            )
        turnover = quantity * price
        cfg = self.config

        brokerage = max(turnover * cfg.brokerage_rate, cfg.brokerage_min)
        exchange = turnover * cfg.exchange_rate
        gst = (brokerage + exchange) * cfg.gst_rate
        sebi = turnover * cfg.sebi_rate

        if side == OrderSide.BUY:
            stt = turnover * cfg.stt_buy_rate
            stamp = turnover * cfg.stamp_duty_buy_rate
        else:
            stt = turnover * cfg.stt_sell_rate
            stamp = turnover * cfg.stamp_duty_sell_rate

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange,
            gst=gst,
            stamp_duty=stamp,
            sebi_charges=sebi,
        )

"""Chronological event-driven backtest engine.

Execution model (Milestone 1):
  signal at bar close → order → risk check → schedule next-bar open
  → slippage → transaction costs → fill → portfolio update

Same-bar execution is forbidden. Strategies only see bars with timestamp <= t.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from quantfund.backtest.broker_sim import BrokerSimulator, SlippageModel
from quantfund.backtest.costs import CostModel, EquityDeliveryCostModel
from quantfund.backtest.portfolio import Portfolio
from quantfund.data.models import MarketBar
from quantfund.risk.limits import RiskConfig, RiskEngine
from quantfund.strategies.base import Strategy, StrategyContext
from quantfund.trading.models import Order, OrderStatus, Signal

ContextEnricher = Callable[[StrategyContext], StrategyContext]


@dataclass
class ScheduledOrder:
    order: Order
    signal_bar_timestamp: datetime


@dataclass
class BacktestConfig:
    """Experiment configuration persisted with results."""

    experiment_id: str = field(default_factory=lambda: uuid4().hex)
    initial_capital: float = 100_000.0
    data_source: str = "unknown"
    data_version: str = "unknown"
    # Phase 1 dataset lineage (optional; required for dataset-backed runs)
    dataset_id: str | None = None
    dataset_version: str | None = None
    research_eligibility: str | None = None
    data_class: str | None = None
    universe_id: str | None = None
    universe_version: str | None = None
    universe_completeness: str | None = None
    adjustment_policy_id: str | None = None
    source_grade: str | None = None
    dataset_warnings: list[str] = field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    risk: RiskConfig = field(default_factory=RiskConfig)
    allow_same_bar_execution: bool = False  # must remain False in M1


@dataclass
class BacktestResult:
    experiment_id: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    code_version: str
    parameters: dict[str, Any]
    data_source: str
    data_version: str
    start_date: datetime | None
    end_date: datetime | None
    initial_capital: float
    cost_model: str
    slippage_model: str
    portfolio: Portfolio
    signals: list[Signal]
    orders: list[Order]
    rejected_orders: list[Order]
    events: list[dict[str, Any]]
    dataset_id: str | None = None
    dataset_version: str | None = None
    research_eligibility: str | None = None
    data_class: str | None = None
    universe_id: str | None = None
    universe_version: str | None = None
    universe_completeness: str | None = None
    adjustment_policy_id: str | None = None
    source_grade: str | None = None
    dataset_warnings: list[str] = field(default_factory=list)

    @property
    def final_equity(self) -> float:
        return self.portfolio.equity


class LookAheadError(RuntimeError):
    """Raised if the engine detects potential future-data access."""


class BacktestEngine:
    """Single-symbol chronological backtester for Milestone 1."""

    def __init__(
        self,
        strategy: Strategy,
        *,
        config: BacktestConfig | None = None,
        cost_model: CostModel | None = None,
        slippage_model: SlippageModel | None = None,
        risk_engine: RiskEngine | None = None,
        broker: BrokerSimulator | None = None,
        context_enricher: ContextEnricher | None = None,
    ) -> None:
        self.strategy = strategy
        self.config = config or BacktestConfig()
        if self.config.allow_same_bar_execution:
            raise ValueError("same-bar execution is not allowed in Milestone 1")
        self.cost_model = cost_model or EquityDeliveryCostModel()
        self.slippage_model = slippage_model or SlippageModel()
        self.risk_engine = risk_engine or RiskEngine(self.config.risk)
        self.broker = broker or BrokerSimulator(
            cost_model=self.cost_model,
            slippage_model=self.slippage_model,
        )
        # Optional Phase 2 hook: inject as-of features / membership (must not add future data)
        self.context_enricher = context_enricher

    def run(self, bars: list[MarketBar]) -> BacktestResult:
        """Run the backtest over chronological bars for one symbol universe."""
        prepared = self.strategy.prepare_data(bars)
        if not prepared:
            raise ValueError("no bars available after strategy.prepare_data")

        # Enforce global chronological order.
        for i in range(1, len(prepared)):
            if prepared[i].timestamp < prepared[i - 1].timestamp:
                raise LookAheadError("input bars are not chronologically ordered")

        meta = self.strategy.metadata()
        portfolio = Portfolio(cash=self.config.initial_capital)
        pending: ScheduledOrder | None = None
        signals: list[Signal] = []
        orders: list[Order] = []
        rejected: list[Order] = []
        events: list[dict[str, Any]] = []

        # History visible to strategy: strictly bars with timestamp <= t
        visible: list[MarketBar] = []

        for idx, bar in enumerate(prepared):
            # 1) Advance simulation time / mark-to-market at open before fills?
            # Execution at this bar's open for orders scheduled on prior close.
            if pending is not None:
                if pending.signal_bar_timestamp >= bar.timestamp:
                    raise LookAheadError(
                        "scheduled order execution time must be after signal bar"
                    )
                fill = self.broker.execute(
                    pending.order,
                    execution_time=bar.timestamp,
                    open_price=bar.open,
                )
                # Cash sufficiency check for buys
                if fill.net_cash_delta < 0 and portfolio.cash + fill.net_cash_delta < -1e-9:
                    pending.order.status = OrderStatus.CANCELLED
                    pending.order.reject_reason = "insufficient_cash_at_fill"
                    rejected.append(pending.order)
                    events.append(
                        {
                            "type": "order_cancelled",
                            "timestamp": bar.timestamp.isoformat(),
                            "reason": "insufficient_cash_at_fill",
                            "order_id": pending.order.order_id,
                        }
                    )
                else:
                    portfolio.apply_fill(fill)
                    events.append(
                        {
                            "type": "fill",
                            "timestamp": fill.timestamp.isoformat(),
                            "order_id": fill.order_id,
                            "side": fill.side.value,
                            "qty": fill.quantity,
                            "price": fill.price,
                            "costs": fill.transaction_cost,
                            "slippage_per_unit": fill.slippage_per_unit,
                        }
                    )
                pending = None

            # Mark portfolio at close for equity curve / strategy context.
            portfolio.update_mark(bar.symbol, bar.close)
            visible.append(bar)
            self._assert_no_future(visible, bar.timestamp)

            context = StrategyContext(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                history=list(visible),
                position_quantity=portfolio.position_quantity(bar.symbol),
                cash=portfolio.cash,
            )
            if self.context_enricher is not None:
                context = self.context_enricher(context)

            signal = self.strategy.generate_signal(context)
            signals.append(signal)
            events.append(
                {
                    "type": "signal",
                    "timestamp": signal.timestamp.isoformat(),
                    "action": signal.action.value,
                    "target_quantity": signal.target_quantity,
                }
            )

            intended = self.strategy.generate_orders(signal, context)
            for order in intended:
                # Risk uses close as reference for limit checks (not fill price).
                decision = self.risk_engine.check_order(
                    order,
                    ref_price=bar.close,
                    current_position_qty=portfolio.position_quantity(bar.symbol),
                    current_exposure=portfolio.exposure(),
                )
                if not decision.accepted:
                    rejected.append(decision.order)
                    orders.append(decision.order)
                    events.append(
                        {
                            "type": "order_rejected",
                            "timestamp": bar.timestamp.isoformat(),
                            "reason": decision.reason,
                            "order_id": decision.order.order_id,
                        }
                    )
                    continue

                accepted = decision.order
                # Schedule for next bar open — never same bar.
                if idx + 1 >= len(prepared):
                    accepted.status = OrderStatus.CANCELLED
                    accepted.reject_reason = "no_next_bar_for_execution"
                    rejected.append(accepted)
                    orders.append(accepted)
                    events.append(
                        {
                            "type": "order_cancelled",
                            "timestamp": bar.timestamp.isoformat(),
                            "reason": "no_next_bar_for_execution",
                            "order_id": accepted.order_id,
                        }
                    )
                    continue

                next_bar = prepared[idx + 1]
                if next_bar.timestamp <= bar.timestamp:
                    raise LookAheadError("next bar does not advance time")

                accepted.status = OrderStatus.SCHEDULED
                accepted.scheduled_execution_time = next_bar.timestamp
                orders.append(accepted)
                if pending is not None:
                    # M1 single-symbol: replace unfilled scheduled order.
                    pending.order.status = OrderStatus.CANCELLED
                    pending.order.reject_reason = "superseded"
                    rejected.append(pending.order)
                pending = ScheduledOrder(
                    order=accepted,
                    signal_bar_timestamp=bar.timestamp,
                )
                events.append(
                    {
                        "type": "order_scheduled",
                        "timestamp": bar.timestamp.isoformat(),
                        "execute_at": next_bar.timestamp.isoformat(),
                        "order_id": accepted.order_id,
                        "side": accepted.side.value,
                        "qty": accepted.quantity,
                    }
                )

            portfolio.record_equity(bar.timestamp)

        start = self.config.start_date or prepared[0].timestamp
        end = self.config.end_date or prepared[-1].timestamp

        if self.config.dataset_warnings:
            events.insert(
                0,
                {
                    "type": "dataset_warning",
                    "warnings": list(self.config.dataset_warnings),
                    "research_eligibility": self.config.research_eligibility,
                    "dataset_id": self.config.dataset_id,
                    "dataset_version": self.config.dataset_version,
                },
            )

        return BacktestResult(
            experiment_id=self.config.experiment_id,
            strategy_id=meta.strategy_id,
            strategy_name=meta.strategy_name,
            strategy_version=meta.strategy_version,
            code_version=meta.code_version,
            parameters=dict(meta.parameters),
            data_source=self.config.data_source,
            data_version=self.config.data_version,
            start_date=start,
            end_date=end,
            initial_capital=self.config.initial_capital,
            cost_model=self.cost_model.name,
            slippage_model=self.slippage_model.name,
            portfolio=portfolio,
            signals=signals,
            orders=orders,
            rejected_orders=rejected,
            events=events,
            dataset_id=self.config.dataset_id,
            dataset_version=self.config.dataset_version,
            research_eligibility=self.config.research_eligibility,
            data_class=self.config.data_class,
            universe_id=self.config.universe_id,
            universe_version=self.config.universe_version,
            universe_completeness=self.config.universe_completeness,
            adjustment_policy_id=self.config.adjustment_policy_id,
            source_grade=self.config.source_grade,
            dataset_warnings=list(self.config.dataset_warnings),
        )

    @staticmethod
    def _assert_no_future(history: list[MarketBar], current_time: datetime) -> None:
        for bar in history:
            if bar.timestamp > current_time:
                raise LookAheadError(
                    f"future bar {bar.timestamp.isoformat()} visible at "
                    f"{current_time.isoformat()}"
                )

"""TRAIN-only cheap screening — never touches VALIDATION or TEST."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.analytics.metrics import compute_metrics
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.models import MarketBar
from quantfund.research.execution_models import resolve_execution_models
from quantfund.research.splits import ChronologicalSplit, SealedTestSetError, SplitConfig
from quantfund.strategies.base import Strategy


class ScreeningPolicy(BaseModel):
    """Versioned cheap-screen thresholds (architecture defaults)."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = "screening_policy_v1"
    min_trades: int = 5
    max_drawdown: float = 0.40
    require_finite_metrics: bool = True
    max_cost_drag_fraction: float | None = None  # costs / max(gross_profit, eps)
    beat_cash: bool = False


@dataclass(frozen=True)
class ScreeningResult:
    passed: bool
    policy_id: str
    metrics: dict[str, Any]
    rejection_reason: str | None
    train_bar_count: int
    validation_accessed: bool = False
    test_accessed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "policy_id": self.policy_id,
            "metrics": self.metrics,
            "rejection_reason": self.rejection_reason,
            "train_bar_count": self.train_bar_count,
            "validation_accessed": self.validation_accessed,
            "test_accessed": self.test_accessed,
        }


class ScreeningDataGuard:
    """Ensures screening code paths only receive TRAIN bars."""

    def __init__(self, split: ChronologicalSplit) -> None:
        self._split = split
        self.validation_accessed = False
        self.test_accessed = False

    @property
    def train_bars(self) -> list[MarketBar]:
        return list(self._split.train_bars)

    @property
    def validation_bars(self) -> list[MarketBar]:
        self.validation_accessed = True
        raise PermissionError("Screening must not access VALIDATION bars")

    @property
    def test_bars(self) -> list[MarketBar]:
        self.test_accessed = True
        try:
            self._split.get_test_bars()
        except SealedTestSetError:
            pass
        raise PermissionError("Screening must not access TEST bars")


def screen_on_train(
    *,
    strategy: Strategy,
    bars: list[MarketBar],
    split_config: SplitConfig,
    policy: ScreeningPolicy,
    cost_model: str,
    slippage_model: str,
    initial_capital: float,
    dataset_id: str,
    dataset_version: str,
    research_eligibility: str,
    universe_id: str = "",
    universe_version: str = "",
) -> ScreeningResult:
    """Run a cheap backtest on TRAIN only and apply ScreeningPolicy."""
    split = ChronologicalSplit.from_bars(bars, split_config)
    guard = ScreeningDataGuard(split)
    train = guard.train_bars
    # Prove TEST still sealed
    try:
        split.get_test_bars()
        return ScreeningResult(
            passed=False,
            policy_id=policy.policy_id,
            metrics={},
            rejection_reason="test_accessible_during_screening",
            train_bar_count=len(train),
            test_accessed=True,
        )
    except SealedTestSetError:
        pass

    if not train:
        return ScreeningResult(
            passed=False,
            policy_id=policy.policy_id,
            metrics={},
            rejection_reason="empty_train",
            train_bar_count=0,
        )

    cost, slip = resolve_execution_models(
        cost_model=cost_model, slippage_model=slippage_model
    )
    bt_config = BacktestConfig(
        experiment_id="screen",
        initial_capital=initial_capital,
        data_source=dataset_id,
        data_version=dataset_version,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        research_eligibility=research_eligibility,
        universe_id=universe_id,
        universe_version=universe_version,
    )
    engine = BacktestEngine(
        strategy,
        config=bt_config,
        cost_model=cost,
        slippage_model=slip,
    )
    result = engine.run(train)
    m = compute_metrics(result)
    metrics = {
        "total_return": m.total_return,
        "sharpe_ratio": m.sharpe_ratio,
        "maximum_drawdown": m.maximum_drawdown,
        "number_of_trades": m.number_of_trades,
        "total_transaction_costs": m.total_transaction_costs,
        "turnover": m.turnover,
    }

    reason: str | None = None
    if policy.require_finite_metrics:
        sharpe = metrics.get("sharpe_ratio")
        if sharpe is not None and (
            sharpe != sharpe or sharpe in (float("inf"), float("-inf"))
        ):
            reason = "non_finite_sharpe"
    if reason is None and (metrics.get("number_of_trades") or 0) < policy.min_trades:
        reason = f"min_trades<{policy.min_trades}"
    mdd = metrics.get("maximum_drawdown")
    if reason is None and mdd is not None and abs(float(mdd)) > policy.max_drawdown:
        reason = f"max_drawdown>{policy.max_drawdown}"
    if reason is None and policy.max_cost_drag_fraction is not None:
        costs = float(metrics.get("total_transaction_costs") or 0.0)
        ret = float(metrics.get("total_return") or 0.0)
        capital = initial_capital
        gross = max(ret * capital, 1e-9)
        if costs / gross > policy.max_cost_drag_fraction:
            reason = "cost_drag_too_high"
    if reason is None and policy.beat_cash:
        if (metrics.get("total_return") or 0.0) <= 0.0:
            reason = "did_not_beat_cash"

    return ScreeningResult(
        passed=reason is None,
        policy_id=policy.policy_id,
        metrics=metrics,
        rejection_reason=reason,
        train_bar_count=len(train),
        validation_accessed=guard.validation_accessed,
        test_accessed=guard.test_accessed,
    )

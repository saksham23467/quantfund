"""Helpers to wire DatasetManifest into BacktestConfig lineage fields."""

from __future__ import annotations

from quantfund.backtest.engine import BacktestConfig
from quantfund.data.datasets.manifest import DatasetManifest
from quantfund.risk.limits import RiskConfig


def backtest_config_from_manifest(
    manifest: DatasetManifest,
    *,
    initial_capital: float,
    risk: RiskConfig | None = None,
    experiment_id: str | None = None,
) -> BacktestConfig:
    cfg = BacktestConfig(
        initial_capital=initial_capital,
        data_source=manifest.source,
        data_version=manifest.dataset_version,
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        research_eligibility=manifest.research_eligibility.value,
        universe_id=manifest.universe_id,
        universe_version=manifest.universe_version,
        universe_completeness=manifest.universe_completeness.value,
        adjustment_policy_id=str(manifest.adjustment_policy.get("policy_id")),
        source_grade=manifest.source_grade.value,
        dataset_warnings=list(manifest.warnings),
        risk=risk or RiskConfig(
            max_order_value=initial_capital,
            max_position_value=initial_capital,
            max_total_exposure=initial_capital,
        ),
    )
    if experiment_id:
        cfg.experiment_id = experiment_id
    return cfg

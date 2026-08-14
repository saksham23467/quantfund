"""Experiment config hashing and reproducibility."""

from __future__ import annotations

from datetime import date

from quantfund.research.experiment import ExperimentConfig
from quantfund.research.splits import Period, SplitConfig


def _cfg(**kwargs) -> ExperimentConfig:
    base = dict(
        strategy_id="momentum",
        strategy_version="1.0.0",
        parameters={"symbol": "TEST", "lookback": 2},
        dataset_id="dev",
        dataset_version="v1",
        universe_id="nifty50",
        universe_version="stage_a_sample_v1",
        feature_versions={"momentum_2": "1.0.0"},
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="FAKE",
        calendar_version="fake_v1",
        split_config=SplitConfig(
            train=Period(start=date(2024, 1, 2), end=date(2024, 1, 3)),
            validation=Period(start=date(2024, 1, 4), end=date(2024, 1, 5)),
            test=Period(start=date(2024, 1, 8), end=date(2024, 1, 8)),
        ),
        start_date="2024-01-02",
        end_date="2024-01-08",
        initial_capital=100_000,
        research_eligibility="development_only",
        family_id="repro_family",
    )
    base.update(kwargs)
    return ExperimentConfig(**base)


def test_identical_configs_same_hash_different_ids():
    a = _cfg(experiment_id="aaa")
    b = _cfg(experiment_id="bbb")
    assert a.compute_hash() == b.compute_hash()


def test_param_change_changes_hash():
    a = _cfg(parameters={"symbol": "TEST", "lookback": 2})
    b = _cfg(parameters={"symbol": "TEST", "lookback": 3})
    assert a.compute_hash() != b.compute_hash()

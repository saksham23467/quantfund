"""Phase 6 — campaign integration, resume, report, safety."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from quantfund.data.models import MarketBar
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.research.campaign import CampaignPurpose, ResearchCampaignConfig
from quantfund.research.campaign_report import format_campaign_report_text
from quantfund.research.campaign_runner import CampaignRunner
from quantfund.research.screening import ScreeningPolicy
from quantfund.research.splits import Period, SplitConfig
from quantfund.storage.registry import ExperimentRegistry


def _bars(n: int = 55) -> list[MarketBar]:
    out = []
    d = date(2024, 1, 2)
    p = 100.0
    i = 0
    while len(out) < n:
        if d.weekday() < 5:
            p += 0.25 if i % 4 else -0.1
            out.append(
                MarketBar(
                    timestamp=datetime(d.year, d.month, d.day),
                    symbol="TEST",
                    open=p,
                    high=p + 1,
                    low=p - 1,
                    close=p,
                    volume=1000 + i,
                )
            )
            i += 1
        d += timedelta(days=1)
    return out


def _universe(bars: list[MarketBar]) -> UniverseVersion:
    dates = [b.timestamp.date() for b in bars]
    return UniverseVersion(
        universe_id="nifty50",
        universe_version="phase6_test",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=dates[-1],
        effective_start=dates[0],
        effective_end=dates[-1],
        source="test",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )


def _config(tmp_suffix: str, bars: list[MarketBar], **kwargs) -> ResearchCampaignConfig:
    dates = [b.timestamp.date() for b in bars]
    base = dict(
        purpose=CampaignPurpose.EXPLORATORY_DEVELOPMENT,
        dataset_id="india_eq_pilot_phase35",
        dataset_version="v1_synthetic",
        universe_id="nifty50",
        universe_version="phase6_test",
        candidate_budget=8,
        experiment_budget=20,
        candidate_generator="mock",
        walkforward_enabled=False,
        screening_policy=ScreeningPolicy(min_trades=1, max_drawdown=0.99),
        split_config=SplitConfig(
            train=Period(start=dates[0], end=dates[19]),
            validation=Period(start=dates[20], end=dates[34]),
            test=Period(start=dates[35], end=dates[-1]),
        ),
        certified_eligibility="development_only",
        source_grade="synthetic",
        family_id=f"phase6_{tmp_suffix}",
        random_seed=7,
        symbol="TEST",
        feature_requests=[
            {"name": "momentum", "params": {"window": 5}},
            {"name": "sma", "params": {"window": 3}},
            {"name": "sma", "params": {"window": 8}},
        ],
    )
    base.update(kwargs)
    return ResearchCampaignConfig(**base)


def test_full_synthetic_campaign_accepted_zero(tmp_path: Path):
    bars = _bars()
    reg = ExperimentRegistry(tmp_path / "reg")
    runner = CampaignRunner(reg, artifacts_root=tmp_path / "camps")
    cfg = _config("full", bars)
    result = runner.run(cfg, bars=bars, universe=_universe(bars))
    assert result.final_state == "FINALIZED"
    assert result.accepted_count == 0
    assert result.claims == "NONE"
    assert result.report["dataset"]["eligibility"] == "development_only"
    assert result.report["walkforward_enabled"] is False
    assert result.report["walkforward_note"] == "walkforward_disabled"
    assert (result.report_path / "campaign_report.json").exists()
    assert (result.report_path / "campaign_report.txt").exists()


def test_campaign_resume_finalized(tmp_path: Path):
    bars = _bars()
    reg = ExperimentRegistry(tmp_path / "reg")
    runner = CampaignRunner(reg, artifacts_root=tmp_path / "camps")
    cfg = _config("resume", bars)
    r1 = runner.run(cfg, bars=bars, universe=_universe(bars))
    r2 = runner.run(cfg, bars=bars, universe=_universe(bars), resume=True)
    assert r2.final_state == "FINALIZED"
    assert r2.config_hash == r1.config_hash
    assert r2.accepted_count == 0


def test_campaign_resume_hash_mismatch_fails(tmp_path: Path):
    bars = _bars()
    reg = ExperimentRegistry(tmp_path / "reg")
    runner = CampaignRunner(reg, artifacts_root=tmp_path / "camps")
    cfg = _config("mismatch", bars, random_seed=1)
    runner.run(cfg, bars=bars, universe=_universe(bars))
    cfg2 = cfg.model_copy(update={"random_seed": 99})
    # same campaign_id different hash
    with pytest.raises(ValueError, match="config hash mismatch"):
        runner.run(cfg2, bars=bars, universe=_universe(bars), resume=True)


def test_budget_exhaustion_does_not_accept(tmp_path: Path):
    bars = _bars()
    reg = ExperimentRegistry(tmp_path / "reg")
    runner = CampaignRunner(reg, artifacts_root=tmp_path / "camps")
    cfg = _config(
        "budget",
        bars,
        candidate_budget=6,
        experiment_budget=3,  # tiny — will exhaust during validation
        screening_policy=ScreeningPolicy(min_trades=1, max_drawdown=0.99),
    )
    result = runner.run(cfg, bars=bars, universe=_universe(bars))
    assert result.final_state == "FINALIZED"
    assert result.accepted_count == 0
    assert result.claims == "NONE"
    trials = reg.count_campaign_trials(cfg.campaign_id)
    assert trials["n_experiments"] <= 3 or any(
        "budget" in w.lower() for w in result.warnings
    )


def test_report_text_contains_safety_banner():
    payload = {
        "campaign_id": "c",
        "config_hash": "h",
        "final_state": "FINALIZED",
        "purpose": "exploratory_development",
        "dataset": {
            "dataset_id": "d",
            "dataset_version": "v",
            "eligibility": "development_only",
            "source_grade": "synthetic",
            "calendar_verified": True,
            "universe_completeness": "full_pit",
        },
        "candidates": {"generated_count": 1},
        "experiments": {
            "budget": {"max_candidates": 20},
            "trial_counts": {"n_experiments": 1},
        },
        "walkforward_enabled": False,
        "walkforward_note": "walkforward_disabled",
        "seal": {"sealed": True, "test_evaluation_log": []},
        "test_evaluation_count": 0,
        "acceptance": {"accepted_count": 0},
        "score_policy_version": "score_policy_v1",
        "cost_model": "equity_delivery_v1",
        "slippage_model": "fixed_bps_5",
        "selection_criterion": "validation_sharpe",
        "warnings": [],
        "claims": "NONE",
        "banner": "INFRASTRUCTURE VALIDATION ONLY — not evidence of edge",
    }
    text = format_campaign_report_text(payload)
    assert "Accepted: 0" in text
    assert "Claims: NONE" in text
    assert "INFRASTRUCTURE VALIDATION ONLY" in text


def test_is_campaign_sealed(tmp_path: Path):
    reg = ExperimentRegistry(tmp_path / "reg")
    reg.create_campaign(
        campaign_id="s",
        config_hash="h",
        purpose="exploratory_development",
        state="DRAFT",
        config_json={},
        created_at="2024-01-01T00:00:00+00:00",
    )
    assert reg.is_campaign_sealed("s") is False
    reg.set_campaign_state("s", "SEALING", sealed=True)
    assert reg.is_campaign_sealed("s") is True


def test_wf_enabled_recorded_in_report(tmp_path: Path):
    from quantfund.research.walkforward import WalkForwardConfig

    bars = _bars(70)
    reg = ExperimentRegistry(tmp_path / "reg")
    runner = CampaignRunner(reg, artifacts_root=tmp_path / "camps")
    cfg = _config(
        "wf",
        bars,
        walkforward_enabled=True,
        walkforward_config=WalkForwardConfig(
            mode="rolling",
            train_sessions=5,
            validation_sessions=2,
            test_sessions=2,
            step_sessions=3,
        ),
        candidate_budget=4,
        experiment_budget=15,
        screening_policy=ScreeningPolicy(min_trades=1, max_drawdown=0.99),
    )
    result = runner.run(cfg, bars=bars, universe=_universe(bars))
    assert result.report["walkforward_enabled"] is True
    assert result.accepted_count == 0

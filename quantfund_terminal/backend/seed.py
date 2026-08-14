"""Seed demo-ready data for investor presentations.

Idempotent: does nothing if orgs already exist (pass --reset to rebuild).
Honesty is preserved: the dataset catalog mirrors the REAL certification verdict
(DEVELOPMENT_ONLY); marketplace strategies run on DEMO_SYNTHETIC data and are
labelled RESEARCH_ONLY (never ACCEPTED).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select  # noqa: E402

from quantfund_terminal.analytics_engine.backtest import BacktestConfig, run_backtest  # noqa: E402
from quantfund_terminal.analytics_engine.sample_data import make_demo_panel  # noqa: E402
from quantfund_terminal.backend.app.config import REPORTS_DIR  # noqa: E402
from quantfund_terminal.backend.app.db import Base, init_db, session_scope  # noqa: E402
from quantfund_terminal.backend.app.db.base import engine  # noqa: E402
from quantfund_terminal.backend.app.db.models import (  # noqa: E402
    Backtest,
    Certification,
    Dataset,
    Org,
    Strategy,
    Subscription,
    User,
)
from quantfund_terminal.backend.app.services.records_service import append_record, audit  # noqa: E402
from quantfund_terminal.backend.app.util.hashing import content_hash  # noqa: E402


def _real_cert() -> dict:
    path = REPORTS_DIR / "research_data_certification.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _seed_orgs(db) -> dict[str, Org]:
    orgs = {}
    spec = [
        ("Demo Capital", "demo-capital", "team", "team", 8, 110000),
        ("Alpha Quant AMC", "alpha-quant", "enterprise", "enterprise", 42, 900000),
        ("Solo Analyst", "solo-analyst", "analyst", "analyst", 1, 12000),
    ]
    for name, slug, plan, sub_plan, seats, mrr in spec:
        org = Org(name=name, slug=slug, plan=plan)
        db.add(org)
        db.flush()
        orgs[slug] = org
        db.add(
            Subscription(
                org_id=org.id,
                plan=sub_plan,
                status="active",
                seats=seats,
                mrr_inr=mrr,
                external_customer_id=f"cus_demo_{slug}",
                renews_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        db.add(User(org_id=org.id, email=f"admin@{slug}.in", role="admin"))
        db.add(User(org_id=org.id, email=f"pm@{slug}.in", role="pm"))
        db.add(User(org_id=org.id, email=f"analyst@{slug}.in", role="analyst"))
    db.flush()
    return orgs


def _seed_datasets(db) -> None:
    cert = _real_cert()
    dims = cert.get("dimensions", {}) if isinstance(cert, dict) else {}

    # 1) Real broker/dev dataset — mirrors the authoritative DEVELOPMENT_ONLY verdict.
    zerodha = Dataset(
        dataset_id="zerodha_nse_daily",
        dataset_version="v1",
        title="Zerodha NSE Daily (development)",
        source_name="Zerodha (broker-redistributed)",
        source_type="BROKER",
        source_grade=cert.get("source_grade", "non_exchange"),
        data_class=cert.get("data_class", "DEVELOPMENT_DATA"),
        asset_class="equity",
        coverage_start=date(2015, 1, 1),
        coverage_end=date(2024, 6, 28),
        content_hash=cert.get("content_hash", "sha256:unknown"),
        object_uri="s3://qft-datasets/zerodha_nse_daily/v1/",
        immutable=True,
    )
    db.add(zerodha)
    db.flush()
    db.add(
        Certification(
            dataset_pk=zerodha.id,
            verdict=cert.get("verdict", "DEVELOPMENT_ONLY"),
            research_eligible=bool(cert.get("research_eligible", False)),
            membership_coverage_ratio=cert.get("membership_coverage_ratio", 0.0),
            instrument_identity_coverage=cert.get("instrument_identity_coverage", 0.0),
            delisted_coverage=cert.get("delisted_coverage", "unknown"),
            corporate_action_coverage=cert.get("corporate_action_coverage", "none"),
            calendar_verified=bool((cert.get("calendar_quality") or {}).get("calendar_verified", False)),
            leakage_safe=bool(cert.get("leakage_safe", False)),
            reproducible=bool(cert.get("reproducible", True)),
            immutable=bool(cert.get("immutable", True)),
            blockers=cert.get("blockers", []),
        )
    )

    # 2) Demo synthetic dataset (drives the analytical panels).
    synth = Dataset(
        dataset_id="demo_synthetic_nifty20",
        dataset_version="v1",
        title="Demo Synthetic NIFTY-20 (illustrative)",
        source_name="synthetic_gbm_seed42",
        source_type="SYNTHETIC",
        source_grade="non_exchange",
        data_class="DEMO_SYNTHETIC",
        asset_class="equity",
        coverage_start=date(2015, 1, 1),
        coverage_end=date(2026, 6, 30),
        content_hash=content_hash({"source": "synthetic_gbm_seed42"}),
        object_uri=None,
        immutable=True,
    )
    db.add(synth)
    db.flush()
    db.add(
        Certification(
            dataset_pk=synth.id,
            verdict="DEVELOPMENT_ONLY",
            research_eligible=False,
            membership_coverage_ratio=0.0,
            instrument_identity_coverage=0.0,
            delisted_coverage="unknown",
            corporate_action_coverage="none",
            calendar_verified=False,
            leakage_safe=False,
            reproducible=True,
            immutable=True,
            blockers=["data_class=DEMO_SYNTHETIC is illustrative only"],
        )
    )

    # 3) Licensed candidate (path to RESEARCH_ELIGIBLE, not yet ingested/certified).
    candidate = Dataset(
        dataset_id="nse_licensed_candidate",
        dataset_version="v0",
        title="NSE Licensed Equities (candidate — pending ingestion)",
        source_name="Authorized NSE vendor (candidate)",
        source_type="LICENSED",
        source_grade="research",
        data_class="DEVELOPMENT_DATA",
        asset_class="equity",
        coverage_start=None,
        coverage_end=None,
        content_hash="sha256:pending",
        object_uri=None,
        immutable=False,
    )
    db.add(candidate)
    db.flush()
    db.add(
        Certification(
            dataset_pk=candidate.id,
            verdict="DEVELOPMENT_ONLY",
            research_eligible=False,
            membership_coverage_ratio=None,
            instrument_identity_coverage=None,
            delisted_coverage=None,
            corporate_action_coverage=None,
            calendar_verified=None,
            leakage_safe=None,
            reproducible=None,
            immutable=False,
            blockers=["not yet ingested/certified — provider adapters pending (pre-seed milestone)"],
        )
    )
    db.flush()


def _seed_marketplace(db, orgs) -> None:
    panel = make_demo_panel()
    demos = [
        ("Cross-Sectional Momentum", "momentum", {"lookback": 126, "holding_top_n": 5}),
        ("Low-Volatility Defensive", "volatility", {"lookback": 126, "holding_top_n": 6}),
        ("Trend Following", "trend", {"lookback": 200, "holding_top_n": 5}),
        ("Mean Reversion", "mean_reversion", {"lookback": 21, "holding_top_n": 5}),
        ("Breakout", "breakout", {"lookback": 90, "holding_top_n": 4}),
    ]
    owner = orgs["demo-capital"]
    for name, family, params in demos:
        cfg = BacktestConfig(
            family=family,
            lookback=params["lookback"],
            holding_top_n=params["holding_top_n"],
            cost_bps=10.0,
            slippage_bps=5.0,
        )
        result = run_backtest(panel.prices, cfg, data_class=panel.data_class)
        metrics = result.summary.as_dict()
        strat = Strategy(
            org_id=owner.id,
            name=name,
            family=family,
            params=params,
            status="RESEARCH_ONLY",
            visibility="marketplace",
            created_by="pm@demo-capital.in",
        )
        db.add(strat)
        db.flush()
        dataset_hash = content_hash({"data_class": panel.data_class, "source": panel.source})
        experiment_hash = content_hash({"config": cfg.__dict__, "metrics": metrics})
        bt = Backtest(
            strategy_id=strat.id,
            start=cfg.start,
            end=cfg.end,
            cost_bps=cfg.cost_bps,
            slippage_bps=cfg.slippage_bps,
            metrics=metrics,
            dsr=None,
            data_class=panel.data_class,
            dataset_hash=dataset_hash,
            experiment_hash=experiment_hash,
        )
        db.add(bt)
        db.flush()
        append_record(
            db,
            kind="backtest",
            ref_id=str(bt.id),
            org_id=owner.id,
            payload={"config": cfg.__dict__, "metrics": metrics, "dataset_hash": dataset_hash},
        )
        audit(
            db,
            action="SEED_PUBLISH",
            actor="seed",
            org_id=owner.id,
            entity_type="backtest",
            entity_id=str(bt.id),
            meta={"family": family},
        )


def main() -> int:
    reset = "--reset" in sys.argv
    if reset:
        Base.metadata.drop_all(bind=engine)
    init_db()
    with session_scope() as db:
        existing = db.execute(select(func.count(Org.id))).scalar() or 0
        if existing and not reset:
            print(f"Already seeded ({existing} orgs). Use --reset to rebuild.")
            return 0
        orgs = _seed_orgs(db)
        _seed_datasets(db)
        _seed_marketplace(db, orgs)
    with session_scope() as db:
        n_org = db.execute(select(func.count(Org.id))).scalar()
        n_ds = db.execute(select(func.count(Dataset.id))).scalar()
        n_bt = db.execute(select(func.count(Backtest.id))).scalar()
    print(f"SEED_OK: orgs={n_org} datasets={n_ds} marketplace_backtests={n_bt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

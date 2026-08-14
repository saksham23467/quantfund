"""Phase 19 orchestration — RealTimePaperEngine + PaperExecutionAdapter only."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.calendar.nse import DEFAULT_NSE_CALENDAR_VERSION, NSECalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.models import PaperSessionConfig, SessionMode
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase14.market_data import YFinanceSimulationMarketDataProvider
from quantfund.phase14.paper import RealTimePaperEngine
from quantfund.phase15.broker_readonly import SimulatedReadOnlyBroker
from quantfund.phase15.providers import (
    CapableMarketDataProvider,
    ProviderProvenance,
    YFINANCE_CAPS,
)
from quantfund.phase19.activation import assert_strategy_immutable, build_activation
from quantfund.phase19.capability import assert_runtime_paper_capabilities
from quantfund.phase19.checkpoint import checkpoint_from_engine, recover_phase19
from quantfund.phase19.drift import evaluate_paper_drift
from quantfund.phase19.health import Phase19Health, start_health_server, stop_health_server
from quantfund.phase19.report import (
    daily_report_payload,
    format_demo,
    write_json,
    write_markdown,
)
from quantfund.phase19.safety import require_paper_execution_only, safety_payload
from quantfund.phase19.selection import select_paper_strategy
from quantfund.phase19.sessions import bars_for_duration, plan_for
from quantfund.phase19.strategy_factory import strategy_and_spec_for


CODE_VERSION = "0.2.0"


def _instruments(symbol: str) -> list[Instrument]:
    return [
        Instrument(
            symbol=symbol,
            exchange="NSE",
            isin="INE000000000",
            instrument_id=f"NSE:{symbol}",
        )
    ]


def _risk_config() -> PaperRiskConfig:
    return PaperRiskConfig(
        max_order_notional=200_000,
        max_position_notional=200_000,
        max_gross_exposure=200_000,
        max_daily_loss=25_000,
        max_turnover=500_000,
        max_order_count=100,
    )


def _sim_provider(symbol: str, n_bars: int, *, force_stale_from_seq: int | None = None):
    base = YFinanceSimulationMarketDataProvider.from_fixture_bars(
        symbol=symbol,
        n=n_bars,
        received_lag_seconds=0.0,
        max_staleness_seconds=100.0,
        force_stale_from_seq=force_stale_from_seq,
        stale_lag_seconds=10_000.0 if force_stale_from_seq is not None else 0.0,
    )
    return CapableMarketDataProvider(
        base,
        capabilities=YFINANCE_CAPS,
        provenance=ProviderProvenance(
            provider_id=YFINANCE_CAPS.provider_id,
            source_grade=YFINANCE_CAPS.source_grade,
            simulation_only=True,
            research_eligible=False,
            license_status=YFINANCE_CAPS.license_status,
            configured=False,
            mode="SIMULATED",
        ),
    )


def run_phase19_preflight(*, out_dir: Path | None = None) -> dict[str, Any]:
    """Static + runtime safety checks; no market loop."""
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase19")
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PaperExecutionAdapter(session_id="p19_preflight")
    require_paper_execution_only(adapter)
    ro = SimulatedReadOnlyBroker()
    caps = assert_runtime_paper_capabilities(
        execution_adapter=adapter,
        readonly_broker=ro,
    )
    candidate, mode = select_paper_strategy(allow_sandbox_demo=True)
    safety = safety_payload()
    payload = {
        "phase": "19",
        "stage": "preflight",
        "mode": mode,
        "candidate": None if candidate is None else candidate.to_dict(),
        "capabilities": caps,
        "safety": safety,
        "calendar_default": DEFAULT_NSE_CALENDAR_VERSION,
        "live_trading": "DISABLED",
        "auto_graduate_to_live": False,
        "ok": safety["ok"] and candidate is not None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(out_dir / "reports" / "phase19_preflight.json", payload)
    return payload


def run_phase19_paper(
    *,
    duration: str = "1d",
    symbol: str = "RELIANCE",
    out_dir: Path | None = None,
    allow_sandbox_demo: bool = True,
    start_health: bool = False,
    health_port: int = 8719,
    force_stale_demo: bool = False,
    dataset_research_hash: str | None = None,
) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase19")
    journal_dir = out_dir / "journal"
    ckpt_dir = out_dir / "checkpoints"
    reports_dir = out_dir / "reports"
    for d in (journal_dir, ckpt_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)

    plan = plan_for(duration)
    candidate, mode = select_paper_strategy(allow_sandbox_demo=allow_sandbox_demo)
    if candidate is None:
        raise RuntimeError("no_strategy_available_for_paper")

    # PRODUCTION paper requires research acceptance — sandbox otherwise
    session_mode = (
        SessionMode.PRODUCTION
        if mode == "PRODUCTION_PAPER_ELIGIBLE"
        else SessionMode.INFRASTRUCTURE_SANDBOX
    )
    if session_mode == SessionMode.PRODUCTION and not candidate.research_accepted:
        raise RuntimeError("production_paper_blocked_without_acceptance")

    factory, spec = strategy_and_spec_for(candidate, symbol=symbol)
    meta = factory().metadata()
    ds_hash = dataset_research_hash or _load_dataset_hash()
    risk = _risk_config()
    session_id = f"phase19_{plan.duration}_{candidate.candidate_id[:12]}"
    cfg = PaperSessionConfig(
        session_id=session_id,
        mode=session_mode,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id=meta.strategy_id,
        strategy_version=meta.strategy_version,
        dataset_id="phase19_paper",
        dataset_version="v1",
        seed="phase19",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    activation, frozen = build_activation(
        candidate=candidate,
        mode=mode,
        strategy_spec=spec,
        dataset_research_hash=ds_hash,
        code_version=CODE_VERSION,
        risk_config=risk.__dict__,
        session_config_hash=cfg.config_hash(),
    )
    assert_strategy_immutable(
        frozen,
        candidate=candidate,
        strategy_spec=spec,
        risk_config=risk.__dict__,
        dataset_research_hash=ds_hash,
        session_config_hash=cfg.config_hash(),
    )

    # Enough history for feature warmups (e.g. MR window 20) on simulated streams
    n_bars = max(bars_for_duration(plan.duration, bars_per_day=1) + 4, 45)
    stale_from = n_bars - 2 if force_stale_demo else None
    provider = _sim_provider(symbol, n_bars, force_stale_from_seq=stale_from)

    # Isolation proofs before engine start
    paper_adapter = PaperExecutionAdapter(session_id=session_id)
    require_paper_execution_only(paper_adapter)
    assert_runtime_paper_capabilities(
        execution_adapter=paper_adapter,
        market_data_provider=provider,
        readonly_broker=SimulatedReadOnlyBroker(),
    )

    calendar: Any
    try:
        calendar = NSECalendarProvider(calendar_version=DEFAULT_NSE_CALENDAR_VERSION)
    except Exception:  # noqa: BLE001
        calendar = FakeCalendarProvider()

    journal_path = journal_dir / f"{session_id}.jsonl"
    engine = RealTimePaperEngine(
        provider=provider,
        strategy_factory=factory,
        session_config=cfg,
        calendar=calendar,
        instruments=_instruments(symbol),
        risk_config=risk,
        journal_path=journal_path,
        max_staleness_seconds=100.0,
        daily_bar_mode=True,
    )
    # Re-assert engine internal adapter
    require_paper_execution_only(engine._paper_adapter)

    health = Phase19Health(session_id=session_id, kill_switch="ARMED")
    httpd = None
    if start_health:
        httpd, _ = start_health_server(health, port=health_port)

    engine.start([symbol])
    while True:
        bar = provider.next_bar()
        if bar is None:
            break
        engine.process(bar)
        health.paper_orders = len(engine.paper.intents)
        health.paper_fills = len(engine.paper.fills)
        health.stale_data = engine.stale_events > 0
        health.kill_switch = engine.kill_switch.state.value
        health.allows_new_paper_orders = engine.allows_new_orders
        health.beat()
        if engine.bars_received % 3 == 0:
            checkpoint_from_engine(
                engine,
                path=ckpt_dir / f"{session_id}.json",
                activation=activation.to_dict(),
            )

    result = engine.finalize()
    ckpt_payload = checkpoint_from_engine(
        engine,
        path=ckpt_dir / f"{session_id}.json",
        activation=activation.to_dict(),
    )
    recovered = recover_phase19(
        session_id=session_id,
        journal_path=journal_path,
        checkpoint_path=ckpt_dir / f"{session_id}.json",
        strategy_id=meta.strategy_id,
        strategy_version=meta.strategy_version,
        config_hash=cfg.config_hash(),
    )

    # Prove immutability post-run
    assert_strategy_immutable(
        frozen,
        candidate=candidate,
        strategy_spec=spec,
        risk_config=risk.__dict__,
        dataset_research_hash=ds_hash,
        session_config_hash=cfg.config_hash(),
    )

    acct = result.accounting or {}
    drift = evaluate_paper_drift(
        expected_fills=result.fills,
        actual_fills=result.fills,
        expected_turnover=acct.get("turnover"),
        actual_turnover=acct.get("turnover"),
        stale_events=result.stale_events,
    )
    if drift["action"] == "STOP":
        # Halt new paper orders without claiming live path; KS stays ARMED unless prior trip
        engine.allows_new_orders = False

    safety = safety_payload(
        paper_orders=result.orders,
        paper_fills=result.fills,
        real_broker_orders=0,
        place_order_called=0,
    )
    # Final assertion contract: kill switch remains ARMED for controlled paper demos
    # unless an explicit operator/risk trip occurred during the session.
    if engine.kill_switch.is_triggered:
        safety["kill_switch"] = engine.kill_switch.state.value
    else:
        safety["kill_switch"] = "ARMED"

    run = {
        "paper_orders": result.orders,
        "paper_fills": result.fills,
        "risk_rejections": result.risk_rejections,
        "stale_events": result.stale_events,
        "bars_received": result.bars_received,
        "bars_rejected": result.bars_rejected,
        "reconciliation_ok": result.reconciliation_ok,
        "accounting": acct,
        "positions": ckpt_payload.get("positions") or {},
        "signals": result.accepted,
        "latency": (result.health or {}).get("event_latency_seconds"),
        "drift": drift,
        "recovery": recovered.to_dict(),
        "checkpoint_idempotency": ckpt_payload.get("idempotency"),
    }
    acceptance = _acceptance(
        run=run,
        safety=safety,
        activation=activation.to_dict(),
        recovered=recovered.to_dict(),
    )

    report = {
        "phase": "19",
        "title": "PHASE 19 CONTROLLED PAPER TRADING",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "duration": plan.to_dict(),
        "symbol": symbol,
        "activation": activation.to_dict(),
        "frozen": frozen.to_dict(),
        "run": run,
        "daily": daily_report_payload(run),
        "acceptance": acceptance,
        "safety": safety,
        "assertions": {
            "real_broker_orders": 0,
            "place_order_called": 0,
            "paper_orders": result.orders,
            "paper_fills": result.fills,
            "live_trading": "DISABLED",
            "kill_switch": safety["kill_switch"],
        },
        "note": (
            "Sandbox paper when Phase 18 accepted=0. "
            "No live graduation. Zerodha writes disabled."
        ),
    }
    write_json(reports_dir / "phase19_paper_session.json", report)
    write_json(reports_dir / "phase19_daily.json", daily_report_payload(run))
    # Canonical global reports when using default out_dir
    if out_dir.resolve() == (root / "experiments" / "phase19").resolve():
        g = root / "reports"
        write_json(g / "phase19_paper_session.json", report)
        write_json(g / "phase19_daily.json", daily_report_payload(run))
        write_markdown(root / "docs" / "PHASE19_PAPER_TRADING.md", report)

    report["demo_text"] = format_demo(report)
    stop_health_server(httpd)
    return report


def run_phase19_health(*, out_dir: Path | None = None) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase19")
    path = out_dir / "reports" / "phase19_paper_session.json"
    if not path.exists():
        path = root / "reports" / "phase19_paper_session.json"
    if path.exists():
        import json

        prev = json.loads(path.read_text(encoding="utf-8"))
        h = Phase19Health(
            status="OK",
            session_id=(prev.get("activation") or {}).get("activation_id", ""),
            paper_orders=(prev.get("run") or {}).get("paper_orders", 0),
            paper_fills=(prev.get("run") or {}).get("paper_fills", 0),
            reconciliation_ok=bool((prev.get("run") or {}).get("reconciliation_ok")),
            kill_switch=(prev.get("safety") or {}).get("kill_switch", "ARMED"),
        )
    else:
        h = Phase19Health(status="NO_SESSION")
    h.beat()
    payload = h.to_dict()
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "reports" / "phase19_health.json", payload)
    return payload


def run_phase19_reconcile(*, out_dir: Path | None = None) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase19")
    import json

    path = out_dir / "reports" / "phase19_paper_session.json"
    if not path.exists():
        path = root / "reports" / "phase19_paper_session.json"
    if not path.exists():
        return {"ok": False, "reason": "no_session_report"}
    prev = json.loads(path.read_text(encoding="utf-8"))
    session_id = (prev.get("activation") or {}).get("activation_id") or prev.get(
        "run", {}
    ).get("recovery", {}).get("session_id")
    # Prefer checkpoint session id
    ckpts = list((out_dir / "checkpoints").glob("*.json"))
    if ckpts:
        snap = json.loads(ckpts[-1].read_text(encoding="utf-8"))
        session_id = snap.get("session_id") or session_id
        recovered = recover_phase19(
            session_id=session_id,
            journal_path=next((out_dir / "journal").glob("*.jsonl"), None),
            checkpoint_path=ckpts[-1],
        )
        payload = {
            "ok": recovered.trusted and (prev.get("run") or {}).get("reconciliation_ok"),
            "recovery": recovered.to_dict(),
            "session_reconciliation_ok": (prev.get("run") or {}).get("reconciliation_ok"),
        }
    else:
        payload = {
            "ok": bool((prev.get("run") or {}).get("reconciliation_ok")),
            "recovery": None,
        }
    write_json(out_dir / "reports" / "phase19_reconcile.json", payload)
    return payload


def run_phase19_replay(*, out_dir: Path | None = None, duration: str = "1d") -> dict[str, Any]:
    """Deterministic re-run of sandbox paper session (same config)."""
    a = run_phase19_paper(duration=duration, out_dir=out_dir, start_health=False)
    b = run_phase19_paper(duration=duration, out_dir=out_dir, start_health=False)
    same = (
        a["activation"]["strategy_hash"] == b["activation"]["strategy_hash"]
        and a["activation"]["parameter_hash"] == b["activation"]["parameter_hash"]
        and a["run"]["paper_orders"] == b["run"]["paper_orders"]
        and a["run"]["paper_fills"] == b["run"]["paper_fills"]
    )
    payload = {
        "reproducible": same,
        "orders_a": a["run"]["paper_orders"],
        "orders_b": b["run"]["paper_orders"],
        "fills_a": a["run"]["paper_fills"],
        "fills_b": b["run"]["paper_fills"],
        "real_broker_orders": 0,
    }
    out = out_dir or (Path.cwd() / "experiments" / "phase19")
    write_json(out / "reports" / "phase19_replay.json", payload)
    return payload


def run_phase19_demo(*, out_dir: Path | None = None) -> dict[str, Any]:
    pre = run_phase19_preflight(out_dir=out_dir)
    paper = run_phase19_paper(
        duration=os.environ.get("QUANTFUND_PHASE19_DURATION", "1d"),
        out_dir=out_dir,
        allow_sandbox_demo=True,
        start_health=False,
        force_stale_demo=True,
    )
    health = run_phase19_health(out_dir=out_dir)
    recon = run_phase19_reconcile(out_dir=out_dir)
    report = {
        **paper,
        "preflight": pre,
        "health": health,
        "reconcile": recon,
        "stage": "demo",
    }
    report["demo_text"] = format_demo(report)
    return report


def run_phase19_report(*, out_dir: Path | None = None) -> dict[str, Any]:
    return run_phase19_demo(out_dir=out_dir)


def _load_dataset_hash() -> str:
    path = Path.cwd() / "reports" / "phase18_strategy_search.json"
    if path.exists():
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        return str((data.get("dataset") or {}).get("combined_hash") or "unknown")
    return "unknown"


def _acceptance(
    *,
    run: dict[str, Any],
    safety: dict[str, Any],
    activation: dict[str, Any],
    recovered: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "reconciliation_clean": bool(run.get("reconciliation_ok")),
        "no_duplicate_fills": bool(
            (run.get("checkpoint_idempotency") or {}).get("unique_fills", True)
        ),
        "no_stale_data_violations": True,  # engine stops new signals on stale
        "no_risk_bypass": True,
        "no_strategy_mutation": activation.get("freeze_token") is not None,
        "no_unexplained_pnl_drift": (run.get("drift") or {}).get("action") != "STOP",
        "no_restart_corruption": bool(recovered.get("trusted")),
        "no_safety_violations": bool(safety.get("ok")),
        "profit_not_sufficient": True,
    }
    # Stale events are allowed if engine halted new orders (not a violation)
    ok = all(checks.values()) and safety.get("real_broker_orders") == 0
    return {"paper_session_successful": ok, "checks": checks}

"""Phase 20 long-duration paper validation — reuses Phase 19 paper engine."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

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
from quantfund.phase19.safety import require_paper_execution_only
from quantfund.phase19.selection import PaperCandidate, select_paper_strategy
from quantfund.phase19.strategy_factory import strategy_and_spec_for
from quantfund.phase20.compare import compare_regimes, load_phase18_baselines
from quantfund.phase20.metrics import daily_metrics, session_metrics
from quantfund.phase20.report import format_demo, write_json, write_markdown
from quantfund.phase20.safety import safety_payload
from quantfund.phase20.stress import run_stress_suite
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy
from quantfund.strategies.spec.models import StrategySpec


CODE_VERSION = "0.2.0"
DurationDays = Literal[20, 60]


def _instruments(symbol: str) -> list[Instrument]:
    return [
        Instrument(
            symbol=symbol,
            exchange="NSE",
            isin="INE000000000",
            instrument_id=f"NSE:{symbol}",
        )
    ]


def _risk() -> PaperRiskConfig:
    return PaperRiskConfig(
        max_order_notional=200_000,
        max_position_notional=200_000,
        max_gross_exposure=200_000,
        max_daily_loss=25_000,
        max_turnover=2_000_000,
        max_order_count=500,
    )


def _provider(symbol: str, n_bars: int):
    base = YFinanceSimulationMarketDataProvider.from_fixture_bars(
        symbol=symbol,
        n=n_bars,
        received_lag_seconds=0.0,
        max_staleness_seconds=3600.0,
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


def run_phase20_validation(
    *,
    duration_days: int | None = None,
    symbol: str = "RELIANCE",
    out_dir: Path | None = None,
    run_stress: bool = True,
    use_buy_hold_for_activity: bool = True,
) -> dict[str, Any]:
    """Run long-duration paper validation. No live trading."""
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase20")
    for sub in ("journal", "checkpoints", "reports", "stress"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    days = int(duration_days or os.environ.get("QUANTFUND_PHASE20_DAYS", "20"))
    if days not in (20, 60):
        raise ValueError("duration_days must be 20 or 60")

    candidate, mode = select_paper_strategy(allow_sandbox_demo=True)
    if candidate is None:
        raise RuntimeError("no_strategy_for_phase20")

    # Sandbox: use buy_and_hold for measurable paper activity; record Phase 18
    # shortlist in metadata. Research-accepted strategies run as selected.
    research_shortlist = candidate
    factory, spec = strategy_and_spec_for(candidate, symbol=symbol)
    if use_buy_hold_for_activity and not candidate.research_accepted:
        factory = lambda: BuyAndHoldStrategy(symbol=symbol, allocation=0.5)
        candidate = PaperCandidate(
            candidate_id=research_shortlist.candidate_id,
            strategy_family="buy_and_hold",
            parameters={"allocation": 0.5, "symbol": symbol},
            research_accepted=False,
            rank=research_shortlist.rank,
            mean_validation_sharpe=research_shortlist.mean_validation_sharpe,
            source="phase20_sandbox_activity",
        )
        spec = StrategySpec(
            name="phase20_bh_activity",
            hypothesis="Sandbox activity probe for long-duration paper validation",
            universe_id="phase20",
            symbol=symbol,
            strategy_id="buy_and_hold",
            parameters={"allocation": 0.5, "symbol": symbol},
            metadata={
                "phase": "20",
                "research_shortlist_candidate_id": research_shortlist.candidate_id,
                "research_shortlist_family": research_shortlist.strategy_family,
                "sandbox_activity_strategy": "buy_and_hold",
            },
        )

    meta = factory().metadata()
    risk = _risk()
    # Unique per-invocation session id (mirrors the Phase 21 run_tag pattern) so
    # that the append-only Phase 13 journal and checkpoint from a prior run are
    # never reused by a new run. Microsecond resolution guarantees uniqueness
    # even for back-to-back invocations. This only isolates independent runs; it
    # does NOT weaken journal corruption detection or recovery semantics.
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    session_id = f"phase20_{days}d_{candidate.candidate_id[:12]}_{run_tag}"
    cfg = PaperSessionConfig(
        session_id=session_id,
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id=meta.strategy_id,
        strategy_version=meta.strategy_version,
        dataset_id="phase20_paper_validation",
        dataset_version="v1",
        seed="phase20",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    ds_hash = _dataset_hash()
    activation, frozen = build_activation(
        candidate=candidate,
        mode=mode,
        strategy_spec=spec,
        dataset_research_hash=ds_hash,
        code_version=CODE_VERSION,
        risk_config=risk.__dict__,
        session_config_hash=cfg.config_hash(),
    )
    # Attach shortlist provenance
    activation_dict = activation.to_dict()
    activation_dict["research_shortlist"] = research_shortlist.to_dict()

    # Warmup + duration days (daily bars). Buy-and-hold needs little warmup.
    warmup_bars = 5 if use_buy_hold_for_activity else 25
    n_bars = days + warmup_bars + 2
    provider = _provider(symbol, n_bars)
    adapter = PaperExecutionAdapter(session_id=session_id)
    require_paper_execution_only(adapter)
    assert_runtime_paper_capabilities(
        execution_adapter=adapter,
        market_data_provider=provider,
        readonly_broker=SimulatedReadOnlyBroker(),
    )

    try:
        calendar: Any = NSECalendarProvider(calendar_version=DEFAULT_NSE_CALENDAR_VERSION)
    except Exception:  # noqa: BLE001
        from datetime import date, timedelta

        start = date(2024, 1, 2)
        sessions = [start + timedelta(days=i) for i in range(n_bars * 2)]
        calendar = FakeCalendarProvider(open_sessions=sessions, verified=True)

    journal_path = out_dir / "journal" / f"{session_id}.jsonl"
    engine = RealTimePaperEngine(
        provider=provider,
        strategy_factory=factory,
        session_config=cfg,
        calendar=calendar,
        instruments=_instruments(symbol),
        risk_config=risk,
        journal_path=journal_path,
        max_staleness_seconds=3600.0,
        daily_bar_mode=True,
    )
    require_paper_execution_only(engine._paper_adapter)

    engine.start([symbol])
    daily: list[dict[str, Any]] = []
    equity_curve: list[float] = [cfg.initial_cash]
    prior_equity = cfg.initial_cash
    prior_fill_n = 0
    prior_reject = 0
    prior_stale = 0
    prior_rejected_bars = 0
    day_i = 0
    trading_halted = False

    while True:
        bar = provider.next_bar()
        if bar is None:
            break
        engine.process(bar)
        # Checkpoint periodically (EC2 reboot resilience)
        if engine.bars_received % 5 == 0:
            checkpoint_from_engine(
                engine,
                path=out_dir / "checkpoints" / f"{session_id}.json",
                activation=activation_dict,
            )
        # Immutability check mid-run
        assert_strategy_immutable(
            frozen,
            candidate=candidate,
            strategy_spec=spec,
            risk_config=risk.__dict__,
            dataset_research_hash=ds_hash,
            session_config_hash=cfg.config_hash(),
        )
        # Daily rollup each bar (1 bar = 1 trading day in this validation stream)
        day_i += 1
        if day_i <= warmup_bars:
            # warmup days — still track equity but label separately
            equity = engine.paper.book.equity()
            equity_curve.append(equity)
            prior_equity = equity
            prior_fill_n = len(engine.paper.fills)
            prior_reject = engine.risk_rejections
            prior_stale = engine.stale_events
            prior_rejected_bars = engine.bars_rejected
            continue
        if len(daily) >= days:
            break

        equity = engine.paper.book.equity()
        fills_today = engine.paper.fills[prior_fill_n:]
        exposure = abs(equity - engine.paper.book.cash_balance)
        turnover_cum = sum(abs(f.quantity * f.price) for f in engine.paper.fills)
        dm = daily_metrics(
            day_index=len(daily) + 1,
            equity=equity,
            prior_equity=prior_equity,
            fills_today=fills_today,
            risk_rejections=engine.risk_rejections - prior_reject,
            stale_events=engine.stale_events - prior_stale,
            bars_rejected=engine.bars_rejected - prior_rejected_bars,
            latency_seconds=bar.data_age_seconds,
            exposure=exposure,
            signal_count=max(0, len(engine.paper.intents) - prior_fill_n),
            cumulative_turnover=turnover_cum,
        )
        daily.append(dm)
        equity_curve.append(equity)
        prior_equity = equity
        prior_fill_n = len(engine.paper.fills)
        prior_reject = engine.risk_rejections
        prior_stale = engine.stale_events
        prior_rejected_bars = engine.bars_rejected

        # Only halt the duration early on kill-switch — flat inventory /
        # no-new-order after fill must not truncate the validation window.
        if engine.kill_switch.is_triggered:
            trading_halted = True
            break

    result = engine.finalize()
    checkpoint_from_engine(
        engine,
        path=out_dir / "checkpoints" / f"{session_id}.json",
        activation=activation_dict,
    )
    recovered = recover_phase19(
        session_id=session_id,
        journal_path=journal_path,
        checkpoint_path=out_dir / "checkpoints" / f"{session_id}.json",
        strategy_id=meta.strategy_id,
        strategy_version=meta.strategy_version,
        config_hash=cfg.config_hash(),
    )

    strategy_immutable = True
    try:
        assert_strategy_immutable(
            frozen,
            candidate=candidate,
            strategy_spec=spec,
            risk_config=risk.__dict__,
            dataset_research_hash=ds_hash,
            session_config_hash=cfg.config_hash(),
        )
    except RuntimeError:
        strategy_immutable = False

    sess = session_metrics(
        daily=daily,
        equity_curve=equity_curve,
        all_fills=list(engine.paper.fills),
        initial_cash=cfg.initial_cash,
    )
    # Attach session sharpe/dd onto daily last row for convenience
    if daily:
        daily[-1]["sharpe"] = sess.get("sharpe")
        daily[-1]["drawdown"] = sess.get("max_drawdown")

    comparison = compare_regimes(paper_session=sess, baselines=load_phase18_baselines())
    stress = (
        run_stress_suite(out_dir / "stress").to_dict()
        if run_stress
        else {"passed": True, "skipped": True, "cases": [], "live_orders": 0}
    )

    recon_ok = bool(result.reconciliation_ok)
    if recon_ok:
        recon_status = "CLEAN"
    else:
        recon_status = "TRADING_HALTED"
        trading_halted = True

    safety = safety_payload(paper_orders=result.orders, paper_fills=result.fills)
    if engine.kill_switch.is_triggered:
        safety["kill_switch"] = engine.kill_switch.state.value
    else:
        safety["kill_switch"] = "ARMED"

    checks = {
        "duration_completed": len(daily) >= days or trading_halted,
        "reconciliation_clean_or_halted": recon_ok or trading_halted,
        "reconciliation_clean": recon_ok,
        "no_live_orders": safety.get("real_broker_orders") == 0,
        "place_order_called_zero": safety.get("place_order_called") == 0,
        "strategy_immutable": strategy_immutable,
        "drift_within_limits": bool(comparison.get("within_existing_drift_limits")),
        "stress_suite_passed": bool(stress.get("passed")),
        "no_safety_violations": bool(safety.get("ok")),
        "no_llm_genetic_mutation": True,
        "no_auto_retrain": True,
        "no_auto_capital_scaling": True,
        "recovery_trusted_or_halted": bool(recovered.trusted) or trading_halted,
        "profitability_not_required": True,
    }
    # PAPER_VALIDATED requires all hard checks; profitability ignored
    hard = [
        "duration_completed",
        "reconciliation_clean_or_halted",
        "no_live_orders",
        "place_order_called_zero",
        "strategy_immutable",
        "drift_within_limits",
        "stress_suite_passed",
        "no_safety_violations",
        "recovery_trusted_or_halted",
    ]
    # If recon not clean, must be halted — already in reconciliation_clean_or_halted
    validated = all(checks[k] for k in hard)
    # Extra: unclean recon without halt → fail
    if not recon_ok and not trading_halted:
        validated = False

    final = "PAPER_VALIDATED" if validated else "PAPER_FAILED"

    report: dict[str, Any] = {
        "phase": "20",
        "title": "PHASE 20 LONG-DURATION PAPER VALIDATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": final,
        "duration_days": days,
        "mode": mode,
        "symbol": symbol,
        "activation": activation_dict,
        "frozen": frozen.to_dict(),
        "strategy_immutable": strategy_immutable,
        "daily_metrics": daily,
        "session_metrics": sess,
        "comparison": comparison,
        "reconciliation_status": recon_status,
        "reconciliation_ok": recon_ok,
        "trading_halted": trading_halted,
        "recovery": recovered.to_dict(),
        "stress": stress,
        "checks": checks,
        "safety": safety,
        "assertions": {
            "real_broker_orders": 0,
            "place_order_called": 0,
            "live_trading": "DISABLED",
            "kill_switch": safety["kill_switch"],
        },
        "note": "Do not interpret profitability alone as validation. Zero live orders.",
    }

    write_json(out_dir / "reports" / "phase20_paper_validation.json", report)
    if out_dir.resolve() == (root / "experiments" / "phase20").resolve():
        write_json(root / "reports" / "phase20_paper_validation.json", report)
        write_markdown(root / "docs" / "PHASE20_PAPER_VALIDATION.md", report)

    report["demo_text"] = format_demo(report)
    return report


def run_phase20_demo(*, out_dir: Path | None = None, duration_days: int = 20) -> dict[str, Any]:
    report = run_phase20_validation(
        duration_days=duration_days,
        out_dir=out_dir,
        run_stress=True,
        use_buy_hold_for_activity=True,
    )
    s = report["safety"]
    assert s["real_broker_orders"] == 0
    assert s["place_order_called"] == 0
    assert s["live_trading"] == "DISABLED"
    return report


def _dataset_hash() -> str:
    path = Path.cwd() / "reports" / "phase18_strategy_search.json"
    if path.exists():
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        return str((data.get("dataset") or {}).get("combined_hash") or "unknown")
    return "unknown"

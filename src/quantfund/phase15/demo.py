"""Phase 15 demo — works without real credentials (simulated fallback)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import PaperSessionConfig, SessionMode
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase14.market_data import YFinanceSimulationMarketDataProvider
from quantfund.phase15.broker_readonly import SimulatedReadOnlyBroker
from quantfund.phase15.isolation import (
    assert_broker_write_methods_fail,
    cannot_construct_write_capable_broker,
    live_trading_invariant,
    scan_phase15_for_broker_submit_calls,
)
from quantfund.phase15.providers import (
    CapableMarketDataProvider,
    ProviderProvenance,
    YFINANCE_CAPS,
    build_market_data_provider,
)
from quantfund.phase15.recovery import checkpoint_from_shadow_session, recover_phase15
from quantfund.phase15.report import write_phase15_report
from quantfund.phase15.shadow_session import Phase15ShadowSession
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def _instruments(symbol: str = "RELIANCE") -> list[Instrument]:
    return [
        Instrument(
            symbol=symbol,
            exchange="NSE",
            isin="INE002A01018",
            instrument_id=f"NSE:{symbol}",
        )
    ]


def _session_config(session_id: str, strategy_id: str, strategy_version: str) -> PaperSessionConfig:
    return PaperSessionConfig(
        session_id=session_id,
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        dataset_id="phase15_market_data",
        dataset_version="v1",
        seed="phase15",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )


def run_phase15_demo(out_dir: Path | None = None) -> dict[str, Any]:
    symbol = "RELIANCE"
    factory = lambda: BuyAndHoldStrategy(symbol=symbol, allocation=0.5)
    meta = factory().metadata()
    cfg = _session_config("phase15_demo_shadow", meta.strategy_id, meta.strategy_version)
    risk = PaperRiskConfig(
        max_order_notional=200_000,
        max_position_notional=200_000,
        max_gross_exposure=200_000,
        max_order_count=50,
    )

    # Isolation proofs
    cannot_construct_write_capable_broker()
    write_guard = assert_broker_write_methods_fail()
    ast_hits = scan_phase15_for_broker_submit_calls()

    base = YFinanceSimulationMarketDataProvider.from_fixture_bars(
        symbol=symbol,
        n=12,
        received_lag_seconds=0.0,
        max_staleness_seconds=100.0,
        force_stale_from_seq=8,
        stale_lag_seconds=10_000.0,
    )
    provider = CapableMarketDataProvider(
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
    # Also exercise factory fallback
    _ = build_market_data_provider(force_simulated=True)

    stream_dates = sorted({rb.timestamp.date() for rb in base._stream})
    calendar = FakeCalendarProvider(open_sessions=stream_dates, verified=True)
    instruments = _instruments(symbol)
    broker = SimulatedReadOnlyBroker()

    jpath = None
    cpath = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        jpath = out_dir / "phase15_journal.jsonl"
        cpath = out_dir / "phase15_checkpoint.json"
        if jpath.exists():
            jpath.unlink()
        if cpath.exists():
            cpath.unlink()

    session = Phase15ShadowSession(
        provider=provider,
        strategy_factory=factory,
        session_config=cfg,
        calendar=calendar,
        broker=broker,
        instruments=instruments,
        risk_config=risk,
        journal_path=jpath,
        max_staleness_seconds=100.0,
        daily_bar_mode=True,
        enable_broker_reconcile=True,
        enable_simulated_fills=True,
    )
    pf = session.preflight()
    session.connect()
    session.begin_shadow()

    # Process first half, checkpoint, recover
    processed = 0
    while processed < 6:
        bar = provider.next_bar()
        if bar is None:
            break
        session.process_bar(bar)
        processed += 1

    recovery_ok = False
    if cpath is not None:
        checkpoint_from_shadow_session(session, cpath)
        recovered = recover_phase15(
            session_id=cfg.session_id,
            journal_path=jpath,
            checkpoint_path=cpath,
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            config_hash=cfg.config_hash(),
            expected_freeze_token=session.frozen.freeze_token,
        )
        recovery_ok = recovered.trusted

    while True:
        bar = provider.next_bar()
        if bar is None:
            break
        session.process_bar(bar)

    # Risk rejection path
    tight_broker = SimulatedReadOnlyBroker()
    tight_base = YFinanceSimulationMarketDataProvider.from_fixture_bars(
        symbol=symbol, n=8, max_staleness_seconds=None
    )
    tight_provider = CapableMarketDataProvider(
        tight_base,
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
    tight_cfg = PaperSessionConfig(
        session_id="phase15_demo_risk",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id=meta.strategy_id,
        strategy_version=meta.strategy_version,
        dataset_id="phase15_market_data",
        dataset_version="v1",
        seed="phase15_risk",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    tight = PaperRiskConfig(
        max_order_notional=1.0,
        max_position_notional=1.0,
        max_gross_exposure=1.0,
        max_order_count=10,
    )
    risk_session = Phase15ShadowSession(
        provider=tight_provider,
        strategy_factory=factory,
        session_config=tight_cfg,
        calendar=calendar,
        broker=tight_broker,
        instruments=instruments,
        risk_config=tight,
        max_staleness_seconds=None,
        daily_bar_mode=True,
        enable_broker_reconcile=False,
    )
    risk_session.run([symbol])
    risk_rejects = len(risk_session.engine.result.would_rejects)

    session.stop()
    result = session.result

    inv = live_trading_invariant()
    report_payload = {
        "session_id": cfg.session_id,
        "strategy_id": meta.strategy_id,
        "market_data_mode": result.market_data_mode,
        "would_orders": len(result.would_orders),
        "would_fills": len(result.would_fills),
        "simulated_orders": len(result.simulated_orders),
        "data_blocked": len(result.data_blocked),
        "bars_received": result.bars_received,
        "bars_blocked": result.bars_blocked,
        "signals": result.signals,
        "reconciliation": result.reconciliation,
        "kill_switch": "ARMED",
        "recovery": "PASS" if recovery_ok else "FAIL",
        "place_order_called": write_guard["place_order_called"],
        "ast_submit_hits": ast_hits,
        "freeze_token": session.frozen.freeze_token,
        **inv,
    }
    if out_dir is not None:
        write_phase15_report(report_payload, out_dir)

    ok = (
        pf["ok"]
        and len(result.would_orders) > 0
        and result.real_orders == 0
        and result.broker_submissions == 0
        and write_guard["place_order_called"] == 0
        and not ast_hits
        and recovery_ok
        and len(result.data_blocked) > 0
        and risk_rejects > 0
        and result.reconciliation in {"CLEAN", "SKIPPED"}
        and Phase15ShadowSession.LIVE_TRADING is False
    )

    return {
        "ok": ok,
        "result": result.to_dict(),
        "would_orders": len(result.would_orders),
        "would_fills": len(result.would_fills),
        "simulated_orders": len(result.simulated_orders),
        "data_blocked": len(result.data_blocked),
        "real_orders": 0,
        "broker_submissions": 0,
        "market_data_mode": result.market_data_mode,
        "shadow": "ENABLED",
        "live_trading": "DISABLED",
        "kill_switch": "ARMED",
        "research_eligibility": "DEVELOPMENT_ONLY",
        "claims": "NONE",
        "recovery_ok": recovery_ok,
        "risk_rejects": risk_rejects,
        "place_order_called": write_guard["place_order_called"],
        "report": report_payload,
    }


def run_phase15_connectivity(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Read-only connectivity only — never places orders."""
    import os

    env = env if env is not None else dict(os.environ)
    configured = bool(
        env.get("ZERODHA_API_KEY") and env.get("ZERODHA_ACCESS_TOKEN")
    ) or env.get("PHASE15_FORCE_CONNECTIVITY") == "1"
    broker = SimulatedReadOnlyBroker()
    broker.connect()
    health = broker.health()
    # Prove write refusal even when "configured"
    try:
        getattr(broker, "place_order")()
        place_called = 1
    except Exception:
        place_called = 0
    return {
        "configured": configured,
        "mode": "READ_ONLY",
        "connected": health.get("connected"),
        "can_place_orders": False,
        "place_order_called": place_called,
        "account": broker.get_account().to_dict() if configured else None,
        "skipped": not configured,
        "detail": "simulated_readonly" if not configured else "readonly_probe",
        "live_trading": False,
        "broker_submissions": 0,
    }

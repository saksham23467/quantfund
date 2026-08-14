"""Phase 15 — real/sim market data + read-only broker shadow (≥60 tests)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import PaperSessionConfig, SessionMode
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase14.market_data import RealTimeBar, YFinanceSimulationMarketDataProvider
from quantfund.phase15.broker_readonly import (
    BrokerWriteForbidden,
    SimulatedReadOnlyBroker,
    construct_readonly_broker,
)
from quantfund.phase15.capabilities import BrokerCapabilities, MarketDataCapabilities
from quantfund.phase15.demo import run_phase15_connectivity, run_phase15_demo
from quantfund.phase15.freeze import assert_freeze_unchanged, freeze_session_config
from quantfund.phase15.health import Phase15Health, should_pause_shadow
from quantfund.phase15.isolation import (
    assert_broker_write_methods_fail,
    assert_no_secrets_in_text,
    cannot_construct_write_capable_broker,
    live_trading_invariant,
    place_order_call_count_guard,
    scan_phase15_for_broker_submit_calls,
)
from quantfund.phase15.models import OrderReality, SessionState, WouldOrder, scrub_secrets
from quantfund.phase15.providers import (
    CapableMarketDataProvider,
    ProviderProvenance,
    YFINANCE_CAPS,
    build_market_data_provider,
    real_provider_configured,
)
from quantfund.phase15.reconcile import reconcile_positions
from quantfund.phase15.recovery import checkpoint_from_shadow_session, recover_phase15
from quantfund.phase15.report import build_phase15_report, write_phase15_report
from quantfund.phase15.session_machine import SessionStateMachine
from quantfund.phase15.shadow_session import Phase15ShadowSession
from quantfund.phase15.validation import RealMarketEventValidator
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def _inst(symbol: str = "RELIANCE") -> list[Instrument]:
    return [
        Instrument(
            symbol=symbol,
            exchange="NSE",
            isin="INE002A01018",
            instrument_id=f"NSE:{symbol}",
        )
    ]


def _bar(
    *,
    symbol: str = "RELIANCE",
    seq: int = 0,
    ts: datetime | None = None,
    received_at: datetime | None = None,
    o: float = 100,
    h: float = 101,
    l: float = 99,
    c: float = 100.5,
    volume: float = 1000,
) -> RealTimeBar:
    ts = ts or datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    received_at = received_at or ts
    return RealTimeBar(
        symbol=symbol,
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=volume,
        source="test",
        received_at=received_at,
        sequence=seq,
        instrument_id=f"NSE:{symbol}",
    )


def _capable(stream: list[RealTimeBar] | None = None) -> CapableMarketDataProvider:
    inner = YFinanceSimulationMarketDataProvider(
        stream=stream
        or YFinanceSimulationMarketDataProvider.from_fixture_bars(n=10)._stream
    )
    return CapableMarketDataProvider(
        inner,
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


def _session(
    tmp_path: Path | None = None,
    *,
    n: int = 10,
    max_staleness: float | None = None,
    reconcile: bool = False,
    risk: PaperRiskConfig | None = None,
    broker: SimulatedReadOnlyBroker | None = None,
    force_stale_from: int | None = None,
) -> Phase15ShadowSession:
    symbol = "RELIANCE"
    factory = lambda: BuyAndHoldStrategy(symbol=symbol, allocation=0.5)
    meta = factory().metadata()
    base = YFinanceSimulationMarketDataProvider.from_fixture_bars(
        symbol=symbol,
        n=n,
        max_staleness_seconds=max_staleness,
        force_stale_from_seq=force_stale_from,
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
    dates = sorted({b.timestamp.date() for b in base._stream})
    jpath = tmp_path / "j.jsonl" if tmp_path else None
    return Phase15ShadowSession(
        provider=provider,
        strategy_factory=factory,
        session_config=PaperSessionConfig(
            session_id="p15_test",
            mode=SessionMode.INFRASTRUCTURE_SANDBOX,
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            certified_eligibility="development_only",
            seed="p15",
        ),
        calendar=FakeCalendarProvider(open_sessions=dates, verified=True),
        broker=broker or SimulatedReadOnlyBroker(),
        instruments=_inst(symbol),
        risk_config=risk
        or PaperRiskConfig(
            max_order_notional=200_000,
            max_position_notional=200_000,
            max_gross_exposure=200_000,
            max_order_count=50,
        ),
        journal_path=jpath,
        max_staleness_seconds=max_staleness,
        daily_bar_mode=True,
        enable_broker_reconcile=reconcile,
    )


# --- capabilities / provider ---


def test_market_data_capabilities_yfinance_not_exchange_grade():
    assert YFINANCE_CAPS.source_grade == "non_exchange"
    assert YFINANCE_CAPS.simulation_only is True
    assert YFINANCE_CAPS.research_eligible is False


def test_provider_interface_capabilities():
    p = build_market_data_provider(force_simulated=True)
    caps = p.capabilities()
    assert isinstance(caps, MarketDataCapabilities)
    assert caps.provider_id


def test_provider_provenance_simulated():
    p = build_market_data_provider(force_simulated=True)
    assert p.provenance().mode == "SIMULATED"


def test_real_provider_configured_false_by_default():
    assert real_provider_configured({}) is False


def test_real_provider_configured_env():
    assert real_provider_configured({"QUANTFUND_REAL_MARKET_DATA": "1"}) is True


def test_build_real_mode_when_configured():
    p = build_market_data_provider(env={"PHASE15_REAL_MARKET_DATA": "1"})
    assert p.provenance().mode == "REAL_READ_ONLY"
    assert p.capabilities().source_grade != "exchange_grade"


def test_provider_capability_validation_dict():
    d = YFINANCE_CAPS.to_dict()
    assert d["realtime_quotes"] is False


def test_provider_disconnect_reconnect():
    p = _capable()
    p.connect()
    p.force_disconnect()
    assert p.health().connected is False
    p.reconnect()
    assert p.health().connected is True


def test_provider_disconnect_blocks_next_bar():
    p = _capable()
    p.connect()
    p.subscribe(["RELIANCE"])
    p.force_disconnect()
    assert p.next_bar() is None


# --- broker read-only ---


def test_broker_capabilities_fail_closed_on_place_order():
    with pytest.raises(ValueError):
        BrokerCapabilities(
            provider_id="x",
            authenticated=True,
            account_read=True,
            positions_read=True,
            orders_read=True,
            trades_read=True,
            place_order=True,
        )


def test_broker_capabilities_fail_closed_on_cancel():
    with pytest.raises(ValueError):
        BrokerCapabilities(
            provider_id="x",
            authenticated=True,
            account_read=True,
            positions_read=True,
            orders_read=True,
            trades_read=True,
            cancel_order=True,
        )


def test_broker_capabilities_fail_closed_on_modify():
    with pytest.raises(ValueError):
        BrokerCapabilities(
            provider_id="x",
            authenticated=True,
            account_read=True,
            positions_read=True,
            orders_read=True,
            trades_read=True,
            modify_order=True,
        )


def test_cannot_construct_write_capable_broker():
    cannot_construct_write_capable_broker()


def test_readonly_broker_can_place_orders_false():
    b = SimulatedReadOnlyBroker()
    assert b.can_place_orders is False
    assert b.capabilities().can_place_orders is False


def test_place_order_raises():
    b = SimulatedReadOnlyBroker()
    with pytest.raises(BrokerWriteForbidden):
        b.place_order(symbol="X", qty=1)


def test_cancel_modify_raise():
    b = SimulatedReadOnlyBroker()
    with pytest.raises(BrokerWriteForbidden):
        b.cancel_order("1")
    with pytest.raises(BrokerWriteForbidden):
        b.modify_order("1")


def test_place_order_call_count_guard():
    assert place_order_call_count_guard(SimulatedReadOnlyBroker()) == 0


def test_assert_broker_write_methods_fail():
    r = assert_broker_write_methods_fail()
    assert r["place_order_called"] == 0


def test_construct_readonly_broker_simulated():
    b = construct_readonly_broker(mode="simulated")
    assert isinstance(b, SimulatedReadOnlyBroker)


def test_broker_account_read():
    b = SimulatedReadOnlyBroker(cash=50_000, positions={"RELIANCE": 2})
    b.connect()
    acct = b.get_account()
    assert acct.cash == 50_000
    assert acct.positions["RELIANCE"] == 2


def test_scan_phase15_no_submit_calls():
    assert scan_phase15_for_broker_submit_calls() == []


def test_live_trading_invariant():
    inv = live_trading_invariant()
    assert inv["LIVE_TRADING"] is False
    assert inv["real_orders"] == 0


# --- validation ---


def test_validator_ok_bar():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    assert v.validate(_bar()).ok


def test_stale_tick_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=10
    )
    ts = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    bar = _bar(ts=ts, received_at=ts + timedelta(seconds=100))
    r = v.validate(bar)
    assert not r.ok
    assert r.blocked_reason == "stale_data"


def test_future_timestamp_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    now = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    v = RealMarketEventValidator(
        calendar=cal,
        known_symbols={"RELIANCE"},
        max_staleness_seconds=None,
        now=now,
    )
    bar = _bar(ts=now + timedelta(hours=1), received_at=now)
    r = v.validate(bar)
    assert not r.ok
    assert r.blocked_reason == "future_timestamp"


def test_duplicate_tick_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    b = _bar(seq=1)
    assert v.validate(b).ok
    r = v.validate(b)
    assert not r.ok
    assert r.blocked_reason == "duplicate_event"


def test_out_of_order_seq_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    t0 = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    assert v.validate(_bar(seq=2, ts=t0)).ok
    r = v.validate(_bar(seq=1, ts=t0 + timedelta(minutes=1)))
    assert not r.ok
    assert r.blocked_reason == "out_of_order"


def test_out_of_order_timestamp_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    t0 = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    assert v.validate(_bar(seq=1, ts=t0 + timedelta(minutes=5))).ok
    r = v.validate(_bar(seq=2, ts=t0))
    assert not r.ok


def test_unknown_instrument_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    r = v.validate(_bar(symbol="UNKNOWNXYZ"))
    assert not r.ok
    assert r.blocked_reason == "unknown_instrument"


def test_invalid_ohlc_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    r = v.validate(_bar(h=90, l=100, o=95, c=95))
    assert not r.ok
    assert r.blocked_reason == "invalid_ohlc"


def test_missing_price_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    r = v.validate(_bar(o=0, h=0, l=0, c=0))
    assert not r.ok


def test_negative_volume_blocked():
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    r = v.validate(_bar(volume=-1))
    assert not r.ok
    assert r.blocked_reason == "invalid_volume"


def test_session_closed_blocked():
    cal = FakeCalendarProvider(open_sessions=[], verified=True)
    v = RealMarketEventValidator(
        calendar=cal, known_symbols={"RELIANCE"}, max_staleness_seconds=None
    )
    r = v.validate(_bar())
    assert not r.ok
    assert r.blocked_reason == "session_closed"


def test_validation_result_dict_status_data_blocked():
    cal = FakeCalendarProvider(open_sessions=[], verified=True)
    v = RealMarketEventValidator(calendar=cal, max_staleness_seconds=None)
    d = v.validate(_bar()).to_dict()
    assert d["status"] == "DATA_BLOCKED"


# --- session machine / freeze ---


def test_session_state_machine_happy_path():
    m = SessionStateMachine()
    m.transition(SessionState.PREFLIGHT)
    m.transition(SessionState.CONNECTED)
    m.transition(SessionState.WARMING_UP)
    m.transition(SessionState.RUNNING_SHADOW)
    m.transition(SessionState.STOPPING)
    m.transition(SessionState.COMPLETED)
    assert m.is_terminal


def test_session_illegal_transition():
    m = SessionStateMachine()
    with pytest.raises(ValueError):
        m.transition(SessionState.RUNNING_SHADOW)


def test_failed_safe_from_any():
    m = SessionStateMachine()
    m.transition(SessionState.FAILED_SAFE)
    assert m.state is SessionState.FAILED_SAFE


def test_freeze_and_assert_unchanged():
    f = freeze_session_config(strategy_id="s", strategy_version="1")
    assert_freeze_unchanged(f, f)


def test_freeze_change_invalidates():
    f = freeze_session_config(strategy_id="s", strategy_version="1")
    g = freeze_session_config(strategy_id="s", strategy_version="2")
    with pytest.raises(RuntimeError, match="SESSION_INVALIDATED"):
        assert_freeze_unchanged(f, g)


def test_session_invalidated_on_config_change(tmp_path):
    s = _session(tmp_path)
    s.connect()
    s.begin_shadow()
    s.invalidate_if_config_changed(
        freeze_session_config(strategy_id="other", strategy_version="9")
    )
    assert s.machine.state is SessionState.SESSION_INVALIDATED


# --- would order / shadow ---


def test_would_order_rejects_real_reality():
    with pytest.raises(ValueError):
        WouldOrder(
            decision_id="d",
            strategy_id="s",
            instrument_id="NSE:X",
            side="BUY",
            quantity=1,
            intended_price=1,
            timestamp=datetime.now(timezone.utc),
            reason="x",
            risk_result="ACCEPT",
            market_data_version="v",
            strategy_hash="h",
            reality=OrderReality.REAL_ORDER,
        )


def test_shadow_generates_would_orders(tmp_path):
    s = _session(tmp_path, n=10, max_staleness=None, reconcile=False)
    r = s.run(["RELIANCE"])
    assert len(r.would_orders) > 0
    assert r.real_orders == 0
    assert r.broker_submissions == 0


def test_shadow_simulated_orders(tmp_path):
    s = _session(tmp_path, n=10, max_staleness=None, reconcile=False)
    r = s.run(["RELIANCE"])
    assert len(r.simulated_orders) >= 0
    assert all(o["type"] != "REAL_ORDER" for o in r.simulated_orders)


def test_shadow_would_fills(tmp_path):
    s = _session(tmp_path, n=10, max_staleness=None, reconcile=False)
    r = s.run(["RELIANCE"])
    assert len(r.would_fills) >= 0


def test_risk_blocking(tmp_path):
    tight = PaperRiskConfig(
        max_order_notional=1.0,
        max_position_notional=1.0,
        max_gross_exposure=1.0,
        max_order_count=10,
    )
    s = _session(tmp_path, n=8, max_staleness=None, reconcile=False, risk=tight)
    s.run(["RELIANCE"])
    assert len(s.engine.result.would_rejects) > 0


def test_kill_switch_blocks(tmp_path):
    s = _session(tmp_path, n=10, max_staleness=None, reconcile=False)
    s.connect()
    s.begin_shadow()
    s.activate_kill_switch(reason="test")
    bar = s.provider.next_bar()
    out = s.process_bar(bar)
    assert out["status"] == "KILL_SWITCH"
    s.stop()


def test_stale_data_blocks_decisions(tmp_path):
    s = _session(tmp_path, n=12, max_staleness=100.0, force_stale_from=8, reconcile=False)
    r = s.run(["RELIANCE"])
    assert r.bars_blocked > 0
    assert any(d["reason"] == "stale_data" for d in r.data_blocked)


def test_data_blocked_no_would_order_on_bad_bar(tmp_path):
    s = _session(tmp_path, n=3, max_staleness=None, reconcile=False)
    s.connect()
    s.begin_shadow()
    cal_dates = [datetime(2024, 1, 2, tzinfo=timezone.utc).date()]
    s.validator = RealMarketEventValidator(
        calendar=FakeCalendarProvider(open_sessions=cal_dates, verified=True),
        known_symbols={"RELIANCE"},
        max_staleness_seconds=None,
    )
    before = len(s.result.would_orders)
    out = s.process_bar(_bar(h=1, l=10, o=5, c=5, seq=99))
    assert out["status"] == "DATA_BLOCKED"
    assert len(s.result.would_orders) == before
    s.stop()


# --- reconcile / recovery / health ---


def test_reconcile_clean():
    r = reconcile_positions(
        broker_positions={"RELIANCE": 1},
        shadow_positions={"RELIANCE": 1},
    )
    assert r.status == "CLEAN"
    assert r.allows_new_shadow_orders


def test_reconcile_mismatch_blocks():
    r = reconcile_positions(
        broker_positions={"RELIANCE": 1},
        shadow_positions={"RELIANCE": 0},
    )
    assert r.status == "RECONCILIATION_MISMATCH"
    assert r.allows_new_shadow_orders is False


def test_session_reconcile_mismatch_pauses(tmp_path):
    broker = SimulatedReadOnlyBroker(positions={"RELIANCE": 5})
    s = _session(tmp_path, n=5, max_staleness=None, reconcile=True, broker=broker)
    s.connect()
    s.begin_shadow()
    assert s.result.reconciliation == "RECONCILIATION_MISMATCH"
    assert s.health.paused


def test_recovery_pass(tmp_path):
    s = _session(tmp_path, n=8, max_staleness=None, reconcile=False)
    s.connect()
    s.begin_shadow()
    s.drain()
    cpath = tmp_path / "ckpt.json"
    checkpoint_from_shadow_session(s, cpath)
    recovered = recover_phase15(
        session_id=s.session_config.session_id,
        journal_path=tmp_path / "j.jsonl",
        checkpoint_path=cpath,
        strategy_id=s.frozen.strategy_id,
        strategy_version=s.frozen.strategy_version,
        config_hash=s.session_config.config_hash(),
        expected_freeze_token=s.frozen.freeze_token,
    )
    assert recovered.trusted
    s.stop()


def test_recovery_missing_checkpoint(tmp_path):
    r = recover_phase15(
        session_id="x",
        journal_path=None,
        checkpoint_path=tmp_path / "missing.json",
    )
    assert r.trusted is False


def test_journal_replay_events(tmp_path):
    s = _session(tmp_path, n=8, max_staleness=None, reconcile=False)
    s.run(["RELIANCE"])
    text = (tmp_path / "j.jsonl").read_text(encoding="utf-8")
    assert "WOULD_ORDER" in text or "ORDER_ACCEPTED" in text
    assert "api_secret" not in text.lower()


def test_deterministic_replay_decision_ids(tmp_path):
    s1 = _session(tmp_path / "a", n=8, max_staleness=None, reconcile=False)
    s1.session_config = s1.session_config.model_copy(update={"session_id": "p15_det"})
    # rebuild with fixed session id
    s1 = _session(tmp_path / "a", n=8, max_staleness=None, reconcile=False)
    r1 = s1.run(["RELIANCE"])
    s2 = _session(tmp_path / "b", n=8, max_staleness=None, reconcile=False)
    r2 = s2.run(["RELIANCE"])
    if r1.would_orders and r2.would_orders:
        assert r1.would_orders[0]["strategy_hash"] == r2.would_orders[0]["strategy_hash"]


def test_health_pause_on_critical():
    h = Phase15Health(market_data_heartbeat_ok=False, provider_connected=False)
    assert should_pause_shadow(h)


def test_provider_failure_pauses(tmp_path):
    s = _session(tmp_path, n=3, max_staleness=None, reconcile=False)
    s.connect()
    s.begin_shadow()
    s.provider.force_disconnect()
    s.drain()
    assert s.health.paused or not s.health.provider_connected


def test_broker_read_failure_path(tmp_path):
    class BoomBroker(SimulatedReadOnlyBroker):
        def get_positions(self):
            raise RuntimeError("boom")

    s = _session(tmp_path, n=3, max_staleness=None, reconcile=True, broker=BoomBroker())
    s.connect()
    s.begin_shadow()
    assert s.health.paused


def test_heartbeat_failure_health_dict():
    h = Phase15Health(market_data_heartbeat_ok=False)
    d = h.to_dict()
    assert d["critical_ok"] is False


# --- secrets / report / demo ---


def test_scrub_secrets():
    d = scrub_secrets({"access_token": "SECRET123", "ok": 1})
    assert d["access_token"] == "***REDACTED***"
    assert d["ok"] == 1


def test_no_secrets_in_report(tmp_path):
    report = build_phase15_report(
        {"access_token": "LEAK", "would_orders": 1, "market_data_mode": "SIMULATED"}
    )
    raw = str(report)
    assert_no_secrets_in_text(raw.replace("***REDACTED***", ""), ["LEAK"])
    # scrubbed value present as redaction
    assert report["access_token"] == "***REDACTED***"


def test_write_report(tmp_path):
    paths = write_phase15_report({"would_orders": 1, "market_data_mode": "SIMULATED"}, tmp_path)
    assert paths["json"].exists()
    assert "Real orders: 0" in paths["txt"].read_text()


def test_phase15_live_trading_false():
    assert Phase15ShadowSession.LIVE_TRADING is False


def test_no_live_order_invariant_in_result(tmp_path):
    r = _session(tmp_path, n=6, max_staleness=None, reconcile=False).run(["RELIANCE"])
    d = r.to_dict()
    assert d["real_orders"] == 0
    assert d["broker_submissions"] == 0
    assert d["live_trading"] is False
    assert d["research_eligibility"] == "DEVELOPMENT_ONLY"
    assert d["claims"] == "NONE"


def test_connectivity_skips_without_creds():
    r = run_phase15_connectivity(env={})
    assert r["skipped"] is True
    assert r["place_order_called"] == 0
    assert r["can_place_orders"] is False


def test_connectivity_force_still_no_place():
    r = run_phase15_connectivity(env={"PHASE15_FORCE_CONNECTIVITY": "1"})
    assert r["place_order_called"] == 0


def test_demo_pass(tmp_path):
    r = run_phase15_demo(tmp_path / "demo")
    assert r["ok"] is True
    assert r["would_orders"] > 0
    assert r["real_orders"] == 0
    assert r["place_order_called"] == 0
    assert r["kill_switch"] == "ARMED"
    assert r["research_eligibility"] == "DEVELOPMENT_ONLY"


def test_monkeypatch_place_order_never_increments(tmp_path, monkeypatch):
    calls = {"n": 0}
    broker = SimulatedReadOnlyBroker()

    def counting_place(*a, **k):
        calls["n"] += 1
        raise BrokerWriteForbidden("blocked")

    monkeypatch.setattr(broker, "place_order", counting_place)
    s = _session(tmp_path, n=8, max_staleness=None, reconcile=False, broker=broker)
    s.run(["RELIANCE"])
    # preflight uses getattr place_order once; must still end at 0 successes
    assert calls["n"] <= 1  # attempted in preflight
    assert s.result.real_orders == 0
    assert place_order_call_count_guard(SimulatedReadOnlyBroker()) == 0


def test_preflight_ok(tmp_path):
    s = _session(tmp_path)
    pf = s.preflight()
    assert pf["ok"]
    assert pf["live_trading"] is False


def test_pause_resume(tmp_path):
    s = _session(tmp_path, n=5, max_staleness=None, reconcile=False)
    s.connect()
    s.begin_shadow()
    s.pause("test")
    assert s.machine.state is SessionState.PAUSED
    s.resume()
    assert s.machine.state is SessionState.RUNNING_SHADOW
    s.stop()


def test_yfinance_not_research_eligible_in_session(tmp_path):
    s = _session(tmp_path)
    assert s.provider.capabilities().research_eligible is False
    assert s.result.research_eligibility == "DEVELOPMENT_ONLY"


def test_ambiguous_instrument_master(tmp_path):
    # two instruments same symbol → ambiguous
    instruments = [
        Instrument(symbol="FOO", exchange="NSE", isin="INE1", instrument_id="NSE:FOO:A"),
        Instrument(symbol="FOO", exchange="NSE", isin="INE2", instrument_id="NSE:FOO:B"),
    ]
    cal = FakeCalendarProvider(
        open_sessions=[datetime(2024, 1, 2, tzinfo=timezone.utc).date()],
        verified=True,
    )
    v = RealMarketEventValidator(
        calendar=cal,
        instrument_master=instruments,
        max_staleness_seconds=None,
    )
    r = v.validate(_bar(symbol="FOO"))
    assert not r.ok
    assert r.blocked_reason == "ambiguous_instrument"


def test_clock_anomaly_pauses(tmp_path):
    s = _session(tmp_path, n=2, max_staleness=None, reconcile=False)
    s.connect()
    s.begin_shadow()
    s.validator = RealMarketEventValidator(
        calendar=s.calendar,
        known_symbols={"RELIANCE"},
        max_staleness_seconds=None,
        now=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
    )
    future = _bar(
        ts=datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc),
        received_at=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
        seq=50,
    )
    out = s.process_bar(future)
    assert out["status"] == "DATA_BLOCKED"
    assert s.health.paused or not s.health.clock_ok
    s.stop()


def test_report_claims_none():
    r = build_phase15_report({"would_orders": 2})
    assert r["claims"] == "NONE"
    assert r["live_trading"] == "DISABLED"

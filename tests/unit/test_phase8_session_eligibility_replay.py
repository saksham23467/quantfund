"""Phase 8 — session, eligibility gate, replay, separation."""

from __future__ import annotations

import inspect

import pytest

from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.models import SessionMode
from quantfund.paper.orders import PaperOrderStatus
from quantfund.paper.replay import replay_deterministic, run_paper_session
from quantfund.paper.risk import PaperRiskConfig
from quantfund.paper.session import PaperSession
from quantfund.strategies import base as strategy_base
from quantfund.trading.models import Fill
from tests.unit.test_phase8_helpers import (
    BuyOnceStrategy,
    calendar_for_events,
    make_events,
    sample_instrument,
    sandbox_config,
)


def test_development_only_paper_eligible_false():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="development_only",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="ev1",
    )
    assert d.paper_eligible is False
    assert any("development_only" in b for b in d.blockers)


def test_infrastructure_sandbox_never_paper_eligible():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        acceptance_evidence_id="ev1",
    )
    assert d.paper_eligible is False
    assert any("infrastructure_sandbox" in b for b in d.blockers)


def test_campaign_acceptance_alone_insufficient():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        campaign_accepted=True,
        acceptance_evidence_id=None,
    )
    assert d.paper_eligible is False
    assert any("missing_acceptance_evidence" in b for b in d.blockers)


def test_production_session_requires_eligibility():
    events = make_events(3)
    cfg = sandbox_config(
        mode=SessionMode.PRODUCTION,
        certified_eligibility="development_only",
    )
    with pytest.raises(ValueError, match="paper_eligible"):
        PaperSession(
            cfg,
            strategy=BuyOnceStrategy(),
            calendar=calendar_for_events(events),
        )


def test_next_bar_open_fill_on_following_event():
    events = make_events(4)
    cfg = sandbox_config(session_id="nb_open")
    result = run_paper_session(
        config=cfg,
        strategy=BuyOnceStrategy(qty=10),
        events=events,
        calendar=calendar_for_events(events),
        instruments=[sample_instrument()],
    )
    assert result.halted is False
    assert len(result.fills) == 1
    # Fill executes on event seq 1 open (signal on seq 0)
    assert result.fills[0].timestamp == events[1].timestamp
    assert result.snapshot["positions"]["AAA"]["quantity"] == 10
    assert result.reconciliation.ok is True
    assert result.paper_eligible is False


def test_kill_switch_in_session_rejects_orders():
    events = make_events(5)
    cfg = sandbox_config(session_id="ks_sess")
    session = PaperSession(
        cfg,
        strategy=BuyOnceStrategy(qty=10),
        calendar=calendar_for_events(events),
    )
    session.start()
    session.activate_kill_switch(reason="test", actor="op")
    for ev in events:
        session.process_event(ev)
    result = session.stop()
    assert any(o["status"] == PaperOrderStatus.REJECTED.value for o in result.orders) or (
        len(result.fills) == 0
    )
    assert "kill_switch_activated" in session.audit.event_types()


def test_risk_limit_in_session():
    events = make_events(4)
    cfg = sandbox_config(session_id="risk_sess")
    result = run_paper_session(
        config=cfg,
        strategy=BuyOnceStrategy(qty=1000),
        events=events,
        calendar=calendar_for_events(events),
        risk_config=PaperRiskConfig(max_order_notional=100),
    )
    assert len(result.fills) == 0
    assert any(o.get("reject_reason") == "max_order_notional" or o["status"] == "REJECTED" for o in result.orders)


def test_deterministic_replay():
    events = make_events(6)
    cfg = sandbox_config(session_id="replay1")

    def factory():
        return BuyOnceStrategy(qty=10)

    rr = replay_deterministic(
        config=cfg,
        strategy_factory=factory,
        events=events,
        calendar=calendar_for_events(events),
    )
    assert rr.deterministic is True
    assert rr.first.state_hash == rr.second.state_hash
    assert rr.first.snapshot == rr.second.snapshot


def test_session_audit_has_required_types():
    events = make_events(4)
    cfg = sandbox_config(session_id="audit1")
    session = PaperSession(
        cfg,
        strategy=BuyOnceStrategy(),
        calendar=calendar_for_events(events),
    )
    session.start()
    for ev in events:
        session.process_event(ev)
    session.stop()
    types = session.audit.event_types()
    for required in (
        "session_started",
        "market_event",
        "signal_generated",
        "session_stopped",
    ):
        assert required in types


def test_duplicate_market_event_halts_fail_closed():
    events = make_events(3)
    cfg = sandbox_config(session_id="dup_halt")
    session = PaperSession(
        cfg,
        strategy=BuyOnceStrategy(),
        calendar=calendar_for_events(events),
    )
    session.start()
    session.process_event(events[0])
    session.process_event(events[0])
    assert session.halted is True
    assert session.halt_reason == "duplicate_event"


def test_invalid_ohlc_event_fails_before_session():
    # construction fails — never invent
    from datetime import datetime, timezone

    from quantfund.paper.models import MarketDataEvent

    with pytest.raises(Exception):
        MarketDataEvent(
            event_id="bad",
            seq=0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            symbol="AAA",
            open=10,
            high=8,
            low=9,
            close=10,
        )


def test_strategy_base_cannot_create_fills():
    src = inspect.getsource(strategy_base)
    assert "Fill(" not in src
    assert "fill_id" not in src


def test_strategy_module_does_not_import_paper_execution():
    src = inspect.getsource(strategy_base)
    assert "quantfund.paper.execution" not in src
    assert "PaperExecutionAdapter" not in src


def test_sandbox_result_flags():
    events = make_events(4)
    cfg = sandbox_config(session_id="flags1")
    result = run_paper_session(
        config=cfg,
        strategy=BuyOnceStrategy(),
        events=events,
        calendar=calendar_for_events(events),
    )
    assert result.mode == SessionMode.INFRASTRUCTURE_SANDBOX
    assert result.paper_eligible is False
    assert result.eligibility.certified_eligibility == "development_only"


def test_exception_fail_closed_on_bad_strategy():
    class Boom(BuyOnceStrategy):
        def generate_signal(self, context):
            raise RuntimeError("boom")

    events = make_events(2)
    cfg = sandbox_config(session_id="boom")
    session = PaperSession(
        cfg,
        strategy=Boom(),
        calendar=calendar_for_events(events),
    )
    session.start()
    session.process_event(events[0])
    assert session.halted is True
    assert "exception" in (session.halt_reason or "")


def test_fills_are_trading_fill_instances():
    events = make_events(4)
    result = run_paper_session(
        config=sandbox_config(session_id="filltype"),
        strategy=BuyOnceStrategy(),
        events=events,
        calendar=calendar_for_events(events),
    )
    assert all(isinstance(f, Fill) for f in result.fills)

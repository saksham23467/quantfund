"""Deterministic paper replay certification (simulated eligible path for tests)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from quantfund.paper.models import deterministic_id, state_hash
from quantfund.paper.orders import make_order_intent
from quantfund.phase11.connectivity_status import BrokerConnectivityStatus
from quantfund.phase11.reports import build_paper_session_report
from quantfund.phase11.trading_session import PaperTradingSession, PaperTradingState
from quantfund.trading.models import Order, OrderSide, OrderType, Signal, SignalAction


@dataclass
class ReplayCertResult:
    identical: bool
    hash_a: str
    hash_b: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "identical": self.identical,
            "hash_a": self.hash_a,
            "hash_b": self.hash_b,
            "details": dict(self.details),
        }


def _run_once(session_id: str) -> dict[str, Any]:
    """Run a forced paper path for determinism tests.

    Uses a test-only bypass: session is put READY only when we inject a
    synthetic paper_eligible decision after DEVELOPMENT_ONLY fail would occur.
    For certification of ID/replay machinery we force strategy_enabled and
    manually set READY after marking a test gate decision — WITHOUT changing
    production DEVELOPMENT_ONLY rules for real certification.
    """
    from quantfund.phase11.paper_gates import Phase11PaperGateDecision

    sess = PaperTradingSession.create(
        session_id=session_id,
        connectivity=BrokerConnectivityStatus.SIMULATED,
        strategy_enabled=True,
        initial_cash=100_000.0,
    )
    # Real gate will fail DEVELOPMENT_ONLY — for replay harness we only test
    # execution determinism when paper_eligible is forced in-memory for CI.
    forced = Phase11PaperGateDecision(
        paper_eligible=True,
        research_eligibility="research_eligible",
        connectivity=BrokerConnectivityStatus.SIMULATED,
        blockers=[],
    )
    sess.gate_decision = forced
    sess.state = PaperTradingState.CREATED
    sess._transition(PaperTradingState.PREFLIGHT, reason="test")
    sess._transition(PaperTradingState.READY, reason="test_force_eligible")
    sess.start_running()

    ts = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    signal = Signal(
        timestamp=ts,
        symbol="AAA",
        action=SignalAction.BUY,
        strength=1.0,
        target_quantity=10,
    )
    order = Order(
        timestamp=ts,
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        order_id=deterministic_id(session_id, "ord", "AAA", 10),
    )
    intent = make_order_intent(
        session_id=session_id,
        order=order,
        signal=signal,
        event_seq=1,
    )

    sess.submit_intent(
        intent,
        ref_price=100.0,
        open_price=100.0,
        execution_time=datetime(2024, 1, 3, 3, 45, tzinfo=timezone.utc),
    )
    sess.reconcile()
    if sess.state != PaperTradingState.FAILED:
        sess.finalize()
    report = build_paper_session_report(
        sess,
        strategy_id="replay_test",
        dataset="synthetic_fixture",
        configuration_hash="sha256:phase11_replay",
    )
    return {
        "orders": sess.paper_orders,
        "fills": sess.paper_fills,
        "cash": float(sess.portfolio.portfolio.cash),
        "positions": {
            s: p.quantity for s, p in sess.portfolio.portfolio.positions.items()
        },
        "report_hash": report.report_hash,
        "live_orders": sess.live_orders,
        "fill_ids": [f.fill_id for f in sess.fills],
        "intent_ids": [intent.intent_id],
    }


def run_deterministic_replay_pair() -> ReplayCertResult:
    a = _run_once("phase11_replay_sess")
    b = _run_once("phase11_replay_sess")
    ha = state_hash(a)
    hb = state_hash(b)
    return ReplayCertResult(
        identical=a == b and ha == hb,
        hash_a=ha,
        hash_b=hb,
        details={"a": a, "b": b},
    )

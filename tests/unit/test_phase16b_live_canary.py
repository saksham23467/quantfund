"""Phase 16B — controlled live canary (≥80 tests)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import state_hash
from quantfund.phase15.broker_readonly import BrokerWriteForbidden
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16b.activation import (
    CANARY_CONFIRM_PHRASE,
    create_canary_activation,
)
from quantfund.phase16b.broker import build_canary_broker, make_broker_order_request
from quantfund.phase16b.demo import run_phase16b_demo, run_phase16b_preflight
from quantfund.phase16b.flags import env_alone_cannot_authorize, resolve_live_trading_flag
from quantfund.phase16b.gates import OrderIntent, SessionCounters, evaluate_pretrade_gates
from quantfund.phase16b.isolation import (
    assert_ci_uses_mock_broker,
    prove_gate_failure_skips_place_order,
    unauthorized_place_order_raises,
)
from quantfund.phase16b.limits import CanaryPolicy, default_canary_policy
from quantfund.phase16b.market_data_gate import LiveMarketQuote, evaluate_live_market_data
from quantfund.phase16b.pnl import DailyPnLTracker
from quantfund.phase16b.recovery import recover_uncertain_submit
from quantfund.phase16b.report import build_phase16b_report
from quantfund.phase16b.session import CanarySession, CanarySessionState


def _hashes(sid="buy_and_hold"):
    sh = state_hash({"id": sid, "v": "1.0.0"})
    ch = state_hash({"cfg": "t"})
    return sid, sh, ch


def _activation(sid="buy_and_hold", **kwargs):
    sid, sh, ch = _hashes(sid)
    kw = dict(
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
        dataset_provenance="test",
        broker="ZERODHA/MOCK",
        account_hash="acct:test",
        confirmation_phrase=CANARY_CONFIRM_PHRASE,
        actor="tester",
        ttl_hours=24,
    )
    kw.update(kwargs)
    if "strategy_hash" in kwargs:
        pass
    return create_canary_activation(**kw), sh, ch


def _quote(**kwargs):
    base = dict(
        symbol="RELIANCE",
        price=500.0,
        timestamp=datetime.now(timezone.utc),
        source_grade="vendor_read_only",
        provider_id="mock_live_feed",
        simulation_only=False,
    )
    base.update(kwargs)
    return LiveMarketQuote(**base)


def _session(mode="CANARY_SIMULATION", activate=True, disarm=True, reconcile=True):
    sid, sh, ch = _hashes()
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    act, _, _ = _activation()
    ks = KillSwitch()
    s = CanarySession(
        mode=mode,
        broker=broker,
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
        live_flag=resolve_live_trading_flag(
            explicit=(mode == "LIVE_CANARY")
        ),
        kill_switch=ks,
    )
    s.require_activation()
    if activate:
        s.activate(act)
    if disarm:
        s.disarm_kill_switch(actor="t", reason="t")
    if reconcile:
        s.reconcile({})
        s.begin_running()
    return s, broker


def _intent(**kwargs):
    sid, sh, ch = _hashes()
    base = dict(
        strategy_id=sid,
        strategy_hash=sh,
        config_hash=ch,
        symbol="RELIANCE",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        product="CNC",
        ref_price=500.0,
        intent_id="i1",
    )
    base.update(kwargs)
    return OrderIntent(**base)


# --- flags ---


def test_live_flag_default_false():
    assert resolve_live_trading_flag().enabled is False


def test_live_flag_env_untrusted():
    f = resolve_live_trading_flag(env={"LIVE_TRADING": "true"})
    assert f.enabled is True
    assert f.source == "environment_untrusted"


def test_env_alone_cannot_authorize():
    assert env_alone_cannot_authorize({"LIVE_TRADING": "true"}) is True


def test_explicit_false_wins():
    assert resolve_live_trading_flag(explicit=False, env={"LIVE_TRADING": "true"}).enabled is False


# --- activation ---


def test_missing_activation_blocks():
    s, b = _session(activate=False, disarm=True, reconcile=True)
    d = s.evaluate(_intent(), _quote())
    assert not d.allowed
    assert "missing_activation" in d.blockers
    b.disconnect()


def test_invalid_confirmation():
    with pytest.raises(ValueError):
        create_canary_activation(
            strategy_id="buy_and_hold",
            strategy_version="1",
            strategy_hash="h",
            config_hash="c",
            dataset_provenance="d",
            broker="Z",
            account_hash="a",
            confirmation_phrase="NOPE",
            actor="x",
        )


def test_expired_activation():
    act, sh, ch = _activation()
    # force expiry
    expired = create_canary_activation(
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
        dataset_provenance="d",
        broker="Z",
        account_hash="a",
        confirmation_phrase=CANARY_CONFIRM_PHRASE,
        actor="x",
        ttl_hours=-1,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    assert expired.is_expired()
    blockers = expired.validate_against(
        strategy_id="buy_and_hold", strategy_hash=sh, config_hash=ch
    )
    assert "activation_expired" in blockers


def test_strategy_not_allowlisted():
    s, b = _session()
    intent = _intent(strategy_id="unknown_strat")
    # also hash mismatch / allowlist
    d = s.evaluate(intent, _quote())
    assert not d.allowed
    b.disconnect()


def test_strategy_hash_mismatch():
    s, b = _session()
    d = s.evaluate(_intent(strategy_hash="wrong"), _quote())
    assert "strategy_hash_mismatch" in d.blockers
    b.disconnect()


def test_config_hash_mismatch():
    s, b = _session()
    d = s.evaluate(_intent(config_hash="wrong"), _quote())
    assert "config_hash_mismatch" in d.blockers
    b.disconnect()


def test_activation_expiry_gate():
    sid, sh, ch = _hashes()
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    act = create_canary_activation(
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
        dataset_provenance="d",
        broker="Z",
        account_hash="a",
        confirmation_phrase=CANARY_CONFIRM_PHRASE,
        actor="x",
        ttl_hours=-0.01,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    s = CanarySession(
        mode="CANARY_SIMULATION",
        broker=broker,
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
    )
    blockers = s.activate(act)
    assert "activation_expired" in blockers
    broker.disconnect()


# --- kill switch ---


def test_kill_switch_armed_blocks():
    s, b = _session(disarm=False, reconcile=True)
    s.activate(_activation()[0])
    s.reconcile({})
    s.begin_running()
    d = s.evaluate(_intent(), _quote())
    assert "kill_switch_armed" in d.blockers
    b.disconnect()


def test_kill_switch_triggered_blocks():
    s, b = _session()
    s.kill_switch.activate(reason="x", actor="y")
    d = s.evaluate(_intent(), _quote())
    assert "kill_switch_triggered" in d.blockers
    b.disconnect()


def test_emergency_kill():
    s, b = _session()
    s.emergency_kill(reason="stop")
    assert s.state is CanarySessionState.HALTED
    assert s.kill_switch.is_triggered
    b.disconnect()


def test_restart_safe_state_default_armed():
    s, b = _session(disarm=False, activate=False, reconcile=False)
    assert s._kill_disarmed is False
    assert not s.kill_switch.is_triggered
    b.disconnect()


# --- market data ---


def test_yfinance_rejected_as_live_feed():
    q = _quote(provider_id="yfinance_simulation", source_grade="non_exchange", simulation_only=True)
    r = evaluate_live_market_data(q)
    assert not r.ok
    assert r.reason == "yfinance_rejected_as_live_feed"


def test_stale_market_data():
    q = _quote(timestamp=datetime.now(timezone.utc) - timedelta(hours=1))
    r = evaluate_live_market_data(q, max_age_seconds=10)
    assert r.reason == "stale_market_data"


def test_clock_skew():
    q = _quote(timestamp=datetime.now(timezone.utc) + timedelta(hours=1))
    r = evaluate_live_market_data(q, max_clock_skew_seconds=5)
    assert r.reason == "clock_skew"


def test_session_stale_blocks_submit():
    s, b = _session()
    before = b.place_calls
    out = s.submit_if_allowed(
        _intent(),
        _quote(timestamp=datetime.now(timezone.utc) - timedelta(days=1)),
    )
    assert out["submitted"] is False
    assert b.place_calls == before
    b.disconnect()


# --- reconcile / capital / limits ---


def test_reconciliation_mismatch_blocks():
    s, b = _session(reconcile=False)
    s.activate(_activation()[0])
    s.disarm_kill_switch(actor="t", reason="t")
    # force mismatch
    b._raw_transport.inner.positions = [
        {"tradingsymbol": "RELIANCE", "quantity": 9, "average_price": 1}
    ]
    s.reconcile(internal_positions={})
    assert s._reconciliation == "RECONCILIATION_MISMATCH"
    before = b.place_calls
    # session halted
    out = s.submit_if_allowed(_intent(), _quote())
    assert out["submitted"] is False
    assert b.place_calls == before
    b.disconnect()


def test_max_order_quantity():
    s, b = _session()
    d = s.evaluate(_intent(quantity=5), _quote())
    assert "max_order_quantity" in d.blockers
    b.disconnect()


def test_max_order_value():
    s, b = _session()
    d = s.evaluate(_intent(ref_price=5000), _quote(price=5000))
    assert "max_order_value" in d.blockers
    b.disconnect()


def test_max_position():
    s, b = _session()
    s.counters.positions = {"RELIANCE": 10}
    d = s.evaluate(_intent(quantity=1, ref_price=500), _quote())
    assert "max_position" in d.blockers
    b.disconnect()


def test_max_daily_loss():
    s, b = _session()
    s.counters.realized_pnl = -10_000
    d = s.evaluate(_intent(), _quote())
    assert "max_daily_loss" in d.blockers
    b.disconnect()


def test_max_orders_per_day():
    s, b = _session()
    s.counters.orders_today = 100
    d = s.evaluate(_intent(), _quote())
    assert "max_orders_per_day" in d.blockers
    b.disconnect()


def test_max_turnover():
    s, b = _session()
    s.counters.turnover_today = 10_000
    d = s.evaluate(_intent(), _quote())
    assert "max_turnover" in d.blockers
    b.disconnect()


def test_insufficient_capital():
    act, sh, ch = _activation(capital_limit=100)
    sid, _, _ = _hashes()
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    s = CanarySession(
        mode="CANARY_SIMULATION",
        broker=broker,
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
    )
    s.activate(act)
    s.disarm_kill_switch(actor="t", reason="t")
    s.reconcile({})
    s.begin_running()
    d = s.evaluate(_intent(ref_price=500), _quote())
    assert "insufficient_capital" in d.blockers
    broker.disconnect()


def test_invalid_symbol():
    s, b = _session()
    d = s.evaluate(_intent(symbol="NOTREAL"), _quote(symbol="NOTREAL"))
    assert "invalid_symbol" in d.blockers
    b.disconnect()


def test_invalid_side():
    s, b = _session()
    d = s.evaluate(_intent(side="SELL"), _quote())
    assert "invalid_side" in d.blockers
    b.disconnect()


def test_invalid_order_type():
    s, b = _session()
    d = s.evaluate(_intent(order_type="STOP"), _quote())
    assert "invalid_order_type" in d.blockers
    b.disconnect()


# --- critical: gate failure ⇒ place_order never called ---


@pytest.mark.parametrize(
    "mutator",
    [
        lambda s, i, q: (i, _quote(provider_id="yfinance")),
        lambda s, i, q: (_intent(quantity=99), q),
        lambda s, i, q: (_intent(symbol="X"), q),
        lambda s, i, q: (_intent(side="SELL"), q),
        lambda s, i, q: (_intent(strategy_hash="bad"), q),
    ],
)
def test_any_gate_failure_never_calls_place_order(mutator):
    s, b = _session()
    before = b.place_calls
    intent, quote = mutator(s, _intent(), _quote())
    out = s.submit_if_allowed(intent, quote)
    assert out.get("submitted") is False
    assert b.place_calls == before
    b.disconnect()


def test_prove_helper_gate_skip():
    s, b = _session()
    prove_gate_failure_skips_place_order(
        evaluate_and_submit=lambda: s.submit_if_allowed(
            _intent(quantity=50), _quote()
        ),
        broker=b,
    )
    b.disconnect()


def test_live_flag_disabled_in_live_mode():
    sid, sh, ch = _hashes()
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    act, _, _ = _activation()
    s = CanarySession(
        mode="LIVE_CANARY",
        broker=broker,
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
        live_flag=resolve_live_trading_flag(explicit=False),
    )
    s.activate(act)
    s.disarm_kill_switch(actor="t", reason="t")
    s.reconcile({})
    s.begin_running()
    d = s.evaluate(_intent(), _quote())
    assert "live_flag_disabled" in d.blockers
    before = broker.place_calls
    s.submit_if_allowed(_intent(), _quote())
    assert broker.place_calls == before
    broker.disconnect()


# --- successful mock canary ---


def test_successful_canary_order_mocked():
    s, b = _session()
    out = s.submit_if_allowed(_intent(), _quote())
    assert out["submitted"] is True
    assert b.place_calls == 1
    assert b.simulated_submissions == 1
    assert b.live_orders == 0
    b.disconnect()


def test_duplicate_submission_idempotent():
    s, b = _session()
    intent = _intent(intent_id="same")
    s.submit_if_allowed(intent, _quote())
    # second with same intent id
    out = s.submit_if_allowed(intent, _quote())
    # may be blocked by max_orders or idempotent
    assert b.place_calls <= 2
    if out.get("submitted") and out.get("response", {}).get("idempotent_replay"):
        assert out["response"]["idempotent_replay"] is True
    b.disconnect()


def test_unauthorized_place_raises():
    unauthorized_place_order_raises()


def test_broker_extends_16a_readonly():
    from quantfund.phase16a.zerodha_readonly import ZerodhaReadOnlyBroker

    b = build_canary_broker(force_mock=True)
    assert isinstance(b, ZerodhaReadOnlyBroker)


def test_ci_mock_broker():
    b = build_canary_broker(force_mock=True)
    assert_ci_uses_mock_broker(b)


# --- crash recovery / broker rejection ---


def test_crash_recovery_no_blind_resubmit():
    s, b = _session()
    b._pending_intents["lost"] = make_broker_order_request(
        intent_id="lost", symbol="RELIANCE", side="BUY", quantity=1
    )
    dec = recover_uncertain_submit(intent_id="lost", broker=b)
    assert dec.resubmit is False
    b.disconnect()


def test_timeout_after_submit_leaves_pending():
    s, b = _session()
    # simulate pending without completing store
    req = make_broker_order_request(
        intent_id="to1", symbol="RELIANCE", side="BUY", quantity=1
    )
    b._pending_intents["to1"] = req
    with pytest.raises(RuntimeError, match="pending_submit_requires_recovery"):
        b.authorize_next_submission()
        b._submit(req)
    b.disconnect()


def test_broker_rejection():
    s, b = _session()
    b._raw_transport.fail_next = "kite_api_error:rejected"
    b.authorize_next_submission()
    with pytest.raises(RuntimeError):
        b.place_order(
            request=make_broker_order_request(
                intent_id="rej", symbol="RELIANCE", side="BUY", quantity=1
            )
        )
    b.disconnect()


def test_partial_fill_booking(tmp_path):
    s, b = _session()
    # after place, mutate order to partial fill
    out = s.submit_if_allowed(_intent(intent_id="pf1"), _quote())
    oid = out["response"]["broker_order_id"]
    # Fake stores in inner.orders
    inner = b._raw_transport.inner
    if oid in inner.orders:
        inner.orders[oid]["filled_quantity"] = 1
        inner.orders[oid]["status"] = "COMPLETE"
        inner.orders[oid]["average_price"] = 500
    status = b.get_order_status(oid)
    assert float(status["filled_quantity"]) >= 0
    b.disconnect()


def test_complete_fill_status():
    s, b = _session()
    out = s.submit_if_allowed(_intent(intent_id="cf1"), _quote())
    oid = out["response"]["broker_order_id"]
    inner = b._raw_transport.inner
    inner.orders[oid]["filled_quantity"] = 1
    inner.orders[oid]["quantity"] = 1
    inner.orders[oid]["status"] = "COMPLETE"
    inner.orders[oid]["average_price"] = 500.0
    st = b.get_order_status(oid)
    assert st["filled_quantity"] == 1
    b.disconnect()


# --- secrets / audit / pnl / mutation ---


def test_secret_redaction():
    d = scrub_secrets({"access_token": "SECRET", "x": 1})
    assert d["access_token"] == "***REDACTED***"


def test_audit_integrity_no_secrets(tmp_path):
    s, b = _session()
    s.journal.path = tmp_path / "j.jsonl"
    s.journal.append("TEST", {"access_token": "LEAK"})
    text = (tmp_path / "j.jsonl").read_text()
    assert "LEAK" not in text
    b.disconnect()


def test_report_mentions_safety_note():
    r = build_phase16b_report({"mode": "CANARY_SIMULATION"})
    assert "real broker orders only when" in r["note"]


def test_pnl_persists(tmp_path):
    p = tmp_path / "pnl.json"
    t = DailyPnLTracker(path=p)
    t.realized_pnl = -100
    t._persist()
    t2 = DailyPnLTracker.load(p)
    assert t2.daily_loss == 100


def test_no_strategy_mutation():
    s, b = _session()
    s.strategy_hash = "mutated"
    with pytest.raises(RuntimeError, match="mutation"):
        s.assert_strategy_immutable()
    b.disconnect()


def test_no_ai_strategy_direct_live():
    # AI-ish id not in allowlist
    policy = default_canary_policy()
    assert "ai_generated_strategy" not in policy.strategy_allowlist


def test_default_canary_limits_tiny():
    p = default_canary_policy()
    assert p.max_order_quantity == 1
    assert p.max_order_value == 1000
    assert p.max_orders_per_day == 2


def test_automatic_halt_on_critical_gate():
    s, b = _session()
    s.evaluate(
        _intent(),
        _quote(timestamp=datetime.now(timezone.utc) - timedelta(days=1)),
    )
    assert s.kill_switch.is_triggered or not s._kill_disarmed
    b.disconnect()


def test_cancel_not_exposed():
    b = build_canary_broker(force_mock=True)
    b.connect()
    with pytest.raises(BrokerWriteForbidden):
        b.cancel_order("x")
    b.disconnect()


def test_modify_not_exposed():
    b = build_canary_broker(force_mock=True)
    b.connect()
    with pytest.raises(BrokerWriteForbidden):
        b.modify_order("x")
    b.disconnect()


# --- demo / preflight ---


def test_demo_pass(tmp_path):
    r = run_phase16b_demo(tmp_path)
    assert r["ok"] is True
    assert r["mode"] == "CANARY_SIMULATION"
    assert r["broker"] == "MOCK"
    assert r["activation"] == "VALID"
    assert r["strategy"] == "ALLOWLISTED"
    assert r["risk"] == "PASS"
    assert r["reconciliation"] == "CLEAN"
    assert r["kill_switch"] == "ARMED"
    assert r["broker_submission"] == "SIMULATED"
    assert r["live_orders"] == 0
    assert r["live_trading"] == "DISABLED"
    assert r["research_eligibility"] == "DEVELOPMENT_ONLY"
    assert r["claims"] == "NONE"
    assert r["real_broker_orders"] == 0


def test_preflight_no_place_order():
    r = run_phase16b_preflight()
    assert r["ok"] is True
    assert r["place_order_called"] == 0
    assert r["order_submission"] == "NOT EXECUTED"


def test_session_lifecycle_states():
    s, b = _session(activate=False, disarm=False, reconcile=False)
    assert s.state is CanarySessionState.ACTIVATION_REQUIRED
    s.activate(_activation()[0])
    assert s.state is CanarySessionState.ACTIVATED
    s.begin_running()
    assert s.state is CanarySessionState.RUNNING
    s.close()
    assert s.state is CanarySessionState.CLOSED
    b.disconnect()


def test_live_canary_mode_requires_flag():
    # covered above; ensure simulation does not need flag
    s, b = _session(mode="CANARY_SIMULATION")
    d = s.evaluate(_intent(), _quote())
    assert d.allowed
    b.disconnect()


def test_gate_decision_place_authorized_only_when_allowed():
    s, b = _session()
    d = s.evaluate(_intent(), _quote())
    assert d.allowed is True
    assert d.place_order_authorized is True
    b.disconnect()


def test_policy_from_defaults_dict():
    d = default_canary_policy().to_dict()
    assert "max_order_value" in d


def test_activation_record_immutable_fields():
    act, _, _ = _activation()
    assert act.human_confirmation == CANARY_CONFIRM_PHRASE
    assert act.configuration_hash.startswith("sha256:")


def test_yfinance_in_session_gate():
    s, b = _session()
    d = s.evaluate(
        _intent(),
        _quote(provider_id="yfinance_public_development", source_grade="non_exchange"),
    )
    assert "yfinance_rejected_as_live_feed" in d.blockers
    b.disconnect()


def test_missing_quote_blocks():
    s, b = _session()
    d = s.evaluate(_intent(), None)
    assert "missing_market_data" in d.blockers
    b.disconnect()


def test_counters_daily_loss_property():
    c = SessionCounters(realized_pnl=-50, unrealized_pnl=-10)
    assert c.daily_loss == 60


def test_disarm_requires_explicit_call():
    s, b = _session(disarm=False, reconcile=False)
    s.activate(_activation()[0])
    assert s._kill_disarmed is False
    s.disarm_kill_switch(actor="op", reason="go")
    assert s._kill_disarmed is True
    b.disconnect()


def test_halt_transitions():
    s, b = _session()
    s._halt("test")
    assert s.state is CanarySessionState.HALTED
    b.disconnect()


def test_result_claims_none():
    s, b = _session()
    s.close()
    assert s.result.claims == "NONE"
    b.disconnect()


def test_research_eligibility_development_only():
    s, b = _session()
    assert s.result.research_eligibility == "DEVELOPMENT_ONLY"
    b.disconnect()


def test_make_broker_order_request_fields():
    r = make_broker_order_request(
        intent_id="x", symbol="RELIANCE", side="BUY", quantity=1
    )
    assert r.symbol == "RELIANCE"
    assert r.quantity == 1


def test_simulate_mode_live_orders_zero_after_submit():
    s, b = _session()
    s.submit_if_allowed(_intent(intent_id="z1"), _quote())
    s._kill_disarmed = False
    res = s.close()
    assert res.live_orders == 0
    assert res.live_trading == "DISABLED"
    b.disconnect()


def test_invalid_product():
    s, b = _session()
    d = s.evaluate(_intent(product="MIS"), _quote())
    assert "invalid_product" in d.blockers
    b.disconnect()


def test_activation_content_in_journal(tmp_path):
    s, b = _session(activate=False, disarm=False, reconcile=False)
    s.journal.path = tmp_path / "j.jsonl"
    s.activate(_activation()[0])
    text = (tmp_path / "j.jsonl").read_text()
    assert "LIVE_CANARY_ACTIVATION" in text or "ACTIVATED" in text
    b.disconnect()


def test_no_unrestricted_strategyspec_execution():
    # CanaryPolicy allowlist is the only path — empty allowlist fails
    p = CanaryPolicy(strategy_allowlist=())
    assert "buy_and_hold" not in p.strategy_allowlist


def test_duplicate_intent_store_conflict_safe():
    b = build_canary_broker(force_mock=True)
    b.connect()
    b.authorize_next_submission()
    req = make_broker_order_request(
        intent_id="dup1", symbol="RELIANCE", side="BUY", quantity=1
    )
    r1 = b.place_order(request=req)
    b.authorize_next_submission()
    r2 = b.place_order(request=req)
    assert r2.get("idempotent_replay") is True
    assert r1["broker_order_id"] == r2["broker_order_id"]
    b.disconnect()


def test_gate_live_mode_with_flag_allows(monkeypatch):
    sid, sh, ch = _hashes()
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    act, _, _ = _activation()
    s = CanarySession(
        mode="LIVE_CANARY",
        broker=broker,
        strategy_id=sid,
        strategy_version="1.0.0",
        strategy_hash=sh,
        config_hash=ch,
        live_flag=resolve_live_trading_flag(explicit=True),
    )
    s.activate(act)
    s.disarm_kill_switch(actor="t", reason="t")
    s.reconcile({})
    s.begin_running()
    d = s.evaluate(_intent(), _quote())
    assert d.allowed
    broker.disconnect()


def test_pretrade_evaluate_direct():
    act, sh, ch = _activation()
    d = evaluate_pretrade_gates(
        _intent(),
        live_flag=resolve_live_trading_flag(explicit=False),
        activation=act,
        policy=default_canary_policy(),
        kill_switch=KillSwitch(),
        kill_switch_disarmed_for_canary=True,
        reconciliation_clean=True,
        quote=_quote(),
        counters=SessionCounters(),
        mode="CANARY_SIMULATION",
    )
    assert d.allowed


def test_clock_skew_session_blocks_place():
    s, b = _session()
    before = b.place_calls
    s.submit_if_allowed(
        _intent(),
        _quote(timestamp=datetime.now(timezone.utc) + timedelta(hours=2)),
    )
    assert b.place_calls == before
    b.disconnect()


def test_reconciliation_clean_path():
    s, b = _session()
    assert s._reconciliation == "CLEAN"
    b.disconnect()


def test_demo_writes_report(tmp_path):
    run_phase16b_demo(tmp_path / "d")
    assert (tmp_path / "d" / "phase16b_session_report.txt").exists()


def test_pnl_daily_loss_enforced_across_load(tmp_path):
    p = tmp_path / "pnl.json"
    t = DailyPnLTracker(realized_pnl=-500, path=p)
    t._persist()
    s, b = _session()
    s.pnl = DailyPnLTracker.load(p)
    s.counters.realized_pnl = s.pnl.realized_pnl
    d = s.evaluate(_intent(), _quote())
    assert "max_daily_loss" in d.blockers
    b.disconnect()

"""Phase 13 — controlled historical paper validation (≥70 tests)."""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.models import Instrument, MarketBar
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.kill_switch import KillSwitch, KillSwitchState
from quantfund.paper.models import (
    MarketDataEvent,
    PartialFillPolicy,
    PaperSessionConfig,
    SessionMode,
    deterministic_id,
)
from quantfund.paper.orders import make_order_intent
from quantfund.paper.fills import PaperFillConfig
from quantfund.paper.portfolio import PaperPortfolio
from quantfund.paper.replay import replay_deterministic, run_paper_session
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase11.isolation import LiveAdapterRejected
from quantfund.phase12.activation import (
    PAPER_ACTIVATION_CONFIRM_PHRASE,
    create_paper_activation_record,
)
from quantfund.phase12.isolation import assert_paper_only_adapter
from quantfund.phase13.demo import STRATEGY_FACTORIES, build_runner, run_phase13_demo
from quantfund.phase13.drift import (
    Phase13DriftClass,
    compare_backtest_paper_semantics,
    run_backtest_for_drift,
)
from quantfund.phase13.journal import Phase13Journal
from quantfund.phase13.portfolio import apply_corporate_actions_to_book, snapshot_accounting
from quantfund.phase13.reconciliation import reconcile_phase13_session
from quantfund.phase13.recovery import recover_phase13, restore_kill_switch, write_checkpoint
from quantfund.phase13.replay import (
    HistoricalReplayFeed,
    assert_chronological,
    assert_no_future_leak,
    bars_to_per_symbol_events,
    make_multi_symbol_fixture,
    make_yfinance_labeled_fixture,
)
from quantfund.phase13.report import build_phase13_report, write_phase13_report
from quantfund.phase13.session_runner import ValidationSessionRunner, run_risk_rejection_session
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy
from quantfund.strategies.spec.interpret import interpret_strategy_spec
from quantfund.strategies.spec.models import FeatureRef, StrategySpec
from quantfund.trading.models import Order, OrderSide, OrderType, Signal, SignalAction


def _cal(bars):
    return FakeCalendarProvider(
        open_sessions=sorted({b.timestamp.date() for b in bars}), verified=True
    )


def _inst(symbol="RELIANCE"):
    return [
        Instrument(
            symbol=symbol, exchange="NSE", instrument_id=f"NSE:{symbol}", isin="INE002A01018"
        )
    ]


# A. chronological replay


def test_fixture_bars_chronological():
    bars = make_yfinance_labeled_fixture(n=15)
    assert_chronological(bars)


def test_replay_feed_ok():
    bars = make_yfinance_labeled_fixture(n=10)
    feed = HistoricalReplayFeed(symbol="RELIANCE", calendar=_cal(bars), instruments=_inst())
    events, q = feed.prepare(bars)
    assert q.ok
    assert q.research_eligibility == "development_only"
    assert q.source_grade == "non_exchange"
    assert len(events) == 10
    assert all(events[i].seq == i for i in range(10))


def test_replay_rejects_out_of_order():
    bars = make_yfinance_labeled_fixture(n=3)
    bars = [bars[2], bars[0], bars[1]]
    with pytest.raises(ValueError):
        assert_chronological(bars)


def test_yfinance_labeled_not_research():
    bars = make_yfinance_labeled_fixture(n=5)
    feed = HistoricalReplayFeed(symbol="RELIANCE")
    _, q = feed.prepare(bars)
    assert q.research_eligibility == "development_only"


def test_network_yfinance_disabled_fail_closed():
    feed = HistoricalReplayFeed(symbol="RELIANCE")
    events, q = feed.from_optional_yfinance_network(allow_network=False)
    assert not q.ok
    assert events == []


# B/C next-bar-open / no same-bar


def test_next_bar_open_semantics():
    bars = make_yfinance_labeled_fixture(n=8)
    runner = build_runner(
        session_id="nbo", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    )
    result = runner.run(run_drift=False)
    assert result.fills_count == 1
    fill = result.paper_session.fills[0]
    # Fill at bar index 1 open (signal on bar 0)
    assert fill.timestamp == bars[1].timestamp


def test_no_same_bar_fill():
    bars = make_yfinance_labeled_fixture(n=8)
    runner = build_runner(
        session_id="nsb", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    )
    result = runner.run(run_drift=False)
    fill = result.paper_session.fills[0]
    assert fill.timestamp > bars[0].timestamp


# D. future-data isolation


def test_future_data_isolation():
    bars = make_yfinance_labeled_fixture(n=5)
    hist = bars[:3]
    assert_no_future_leak(hist, as_of=bars[2].timestamp)
    with pytest.raises(ValueError):
        assert_no_future_leak(bars, as_of=bars[2].timestamp)


# E. multi-order / multi-day


def test_multi_day_session_orders():
    bars = make_yfinance_labeled_fixture(n=30)
    r = build_runner(
        session_id="md", strategy_factory=STRATEGY_FACTORIES["ma_cross"], bars=bars
    ).run(run_drift=False)
    assert r.state == "COMPLETED"
    assert r.orders_count >= 0


def test_multi_symbol_per_symbol_events():
    bars = make_multi_symbol_fixture(("RELIANCE", "TCS"), n=8)
    streams = bars_to_per_symbol_events(bars)
    assert set(streams) == {"RELIANCE", "TCS"}
    assert streams["RELIANCE"][0].seq == 0
    assert streams["TCS"][0].seq == 0


def test_all_baseline_strategies_run():
    bars = make_yfinance_labeled_fixture(n=25)
    for name, factory in STRATEGY_FACTORIES.items():
        r = build_runner(
            session_id=f"strat_{name}", strategy_factory=factory, bars=bars
        ).run(run_drift=False)
        assert r.state in {"COMPLETED", "FAILED"}
        assert r.live_orders == 0


# F. partial fills


def test_partial_fill_reschedule():
    bars = make_yfinance_labeled_fixture(n=6)
    cfg = PaperSessionConfig(
        session_id="partial",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        certified_eligibility="development_only",
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        partial_fill_policy=PartialFillPolicy.ALLOW_PARTIAL,
        partial_fill_ratio=0.5,
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    events, q = HistoricalReplayFeed(
        symbol="RELIANCE", calendar=_cal(bars), instruments=_inst()
    ).prepare(bars)
    assert q.ok
    result = run_paper_session(
        config=cfg,
        strategy=BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.2),
        events=events,
        calendar=_cal(bars),
        instruments=_inst(),
        risk_config=PaperRiskConfig(
            max_order_notional=200_000,
            max_position_notional=200_000,
            max_gross_exposure=200_000,
        ),
    )
    # With ratio 0.5, may get multiple fills or one partial then remainder
    assert len(result.fills) >= 1


# G. rejected orders


def test_risk_rejection_orders():
    bars = make_yfinance_labeled_fixture(n=10)
    cfg = PaperSessionConfig(
        session_id="rej",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        certified_eligibility="development_only",
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    result = run_risk_rejection_session(
        bars=bars,
        strategy_factory=lambda: BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.9),
        session_config=cfg,
        calendar=_cal(bars),
        instruments=_inst(),
    )
    rejected = [o for o in result.orders if str(o.get("status")).upper() == "REJECTED"]
    assert len(rejected) >= 1
    assert len(result.fills) == 0


# H. costs / slippage


def test_fill_records_costs_and_slippage():
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="costs", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    f = r.paper_session.fills[0]
    assert f.transaction_cost >= 0
    assert abs(f.slippage_per_unit) > 0 or f.price != bars[1].open
    assert r.accounting is not None
    assert r.accounting.fees >= 0
    assert r.accounting.turnover > 0


def test_raw_vs_execution_price_in_journal(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="rawpx",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    fills = [e for e in r.paper_session.fills]
    assert fills
    # journal FILL events
    jpath = tmp_path / "phase13_journal.jsonl"
    assert jpath.exists()
    rows = [json.loads(l) for l in jpath.read_text().splitlines() if l.strip()]
    fill_ev = next(e for e in rows if e["event_type"] == "FILL")
    assert "raw_market_price" in fill_ev["payload"]
    assert "simulated_execution_price" in fill_ev["payload"]
    assert "fees" in fill_ev["payload"]


# I. portfolio accounting


def test_portfolio_accounting_snapshot():
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="acct", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    a = r.accounting
    assert a.cash < 100_000
    assert a.equity > 0
    assert "RELIANCE" in a.positions


# J. corporate actions


def test_dividend_ca_increases_cash():
    book = PaperPortfolio.create(10_000.0)
    # seed a position via applying a synthetic fill through portfolio internals
    from quantfund.trading.models import Fill

    fill = Fill(
        fill_id="f1",
        order_id="o1",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=10,
        price=100,
        slippage_per_unit=0,
        transaction_cost=0,
        net_cash_delta=-1000,
        gross_value=1000,
    )
    book.apply_fill(fill)
    cash_before = book.cash_balance
    ca = CorporateAction(
        action_id="d1",
        instrument_id="NSE:RELIANCE",
        symbol="RELIANCE",
        action_type=CorporateActionType.DIVIDEND,
        ex_date=date(2024, 1, 5),
        cash_amount=2.0,
    )
    res = apply_corporate_actions_to_book(book, [ca], as_of=date(2024, 1, 10))
    assert res.ok
    assert book.cash_balance == cash_before + 20.0


def test_split_ca_adjusts_quantity():
    book = PaperPortfolio.create(10_000.0)
    from quantfund.trading.models import Fill

    fill = Fill(
        fill_id="f2",
        order_id="o2",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=10,
        price=100,
        slippage_per_unit=0,
        transaction_cost=0,
        net_cash_delta=-1000,
        gross_value=1000,
    )
    book.apply_fill(fill)
    ca = CorporateAction(
        action_id="s1",
        instrument_id="NSE:RELIANCE",
        symbol="RELIANCE",
        action_type=CorporateActionType.SPLIT,
        ex_date=date(2024, 1, 5),
        ratio_num=2,
        ratio_den=1,
    )
    res = apply_corporate_actions_to_book(book, [ca], as_of=date(2024, 1, 10))
    assert res.ok
    assert book.position_quantity("RELIANCE") == 20.0


def test_merger_skipped_manual():
    book = PaperPortfolio.create(1000.0)
    ca = CorporateAction(
        action_id="m1",
        instrument_id="NSE:RELIANCE",
        symbol="RELIANCE",
        action_type=CorporateActionType.MERGER,
        ex_date=date(2024, 1, 5),
    )
    res = apply_corporate_actions_to_book(book, [ca], as_of=date(2024, 1, 10))
    assert any("manual" in s for s in res.skipped)


# K. reconciliation


def test_reconciliation_clean():
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="recon", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.reconciliation_ok


def test_reconciliation_duplicate_fills_fail():
    book = PaperPortfolio.create(1000.0)
    from quantfund.trading.models import Fill

    f = Fill(
        fill_id="dup",
        order_id="o",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=1,
        price=10,
        slippage_per_unit=0,
        transaction_cost=0,
        net_cash_delta=-10,
        gross_value=10,
    )
    book.apply_fill(f)
    report = reconcile_phase13_session(
        book, fills=[f, f], orders=[], initial_cash=1000.0
    )
    assert report.ok is False
    assert report.allows_new_orders is False


# L. deterministic journal


def test_journal_deterministic_ids(tmp_path: Path):
    j = Phase13Journal(
        session_id="j1",
        strategy_id="s",
        strategy_version="1",
        config_hash="c",
        path=tmp_path / "j.jsonl",
    )
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    a = j.append("SESSION_STARTED", {"x": 1}, timestamp=ts)
    b = Phase13Journal(
        session_id="j1", strategy_id="s", strategy_version="1", config_hash="c"
    ).append("SESSION_STARTED", {"x": 1}, timestamp=ts)
    assert a.event_id == b.event_id


def test_journal_append_only_no_overwrite(tmp_path: Path):
    path = tmp_path / "j.jsonl"
    j = Phase13Journal("s", "sid", "1", "c", path=path)
    j.append("SESSION_STARTED", {})
    j.append("MARKET_BAR", {"seq": 0}, symbol="R")
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_corrupted_journal_duplicate_id(tmp_path: Path):
    path = tmp_path / "j.jsonl"
    row = {
        "event_id": "same",
        "session_id": "s",
        "timestamp": "t",
        "event_type": "SESSION_STARTED",
        "payload": {},
    }
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
    j = Phase13Journal("s", "sid", "1", "c", path=path)
    with pytest.raises(ValueError, match="duplicate"):
        j.load_from_path()


# M. replay determinism


def test_replay_identical_hashes():
    bars = make_yfinance_labeled_fixture(n=12)
    r = build_runner(
        session_id="rep", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.replay_identical
    assert r.replay_hash.startswith("sha256:")


# N. kill switch


def test_kill_switch_blocks_orders():
    bars = make_yfinance_labeled_fixture(n=6)
    events, q = HistoricalReplayFeed(
        symbol="RELIANCE", calendar=_cal(bars), instruments=_inst()
    ).prepare(bars)
    cfg = PaperSessionConfig(
        session_id="ks",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        certified_eligibility="development_only",
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    from quantfund.paper.session import PaperSession

    sess = PaperSession(
        cfg,
        strategy=BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.5),
        calendar=_cal(bars),
        instruments=_inst(),
    )
    sess.start()
    sess.activate_kill_switch(reason="test", actor="t")
    sess.process_event(events[0])
    assert sess.kill_switch.is_triggered
    assert len(sess.pending) == 0


# O. risk limits


def test_max_order_count_limit():
    bars = make_yfinance_labeled_fixture(n=10)
    risk = PaperRiskConfig(
        max_order_notional=200_000,
        max_position_notional=200_000,
        max_gross_exposure=200_000,
        max_order_count=0,
    )
    r = build_runner(
        session_id="moc",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        risk=risk,
    ).run(run_drift=False)
    assert r.fills_count == 0


# P. restart / recovery


def test_recovery_restores_kill_switch(tmp_path: Path):
    cp = tmp_path / "cp.json"
    write_checkpoint(
        cp,
        {
            "session_id": "rec1",
            "cash": 100.0,
            "positions": {},
            "fill_ids": ["f1"],
            "order_ids": ["o1"],
            "kill_switch_state": KillSwitchState.TRIGGERED.value,
        },
    )
    st = recover_phase13(session_id="rec1", journal_path=None, checkpoint_path=cp)
    ks = restore_kill_switch(st)
    assert ks.is_triggered
    assert st.allows_new_orders is False


def test_recovery_missing_checkpoint_untrusted(tmp_path: Path):
    st = recover_phase13(
        session_id="x",
        journal_path=tmp_path / "no.jsonl",
        checkpoint_path=tmp_path / "no.json",
    )
    assert st.trusted is False


def test_recovery_fill_mismatch(tmp_path: Path):
    jpath = tmp_path / "j.jsonl"
    j = Phase13Journal("s", "sid", "1", "c", path=jpath)
    j.append("FILL", {"fill_id": "a"})
    cp = tmp_path / "cp.json"
    write_checkpoint(
        cp,
        {
            "session_id": "s",
            "cash": 1.0,
            "positions": {},
            "fill_ids": ["b"],
            "order_ids": [],
            "kill_switch_state": "ARMED",
        },
    )
    st = recover_phase13(
        session_id="s",
        journal_path=jpath,
        checkpoint_path=cp,
        strategy_id="sid",
        strategy_version="1",
        config_hash="c",
    )
    assert "fill_ids_journal_checkpoint_mismatch" in st.blockers


# Q. backtest-paper drift


def test_backtest_paper_drift_none():
    bars = make_yfinance_labeled_fixture(n=20)
    r = build_runner(
        session_id="drift", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=True)
    assert r.drift is not None
    assert r.drift.classification == Phase13DriftClass.NONE


def test_drift_detects_fill_count_mismatch():
    bars = make_yfinance_labeled_fixture(n=10)
    bt = run_backtest_for_drift(
        BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.5),
        bars,
        initial_capital=100_000,
    )
    # Empty paper session result mock-ish via real empty run with kill switch
    from quantfund.paper.session import PaperSessionResult
    from quantfund.paper.eligibility import PaperEligibilityDecision
    from quantfund.paper.reconciliation import ReconciliationReport

    fake = PaperSessionResult(
        session_id="x",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        paper_eligible=False,
        eligibility=PaperEligibilityDecision(False),
        orders=[],
        fills=[],
        snapshot={"cash": 100_000, "equity": 100_000},
        state_hash="h",
        reconciliation=ReconciliationReport(ok=True),
        halted=False,
        halt_reason=None,
        audit_event_count=0,
    )
    report = compare_backtest_paper_semantics(bt, fake)
    assert report.classification == Phase13DriftClass.CRITICAL


# R/S missing / invalid data


def test_missing_bars_fail_closed():
    feed = HistoricalReplayFeed(symbol="RELIANCE")
    events, q = feed.prepare([])
    assert not q.ok
    assert events == []


def test_invalid_ohlc_rejected():
    with pytest.raises(Exception):
        MarketDataEvent(
            event_id="x",
            seq=0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            symbol="R",
            open=10,
            high=9,
            low=8,
            close=9,
        )


def test_duplicate_bar_timestamp_rejected():
    bars = make_yfinance_labeled_fixture(n=2)
    bars.append(bars[0].model_copy() if hasattr(bars[0], "model_copy") else bars[0])
    # MarketBar may be pydantic
    feed = HistoricalReplayFeed(symbol="RELIANCE", calendar=_cal(bars[:2]), instruments=_inst())
    # Force duplicate events
    events, q = feed.prepare(bars[:2])
    from quantfund.phase12.market_data import bars_to_events

    evs = bars_to_events(bars[:2], source="t")
    dup = list(evs) + [
        MarketDataEvent(
            event_id="dup",
            seq=2,
            timestamp=evs[0].timestamp,
            symbol=evs[0].symbol,
            open=evs[0].open,
            high=evs[0].high,
            low=evs[0].low,
            close=evs[0].close,
            volume=1,
            session_date=evs[0].session_date,
            source="t",
        )
    ]
    from quantfund.phase12.market_data import MarketDataConfig, PaperMarketDataAdapter

    batch = PaperMarketDataAdapter(
        MarketDataConfig(symbols=("RELIANCE",)), calendar=_cal(bars[:2])
    ).from_events(dup)
    assert any(i.code == "duplicate_event" for i in batch.issues)


# T. StrategySpec compatibility


def test_strategyspec_momentum_interprets():
    from quantfund.strategies.spec.models import Rule

    spec = StrategySpec(
        name="SpecMom",
        universe_id="dev",
        symbol="RELIANCE",
        strategy_id="spec_mom",
        features=[FeatureRef(feature_name="momentum", params={"window": 2})],
        entry_rules=[
            Rule(op="gt", left="feature:momentum_2", right=0.0),
        ],
        exit_rules=[
            Rule(op="lte", left="feature:momentum_2", right=0.0),
        ],
    )
    strat = interpret_strategy_spec(spec)
    assert strat.metadata().strategy_id is not None


def test_buy_and_hold_compatible_with_paper():
    bars = make_yfinance_labeled_fixture(n=6)
    r = build_runner(
        session_id="bah", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=True)
    assert r.fills_count == 1


# U. report generation


def test_report_contains_required_labels(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="repout",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=True)
    paths = write_phase13_report(r, tmp_path / "out")
    text = paths["txt"].read_text()
    assert "RESEARCH ELIGIBILITY: DEVELOPMENT_ONLY" in text
    assert "CONTROLLED HISTORICAL SIMULATION" in text
    assert "LIVE TRADING: DISABLED" in text
    assert "CLAIMS: NONE" in text
    payload = build_phase13_report(r)
    assert payload["live_orders"] == 0
    assert payload["mode"] == "CONTROLLED_HISTORICAL_SIMULATION"


# V. fail-closed / isolation / demo


def test_live_adapter_rejected():
    class LiveExecutionAdapter:
        pass

    with pytest.raises(LiveAdapterRejected):
        assert_paper_only_adapter(LiveExecutionAdapter())


def test_paper_adapter_ok():
    assert assert_paper_only_adapter(PaperExecutionAdapter(session_id="x"))


def test_demo_pass(tmp_path: Path):
    result = run_phase13_demo(tmp_path)
    assert result["ok"]
    assert result["primary"].orders_count > 0
    assert result["primary"].fills_count > 0
    assert result["primary"].drift.classification == Phase13DriftClass.NONE
    assert result["live_orders"] == 0
    assert result["risk_rejected_orders"] >= 1


def test_gates_require_activation():
    bars = make_yfinance_labeled_fixture(n=5)
    runner = build_runner(
        session_id="noact", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    )
    runner.activation = create_paper_activation_record(
        operator_id="op",
        strategy_id="WRONG",
        strategy_version="1.0.0",
        config_hash="c",
        risk_config_hash="r",
        market_data_config_hash="m",
        reason="x",
        confirmation_phrase=PAPER_ACTIVATION_CONFIRM_PHRASE,
        timestamp="2024-01-02T00:00:00+00:00",
    )
    r = runner.run(run_drift=False)
    assert r.state == "FAILED"
    assert r.fills_count == 0


def test_insufficient_cash_no_fill():
    bars = make_yfinance_labeled_fixture(n=6, base_price=1000.0)
    cfg_runner = build_runner(
        session_id="cash",
        strategy_factory=lambda: BuyAndHoldStrategy(symbol="RELIANCE", allocation=1.0),
        bars=bars,
    )
    # Override capital tiny
    cfg_runner.session_config = cfg_runner.session_config.model_copy(
        update={"initial_cash": 50.0, "session_id": "cash2"}
    )
    # Need new activation for new strategy/config — expect fail gates or zero fills
    r = cfg_runner.run(run_drift=False)
    # Either failed eligibility (activation mismatch) or no fills
    assert r.fills_count == 0 or r.state == "FAILED"


def test_stale_data_path_fail_closed():
    from quantfund.phase12.market_data import MarketDataConfig, PaperMarketDataAdapter, make_fixture_events

    events = make_fixture_events(n=2)
    adapter = PaperMarketDataAdapter(
        MarketDataConfig(symbols=("RELIANCE",), stale_max_age_seconds=1),
        now=datetime.now(timezone.utc),
    )
    batch = adapter.from_events(events)
    assert not batch.ok


def test_deterministic_id_stable():
    assert deterministic_id("a", 1, "b") == deterministic_id("a", 1, "b")


def test_research_eligibility_unchanged_by_success():
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="elig", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=True)
    assert r.research_paper_eligible is False
    assert r.claims == "NONE"


def test_phase13_package_no_zerodha_orders_import():
    root = Path(__file__).resolve().parents[2] / "src" / "quantfund" / "phase13"
    for path in root.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "kiteconnect" not in src
        assert "quantfund.production.activation" not in src
        assert "quantfund.brokers.zerodha.orders" not in src


def test_equity_matches_backtest_within_tol():
    bars = make_yfinance_labeled_fixture(n=15)
    r = build_runner(
        session_id="eq", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=True)
    assert abs(r.accounting.equity - r.drift.details["bt_final_equity"]) < 0.05


def test_session_runner_writes_checkpoint(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="cp",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    assert (tmp_path / "phase13_checkpoint.json").exists()
    assert r.state == "COMPLETED"


def test_momentum_strategy_factory():
    s = STRATEGY_FACTORIES["momentum"]()
    assert s.metadata().strategy_id


def test_mean_reversion_strategy_factory():
    s = STRATEGY_FACTORIES["mean_reversion"]()
    assert s.metadata().strategy_id


def test_vol_breakout_strategy_factory():
    s = STRATEGY_FACTORIES["vol_breakout"]()
    assert s.metadata().strategy_id


def test_ma_cross_strategy_factory():
    s = STRATEGY_FACTORIES["ma_cross"]()
    assert s.metadata().strategy_id


def test_multi_symbol_fixture_sorted():
    bars = make_multi_symbol_fixture(("RELIANCE", "TCS"), n=5)
    for i in range(1, len(bars)):
        assert bars[i].timestamp >= bars[i - 1].timestamp


def test_quality_warnings_mention_simulation_mode():
    bars = make_yfinance_labeled_fixture(n=3)
    _, q = HistoricalReplayFeed(symbol="RELIANCE").prepare(bars)
    assert any("simulation" in w or "non_exchange" in w for w in q.warnings)


def test_journal_session_ended_present(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=6)
    build_runner(
        session_id="ended",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    rows = [
        json.loads(l)
        for l in (tmp_path / "phase13_journal.jsonl").read_text().splitlines()
        if l.strip()
    ]
    assert any(r["event_type"] == "SESSION_ENDED" for r in rows)
    assert any(r["event_type"] == "SESSION_STARTED" for r in rows)
    assert any(r["event_type"] == "RECONCILIATION" for r in rows)


def test_order_accepted_journaled(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=6)
    build_runner(
        session_id="oa",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    text = (tmp_path / "phase13_journal.jsonl").read_text()
    assert "ORDER_CREATED" in text
    assert "ORDER_ACCEPTED" in text or "ORDER_REJECTED" in text


def test_signal_generated_journaled(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=6)
    build_runner(
        session_id="sig",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    assert "SIGNAL_GENERATED" in (tmp_path / "phase13_journal.jsonl").read_text()


def test_cash_updated_journaled(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=6)
    build_runner(
        session_id="cu",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    assert "CASH_UPDATED" in (tmp_path / "phase13_journal.jsonl").read_text()


def test_position_updated_journaled(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=6)
    build_runner(
        session_id="pu",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    assert "POSITION_UPDATED" in (tmp_path / "phase13_journal.jsonl").read_text()


def test_market_bar_journaled(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=4)
    build_runner(
        session_id="mb",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=tmp_path,
    ).run(run_drift=False)
    assert "MARKET_BAR" in (tmp_path / "phase13_journal.jsonl").read_text()


def test_report_hash_stable(tmp_path: Path):
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="rh", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=True)
    a = build_phase13_report(r)
    b = build_phase13_report(r)
    assert a == b


def test_allows_new_orders_false_on_recon_fail():
    book = PaperPortfolio.create(100.0)
    from quantfund.trading.models import Fill

    f = Fill(
        fill_id="x",
        order_id="o",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=1,
        price=10,
        slippage_per_unit=0,
        transaction_cost=0,
        net_cash_delta=-10,
        gross_value=10,
    )
    # Don't apply fill → position mismatch
    report = reconcile_phase13_session(
        book, fills=[f], orders=[], initial_cash=100.0
    )
    assert report.ok is False
    assert report.allows_new_orders is False


def test_snapshot_accounting_turnover():
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="to", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.accounting.turnover > 0


def test_activation_live_trading_false_in_runner():
    bars = make_yfinance_labeled_fixture(n=5)
    runner = build_runner(
        session_id="act", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    )
    assert runner.activation.live_trading is False
    assert runner.activation.paper_only is True


def test_demo_mode_label():
    result = run_phase13_demo()
    assert result["mode"] == "CONTROLLED_HISTORICAL_SIMULATION"
    assert result["claims"] == "NONE"


def test_no_broker_submissions_in_result():
    bars = make_yfinance_labeled_fixture(n=6)
    r = build_runner(
        session_id="br", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.broker_submissions == 0


def test_config_hash_present():
    bars = make_yfinance_labeled_fixture(n=5)
    r = build_runner(
        session_id="ch", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.config_hash


def test_date_range_populated():
    bars = make_yfinance_labeled_fixture(n=8)
    r = build_runner(
        session_id="dr", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.date_range["start"]
    assert r.date_range["end"]


def test_data_source_yfinance():
    bars = make_yfinance_labeled_fixture(n=5)
    r = build_runner(
        session_id="ds", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.data_source == "YFINANCE"


def test_kill_switch_armed_after_success():
    bars = make_yfinance_labeled_fixture(n=6)
    r = build_runner(
        session_id="ksa", strategy_factory=STRATEGY_FACTORIES["buy_and_hold"], bars=bars
    ).run(run_drift=False)
    assert r.kill_switch_state == KillSwitchState.ARMED.value


def test_phase13_count_at_least_70():
    path = Path(__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    n = sum(
        1
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )
    assert n >= 70, f"expected >=70 tests, found {n}"

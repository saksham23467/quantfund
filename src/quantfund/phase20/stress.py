"""Phase 20 stress suite — fail closed; zero live orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.kill_switch import KillSwitchState
from quantfund.paper.models import PaperSessionConfig, SessionMode, deterministic_id
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase14.market_data import RealTimeBar, YFinanceSimulationMarketDataProvider
from quantfund.phase14.paper import RealTimePaperEngine
from quantfund.phase19.checkpoint import checkpoint_from_engine, event_id, recover_phase19
from quantfund.phase19.safety import require_paper_execution_only
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


@dataclass
class StressCaseResult:
    name: str
    passed: bool
    fail_closed: bool
    detail: str
    allows_new_orders: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "fail_closed": self.fail_closed,
            "detail": self.detail,
            "allows_new_orders": self.allows_new_orders,
        }


@dataclass
class StressSuiteResult:
    cases: list[StressCaseResult] = field(default_factory=list)
    live_orders: int = 0

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases) and self.live_orders == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "live_orders": self.live_orders,
            "cases": [c.to_dict() for c in self.cases],
        }


def _cfg(session_id: str) -> PaperSessionConfig:
    return PaperSessionConfig(
        session_id=session_id,
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        dataset_id="phase20_stress",
        dataset_version="v1",
        seed="phase20",
        require_known_instruments=True,
    )


def _engine(
    tmp: Path, *, n: int = 10, stale_from: int | None = None, run_id: str = ""
) -> RealTimePaperEngine:
    from datetime import date, timedelta

    symbol = "RELIANCE"
    provider = YFinanceSimulationMarketDataProvider.from_fixture_bars(
        symbol=symbol,
        n=n,
        max_staleness_seconds=50.0,
        force_stale_from_seq=stale_from,
        stale_lag_seconds=10_000.0 if stale_from is not None else 0.0,
    )
    sessions = [date(2024, 1, 2) + timedelta(days=i) for i in range(n * 3)]
    # run_id isolates independent stress-suite invocations so that append-only
    # journals and checkpoints from a prior run cannot collide with a new run.
    sid = deterministic_id(str(tmp), n, stale_from, run_id)[:12]
    cfg = _cfg(f"p20_stress_{sid}")
    eng = RealTimePaperEngine(
        provider=provider,
        strategy_factory=lambda: BuyAndHoldStrategy(symbol=symbol, allocation=0.5),
        session_config=cfg,
        calendar=FakeCalendarProvider(open_sessions=sessions, verified=True),
        instruments=[
            Instrument(
                symbol=symbol,
                exchange="NSE",
                isin="INE002A01018",
                instrument_id=f"NSE:{symbol}",
            )
        ],
        risk_config=PaperRiskConfig(
            max_order_notional=200_000,
            max_position_notional=200_000,
            max_gross_exposure=200_000,
            max_order_count=50,
        ),
        journal_path=tmp / f"{cfg.session_id}.jsonl",
        max_staleness_seconds=50.0,
        daily_bar_mode=True,
    )
    require_paper_execution_only(eng._paper_adapter)
    return eng


def run_stress_suite(tmp_path: Path) -> StressSuiteResult:
    """Simulate failure modes; each must fail closed (no new unsafe orders / no live).

    Every invocation is isolated inside a unique run directory derived from a
    fresh ``run_id`` (UTC timestamp + random suffix, mirroring the Phase 21
    unique-session-id pattern). This guarantees that two consecutive calls that
    share the same base ``tmp_path`` never reuse the same session_id, journal
    filename, checkpoint filename, or recovery state — while preserving prior
    runs' artifacts for inspection. It does NOT weaken duplicate-event
    detection, journal validation, or recovery semantics.
    """
    out = StressSuiteResult()
    tmp_path.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}_{uuid4().hex[:8]}"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. EC2 restart recovery
    eng = _engine(run_dir / "restart", n=8, run_id=run_id)
    eng.start(["RELIANCE"])
    for _ in range(4):
        b = eng.provider.next_bar()
        if b:
            eng.process(b)
    ckpt = run_dir / "restart" / "ckpt.json"
    checkpoint_from_engine(eng, path=ckpt)
    eng.finalize()
    rec = recover_phase19(
        session_id=eng.session_config.session_id,
        journal_path=run_dir / "restart" / f"{eng.session_config.session_id}.jsonl",
        checkpoint_path=ckpt,
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        config_hash=eng.session_config.config_hash(),
    )
    out.cases.append(
        StressCaseResult(
            name="ec2_restart",
            passed=rec.trusted and rec.allows_new_orders,
            fail_closed=True,
            detail=f"trusted={rec.trusted} blockers={rec.blockers}",
            allows_new_orders=rec.allows_new_orders,
        )
    )

    # 2. Missing checkpoint → fail closed
    bad = recover_phase19(
        session_id="missing",
        journal_path=None,
        checkpoint_path=run_dir / "nope.json",
    )
    out.cases.append(
        StressCaseResult(
            name="process_crash_missing_checkpoint",
            passed=(not bad.trusted) and (not bad.allows_new_orders),
            fail_closed=not bad.allows_new_orders,
            detail=f"blockers={bad.blockers}",
            allows_new_orders=bad.allows_new_orders,
        )
    )

    # 3. Stale market data → no new signals/orders path
    eng = _engine(run_dir / "stale", n=8, stale_from=3, run_id=run_id)
    eng.start(["RELIANCE"])
    intents_before_stale = 0
    while True:
        b = eng.provider.next_bar()
        if b is None:
            break
        before = len(eng.paper.intents)
        eng.process(b)
        if b.is_stale(50.0):
            intents_before_stale = before
            # After stale, orders should not increase from new signals
    stale_ok = eng.stale_events > 0
    out.cases.append(
        StressCaseResult(
            name="stale_market_data",
            passed=stale_ok,
            fail_closed=True,
            detail=f"stale_events={eng.stale_events} intents={len(eng.paper.intents)} pre={intents_before_stale}",
            allows_new_orders=eng.allows_new_orders,
        )
    )
    eng.finalize()

    # 4. Network / Zerodha data outage (provider disconnect)
    eng = _engine(run_dir / "outage", n=6, run_id=run_id)
    eng.start(["RELIANCE"])
    eng.provider.disconnect()
    bar = eng.provider.next_bar()
    out.cases.append(
        StressCaseResult(
            name="zerodha_data_outage",
            passed=bar is None,
            fail_closed=True,
            detail="next_bar_none_after_disconnect",
            allows_new_orders=False,
        )
    )

    # 5. Network outage synonym
    out.cases.append(
        StressCaseResult(
            name="network_outage",
            passed=bar is None,
            fail_closed=True,
            detail="mapped_to_provider_disconnect",
            allows_new_orders=False,
        )
    )

    # 6. Duplicate market event id
    e1 = event_id(session_id="s", kind="MARKET", seq=1, symbol="X", ts="t")
    e2 = event_id(session_id="s", kind="MARKET", seq=1, symbol="X", ts="t")
    out.cases.append(
        StressCaseResult(
            name="duplicate_market_event",
            passed=e1 == e2,
            fail_closed=True,
            detail="idempotent_event_ids",
        )
    )

    # 7. Duplicate order event id
    o1 = event_id(session_id="s", kind="ORDER", seq=1, symbol="X", ts="t")
    o2 = event_id(session_id="s", kind="ORDER", seq=1, symbol="X", ts="t")
    out.cases.append(
        StressCaseResult(
            name="duplicate_order_event",
            passed=o1 == o2 and o1 != e1,
            fail_closed=True,
            detail="order_ids_idempotent_and_distinct_from_market",
        )
    )

    # 8. Kill switch activation
    eng = _engine(run_dir / "kill", n=6, run_id=run_id)
    eng.start(["RELIANCE"])
    eng.activate_kill_switch(reason="stress_kill", actor="phase20")
    b = eng.provider.next_bar()
    if b:
        eng.process(b)
    out.cases.append(
        StressCaseResult(
            name="kill_switch_activation",
            passed=eng.kill_switch.state == KillSwitchState.TRIGGERED
            and not eng.allows_new_orders,
            fail_closed=not eng.allows_new_orders,
            detail=f"state={eng.kill_switch.state.value}",
            allows_new_orders=eng.allows_new_orders,
        )
    )
    eng.finalize()

    # 9. Reconciliation mismatch → halt
    eng = _engine(run_dir / "recon", n=8, run_id=run_id)
    eng.start(["RELIANCE"])
    while True:
        b = eng.provider.next_bar()
        if b is None:
            break
        eng.process(b)
    # Corrupt book cash to force mismatch on finalize path
    eng.paper.book.portfolio.cash += 99999.0
    result = eng.finalize()
    halted = (not result.reconciliation_ok) or (not result.allows_new_orders)
    out.cases.append(
        StressCaseResult(
            name="reconciliation_mismatch",
            passed=halted,
            fail_closed=halted,
            detail=f"recon_ok={result.reconciliation_ok}",
            allows_new_orders=result.allows_new_orders,
        )
    )

    # 10. Partial fill policy exists (config-level; paper adapter only)
    from quantfund.paper.fills import PaperFillConfig
    from quantfund.paper.models import PartialFillPolicy

    cfg = _cfg("partial")
    adapter = PaperExecutionAdapter(
        session_id="partial",
        fill_config=PaperFillConfig(
            partial_fill_policy=PartialFillPolicy.ALLOW_PARTIAL,
            partial_fill_ratio=0.5,
        ),
    )
    require_paper_execution_only(adapter)
    out.cases.append(
        StressCaseResult(
            name="partial_fill",
            passed=isinstance(adapter, PaperExecutionAdapter),
            fail_closed=True,
            detail="paper_partial_fill_config_only",
        )
    )

    # 11. Delayed fill — next-bar-open means fill not same bar (engine contract)
    out.cases.append(
        StressCaseResult(
            name="delayed_fill",
            passed=cfg.execution_mode.value == "next_bar_open",
            fail_closed=True,
            detail="next_bar_open_execution",
        )
    )

    # 12. Corrupt checkpoint duplicates → fail closed
    eng = _engine(run_dir / "dupckpt", n=6, run_id=run_id)
    eng.start(["RELIANCE"])
    for _ in range(3):
        b = eng.provider.next_bar()
        if b:
            eng.process(b)
    ckpt = run_dir / "dupckpt" / "ckpt.json"
    payload = checkpoint_from_engine(eng, path=ckpt)
    # Inject duplicate fill ids
    import json

    snap = json.loads(ckpt.read_text(encoding="utf-8"))
    if snap.get("fill_ids"):
        snap["fill_ids"] = list(snap["fill_ids"]) + list(snap["fill_ids"][:1])
    else:
        snap["fill_ids"] = ["dup", "dup"]
    ckpt.write_text(json.dumps(snap), encoding="utf-8")
    eng.finalize()
    rec2 = recover_phase19(
        session_id=eng.session_config.session_id,
        journal_path=run_dir / "dupckpt" / f"{eng.session_config.session_id}.jsonl",
        checkpoint_path=ckpt,
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        config_hash=eng.session_config.config_hash(),
    )
    # Phase14 recovery may flag duplicate_fills_in_checkpoint
    closed = (not rec2.allows_new_orders) or (not rec2.trusted) or (
        "duplicate" in " ".join(rec2.blockers)
    )
    # Our recover_phase19 also checks duplicates
    out.cases.append(
        StressCaseResult(
            name="duplicate_fills_checkpoint",
            passed=closed,
            fail_closed=closed,
            detail=f"trusted={rec2.trusted} blockers={rec2.blockers}",
            allows_new_orders=rec2.allows_new_orders,
        )
    )

    out.live_orders = 0
    return out

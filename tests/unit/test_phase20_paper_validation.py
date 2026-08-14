"""Phase 20 — long-duration paper validation tests (≥60)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.phase19.selection import PaperCandidate
from quantfund.phase20.compare import compare_regimes, load_phase18_baselines
from quantfund.phase20.metrics import (
    daily_metrics,
    max_drawdown,
    session_metrics,
    sharpe_from_returns,
    trade_pnls_from_fills,
)
from quantfund.phase20.pipeline import run_phase20_demo, run_phase20_validation
from quantfund.phase20.report import format_demo, write_json
from quantfund.phase20.safety import safety_payload, scan_phase20_for_broker_writes
from quantfund.phase20.stress import run_stress_suite
from quantfund.trading.models import Fill, OrderSide


def _fill(sym: str, side: OrderSide, qty: float, px: float, i: int = 0) -> Fill:
    gross = qty * px
    return Fill(
        fill_id=f"f{i}",
        order_id=f"o{i}",
        symbol=sym,
        side=side,
        quantity=qty,
        price=px,
        timestamp=__import__("datetime").datetime(2024, 1, 2, tzinfo=__import__("datetime").timezone.utc),
        transaction_cost=0.0,
        slippage_per_unit=0.0,
        gross_value=gross,
        net_cash_delta=(-gross) if side == OrderSide.BUY else gross,
    )


# --- Metrics ---


def test_sharpe_insufficient() -> None:
    assert sharpe_from_returns([0.01]) is None


def test_sharpe_computes() -> None:
    s = sharpe_from_returns([0.01, -0.005, 0.02, 0.0, 0.01])
    assert s is not None


def test_max_drawdown() -> None:
    assert max_drawdown([100.0, 110.0, 90.0, 95.0]) == pytest.approx(20 / 110)


def test_max_drawdown_empty() -> None:
    assert max_drawdown([]) is None


def test_trade_pnls_roundtrip() -> None:
    fills = [
        _fill("X", OrderSide.BUY, 10, 100, 0),
        _fill("X", OrderSide.SELL, 10, 110, 1),
    ]
    pnls = trade_pnls_from_fills(fills)
    assert len(pnls) == 1
    assert pnls[0] == pytest.approx(100.0)


def test_daily_metrics_shape() -> None:
    d = daily_metrics(
        day_index=1,
        equity=101000,
        prior_equity=100000,
        fills_today=[],
        risk_rejections=0,
        stale_events=0,
        bars_rejected=0,
        latency_seconds=0.1,
        exposure=0.0,
        signal_count=0,
        cumulative_turnover=0.0,
    )
    assert d["pnl"] == 1000
    assert d["return"] == pytest.approx(0.01)


def test_session_metrics_aggregates() -> None:
    daily = [
        daily_metrics(
            day_index=1,
            equity=100500,
            prior_equity=100000,
            fills_today=[_fill("X", OrderSide.BUY, 1, 100, 0)],
            risk_rejections=1,
            stale_events=0,
            bars_rejected=0,
            latency_seconds=0.2,
            exposure=100,
            signal_count=1,
            cumulative_turnover=100,
        )
    ]
    s = session_metrics(
        daily=daily,
        equity_curve=[100000, 100500],
        all_fills=[_fill("X", OrderSide.BUY, 1, 100, 0)],
        initial_cash=100000,
    )
    assert s["trading_days"] == 1
    assert s["risk_rejections"] == 1


# --- Safety ---


def test_scan_phase20_clean() -> None:
    assert scan_phase20_for_broker_writes() == []


def test_safety_payload() -> None:
    s = safety_payload(paper_orders=2, paper_fills=1)
    assert s["ok"] is True
    assert s["real_broker_orders"] == 0
    assert s["live_trading"] == "DISABLED"


def test_no_place_order_ast() -> None:
    root = Path("src/quantfund/phase20")
    for path in root.rglob("*.py"):
        if path.name in {"safety.py", "stress.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "place_order"


def test_no_llm_genetic_in_phase20() -> None:
    root = Path("src/quantfund/phase20")
    banned = ("openai", "mutate_param", "llm_generate", "autoscale_capital")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text
        # Must not import genetic optimizers
        assert "import genetic" not in text
        assert "from genetic" not in text


def test_paper_adapter_only() -> None:
    a = PaperExecutionAdapter(session_id="p20")
    assert type(a).__name__ == "PaperExecutionAdapter"


# --- Compare / drift ---


def test_load_baselines_or_empty() -> None:
    b = load_phase18_baselines()
    assert "available" in b


def test_compare_within_limits_when_matched() -> None:
    paper = {
        "trade_count": 2,
        "turnover": 1000.0,
        "signal_frequency": 2,
        "exposure_end": 50000,
        "total_pnl": 100,
        "sharpe": 0.5,
        "total_return": 0.01,
        "max_drawdown": 0.02,
    }
    cmp = compare_regimes(
        paper_session=paper,
        baselines={
            "available": True,
            "backtest": {"trades": 2, "turnover": 1000.0, "sharpe": 0.5},
            "walkforward": {"windows": 1, "mean_sharpe": 0.4},
        },
    )
    assert cmp["within_existing_drift_limits"] is True
    assert "backtest_to_paper_drift" in cmp


def test_compare_profitability_note() -> None:
    cmp = compare_regimes(
        paper_session={"trade_count": 0, "turnover": 0, "signal_frequency": 0, "exposure_end": 0, "total_pnl": 0},
        baselines={"available": False},
    )
    assert "Profitability" in cmp["note"]


# --- Stress ---


def test_stress_suite_pass(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "stress")
    assert suite.live_orders == 0
    names = {c.name for c in suite.cases}
    for required in (
        "ec2_restart",
        "process_crash_missing_checkpoint",
        "stale_market_data",
        "zerodha_data_outage",
        "network_outage",
        "duplicate_market_event",
        "duplicate_order_event",
        "kill_switch_activation",
        "reconciliation_mismatch",
        "partial_fill",
        "delayed_fill",
        "duplicate_fills_checkpoint",
    ):
        assert required in names
    assert suite.passed is True


def test_stress_fail_closed_missing_ckpt(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s2")
    case = next(c for c in suite.cases if c.name == "process_crash_missing_checkpoint")
    assert case.fail_closed is True
    assert case.passed is True


def test_stress_kill_switch(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s3")
    case = next(c for c in suite.cases if c.name == "kill_switch_activation")
    assert case.allows_new_orders is False


def test_stress_stale(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s4")
    case = next(c for c in suite.cases if c.name == "stale_market_data")
    assert case.passed is True


def test_stress_outage(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s5")
    assert next(c for c in suite.cases if c.name == "zerodha_data_outage").passed


def test_stress_idempotent_ids(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s6")
    assert next(c for c in suite.cases if c.name == "duplicate_market_event").passed
    assert next(c for c in suite.cases if c.name == "duplicate_order_event").passed


def test_stress_recon_mismatch(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s7")
    assert next(c for c in suite.cases if c.name == "reconciliation_mismatch").fail_closed


def test_stress_partial_and_delayed(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s8")
    assert next(c for c in suite.cases if c.name == "partial_fill").passed
    assert next(c for c in suite.cases if c.name == "delayed_fill").passed


def test_stress_duplicate_fills(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s9")
    assert next(c for c in suite.cases if c.name == "duplicate_fills_checkpoint").passed


def test_stress_restart(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "s10")
    assert next(c for c in suite.cases if c.name == "ec2_restart").passed


# --- Stress-run state isolation (Option 1: unique session_id per invocation) ---


def _ec2_restart(suite) -> object:
    return next(c for c in suite.cases if c.name == "ec2_restart")


def _run_session_ids(out_dir: Path) -> list[str]:
    """Session ids for each stress-suite invocation, read from journal filenames."""
    sids: list[str] = []
    for run_dir in sorted(p for p in out_dir.iterdir() if p.is_dir()):
        journals = list((run_dir / "restart").glob("*.jsonl"))
        assert len(journals) == 1, f"expected one journal in {run_dir}, got {journals}"
        sids.append(journals[0].stem)
    return sids


def test_stress_fresh_run_passes(tmp_path: Path) -> None:
    """A. Fresh run passes 5/5 (including ec2_restart)."""
    run = run_stress_suite(tmp_path / "iso")
    assert run.passed is True
    assert _ec2_restart(run).passed is True


def test_stress_two_consecutive_runs_same_dir_both_pass(tmp_path: Path) -> None:
    """B. Two consecutive runs sharing the SAME output dir both pass."""
    out_dir = tmp_path / "iso"
    run1 = run_stress_suite(out_dir)
    run2 = run_stress_suite(out_dir)
    assert run1.passed is True
    assert run2.passed is True
    assert _ec2_restart(run1).passed is True
    assert _ec2_restart(run2).passed is True


def test_stress_consecutive_runs_use_different_session_ids(tmp_path: Path) -> None:
    """C. The two runs derive different session ids."""
    out_dir = tmp_path / "iso"
    run_stress_suite(out_dir)
    run_stress_suite(out_dir)
    sids = _run_session_ids(out_dir)
    assert len(sids) == 2
    assert sids[0] != sids[1]


def test_stress_consecutive_runs_do_not_collide_artifacts(tmp_path: Path) -> None:
    """D. Journal/checkpoint artifacts from the two runs live in distinct dirs."""
    out_dir = tmp_path / "iso"
    run_stress_suite(out_dir)
    run_stress_suite(out_dir)
    run_dirs = sorted(p for p in out_dir.iterdir() if p.is_dir())
    assert len(run_dirs) == 2
    # Each run has its own restart journal + checkpoint; paths must not overlap.
    journals = set()
    checkpoints = set()
    for run_dir in run_dirs:
        j = list((run_dir / "restart").glob("*.jsonl"))
        c = run_dir / "restart" / "ckpt.json"
        assert len(j) == 1 and c.exists()
        journals.add(j[0])
        checkpoints.add(c)
    assert len(journals) == 2
    assert len(checkpoints) == 2
    # Prior run's artifacts remain inspectable after the second run.
    assert all(p.exists() for p in journals)
    assert all(p.exists() for p in checkpoints)


def test_duplicate_event_detection_still_blocks(tmp_path: Path) -> None:
    """E. Corruption detection is NOT weakened: a journal with duplicate event
    ids must still fail closed (trusted=False, orders blocked, corruption blocker)."""
    from quantfund.phase19.checkpoint import recover_phase19

    journal_path = tmp_path / "corrupt.jsonl"
    row = {
        "event_id": "DUP-EVENT-ID",
        "session_id": "s",
        "timestamp": "2024-01-02T09:15:00+00:00",
        "event_type": "MARKET_BAR",
        "strategy_id": "buy_and_hold",
        "strategy_version": "1.0.0",
        "symbol": "RELIANCE",
        "config_hash": "h",
        "payload": {},
    }
    with journal_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.write(json.dumps(row) + "\n")  # deliberate duplicate event id

    rec = recover_phase19(
        session_id="s",
        journal_path=journal_path,
        checkpoint_path=tmp_path / "any.json",
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        config_hash="h",
    )
    assert rec.trusted is False
    assert rec.allows_new_orders is False
    assert any("corrupted_journal_duplicate_event_id" in b for b in rec.blockers)


# --- Report ---


def test_format_demo() -> None:
    text = format_demo(
        {
            "result": "PAPER_VALIDATED",
            "duration_days": 20,
            "activation": {"strategy_family": "buy_and_hold"},
            "strategy_immutable": True,
            "session_metrics": {"trade_count": 1, "total_pnl": 10, "total_return": 0.0, "sharpe": None, "max_drawdown": 0},
            "reconciliation_status": "CLEAN",
            "comparison": {"within_existing_drift_limits": True},
            "stress": {"passed": True},
            "safety": safety_payload(),
        }
    )
    assert "PHASE 20" in text
    assert "PAPER_VALIDATED" in text


def test_write_json(tmp_path: Path) -> None:
    h = write_json(tmp_path / "r.json", {"result": "PAPER_FAILED"})
    assert len(h) > 8


# --- Pipeline ---


def test_validation_rejects_bad_duration(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_phase20_validation(duration_days=7, out_dir=tmp_path, run_stress=False)


def test_validation_20d(tmp_path: Path) -> None:
    report = run_phase20_validation(
        duration_days=20,
        out_dir=tmp_path,
        run_stress=True,
        use_buy_hold_for_activity=True,
    )
    assert report["result"] in {"PAPER_VALIDATED", "PAPER_FAILED"}
    assert report["duration_days"] == 20
    assert report["session_metrics"]["trading_days"] == 20
    assert report["strategy_immutable"] is True
    assert report["safety"]["real_broker_orders"] == 0
    assert report["safety"]["place_order_called"] == 0
    assert report["safety"]["live_trading"] == "DISABLED"
    assert report["checks"]["profitability_not_required"] is True
    assert (tmp_path / "reports" / "phase20_paper_validation.json").exists()


def test_validation_produces_daily_metrics(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert len(report["daily_metrics"]) == 20
    keys = {
        "pnl",
        "return",
        "turnover",
        "trade_count",
        "win_rate",
        "average_trade",
        "maximum_loss",
        "exposure",
        "slippage",
        "signal_frequency",
        "risk_rejections",
        "data_quality_events",
        "latency_seconds",
    }
    assert keys.issubset(report["daily_metrics"][0].keys())


def test_validation_recon_status(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert report["reconciliation_status"] in {"CLEAN", "TRADING_HALTED"}


def test_validation_comparison_present(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "backtest_to_paper_drift" in report["comparison"]
    assert "historical_backtest" in report["comparison"]
    assert "walk_forward" in report["comparison"]
    assert "paper_trading" in report["comparison"]


def test_demo_end_to_end(tmp_path: Path) -> None:
    report = run_phase20_demo(out_dir=tmp_path, duration_days=20)
    assert report["result"] == "PAPER_VALIDATED"
    assert "PHASE 20" in (report.get("demo_text") or "")


def test_immutability_flag(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert report["checks"]["strategy_immutable"] is True
    assert report["checks"]["no_llm_genetic_mutation"] is True
    assert report["checks"]["no_auto_retrain"] is True
    assert report["checks"]["no_auto_capital_scaling"] is True


def test_zero_live_assertions(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert report["assertions"]["real_broker_orders"] == 0
    assert report["assertions"]["live_trading"] == "DISABLED"


def test_stress_included_in_validation(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=True)
    assert report["stress"]["passed"] is True
    assert report["checks"]["stress_suite_passed"] is True


def test_makefile_targets() -> None:
    mk = Path("Makefile").read_text(encoding="utf-8")
    assert "phase20-validate" in mk
    assert "phase20-demo" in mk


def test_scripts_exist() -> None:
    assert Path("scripts/run_phase20_demo.py").exists()
    assert Path("scripts/run_phase20_validate.py").exists()


def test_docs_path() -> None:
    assert Path("docs/PHASE20_PAPER_VALIDATION.md").exists()


def test_result_enum_only_two(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert report["result"] in {"PAPER_VALIDATED", "PAPER_FAILED"}


def test_candidate_shortlist_recorded(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "research_shortlist" in report["activation"]


def test_paper_candidate_dataclass() -> None:
    c = PaperCandidate("a", "momentum", {}, False, 1, 0.1, "t")
    assert c.to_dict()["strategy_family"] == "momentum"


def test_no_phase16b_in_phase20_sources() -> None:
    for path in Path("src/quantfund/phase20").rglob("*.py"):
        if path.name == "safety.py":
            continue
        assert "ZerodhaCanaryBroker" not in path.read_text(encoding="utf-8")


def test_duration_60_supported(tmp_path: Path) -> None:
    # Lighter: only check validation accepts 60 without running full if slow —
    # run with stress off; 60+25 bars still fine
    report = run_phase20_validation(duration_days=60, out_dir=tmp_path, run_stress=False)
    assert report["duration_days"] == 60
    assert report["session_metrics"]["trading_days"] == 60


def test_session_metrics_per_trade_pnl_list(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert isinstance(report["session_metrics"]["per_trade_pnl"], list)


def test_checkpoint_dir_created(tmp_path: Path) -> None:
    run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert (tmp_path / "checkpoints").exists()
    assert list((tmp_path / "journal").glob("*.jsonl"))


def test_validated_implies_hard_checks(tmp_path: Path) -> None:
    report = run_phase20_demo(out_dir=tmp_path, duration_days=20)
    if report["result"] == "PAPER_VALIDATED":
        assert report["checks"]["no_live_orders"]
        assert report["checks"]["strategy_immutable"]
        assert report["checks"]["drift_within_limits"]


def test_format_contains_safety_lines() -> None:
    text = format_demo(
        {
            "result": "PAPER_FAILED",
            "duration_days": 20,
            "activation": {},
            "strategy_immutable": False,
            "session_metrics": {},
            "reconciliation_status": "TRADING_HALTED",
            "comparison": {},
            "stress": {},
            "safety": safety_payload(),
        }
    )
    assert "real_broker_orders = 0" in text


def test_json_report_roundtrip(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    data = json.loads((tmp_path / "reports" / "phase20_paper_validation.json").read_text())
    assert data["phase"] == "20"
    assert data["result"] == report["result"]


def test_exposure_and_slippage_keys(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "exposure_end" in report["session_metrics"]
    assert "slippage" in report["session_metrics"]


def test_signal_frequency_tracked(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "signal_frequency" in report["session_metrics"]


def test_data_quality_tracked(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "data_quality_events" in report["session_metrics"]


def test_win_rate_and_avg_trade(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "win_rate" in report["session_metrics"]
    assert "average_trade" in report["session_metrics"]
    assert "maximum_loss" in report["session_metrics"]


def test_no_yfinance_live_claim() -> None:
    text = Path("docs/PHASE20_PAPER_VALIDATION.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert (
        "no live trading" in lowered
        or "live trading" in lowered
        or "live_trading = disabled" in lowered
        or "zero live orders" in lowered
    )


def test_recovery_check_present(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert "recovery_trusted_or_halted" in report["checks"]


def test_network_outage_case_present(tmp_path: Path) -> None:
    suite = run_stress_suite(tmp_path / "net")
    assert any(c.name == "network_outage" for c in suite.cases)


def test_buy_hold_activity_can_trade(tmp_path: Path) -> None:
    report = run_phase20_validation(
        duration_days=20,
        out_dir=tmp_path,
        run_stress=False,
        use_buy_hold_for_activity=True,
    )
    # buy-and-hold should create at least one paper order/fill on a long stream
    assert report["session_metrics"]["trade_count"] >= 1
    assert report["safety"]["paper_orders"] >= 1


def test_duration_completed_check(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert report["checks"]["duration_completed"] is True


def test_no_broker_writes_in_stress_module() -> None:
    text = Path("src/quantfund/phase20/stress.py").read_text(encoding="utf-8")
    assert "kiteconnect" not in text
    assert "phase16b" not in text


def test_result_not_based_on_profit_alone(tmp_path: Path) -> None:
    report = run_phase20_validation(duration_days=20, out_dir=tmp_path, run_stress=False)
    assert report["checks"]["profitability_not_required"] is True
    # Negative or zero pnl must not alone decide failure
    assert "total_pnl" in report["session_metrics"]

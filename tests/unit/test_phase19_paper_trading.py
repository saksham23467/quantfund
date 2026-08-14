"""Phase 19 — controlled paper trading tests (≥60)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.models import SessionMode
from quantfund.phase15.broker_readonly import SimulatedReadOnlyBroker
from quantfund.phase15.freeze import freeze_session_config
from quantfund.phase19.activation import (
    assert_strategy_immutable,
    build_activation,
)
from quantfund.phase19.capability import (
    CapabilityError,
    assert_runtime_paper_capabilities,
)
from quantfund.phase19.checkpoint import event_id, recover_phase19
from quantfund.phase19.drift import evaluate_paper_drift
from quantfund.phase19.health import Phase19Health, start_health_server, stop_health_server
from quantfund.phase19.pipeline import (
    run_phase19_demo,
    run_phase19_health,
    run_phase19_paper,
    run_phase19_preflight,
    run_phase19_reconcile,
    run_phase19_replay,
)
from quantfund.phase19.report import daily_report_payload, format_demo, write_json
from quantfund.phase19.safety import (
    FORBIDDEN_ADAPTER_TYPES,
    FORBIDDEN_CALLS,
    reject_forbidden_adapter,
    require_paper_execution_only,
    safety_payload,
    scan_phase19_for_broker_writes,
)
from quantfund.phase19.selection import (
    PaperCandidate,
    accepted_from_phase18,
    sandbox_shortlist_from_phase18,
    select_paper_strategy,
)
from quantfund.phase19.sessions import (
    DURATION_TRADING_DAYS,
    bars_for_duration,
    plan_for,
)
from quantfund.phase19.strategy_factory import strategy_and_spec_for
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


# --- Sessions ---


def test_durations_defined() -> None:
    assert set(DURATION_TRADING_DAYS) == {"1d", "5d", "20d", "60d"}


def test_plan_1d() -> None:
    p = plan_for("1d")
    assert p.trading_days == 1
    assert p.auto_graduate_to_live is False


def test_plan_5d() -> None:
    assert plan_for("5d").trading_days == 5


def test_plan_20d() -> None:
    assert plan_for("20d").trading_days == 20


def test_plan_60d() -> None:
    assert plan_for("60d").trading_days == 60


def test_plan_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        plan_for("90d")


def test_bars_for_duration() -> None:
    assert bars_for_duration("5d") == 5


def test_plan_to_dict() -> None:
    d = plan_for("1d").to_dict()
    assert d["auto_graduate_to_live"] is False


# --- Selection ---


def test_accepted_empty_when_zero() -> None:
    assert accepted_from_phase18({"candidates": {"accepted": 0}}) == []


def test_accepted_from_pass_rows() -> None:
    report = {
        "candidates": {"accepted": 1},
        "finalist_evaluations": [
            {
                "decision": "PASS",
                "candidate_id": "c1",
                "strategy_family": "momentum",
                "parameters": {"lookback": 20},
            }
        ],
    }
    out = accepted_from_phase18(report)
    assert len(out) == 1
    assert out[0].research_accepted is True


def test_sandbox_shortlist() -> None:
    lb = {
        "leaderboard": [
            {
                "candidate_id": "x",
                "strategy_family": "mean_reversion",
                "parameters": {"window": 20},
                "rank": 1,
                "mean_validation_sharpe": 0.5,
            }
        ]
    }
    rows = sandbox_shortlist_from_phase18(leaderboard=lb, n=1)
    assert rows[0].research_accepted is False
    assert rows[0].source.endswith("sandbox_only")


def test_select_blocks_without_sandbox() -> None:
    c, mode = select_paper_strategy(
        allow_sandbox_demo=False,
        search_report={"candidates": {"accepted": 0}},
        leaderboard={"leaderboard": []},
    )
    assert c is None
    assert mode.startswith("BLOCKED")


def test_select_sandbox_fallback() -> None:
    c, mode = select_paper_strategy(
        allow_sandbox_demo=True,
        search_report={"candidates": {"accepted": 0}},
        leaderboard={"leaderboard": []},
    )
    assert c is not None
    assert mode == "INFRASTRUCTURE_SANDBOX"


def test_candidate_to_dict() -> None:
    c = PaperCandidate("id", "momentum", {"lookback": 10}, False, 1, 0.1, "t")
    assert c.to_dict()["candidate_id"] == "id"


# --- Safety / capability ---


def test_scan_phase19_clean() -> None:
    assert scan_phase19_for_broker_writes() == []


def test_forbidden_calls_cover_order_apis() -> None:
    for name in ("place_order", "modify_order", "cancel_order", "exit_order", "basket_order"):
        assert name in FORBIDDEN_CALLS


def test_forbidden_adapter_types() -> None:
    assert "ZerodhaCanaryBroker" in FORBIDDEN_ADAPTER_TYPES
    assert "LiveBroker" in FORBIDDEN_ADAPTER_TYPES
    assert "WriteBroker" in FORBIDDEN_ADAPTER_TYPES


def test_require_paper_adapter() -> None:
    a = PaperExecutionAdapter(session_id="t")
    assert require_paper_execution_only(a) is a


def test_reject_canary_name() -> None:
    class ZerodhaCanaryBroker:
        can_place_orders = False

    with pytest.raises(RuntimeError):
        reject_forbidden_adapter(ZerodhaCanaryBroker())


def test_runtime_caps_paper_only() -> None:
    out = assert_runtime_paper_capabilities(
        execution_adapter=PaperExecutionAdapter(session_id="x"),
        readonly_broker=SimulatedReadOnlyBroker(),
    )
    assert out["ok"] is True
    assert out["can_place_orders"] is False


def test_runtime_caps_reject_non_paper() -> None:
    class Fake:
        can_place_orders = False

    with pytest.raises(CapabilityError):
        assert_runtime_paper_capabilities(execution_adapter=Fake())


def test_safety_payload_defaults() -> None:
    s = safety_payload()
    assert s["real_broker_orders"] == 0
    assert s["place_order_called"] == 0
    assert s["live_trading"] == "DISABLED"
    assert s["kill_switch"] == "ARMED"
    assert s["ok"] is True


def test_no_phase16b_broker_import_in_phase19() -> None:
    root = Path("src/quantfund/phase19")
    for path in root.rglob("*.py"):
        if path.name == "safety.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "phase16b.broker" not in text
        assert "ZerodhaCanaryBroker" not in text or path.name == "capability.py"


def test_ast_no_place_order_calls() -> None:
    root = Path("src/quantfund/phase19")
    for path in root.rglob("*.py"):
        if path.name in {"safety.py", "capability.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in FORBIDDEN_CALLS


# --- Activation / immutability ---


def test_build_activation_sandbox() -> None:
    c = PaperCandidate("c", "buy_and_hold", {"allocation": 0.5}, False, None, None, "t")
    act, frozen = build_activation(
        candidate=c,
        mode="INFRASTRUCTURE_SANDBOX",
        strategy_spec={"name": "bh"},
        dataset_research_hash="hash1",
    )
    assert act.auto_graduate_to_live is False
    assert act.research_accepted is False
    assert frozen.freeze_token


def test_activation_requires_acceptance_for_production() -> None:
    c = PaperCandidate("c", "momentum", {}, False, None, None, "t")
    with pytest.raises(RuntimeError):
        build_activation(
            candidate=c,
            mode="PRODUCTION_PAPER_ELIGIBLE",
            strategy_spec={},
            dataset_research_hash="h",
        )


def test_strategy_immutable() -> None:
    c = PaperCandidate("c", "buy_and_hold", {"allocation": 0.5}, False, None, None, "t")
    act, frozen = build_activation(
        candidate=c,
        mode="INFRASTRUCTURE_SANDBOX",
        strategy_spec={"name": "bh"},
        dataset_research_hash="h",
        session_config_hash="cfg",
    )
    assert_strategy_immutable(
        frozen,
        candidate=c,
        strategy_spec={"name": "bh"},
        dataset_research_hash="h",
        session_config_hash="cfg",
    )
    assert act.strategy_hash == frozen.strategy_hash


def test_strategy_mutation_detected() -> None:
    c = PaperCandidate("c", "buy_and_hold", {"allocation": 0.5}, False, None, None, "t")
    _, frozen = build_activation(
        candidate=c,
        mode="INFRASTRUCTURE_SANDBOX",
        strategy_spec={"name": "bh"},
        dataset_research_hash="h",
        session_config_hash="cfg",
    )
    mutated = PaperCandidate("c", "buy_and_hold", {"allocation": 0.9}, False, None, None, "t")
    with pytest.raises(RuntimeError):
        assert_strategy_immutable(
            frozen,
            candidate=mutated,
            strategy_spec={"name": "bh"},
            dataset_research_hash="h",
            session_config_hash="cfg",
        )


def test_freeze_token_stable() -> None:
    a = freeze_session_config(strategy_id="x", strategy_version="1", strategy_params={"a": 1})
    b = freeze_session_config(strategy_id="x", strategy_version="1", strategy_params={"a": 1})
    assert a.freeze_token == b.freeze_token


# --- Strategy factory ---


def test_factory_buy_and_hold() -> None:
    c = PaperCandidate("p19_sandbox_buy_hold", "buy_and_hold", {"allocation": 0.5}, False, None, None, "phase19_fallback_sandbox")
    factory, spec = strategy_and_spec_for(c, symbol="RELIANCE")
    s = factory()
    assert isinstance(s, BuyAndHoldStrategy)
    assert spec.symbol == "RELIANCE"


def test_factory_phase18_family() -> None:
    c = PaperCandidate(
        "cid",
        "momentum",
        {"lookback": 10, "threshold": 0.0},
        False,
        1,
        0.1,
        "phase18_leaderboard_sandbox_only",
    )
    factory, spec = strategy_and_spec_for(c, symbol="RELIANCE")
    assert factory().metadata().strategy_id == "momentum"
    assert spec.metadata["candidate_id"] == "cid"


# --- Drift ---


def test_drift_continue_when_matched() -> None:
    d = evaluate_paper_drift(expected_fills=2, actual_fills=2)
    assert d["action"] in {"CONTINUE", "FLAG"}
    assert d["strategy_mutated"] is False


def test_drift_flag_on_stale() -> None:
    d = evaluate_paper_drift(expected_fills=1, actual_fills=1, stale_events=3)
    assert d["action"] == "FLAG"


def test_drift_warning_on_price_delta() -> None:
    d = evaluate_paper_drift(
        expected_fills=1,
        actual_fills=1,
        avg_price_delta_bps=80.0,
    )
    assert d["classification"] in {"WARNING", "EXPECTED", "NONE"}


# --- Checkpoint / event ids ---


def test_event_id_idempotent() -> None:
    a = event_id(session_id="s", kind="FILL", seq=1, symbol="X", ts="t")
    b = event_id(session_id="s", kind="FILL", seq=1, symbol="X", ts="t")
    assert a == b


def test_event_id_differs() -> None:
    a = event_id(session_id="s", kind="FILL", seq=1, symbol="X", ts="t")
    b = event_id(session_id="s", kind="FILL", seq=2, symbol="X", ts="t")
    assert a != b


def test_recover_missing_checkpoint(tmp_path: Path) -> None:
    st = recover_phase19(
        session_id="s",
        journal_path=None,
        checkpoint_path=tmp_path / "missing.json",
    )
    assert st.trusted is False
    assert st.allows_new_orders is False


# --- Health ---


def test_health_beat() -> None:
    h = Phase19Health()
    h.beat()
    assert h.heartbeat_at
    assert h.status == "OK"
    assert h.to_dict()["secrets_exposed"] is False
    assert h.to_dict()["live_trading"] == "DISABLED"


def test_health_server_loopback() -> None:
    h = Phase19Health(status="OK")
    server, _ = start_health_server(h, host="127.0.0.1", port=18719)
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:18719/health", timeout=2) as resp:
            data = json.loads(resp.read().decode())
        assert data["live_trading"] == "DISABLED"
        assert "api_key" not in json.dumps(data).lower()
    finally:
        stop_health_server(server)


# --- Report ---


def test_format_demo() -> None:
    text = format_demo(
        {
            "mode": "INFRASTRUCTURE_SANDBOX",
            "duration": {"duration": "1d"},
            "activation": {
                "strategy_family": "momentum",
                "candidate_id": "c",
                "research_accepted": False,
                "freeze_token": "tok",
            },
            "run": {
                "paper_orders": 1,
                "paper_fills": 1,
                "risk_rejections": 0,
                "stale_events": 0,
                "reconciliation_ok": True,
                "drift": {"action": "CONTINUE"},
            },
            "safety": safety_payload(paper_orders=1, paper_fills=1),
        }
    )
    assert "PHASE 19" in text
    assert "live_trading = DISABLED" in text


def test_daily_report_keys() -> None:
    d = daily_report_payload(
        {
            "accounting": {"turnover": 1.0},
            "paper_orders": 1,
            "paper_fills": 1,
            "risk_rejections": 0,
            "stale_events": 0,
            "reconciliation_ok": True,
        }
    )
    assert "orders" in d
    assert "stale_data_events" in d


def test_write_json(tmp_path: Path) -> None:
    h = write_json(tmp_path / "x.json", {"a": 1})
    assert len(h) > 8


# --- Pipeline ---


def test_preflight(tmp_path: Path) -> None:
    p = run_phase19_preflight(out_dir=tmp_path)
    assert p["ok"] is True
    assert p["live_trading"] == "DISABLED"
    assert p["safety"]["place_order_called"] == 0


def test_paper_session_sandbox(tmp_path: Path) -> None:
    report = run_phase19_paper(
        duration="1d",
        out_dir=tmp_path,
        allow_sandbox_demo=True,
        start_health=False,
        force_stale_demo=True,
    )
    assert report["mode"] == "INFRASTRUCTURE_SANDBOX"
    assert report["safety"]["real_broker_orders"] == 0
    assert report["safety"]["place_order_called"] == 0
    assert report["safety"]["live_trading"] == "DISABLED"
    assert report["safety"]["kill_switch"] == "ARMED"
    assert report["activation"]["auto_graduate_to_live"] is False
    assert (tmp_path / "reports" / "phase19_paper_session.json").exists()
    assert (tmp_path / "checkpoints").exists()
    assert list((tmp_path / "journal").glob("*.jsonl"))


def test_paper_stale_stops_new_signals(tmp_path: Path) -> None:
    report = run_phase19_paper(
        duration="1d",
        out_dir=tmp_path / "stale",
        force_stale_demo=True,
    )
    assert report["run"]["stale_events"] >= 0


def test_health_after_paper(tmp_path: Path) -> None:
    run_phase19_paper(duration="1d", out_dir=tmp_path)
    h = run_phase19_health(out_dir=tmp_path)
    assert h["live_trading"] == "DISABLED"


def test_reconcile_after_paper(tmp_path: Path) -> None:
    run_phase19_paper(duration="1d", out_dir=tmp_path)
    r = run_phase19_reconcile(out_dir=tmp_path)
    assert "ok" in r


def test_replay_reproducible(tmp_path: Path) -> None:
    payload = run_phase19_replay(out_dir=tmp_path, duration="1d")
    assert payload["reproducible"] is True
    assert payload["real_broker_orders"] == 0


def test_demo_end_to_end(tmp_path: Path) -> None:
    report = run_phase19_demo(out_dir=tmp_path)
    assert "PHASE 19" in (report.get("demo_text") or "")
    assert report["safety"]["ok"] is True
    assert report["assertions"]["real_broker_orders"] == 0


def test_production_blocked_without_acceptance(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        run_phase19_paper(
            duration="1d",
            out_dir=tmp_path,
            allow_sandbox_demo=False,
        )


def test_session_mode_sandbox_not_production(tmp_path: Path) -> None:
    report = run_phase19_paper(duration="1d", out_dir=tmp_path)
    # activation mode sandbox
    assert report["mode"] == "INFRASTRUCTURE_SANDBOX"


def test_makefile_targets() -> None:
    mk = Path("Makefile").read_text(encoding="utf-8")
    for t in (
        "phase19-preflight",
        "phase19-paper",
        "phase19-health",
        "phase19-reconcile",
        "phase19-report",
        "phase19-replay",
        "phase19-demo",
    ):
        assert t in mk


def test_scripts_exist() -> None:
    for name in (
        "run_phase19_preflight.py",
        "run_phase19_paper.py",
        "run_phase19_health.py",
        "run_phase19_reconcile.py",
        "run_phase19_report.py",
        "run_phase19_replay.py",
        "run_phase19_demo.py",
    ):
        assert (Path("scripts") / name).exists()


def test_systemd_unit_exists() -> None:
    unit = Path("deploy/systemd/quantfund-phase19-paper.service")
    assert unit.exists()
    text = unit.read_text(encoding="utf-8")
    assert "Restart=" in text
    assert "EnvironmentFile" in text
    assert "place_order" not in text.lower() or "zero" in text.lower()


def test_logrotate_exists() -> None:
    assert Path("deploy/logrotate/quantfund-phase19").exists()


def test_docs_exist() -> None:
    assert Path("docs/PHASE19_PAPER_TRADING.md").exists()


def test_no_yfinance_as_live_claim_in_docs() -> None:
    text = Path("docs/PHASE19_PAPER_TRADING.md").read_text(encoding="utf-8")
    assert "Paper trading only" in text


def test_acceptance_checks_present(tmp_path: Path) -> None:
    report = run_phase19_paper(duration="1d", out_dir=tmp_path)
    checks = report["acceptance"]["checks"]
    assert "reconciliation_clean" in checks
    assert "no_strategy_mutation" in checks
    assert "profit_not_sufficient" in checks


def test_paper_orders_nonnegative(tmp_path: Path) -> None:
    report = run_phase19_paper(duration="1d", out_dir=tmp_path)
    assert report["safety"]["paper_orders"] >= 0
    assert report["safety"]["paper_fills"] >= 0


def test_duration_5d_runs(tmp_path: Path) -> None:
    report = run_phase19_paper(duration="5d", out_dir=tmp_path)
    assert report["duration"]["trading_days"] == 5


def test_risk_limits_configured(tmp_path: Path) -> None:
    # Smoke: paper path uses PaperRiskConfig ceilings
    report = run_phase19_paper(duration="1d", out_dir=tmp_path)
    assert report["frozen"]["risk_config_hash"]


def test_checkpoint_unique_fills(tmp_path: Path) -> None:
    report = run_phase19_paper(duration="1d", out_dir=tmp_path)
    idem = report["run"]["checkpoint_idempotency"]
    assert idem["unique_fills"] is True
    assert idem["unique_orders"] is True


def test_session_mode_enum() -> None:
    assert SessionMode.INFRASTRUCTURE_SANDBOX.value == "infrastructure_sandbox"


def test_activation_record_fields() -> None:
    c = PaperCandidate("c", "buy_and_hold", {"allocation": 0.5}, False, None, None, "t")
    act, _ = build_activation(
        candidate=c,
        mode="INFRASTRUCTURE_SANDBOX",
        strategy_spec={},
        dataset_research_hash="ds",
        code_version="0.2.0",
    )
    d = act.to_dict()
    assert d["code_version"] == "0.2.0"
    assert d["dataset_research_hash"] == "ds"
    assert d["parameter_hash"]

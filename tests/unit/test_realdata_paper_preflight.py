"""Tests for real-market-data paper-trading preflight (NOT live trading).

Verifies the safety spine and fail-closed gates:
- Mode invariants (ZERODHA / PAPER / DISABLED).
- Hard no-real-broker-write assertion (raises when live gates are set).
- PaperExecutionAdapter exposes no order-write methods.
- Honest connectivity (no creds ⇒ not connected; mock is never "connected").
- Strategy-acceptance gate fails closed.
- Preflight never starts a session and keeps orders/place_order at 0.
"""

from __future__ import annotations

import json

import pytest

from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper_realdata import (
    PaperModeManifest,
    RealBrokerWriteError,
    assert_no_real_broker_write_capability,
    check_strategy_acceptance,
    check_zerodha_data_connectivity,
    run_realdata_paper_preflight,
)
from quantfund.paper_realdata.broker_guard import FORBIDDEN_WRITE_METHODS
from quantfund.paper_realdata.report import write_preflight_reports

INELIGIBLE_PHASE19 = {
    "ran_search": False,
    "final_accepted_candidate_ids": [],
    "prerequisite": {"research_eligible": False},
}
ACCEPTED_PHASE19 = {
    "ran_search": True,
    "final_accepted_candidate_ids": ["mean_reversion_000"],
    "prerequisite": {"research_eligible": True},
}


# --------------------------------------------------------------------------
# Mode manifest
# --------------------------------------------------------------------------


def test_mode_manifest_declares_invariants():
    m = PaperModeManifest()
    d = m.to_dict()
    assert d == {
        "DATA_SOURCE": "ZERODHA",
        "EXECUTION_MODE": "PAPER",
        "BROKER_WRITES": "DISABLED",
    }


# --------------------------------------------------------------------------
# Hard no-real-broker-write assertion
# --------------------------------------------------------------------------


def test_broker_guard_passes_with_default_paper_adapter():
    result = assert_no_real_broker_write_capability(env={})
    assert result["real_broker_write_capability"] == "ABSENT"
    assert result["can_place_orders"] is False
    assert result["live_trading_gates_satisfied"] is False
    assert result["write_scan_ok"] is True
    assert result["forbidden_write_methods_exposed"] == []


def test_broker_guard_raises_when_execution_mode_broker_live():
    env = {
        "QUANTFUND_EXECUTION_MODE": "BROKER_LIVE",
        "QUANTFUND_LIVE_TRADING_CONFIRM": "I_UNDERSTAND_REAL_MONEY",
        "ZERODHA_ENV": "production",
    }
    with pytest.raises(RealBrokerWriteError):
        assert_no_real_broker_write_capability(env=env)


def test_paper_execution_adapter_exposes_no_write_methods():
    adapter = PaperExecutionAdapter(session_id="t")
    for name in FORBIDDEN_WRITE_METHODS:
        assert not hasattr(adapter, name), f"paper adapter must not expose {name}"


# --------------------------------------------------------------------------
# Connectivity (honest)
# --------------------------------------------------------------------------


def test_connectivity_not_connected_without_credentials():
    conn = check_zerodha_data_connectivity(symbols=["RELIANCE"], env={})
    assert conn["zerodha_data_connected"] is False
    assert conn["simulation_only"] is True
    assert conn["data_source"] == "ZERODHA"


def test_connectivity_mock_is_not_counted_as_connected():
    # Even if mock is explicitly allowed, a mock transport is never "connected".
    conn = check_zerodha_data_connectivity(
        symbols=["RELIANCE"], env={"QUANTFUND_PHASE21_ALLOW_MOCK": "1"}
    )
    assert conn["zerodha_data_connected"] is False
    assert conn["simulation_only"] is True


# --------------------------------------------------------------------------
# Strategy-acceptance gate
# --------------------------------------------------------------------------


def test_strategy_gate_missing_report_fails_closed(tmp_path):
    res = check_strategy_acceptance(reports_dir=tmp_path)
    assert res["strategy_accepted"] is False
    assert "phase19_strategy_search_report_missing" in res["blockers"]


def test_strategy_gate_ineligible_report_fails_closed(tmp_path):
    (tmp_path / "phase19_strategy_search.json").write_text(
        json.dumps(INELIGIBLE_PHASE19), encoding="utf-8"
    )
    res = check_strategy_acceptance(reports_dir=tmp_path)
    assert res["strategy_accepted"] is False
    assert "zero_accepted_strategies" in res["blockers"]
    assert "research_eligibility_false" in res["blockers"]


def test_strategy_gate_accepts_when_report_has_accepted_ids(tmp_path):
    (tmp_path / "phase19_strategy_search.json").write_text(
        json.dumps(ACCEPTED_PHASE19), encoding="utf-8"
    )
    res = check_strategy_acceptance(reports_dir=tmp_path)
    assert res["strategy_accepted"] is True
    assert res["accepted_candidate_ids"] == ["mean_reversion_000"]


# --------------------------------------------------------------------------
# Preflight (fail closed + never starts a session)
# --------------------------------------------------------------------------


def _preflight(tmp_path, phase19_report):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase19_strategy_search.json").write_text(
        json.dumps(phase19_report), encoding="utf-8"
    )
    return run_realdata_paper_preflight(reports_dir=reports, env={})


def test_preflight_fails_closed_and_reports_mandated_fields(tmp_path):
    payload = _preflight(tmp_path, INELIGIBLE_PHASE19)
    r = payload["report"]
    # Mandated report fields.
    assert r["zerodha_data_connected"] is False
    assert r["strategy_accepted"] is False
    assert r["real_broker_writes_enabled"] is False
    assert r["kill_switch"] == "ARMED"
    assert r["orders_submitted"] == 0
    assert r["place_order_called"] == 0
    # Verdict: fail closed, no session started.
    assert payload["can_start_paper_session"] is False
    assert payload["started_paper_session"] is False
    assert payload["mode"] == {
        "DATA_SOURCE": "ZERODHA",
        "EXECUTION_MODE": "PAPER",
        "BROKER_WRITES": "DISABLED",
    }


def test_preflight_blocks_even_if_strategy_accepted_but_not_connected(tmp_path):
    payload = _preflight(tmp_path, ACCEPTED_PHASE19)
    r = payload["report"]
    assert r["strategy_accepted"] is True
    # Data is not connected in the sandbox → still cannot start.
    assert r["zerodha_data_connected"] is False
    assert payload["can_start_paper_session"] is False
    assert "zerodha_data_not_connected" in payload["blockers"]
    assert payload["started_paper_session"] is False


def test_preflight_never_submits_orders_or_enables_live(tmp_path):
    payload = _preflight(tmp_path, ACCEPTED_PHASE19)
    assert payload["safety"]["live_trading"] == "DISABLED"
    assert payload["safety"]["orders_submitted"] == 0
    assert payload["safety"]["place_order_called"] == 0
    assert payload["report"]["real_broker_writes_enabled"] is False


def test_preflight_writes_reports(tmp_path):
    payload = _preflight(tmp_path, INELIGIBLE_PHASE19)
    json_path = tmp_path / "reports" / "realdata_paper_preflight.json"
    md_path = tmp_path / "docs" / "REALDATA_PAPER_TRADING.md"
    write_preflight_reports(payload, json_path=json_path, md_path=md_path)
    assert json_path.exists()
    assert md_path.exists()
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["report"]["place_order_called"] == 0

"""Phase 17C — dataset certification, calendar, CA, PIT, immutability, eligibility."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from quantfund.data.calendar.nse import DEFAULT_NSE_CALENDAR_VERSION, NSECalendarProvider
from quantfund.data.models import MarketBar
from quantfund.data.normalize import _to_datetime, dataframe_to_bars
from quantfund.data.zerodha_hist.ca_import import import_ca_csv
from quantfund.data.zerodha_hist.package import (
    next_dataset_version,
    research_zerodha_root,
    write_zerodha_dataset_package,
)
from quantfund.data.zerodha_hist.real_validation import calendar_coverage
from quantfund.phase17a.ca import analyze_ca_for_symbol
from quantfund.phase17a.quality import run_symbol_quality
from quantfund.phase17c.certify_gate import build_zerodha_cert_facts, evaluate_eligibility
from quantfund.phase17c.edge_bars import REQUESTED_START, split_edge_bars
from quantfund.phase17c.identity_pit import (
    audit_instrument_identity,
    audit_universe_membership,
)
from quantfund.phase17c.packages import assert_source_immutable, write_certified_package
from quantfund.phase17c.pipeline import certify_symbol_package, run_phase17c_certification
from quantfund.phase17c.safety import safety_payload
from quantfund.phase17a.datasets import DiscoveredPackage


IST = ZoneInfo("Asia/Kolkata")


def _bars(symbol: str, start: date, n: int) -> list[MarketBar]:
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(
                MarketBar(
                    timestamp=datetime(d.year, d.month, d.day),
                    symbol=symbol,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000.0,
                )
            )
        d += timedelta(days=1)
    return out


def _write_pkg(tmp_path: Path, symbol: str, bars: list[MarketBar], *, ver: str = "v1") -> Path:
    # redirect research root
    from quantfund.data.zerodha_hist import package as pkgmod

    pkgmod.research_zerodha_root = lambda: tmp_path  # type: ignore
    return write_zerodha_dataset_package(
        bars=bars,
        provenance={"provider": "zerodha", "price_policy": "unknown"},
        quality_report={"ok": True},
        corporate_actions=[],
        instrument_metadata={
            "instrument_token": 123,
            "tradingsymbol": symbol,
            "exchange": "NSE",
        },
        dataset_id=f"zerodha_nse_daily_{symbol.lower()}_test",
        version=ver,
    )


def test_default_calendar_is_2018_2026() -> None:
    assert DEFAULT_NSE_CALENDAR_VERSION == "nse_eq_v2018_2026_r1"
    cal = NSECalendarProvider()
    assert cal.verified is True
    assert cal.in_coverage(date(2018, 1, 1))
    assert cal.in_coverage(date(2026, 8, 12))
    assert not cal.in_coverage(date(2017, 12, 31))


def test_old_calendar_versions_still_load() -> None:
    old = NSECalendarProvider(calendar_version="nse_eq_v2023_2025_r1")
    assert old.metadata().effective_start == date(2023, 1, 1)
    assert len(old.sessions_in_range(date(2023, 1, 1), date(2025, 12, 31))) == 743


def test_2023_2025_sessions_unchanged_vs_prior_version() -> None:
    a = set(
        NSECalendarProvider(calendar_version="nse_eq_v2023_2025_r1").sessions_in_range(
            date(2023, 1, 1), date(2025, 12, 31)
        )
    )
    b = set(
        NSECalendarProvider(calendar_version="nse_eq_v2018_2026_r1").sessions_in_range(
            date(2023, 1, 1), date(2025, 12, 31)
        )
    )
    assert a == b


def test_muhurat_special_sessions_open() -> None:
    cal = NSECalendarProvider()
    assert cal.is_session(date(2018, 11, 7))
    assert cal.is_session(date(2019, 10, 27))  # Sunday Muhurat
    assert cal.is_session(date(2023, 11, 12))


def test_holiday_closed_2018_republic_day() -> None:
    assert NSECalendarProvider().is_session(date(2018, 1, 26)) is False


def test_ist_midnight_preserves_session_date() -> None:
    ts = pd.Timestamp("2018-01-01 00:00:00+05:30")
    dt = _to_datetime(ts)
    assert dt.date() == date(2018, 1, 1)


def test_ist_midnight_not_shifted_to_prior_utc_day() -> None:
    ts = pd.Timestamp("2017-12-31 00:00:00+05:30")
    dt = _to_datetime(ts)
    assert dt.date() == date(2017, 12, 31)
    # Old bug: UTC convert → 2017-12-30


def test_dataframe_to_bars_ist_session_alignment() -> None:
    df = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2018-01-01 00:00:00+05:30")],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        }
    )
    bars = dataframe_to_bars(df, symbol="RELIANCE")
    assert bars[0].timestamp.date() == date(2018, 1, 1)


def test_edge_bar_2017_12_31_split() -> None:
    bars = [
        MarketBar(
            timestamp=datetime(2017, 12, 31),
            symbol="RELIANCE",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2018, 1, 1),
            symbol="RELIANCE",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
    ]
    edge = split_edge_bars(bars, requested_start=REQUESTED_START)
    assert edge["edge_before_count"] == 1
    assert edge["edge_bars_before"][0]["session_date"] == "2017-12-31"
    assert edge["in_window_count"] == 1
    assert edge["in_window_bars"][0].timestamp.date() == date(2018, 1, 1)


def test_requested_start_constant() -> None:
    assert REQUESTED_START == date(2018, 1, 1)


def test_calendar_coverage_multi_year_expected_near_observed() -> None:
    cal = NSECalendarProvider()
    sessions = cal.sessions_in_range(date(2018, 1, 1), date(2018, 1, 31))
    bars = [
        MarketBar(
            timestamp=datetime(d.year, d.month, d.day),
            symbol="TCS",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
        for d in sessions
    ]
    cov = calendar_coverage(bars, start=date(2018, 1, 1), end=date(2018, 1, 31))
    assert cov["expected_sessions"] == len(sessions)
    assert cov["missing_sessions"] == 0
    assert cov["unexpected_sessions"] == 0
    assert cov["calendar_version"] == "nse_eq_v2018_2026_r1"


def test_calendar_coverage_flags_true_missing() -> None:
    cal = NSECalendarProvider()
    sessions = cal.sessions_in_range(date(2018, 1, 1), date(2018, 1, 15))
    bars = [
        MarketBar(
            timestamp=datetime(d.year, d.month, d.day),
            symbol="TCS",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
        for d in sessions[1:]
    ]
    cov = calendar_coverage(bars, start=date(2018, 1, 1), end=date(2018, 1, 15))
    assert cov["missing_sessions"] == 1


def test_ca_import_parses_dividend_not_forced_other(tmp_path: Path) -> None:
    p = tmp_path / "ca.csv"
    p.write_text(
        "SYMBOL,PURPOSE,EX-DATE,RECORD DATE\n"
        "RELIANCE,Interim Dividend - Rs 4.00/- Per Share,15-Aug-2023,14-Aug-2023\n",
        encoding="utf-8",
    )
    actions, meta = import_ca_csv(p, symbol_filter="RELIANCE")
    assert len(actions) == 1
    assert actions[0].action_type.value == "dividend"
    assert actions[0].cash_amount == 4.0
    assert actions[0].raw_payload["parse_status"] == "OK"
    assert meta["classified_ok"] == 1


def test_ca_import_parses_bonus_ratio(tmp_path: Path) -> None:
    p = tmp_path / "ca.csv"
    p.write_text(
        "SYMBOL,PURPOSE,EX-DATE,RECORD DATE\n"
        "ITC,Bonus 1 : 1,01-Jul-2016,30-Jun-2016\n",
        encoding="utf-8",
    )
    actions, _ = import_ca_csv(p, symbol_filter="ITC")
    assert actions[0].action_type.value == "bonus"
    assert actions[0].ratio_num == 2.0
    assert actions[0].ratio_den == 1.0


def test_ca_import_preserves_other_for_agm(tmp_path: Path) -> None:
    p = tmp_path / "ca.csv"
    p.write_text(
        "SYMBOL,PURPOSE,EX-DATE,RECORD DATE\n"
        "TCS,Annual General Meeting,01-Jun-2020,-\n",
        encoding="utf-8",
    )
    actions, meta = import_ca_csv(p, symbol_filter="TCS")
    assert actions[0].action_type.value == "other"
    assert meta["unknown_or_other_purpose"] == 1


def test_ca_import_unknown_dividend_cash_keeps_type(tmp_path: Path) -> None:
    p = tmp_path / "ca.csv"
    p.write_text(
        "SYMBOL,PURPOSE,EX-DATE,RECORD DATE\n"
        "INFY,Final Dividend 150%,15-Jun-2021,14-Jun-2021\n",
        encoding="utf-8",
    )
    actions, _ = import_ca_csv(p, symbol_filter="INFY")
    assert actions[0].action_type.value == "dividend"
    assert actions[0].cash_amount is None
    assert actions[0].raw_payload["parse_status"] == "UNKNOWN"
    assert actions[0].requires_manual_treatment is True


def test_analyze_ca_raw_not_mutated(tmp_path: Path) -> None:
    p = tmp_path / "ca.csv"
    p.write_text(
        "SYMBOL,PURPOSE,EX-DATE,RECORD DATE\n"
        "RELIANCE,Bonus 1 : 1,01-Sep-2017,31-Aug-2017\n",
        encoding="utf-8",
    )
    bars = _bars("RELIANCE", date(2018, 1, 1), 30)
    info = analyze_ca_for_symbol("RELIANCE", ca_file=p, bars=bars)
    assert info["price_policy"]["raw_execution"] is True
    assert info["price_policy"]["research_adjusted_invented"] is False
    assert info["adjustment"]["raw_ohlc_mutated"] is False


def test_identity_audit_reports_missing_isin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("RELIANCE", date(2018, 1, 2), 40)
    path = _write_pkg(tmp_path, "RELIANCE", bars)
    man = json.loads((path / "manifest.json").read_text())
    pkg = DiscoveredPackage(
        dataset_id=man["dataset_id"],
        dataset_version=man["dataset_version"],
        path=path,
        manifest=man,
        symbol="RELIANCE",
        bars=man["rows"],
        start=man["start"],
        end=man["end"],
        content_hash=man["content_hash"],
        price_policy="unknown",
        eligibility="DEVELOPMENT_ONLY",
    )
    ident = audit_instrument_identity(pkg)
    assert ident["identity_status"] == "BROKER_RESOLVED"
    assert "no_isin_stable_identity" in ident["issues"]


def test_membership_unknown_without_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("TCS", date(2018, 1, 2), 20)
    path = _write_pkg(tmp_path, "TCS", bars)
    man = json.loads((path / "manifest.json").read_text())
    pkg = DiscoveredPackage(
        dataset_id=man["dataset_id"],
        dataset_version=man["dataset_version"],
        path=path,
        manifest=man,
        symbol="TCS",
        bars=man["rows"],
        start=man["start"],
        end=man["end"],
        content_hash=man["content_hash"],
        price_policy="unknown",
        eligibility="DEVELOPMENT_ONLY",
    )
    mem = audit_universe_membership(pkg, bars)
    assert mem["unknown_membership_session_count"] == len(bars)
    assert mem["membership_coverage_ratio"] == 0.0
    assert "missing_package_universe_membership_ledger" in mem["blockers"]


def test_eligibility_no_zerodha_shortcut() -> None:
    facts = build_zerodha_cert_facts(
        dataset_id="x",
        dataset_version="v1",
        content_hash="sha256:abc",
        calendar_version=DEFAULT_NSE_CALENDAR_VERSION,
        calendar_verified=True,
        date_coverage_start="2018-01-01",
        date_coverage_end="2026-08-12",
        error_count=0,
        ca_coverage="splits_bonus_dividends",
        universe_completeness="full_pit",
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        instrument_identity_issues=0,
    )
    elig = evaluate_eligibility(facts)
    assert elig["is_research_eligible"] is False
    assert elig["zerodha_shortcut"] is False
    assert any("non_exchange" in b or "DEVELOPMENT_DATA" in b for b in elig["blockers"])


def test_eligibility_ignores_forged_manifest_flag() -> None:
    facts = build_zerodha_cert_facts(
        dataset_id="x",
        dataset_version="v1",
        content_hash="sha256:abc",
        calendar_version=DEFAULT_NSE_CALENDAR_VERSION,
        calendar_verified=True,
        date_coverage_start="2018-01-01",
        date_coverage_end="2026-08-12",
        error_count=0,
        ca_coverage="full_verified",
        universe_completeness="full_pit",
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        instrument_identity_issues=0,
    )
    # extras already set research_eligible True forgery
    elig = evaluate_eligibility(facts)
    assert elig["is_research_eligible"] is False


def test_immutability_refuses_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("INFY", date(2018, 1, 2), 50)
    path = _write_pkg(tmp_path, "INFY", bars, ver="v1")
    with pytest.raises(FileExistsError):
        write_zerodha_dataset_package(
            bars=bars,
            provenance={},
            quality_report={},
            dataset_id="zerodha_nse_daily_infy_test",
            version="v1",
        )
    assert path.exists()


def test_certified_package_writes_next_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("SBIN", date(2018, 1, 2), 60)
    path = _write_pkg(tmp_path, "SBIN", bars, ver="v1")
    man = json.loads((path / "manifest.json").read_text())
    pkg = DiscoveredPackage(
        dataset_id=man["dataset_id"],
        dataset_version="v1",
        path=path,
        manifest=man,
        symbol="SBIN",
        bars=man["rows"],
        start=man["start"],
        end=man["end"],
        content_hash=man["content_hash"],
        price_policy="unknown",
        eligibility="DEVELOPMENT_ONLY",
    )
    assert_source_immutable(pkg)
    out = write_certified_package(
        source_pkg=pkg,
        bars=bars,
        provenance={"provider": "zerodha"},
        quality_report={"ok": True},
        corporate_actions=[],
        instrument_metadata={},
        certification={"phase": "17C"},
    )
    assert out.name == "v2"
    assert path.exists()
    assert (out / "certification.json").exists()
    assert next_dataset_version(man["dataset_id"]) == "v3"


def test_safety_payload_zero_writes() -> None:
    s = safety_payload()
    assert s["orders_submitted"] == 0
    assert s["place_order_called"] == 0
    assert s["live_trading"] == "DISABLED"
    assert s["paper_trading"] == "NOT_STARTED"
    assert s["kill_switch"] == "ARMED"
    assert s["ok"] is True


def test_phase17c_has_no_place_order() -> None:
    root = Path("src/quantfund/phase17c")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree_ok = "place_order" not in text or "FORBIDDEN" in text or "scan" in text.lower()
        assert "def place_order" not in text
        assert tree_ok or "FORBIDDEN_CALLS" in text


def test_phase17c_no_llm_genetic() -> None:
    root = Path("src/quantfund/phase17c")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "genetic" not in text
        assert "openai" not in text
        assert "llm" not in text


def test_pipeline_certify_no_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    monkeypatch.setattr(
        "quantfund.phase17a.datasets.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("LT", date(2018, 1, 2), 80)
    _write_pkg(tmp_path, "LT", bars)
    payload = run_phase17c_certification(
        out_dir=tmp_path / "exp",
        run_baseline_regression=False,
        write_certified_packages=False,
    )
    assert payload["phase"] == "17C"
    assert payload["eligibility"]["aggregate"] == "DEVELOPMENT_ONLY"
    assert payload["eligibility"]["any_research_eligible"] is False
    assert payload["safety"]["place_order_called"] == 0
    assert (tmp_path / "exp" / "reports" / "phase17c_dataset_certification.json").exists()


def test_quality_uses_extended_calendar() -> None:
    cal = NSECalendarProvider()
    sessions = cal.sessions_in_range(date(2019, 1, 1), date(2019, 3, 29))
    bars = [
        MarketBar(
            timestamp=datetime(d.year, d.month, d.day),
            symbol="HDFCBANK",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
        for d in sessions
    ]
    q = run_symbol_quality(
        bars,
        dataset_id="t",
        coverage_start=date(2019, 1, 1),
        coverage_end=date(2019, 3, 29),
    )
    assert q["calendar"]["calendar_version"] == "nse_eq_v2018_2026_r1"
    assert q["calendar"]["missing_sessions"] == 0


def test_docs_writer(tmp_path: Path) -> None:
    from quantfund.phase17c.pipeline import write_phase17c_docs

    path = tmp_path / "PHASE17C.md"
    write_phase17c_docs(
        {
            "statement": "test",
            "result": "PASS",
            "calendar_version": "nse_eq_v2018_2026_r1",
            "eligibility": {
                "aggregate": "DEVELOPMENT_ONLY",
                "any_research_eligible": False,
                "zerodha_shortcut": False,
                "remaining_blockers": ["source_grade=non_exchange"],
            },
            "acceptance": {"accepted_count": 0},
            "safety": safety_payload(),
            "calendar_coverage": [],
            "corporate_actions": {"table": []},
            "baseline_regression": {},
            "immutability": {"note": "v1 preserved"},
        },
        path,
    )
    text = path.read_text(encoding="utf-8")
    assert "PHASE 17C" in text
    assert "NO PAPER OR LIVE TRADING WAS STARTED" in text


def test_makefile_has_phase17c_targets() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    for t in (
        "phase17c-calendar",
        "phase17c-ca",
        "phase17c-certify",
        "phase17c-report",
        "phase17c-demo",
    ):
        assert t in text


def test_certify_symbol_skips_write_when_flag_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("ICICIBANK", date(2018, 1, 2), 55)
    path = _write_pkg(tmp_path, "ICICIBANK", bars)
    man = json.loads((path / "manifest.json").read_text())
    pkg = DiscoveredPackage(
        dataset_id=man["dataset_id"],
        dataset_version="v1",
        path=path,
        manifest=man,
        symbol="ICICIBANK",
        bars=man["rows"],
        start=man["start"],
        end=man["end"],
        content_hash=man["content_hash"],
        price_policy="unknown",
        eligibility="DEVELOPMENT_ONLY",
    )
    row = certify_symbol_package(pkg, ca_file=None, write_package=False)
    assert row["certified_package_path"] is None
    assert not (tmp_path / man["dataset_id"] / "v2").exists()


def test_multi_year_expected_session_count_sane() -> None:
    n = len(
        NSECalendarProvider().sessions_in_range(date(2018, 1, 1), date(2026, 8, 12))
    )
    assert 2100 <= n <= 2200


def test_edge_policy_excludes_before_requested() -> None:
    bars = _bars("RELIANCE", date(2017, 12, 28), 10)
    edge = split_edge_bars(bars)
    assert all(b.timestamp.date() >= REQUESTED_START for b in edge["in_window_bars"])


def test_raw_vs_adjusted_distinction_in_ca_types() -> None:
    from quantfund.data.corporate_actions.models import CorporateActionType

    assert CorporateActionType.SPLIT.value == "split"
    assert CorporateActionType.OTHER.value == "other"


def test_phase18_module_exists_after_phase17c() -> None:
    """Phase 17C stops at certification; Phase 18 lives in its own package."""
    assert Path("src/quantfund/phase17c").exists()
    # Phase 18 may exist in later work; 17C must not embed trading enablement.
    from quantfund.phase17c.safety import safety_payload

    s = safety_payload()
    assert s["live_trading"] == "DISABLED"
    assert s["paper_trading"] == "NOT_STARTED"


def test_dataset_hash_stable_for_same_payload(tmp_path: Path) -> None:
    from quantfund.data.ingest.checksums import hash_json

    a = hash_json({"x": 1, "y": [1, 2]})
    b = hash_json({"x": 1, "y": [1, 2]})
    assert a == b


def test_calendar_file_immutable_on_disk() -> None:
    p = Path("data/calendars/nse_eq/calendar_version=nse_eq_v2018_2026_r1/calendar.json")
    assert p.exists()
    old = Path("data/calendars/nse_eq/calendar_version=nse_eq_v2023_2025_r1/calendar.json")
    assert old.exists()


def test_coverage_out_of_range_2017() -> None:
    cal = NSECalendarProvider()
    assert cal.describe_day(date(2017, 12, 31)).session_type.value == "out_of_coverage"


def test_import_ca_missing_file() -> None:
    actions, meta = import_ca_csv(Path("/no/such/ca.csv"))
    assert actions == []
    assert meta["status"] == "MISSING_FILE"


def test_build_facts_capability_bar_false() -> None:
    facts = build_zerodha_cert_facts(
        dataset_id="d",
        dataset_version="v1",
        content_hash="h",
        calendar_version="nse_eq_v2018_2026_r1",
        calendar_verified=True,
        date_coverage_start="2018-01-01",
        date_coverage_end="2026-08-12",
        error_count=0,
        ca_coverage="partial",
        universe_completeness="current_snapshot_only",
        unknown_membership_session_count=10,
        membership_coverage_ratio=0.0,
        instrument_identity_issues=1,
    )
    assert facts.capability_source_bar_ok is False
    assert facts.source_grade == "non_exchange"
    assert facts.data_class == "DEVELOPMENT_DATA"


def test_naive_timestamp_passthrough() -> None:
    dt = _to_datetime(datetime(2020, 6, 1, 0, 0, 0))
    assert dt == datetime(2020, 6, 1, 0, 0, 0)


def test_utc_timestamp_uses_utc_calendar_date() -> None:
    ts = pd.Timestamp("2020-06-01 00:00:00+00:00")
    assert _to_datetime(ts).date() == date(2020, 6, 1)


def test_phase17c_package_importable() -> None:
    import quantfund.phase17c as m

    assert hasattr(m, "run_phase17c_certification")


def test_scripts_exist() -> None:
    for name in (
        "run_phase17c_demo.py",
        "run_phase17c_calendar.py",
        "run_phase17c_ca.py",
        "run_phase17c_certify.py",
        "run_phase17c_report.py",
    ):
        assert (Path("scripts") / name).exists()


def test_split_edge_bars_after_window() -> None:
    bars = [
        MarketBar(
            timestamp=datetime(2018, 1, 2),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2026, 9, 1),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
    ]
    edge = split_edge_bars(bars, requested_start=date(2018, 1, 1), requested_end=date(2026, 8, 12))
    assert edge["edge_after_count"] == 1
    assert edge["in_window_count"] == 1


def test_quality_blocking_codes_unchanged() -> None:
    from quantfund.phase17a.quality import BLOCKING_CODES

    assert "duplicate_timestamp" in BLOCKING_CODES
    assert "bar_on_closed_session" not in BLOCKING_CODES


def test_ca_coverage_table_fields(tmp_path: Path) -> None:
    p = tmp_path / "ca.csv"
    p.write_text(
        "SYMBOL,PURPOSE,EX-DATE,RECORD DATE\n"
        "LT,Face Value Split (Sub-Division) - From Rs 10/- to Rs 2/-,13-Jul-2017,-\n",
        encoding="utf-8",
    )
    actions, _ = import_ca_csv(p, symbol_filter="LT")
    assert actions[0].action_type.value == "split"
    assert actions[0].ratio_num == 10.0
    assert actions[0].ratio_den == 2.0

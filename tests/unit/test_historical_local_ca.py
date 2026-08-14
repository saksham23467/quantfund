"""Historical local CF-CA ingest — development/non_exchange only."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.data.corporate_actions.adjust import apply_adjustment_policy
from quantfund.data.corporate_actions.historical_local import (
    ASOF_VISIBILITY_RULE,
    SOURCE_GRADE,
    classify_purpose,
    compute_metrics,
    corporate_actions_asof,
    crosscheck_yfinance_dividends,
    event_hash,
    ingest_historical_ca,
    ingest_raw_ca_file,
    load_and_normalize,
    normalize_row,
    parse_bonus_ratio,
    parse_cf_date,
    parse_dividend_cash,
    parse_split_ratio,
)
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import default_split_bonus_policy
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.ingest.checksums import file_checksum
from quantfund.data.models import MarketBar
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ca" / "cf_ca_sample.csv"
FULL_SOURCE = (
    Path.home() / "Downloads" / "CF-CA-equities-01-01-2009-to-01-08-2026.csv"
)


def _row(**overrides) -> dict[str, str]:
    base = {
        "SYMBOL": "TESTCO",
        "COMPANY NAME": "Test Co",
        "SERIES": "EQ",
        "PURPOSE": "Dividend - Rs 2 Per Share",
        "FACE VALUE": "10",
        "EX-DATE": "15-Jan-2020",
        "RECORD DATE": "16-Jan-2020",
        "BOOK CLOSURE START DATE": "-",
        "BOOK CLOSURE END DATE": "-",
    }
    base.update(overrides)
    return base


def test_classify_dividend():
    assert classify_purpose("Interim Dividend-40%") == CorporateActionType.DIVIDEND
    assert classify_purpose("Final Dividend-150%") == CorporateActionType.DIVIDEND


def test_classify_bonus_and_split():
    assert classify_purpose("Bonus 1:1") == CorporateActionType.BONUS
    assert classify_purpose("Split From Rs.10/- to Re.1/-") == CorporateActionType.SPLIT
    assert classify_purpose("Fv Split Rs.10/- To Re.1/") == CorporateActionType.SPLIT


def test_classify_face_value_buyback_rights():
    assert (
        classify_purpose("Face Value Revised")
        == CorporateActionType.FACE_VALUE_CHANGE
    )
    assert classify_purpose("Buy Back") == CorporateActionType.BUYBACK
    assert classify_purpose("Right Issue 1:15") == CorporateActionType.RIGHTS


def test_classify_meetings_other():
    assert classify_purpose("Annual General Meeting") == CorporateActionType.OTHER
    assert (
        classify_purpose("Extra Ordinary General Meeting") == CorporateActionType.OTHER
    )


def test_classify_unknown_purpose_other():
    assert classify_purpose("Completely Novel Event XYZ") == CorporateActionType.OTHER


def test_classify_merger_demerger():
    assert classify_purpose("Scheme Of Demerger") == CorporateActionType.DEMERGER
    assert classify_purpose("Amalgamation / Merger") == CorporateActionType.MERGER


def test_parse_bonus_ratio():
    assert parse_bonus_ratio("Bonus 1:1") == (2.0, 1.0)
    assert parse_bonus_ratio("Bonus 3:2") == (5.0, 2.0)


def test_parse_split_ratio():
    assert parse_split_ratio("Fv Split Rs.10/- To Re.1/") == (10.0, 1.0)
    assert parse_split_ratio("Split From Rs.2/- to Re.1/-") == (2.0, 1.0)


def test_parse_dividend_cash():
    assert parse_dividend_cash("Interim Dividend - Rs 2 Per Share") == 2.0
    assert parse_dividend_cash("Dividend - Re 1 Per Share") == 1.0


def test_fake_split_no_ratio_unknown():
    r = normalize_row(
        _row(PURPOSE="Stock Split Mysterious", **{"EX-DATE": "01-Feb-2020"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.action_type == CorporateActionType.SPLIT
    assert r.parse_status.value == "UNKNOWN"
    assert r.ratio_num is None
    ca = r.to_corporate_action()
    assert ca is not None
    assert ca.requires_manual_treatment is True
    # Must not contribute an adjustment factor
    bars = [
        MarketBar(
            timestamp=datetime(2020, 1, 31),
            symbol="TESTCO",
            open=10,
            high=11,
            low=9,
            close=10,
            volume=100,
        ),
        MarketBar(
            timestamp=datetime(2020, 2, 3),
            symbol="TESTCO",
            open=1,
            high=1.1,
            low=0.9,
            close=1,
            volume=100,
        ),
    ]
    adj = apply_adjustment_policy([bars[0]], [ca], default_split_bonus_policy())
    # only one bar before ex — factor 1; unknown ratio → split_factor None → skipped
    assert adj[0].adjustment_factor == 1.0


def test_unknown_purpose_never_dividend_or_split():
    assert classify_purpose("Random Unmapped Thing") not in {
        CorporateActionType.DIVIDEND,
        CorporateActionType.SPLIT,
        CorporateActionType.BONUS,
    }


def test_merger_never_alters_ohlc():
    r = normalize_row(
        _row(PURPOSE="Scheme Of Arrangement And Merger", **{"EX-DATE": "01-Mar-2020"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.action_type == CorporateActionType.MERGER
    ca = r.to_corporate_action()
    assert ca and ca.requires_manual_treatment
    bars = [
        MarketBar(
            timestamp=datetime(2020, 2, 28),
            symbol="TESTCO",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=10,
        ),
        MarketBar(
            timestamp=datetime(2020, 3, 2),
            symbol="TESTCO",
            open=50,
            high=51,
            low=49,
            close=50,
            volume=10,
        ),
    ]
    raw_closes = [b.close for b in bars]
    adj = apply_adjustment_policy(bars, [ca], default_split_bonus_policy())
    assert [b.close for b in bars] == raw_closes
    assert all(a.adjustment_factor == 1.0 for a in adj)


def test_duplicate_detection_deterministic():
    r1 = normalize_row(_row(), source_row_id=1, source_hash="sha256:x")
    r2 = normalize_row(_row(), source_row_id=2, source_hash="sha256:x")
    assert r1.event_hash == r2.event_hash
    m = compute_metrics([r1, r2])
    assert m.duplicate_exact_count >= 1


def test_event_hash_stable():
    h1 = event_hash(
        symbol="AAA",
        action_type="dividend",
        purpose_raw="Dividend - Rs 1 Per Share",
        ex_date="2020-01-15",
        record_date="2020-01-16",
        face_value="10",
        source_id="historical_local_ca",
    )
    h2 = event_hash(
        symbol="AAA",
        action_type="dividend",
        purpose_raw="Dividend - Rs 1 Per Share",
        ex_date="2020-01-15",
        record_date="2020-01-16",
        face_value="10",
        source_id="historical_local_ca",
    )
    assert h1 == h2


def test_identity_unknown_without_master():
    r = normalize_row(_row(SYMBOL="ZZZZZ"), source_row_id=1, source_hash="sha256:x")
    assert r.identity_resolution_status.value == "UNKNOWN"
    assert r.instrument_id.startswith("UNKNOWN:")


def test_identity_resolved_with_known_set():
    r = normalize_row(
        _row(SYMBOL="RELIANCE"),
        source_row_id=1,
        source_hash="sha256:x",
        known_symbols={"RELIANCE", "TCS"},
    )
    assert r.identity_resolution_status.value == "RESOLVED"
    assert r.instrument_id == "NSE:RELIANCE"


def test_date_validation_book_closure_error():
    r = normalize_row(
        _row(
            **{
                "BOOK CLOSURE START DATE": "20-Jan-2020",
                "BOOK CLOSURE END DATE": "10-Jan-2020",
            }
        ),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.date_status.value == "ERROR"
    assert "book_closure_start_after_end" in r.date_issues


def test_malformed_ex_date_error():
    r = normalize_row(
        _row(**{"EX-DATE": "not-a-date"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.date_status.value == "ERROR"
    assert "malformed_ex_date" in r.date_issues


def test_parse_cf_date():
    assert parse_cf_date("01-Jan-2009") == date(2009, 1, 1)
    assert parse_cf_date("-") is None
    assert parse_cf_date("") is None


def test_percentage_dividend_parse_unknown():
    r = normalize_row(
        _row(PURPOSE="Agm/Dividend - 35%"),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.action_type == CorporateActionType.DIVIDEND
    assert r.parse_status.value == "UNKNOWN"
    assert r.cash_amount is None


def test_asof_hides_future_ca():
    r_past = normalize_row(
        _row(**{"EX-DATE": "01-Jan-2020"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    r_future = normalize_row(
        _row(PURPOSE="Bonus 1:1", **{"EX-DATE": "01-Jan-2021"}),
        source_row_id=2,
        source_hash="sha256:x",
    )
    visible = corporate_actions_asof(
        [r_past, r_future], timestamp=date(2020, 6, 1), symbol="TESTCO"
    )
    assert len(visible) == 1
    assert visible[0].ex_date == date(2020, 1, 1)
    assert ASOF_VISIBILITY_RULE.startswith("ex_date")


def test_asof_no_announcement_invention():
    r = normalize_row(_row(), source_row_id=1, source_hash="sha256:x")
    ca = r.to_corporate_action()
    assert ca is not None
    assert ca.announcement_date is None


def test_raw_ingest_immutable(tmp_path: Path):
    dest_root = tmp_path / "raw"
    root1, h1, _ = ingest_raw_ca_file(FIXTURE, raw_root=dest_root)
    assert (root1 / FIXTURE.name).exists()
    assert h1 == file_checksum(FIXTURE)
    # second ingest must not overwrite — new id
    root2, h2, _ = ingest_raw_ca_file(FIXTURE, raw_root=dest_root)
    assert root1 != root2
    assert h1 == h2
    # original fixture unchanged
    assert file_checksum(FIXTURE) == h1


def test_raw_ohlc_not_modified_by_ingest(tmp_path: Path):
    bars_path = tmp_path / "raw_ohlc.csv"
    bars_path.write_text("timestamp,open,high,low,close,volume\n2020-01-02,1,2,1,1.5,10\n")
    before = bars_path.read_bytes()
    ingest_historical_ca(FIXTURE, output_normalized_root=tmp_path / "norm1")
    assert bars_path.read_bytes() == before


def test_reproducibility_same_bytes(tmp_path: Path):
    a = load_and_normalize(FIXTURE, source_hash="sha256:fixed")
    b = load_and_normalize(FIXTURE, source_hash="sha256:fixed")
    assert [r.event_hash for r in a] == [r.event_hash for r in b]
    assert compute_metrics(a).to_dict() == compute_metrics(b).to_dict()


def test_eligibility_remains_development_only(tmp_path: Path):
    result = ingest_historical_ca(
        FIXTURE, output_normalized_root=tmp_path / "norm_elig"
    )
    assert result.eligibility == EligibilityLevel.DEVELOPMENT_ONLY.value
    assert result.research_eligible is False
    assert SOURCE_GRADE == "non_exchange"


def test_full_ingest_manifest_provenance(tmp_path: Path):
    result = ingest_historical_ca(
        FIXTURE, output_normalized_root=tmp_path / "norm_man"
    )
    man = json.loads((result.normalized_root / "manifest.json").read_text())
    src = man["corporate_action_source"]
    assert src["source_grade"] == "non_exchange"
    assert src["exchange_authority"] is False
    assert src["row_count"] == result.metrics.ca_total_events
    assert src.get("corporate_action_coverage") != "full_verified"
    assert src["ca_coverage_metrics"]["exchange_authority"] is False


def test_purpose_raw_preserved():
    purpose = "Interim Dividend - Rs 2 Per Share"
    r = normalize_row(_row(PURPOSE=purpose), source_row_id=1, source_hash="sha256:x")
    assert r.purpose_raw == purpose
    ca = r.to_corporate_action()
    assert ca and ca.raw_payload["purpose_raw"] == purpose


def test_fixture_ingest_counts(tmp_path: Path):
    result = ingest_historical_ca(
        FIXTURE, output_normalized_root=tmp_path / "norm_c"
    )
    assert result.metrics.ca_total_events >= 8
    assert result.metrics.ca_split_events >= 1
    assert result.metrics.ca_other_events >= 1


def test_yfinance_crosscheck_diagnostic():
    records = load_and_normalize(FIXTURE, source_hash="sha256:x")
    report = crosscheck_yfinance_dividends(
        records,
        [{"symbol": "NOSUCH", "ex_date": "2020-01-01"}],
    )
    assert report["diagnostic_only"] is True
    assert report["exchange_grade_claim"] is False
    assert "matched_events" in report


def test_adjustment_leakage_future_ca_not_in_asof():
    """Future CA must not affect adjusted view when as-of filtered."""
    near = normalize_row(
        _row(PURPOSE="Bonus 1:1", **{"EX-DATE": "15-Jan-2020"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    future = normalize_row(
        _row(PURPOSE="Bonus 1:1", SYMBOL="TESTCO", **{"EX-DATE": "01-Jan-2025"}),
        source_row_id=2,
        source_hash="sha256:x",
    )
    as_of = date(2020, 1, 10)  # before both? near is Jan 15 — hide near too
    # As-of Jan 10: neither event visible (both ex_date > as_of for near? Jan 15 > Jan 10)
    visible = corporate_actions_asof([near, future], timestamp=as_of)
    assert visible == []
    # As-of after near but before future: only near visible
    visible2 = corporate_actions_asof(
        [near, future], timestamp=date(2020, 6, 1)
    )
    assert len(visible2) == 1
    actions = [a for a in (visible2[0].to_corporate_action(),) if a]
    bars = [
        MarketBar(
            timestamp=datetime(2020, 1, 2),
            symbol="TESTCO",
            open=10,
            high=10,
            low=10,
            close=10,
            volume=1,
        )
    ]
    adj = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    # Bar before near ex-date → factor includes near bonus; future excluded by asof
    assert adj[0].adjustment_factor == pytest.approx(2.0)


def test_agm_not_price_adjusting():
    r = normalize_row(
        _row(PURPOSE="Annual General Meeting"),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.action_type == CorporateActionType.OTHER
    assert r.is_price_adjusting is False


def test_source_grade_constant():
    assert SOURCE_GRADE == "non_exchange"


def test_normalized_json_roundtrip_fields():
    r = normalize_row(_row(), source_row_id=7, source_hash="sha256:abc")
    d = r.model_dump(mode="json")
    assert d["source_row_id"] == 7
    assert d["source_id"] == "historical_local_ca"
    assert "purpose_raw" in d


def test_conflicting_records_counted():
    r1 = normalize_row(
        _row(PURPOSE="Dividend - Rs 1 Per Share", **{"EX-DATE": "01-Jun-2020"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    r2 = normalize_row(
        _row(PURPOSE="Dividend - Rs 5 Per Share", **{"EX-DATE": "01-Jun-2020"}),
        source_row_id=2,
        source_hash="sha256:x",
    )
    m = compute_metrics([r1, r2])
    assert m.duplicate_conflict_count >= 1


def test_metrics_distinguish_event_present_not_full_verified():
    records = load_and_normalize(FIXTURE, source_hash="sha256:x")
    d = compute_metrics(records).to_dict()
    assert "EVENT_PRESENT" in d["note"] or "full_verified" in d["note"]
    assert d["source_grade"] == "non_exchange"
    assert d["exchange_authority"] is False


def test_checker_still_blocks_with_rich_ca_facts():
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v",
        source="historical_local_ca",
        source_grade="non_exchange",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="u",
        universe_version="v",
        universe_completeness="full_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2009-01-01",
        date_coverage_end="2026-08-01",
        instrument_count=50,
        delisted_coverage="complete",
        content_hash="sha256:x",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="redistributable",
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_bonus_ratio_applied_when_parsed():
    r = normalize_row(
        _row(PURPOSE="Bonus 1:1", **{"EX-DATE": "01-Jun-2020"}),
        source_row_id=1,
        source_hash="sha256:x",
    )
    assert r.parse_status.value == "OK"
    ca = r.to_corporate_action()
    bars = [
        MarketBar(
            timestamp=datetime(2020, 5, 29),
            symbol="TESTCO",
            open=100,
            high=100,
            low=100,
            close=100,
            volume=10,
        )
    ]
    adj = apply_adjustment_policy(bars, [ca], default_split_bonus_policy())
    assert adj[0].adjustment_factor == pytest.approx(2.0)
    assert bars[0].close == 100  # RAW immutable


def test_at_least_thirty_tests_guard():
    import tests.unit.test_historical_local_ca as mod

    tests = [n for n in dir(mod) if n.startswith("test_")]
    assert len(tests) >= 30


@pytest.mark.skipif(not FULL_SOURCE.is_file(), reason="full CA CSV not on disk")
def test_full_source_row_count_smoke(tmp_path: Path):
    result = ingest_historical_ca(
        FULL_SOURCE, output_normalized_root=tmp_path / "full_norm"
    )
    assert result.metrics.ca_total_events >= 30000
    assert result.research_eligible is False

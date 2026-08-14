"""Real research package integration — adversarial + wiring tests (≥30).

Does not weaken eligibility. Synthetic/yfinance remain DEVELOPMENT_ONLY.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from quantfund.data.certification import facts_hash, write_certification, certify
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.ingest.checksums import directory_checksum, write_checksums
from quantfund.data.packages.membership import (
    discover_package_membership_path,
    resolve_package_universe,
)
from quantfund.data.packages.vendor_import import (
    deterministic_package_identity,
    materialize_research_package,
    write_package_json,
)
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.providers.package_validator import validate_research_package
from quantfund.research.certify_package import (
    certify_research_package,
    reverify_certification_artifact,
)


FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"
)


def _bars_csv(path: Path, symbol: str = "AAA") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["timestamp,open,high,low,close,volume"]
    # Use known NSE open days in 2024
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    for d in days:
        lines.append(f"{d}T00:00:00Z,100,101,99,100.5,1000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _instrument(symbol: str = "AAA", **kw):
    base = {
        "symbol": symbol,
        "instrument_id": f"NSE:{symbol}",
        "exchange": "NSE",
        "currency": "INR",
        "listing_date": "2020-01-01",
        "symbol_history": [],
    }
    base.update(kw)
    return base


def _membership_json(path: Path, symbols: list[str], *, future_leak: bool = False):
    memberships = []
    for s in symbols:
        memberships.append(
            {
                "universe_id": "nifty50",
                "instrument_id": f"NSE:{s}",
                "symbol": s,
                "member_from": "2024-01-01",
                "member_to": None,
                "source": "test",
                "verification_status": "verified",
            }
        )
    if future_leak:
        memberships.append(
            {
                "universe_id": "nifty50",
                "instrument_id": "NSE:FUTURE",
                "symbol": "FUTURE",
                "member_from": "2099-01-01",
                "member_to": None,
                "source": "test",
                "verification_status": "verified",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "completeness": "partial_pit",
                "verification_status": "verified",
                "source": "test",
                "memberships": memberships,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _make_pkg(
    tmp_path: Path,
    *,
    source_grade: str = "paid",
    exchange_authority: bool = True,
    license_status: str = "internal_research_only",
    synthetic: bool = False,
    with_membership: bool = True,
    with_terminal: bool = True,
    with_ca: bool = True,
    extras: dict | None = None,
    name: str = "pkg",
) -> Path:
    root = tmp_path / name
    bars = tmp_path / f"{name}_bars"
    bars.mkdir(exist_ok=True)
    bar = _bars_csv(bars / "AAA.csv")
    mem = None
    if with_membership:
        mem = _membership_json(tmp_path / f"{name}_mem.json", ["AAA"])
    instruments = [_instrument("AAA")]
    if with_terminal:
        instruments[0]["delisting_date"] = None
    cas = []
    if with_ca:
        cas = [
            {
                "action_id": "s1",
                "instrument_id": "NSE:AAA",
                "symbol": "AAA",
                "action_type": "split",
                "ex_date": "2023-06-01",
                "ratio_num": 2.0,
                "ratio_den": 1.0,
                "source": "test",
                "verified": True,
            },
            {
                "action_id": "b1",
                "instrument_id": "NSE:AAA",
                "symbol": "AAA",
                "action_type": "bonus",
                "ex_date": "2023-07-01",
                "ratio_num": 1.0,
                "ratio_den": 1.0,
                "source": "test",
                "verified": True,
            },
            {
                "action_id": "d1",
                "instrument_id": "NSE:AAA",
                "symbol": "AAA",
                "action_type": "dividend",
                "ex_date": "2023-08-01",
                "cash_amount": 5.0,
                "source": "test",
                "verified": True,
            },
        ]
    terminals = []
    if with_terminal:
        terminals = [
            {
                "event_id": "t1",
                "instrument_id": "NSE:DEAD",
                "symbol": "DEAD",
                "event_type": "delisting",
                "event_date": "2023-12-01",
                "last_trade_date": "2023-11-30",
                "source": "test",
                "verification_status": "verified",
            }
        ]
        instruments.append(
            _instrument("DEAD", delisting_date="2023-12-01", listing_date="2010-01-01")
        )
        # no bars for DEAD — ok

    materialize_research_package(
        root,
        package_id=f"test_{name}",
        package_version="v1",
        provider="test_vendor",
        source_grade=source_grade,
        license_status=license_status,
        instruments=instruments,
        bars_by_symbol={"AAA": bar},
        corporate_actions=cas if with_ca else [],
        terminal_events=terminals if with_terminal else [],
        membership_file=mem,
        exchange_authority=exchange_authority,
        synthetic=synthetic,
        write_checksums=True,
    )
    if extras:
        meta_path = root / "package.json"
        meta = json.loads(meta_path.read_text())
        meta.update(extras)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        # invalidate checksums after edit
        write_checksums(root, label="package")
    return root


# --- Adversarial / gate tests ---


def test_forged_research_eligible_rejected_by_validator(tmp_path: Path):
    root = _make_pkg(tmp_path)
    meta = json.loads((root / "package.json").read_text())
    meta["research_eligible"] = True
    (root / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    v = validate_research_package(root)
    assert v.valid is False
    assert any(e.code == "eligibility_assertion_forbidden" for e in v.errors)


def test_forged_completeness_in_manifest_ignored_for_eligibility(tmp_path: Path):
    """Manifest booleans are not eligibility authority (extras path)."""
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="vendor",
        source_grade="synthetic",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="v",
        universe_completeness="full_pit",
        corporate_action_coverage="full_verified",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-05",
        instrument_count=1,
        delisted_coverage="complete",
        content_hash="sha256:x",
        error_count=0,
        capability_source_bar_ok=False,
        provenance_complete=True,
        license_status="internal_research_only",
        extras={"research_eligible": True, "synthetic": True},
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("Ignored" in n or "ignored" in n.lower() for n in d.notes) or d.blockers


def test_altered_checksum_fails_validation(tmp_path: Path):
    root = _make_pkg(tmp_path)
    (root / "checksums.sha256").write_text("package sha256:deadbeef\n", encoding="utf-8")
    v = validate_research_package(root)
    assert v.valid is False
    assert any(e.code == "checksum_mismatch" for e in v.errors)


def test_discover_package_membership(tmp_path: Path):
    root = _make_pkg(tmp_path)
    assert discover_package_membership_path(root) is not None


def test_resolve_package_universe_uses_package_membership(tmp_path: Path):
    root = _make_pkg(tmp_path)
    provider = LocalResearchPackageProvider(root, validate=False, allow_invalid=True)
    res = resolve_package_universe(
        root,
        instruments=provider.get_instruments(),
        start=date(2024, 1, 2),
        end=date(2024, 1, 5),
    )
    assert res.source == "package"
    assert res.audit is not None and res.audit.ok


def test_overlapping_membership_rejected(tmp_path: Path):
    root = _make_pkg(tmp_path, with_membership=False)
    mem = {
        "completeness": "partial_pit",
        "memberships": [
            {
                "universe_id": "nifty50",
                "instrument_id": "NSE:AAA",
                "symbol": "AAA",
                "member_from": "2024-01-01",
                "member_to": "2024-06-01",
                "source": "t",
                "verification_status": "verified",
            },
            {
                "universe_id": "nifty50",
                "instrument_id": "NSE:AAA",
                "symbol": "AAA",
                "member_from": "2024-05-01",
                "member_to": None,
                "source": "t",
                "verification_status": "verified",
            },
        ],
    }
    uni = root / "universe"
    uni.mkdir(exist_ok=True)
    (uni / "membership.json").write_text(json.dumps(mem), encoding="utf-8")
    write_checksums(root, label="package")
    v = validate_research_package(root)
    assert v.valid is False
    assert any(e.code == "invalid_membership" for e in v.errors)


def test_future_membership_leakage_quality_error(tmp_path: Path):
    root = _make_pkg(tmp_path, with_membership=False)
    _membership_json(root / "universe" / "membership.json", ["AAA"], future_leak=True)
    write_checksums(root, label="package")
    elig, facts, blockers, meta = certify_research_package(root)
    # Future membership should produce quality ERROR when asof_date pinned
    assert facts is not None
    assert (
        facts.error_count > 0
        or any("future_membership" in c for c in facts.quality_error_codes)
        or elig == "development_only"
    )


def test_missing_delisting_evidence_blocks_research(tmp_path: Path):
    root = _make_pkg(tmp_path, with_terminal=False)
    elig, facts, blockers, _ = certify_research_package(root)
    assert elig == "development_only"
    assert facts is None or facts.delisted_coverage in {"none", "unknown"} or any(
        "delisted" in b for b in blockers
    )


def test_incomplete_ca_blocks(tmp_path: Path):
    root = _make_pkg(tmp_path, with_ca=False)
    elig, facts, blockers, _ = certify_research_package(root)
    assert elig == "development_only"
    assert any("corporate_action" in b for b in blockers) or (
        facts and facts.corporate_action_coverage in {"none", "partial"}
    )


def test_synthetic_pretending_exchange_fails_validator(tmp_path: Path):
    with pytest.raises(ValueError, match="exchange_authority forbidden"):
        write_package_json(
            tmp_path / "bad",
            package_id="x",
            package_version="1",
            provider="x",
            source_grade="synthetic",
            license_status="redistributable",
            exchange_authority=True,
            synthetic=True,
        )


def test_synthetic_source_grade_development_only_on_pilot():
    elig, _, blockers, _ = certify_research_package(FIXTURE)
    assert elig == "development_only"
    assert any("synthetic" in b or "source_grade" in b for b in blockers)


def test_yfinance_capability_bar_false():
    from quantfund.data.providers.capabilities import (
        CoverageQuality,
        LicenseStatus,
        ProviderCapabilities,
    )
    from quantfund.data.grades import SourceGrade

    caps = ProviderCapabilities(
        provider_id="yfinance",
        provider_name="yfinance",
        source_grade=SourceGrade.NON_EXCHANGE,
        historical_depth="unknown",
        corporate_action_quality=CoverageQuality.UNKNOWN,
        delisted_coverage=CoverageQuality.NONE,
        universe_membership_quality=CoverageQuality.UNKNOWN,
        identity_coverage=CoverageQuality.UNKNOWN,
        exchange_authority=False,
        license_status=LicenseStatus.UNKNOWN,
    )
    assert caps.can_satisfy_research_eligibility_source_bar() is False


def test_invalid_license_unknown_blocks_eligibility():
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="vendor",
        source_grade="paid",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="v",
        universe_completeness="partial_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-05",
        instrument_count=1,
        delisted_coverage="partial",
        content_hash="sha256:x",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="unknown",
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("license" in b for b in d.blockers)


def test_duplicate_bars_block(tmp_path: Path):
    root = _make_pkg(tmp_path)
    # Append duplicate bar row
    bar = root / "bars" / "AAA.csv"
    bar.write_text(bar.read_text() + "2024-01-02T00:00:00Z,100,101,99,100.5,1000\n")
    write_checksums(root, label="package")
    # Provider/validate_bars may raise, or certify returns development_only
    try:
        elig, facts, blockers, _ = certify_research_package(root)
        assert elig == "development_only"
        assert facts is None or facts.duplicate_bars > 0 or facts.error_count > 0 or blockers
    except Exception as exc:  # noqa: BLE001 — fail-closed on duplicate timestamps
        assert "duplicate" in str(exc).lower()


def test_facts_hash_stable_for_same_facts():
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="vendor",
        source_grade="paid",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="v",
        universe_completeness="partial_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-05",
        instrument_count=1,
        delisted_coverage="partial",
        content_hash="sha256:x",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="internal_research_only",
    )
    assert facts_hash(facts) == facts_hash(facts)


def test_facts_hash_mismatch_detected(tmp_path: Path):
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="vendor",
        source_grade="paid",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="v",
        universe_completeness="partial_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-05",
        instrument_count=1,
        delisted_coverage="partial",
        content_hash="sha256:x",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="internal_research_only",
    )
    decision = certify(facts)
    path = write_certification(tmp_path / "cert.txt", facts=facts, decision=decision)
    # Tamper sidecar
    side = path.with_suffix(".json")
    raw = json.loads(side.read_text())
    raw["facts"]["error_count"] = 99
    side.write_text(json.dumps(raw), encoding="utf-8")
    from quantfund.data.certification import load_and_verify_certification

    _, ok = load_and_verify_certification(side)
    assert ok is False


def test_package_changed_after_certification_detected(tmp_path: Path):
    root = _make_pkg(tmp_path)
    elig, facts, blockers, meta = certify_research_package(
        root, write_cert_path=tmp_path / "out" / "cert.txt"
    )
    assert facts is not None
    # Mutate bars after cert
    bar = root / "bars" / "AAA.csv"
    bar.write_text(bar.read_text() + "2024-01-08T00:00:00Z,100,101,99,100,1\n")
    issues = reverify_certification_artifact(
        tmp_path / "out" / "cert.json", package_root=root
    )
    assert any("package_changed" in i or "recertify" in i or "hash" in i for i in issues) or issues


def test_deterministic_package_identity_stable(tmp_path: Path):
    root = _make_pkg(tmp_path)
    p = LocalResearchPackageProvider(root)
    a = p.package_identity()
    b = deterministic_package_identity(
        package_id="test_pkg",
        package_version="v1",
        content_hash=p.validation.content_hash if p.validation else "x",
    )
    assert a == b


def test_provider_membership_path(tmp_path: Path):
    root = _make_pkg(tmp_path)
    p = LocalResearchPackageProvider(root)
    assert p.membership_path() is not None


def test_unknown_membership_on_fixture_still_blocks():
    elig, facts, blockers, meta = certify_research_package(FIXTURE)
    assert elig == "development_only"
    assert facts is not None
    assert facts.unknown_membership_session_count > 0 or any(
        "unknown_membership" in b for b in blockers
    )


def test_certify_unconfigured_package():
    elig, facts, blockers, meta = certify_research_package(None)
    # When None, resolve env — typically unset
    assert elig == "development_only"
    assert facts is None or "research_package_not_configured" in blockers or meta.get(
        "configured"
    ) in {True, False}


def test_invalid_ca_json_fails_validator(tmp_path: Path):
    root = _make_pkg(tmp_path)
    (root / "corporate_actions.json").write_text('{"not":"a list"}', encoding="utf-8")
    write_checksums(root, label="package")
    v = validate_research_package(root)
    assert v.valid is False


def test_invalid_terminal_json_fails_validator(tmp_path: Path):
    root = _make_pkg(tmp_path)
    (root / "terminal_events.json").write_text("{}", encoding="utf-8")
    write_checksums(root, label="package")
    v = validate_research_package(root)
    assert v.valid is False


def test_merger_event_requires_manual_treatment(tmp_path: Path):
    from quantfund.data.corporate_actions.models import CorporateAction

    a = CorporateAction.model_validate(
        {
            "action_id": "m1",
            "instrument_id": "NSE:AAA",
            "symbol": "AAA",
            "action_type": "merger",
            "ex_date": "2024-01-02",
            "source": "t",
        }
    )
    assert a.requires_manual_treatment is True


def test_symbol_history_accepted_on_instrument(tmp_path: Path):
    root = _make_pkg(tmp_path)
    inst = json.loads((root / "instruments.json").read_text())
    inst[0]["symbol_history"] = [
        {"symbol": "OLD", "valid_from": "2015-01-01", "valid_to": "2019-12-31"},
        {"symbol": "AAA", "valid_from": "2020-01-01", "valid_to": None},
    ]
    (root / "instruments.json").write_text(json.dumps(inst), encoding="utf-8")
    write_checksums(root, label="package")
    p = LocalResearchPackageProvider(root)
    assert p.get_instruments()[0].symbol_history


def test_calendar_unverified_blocks():
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="vendor",
        source_grade="paid",
        calendar_id="XBOM",
        calendar_version="unverified",
        calendar_verified=False,
        universe_id="nifty50",
        universe_version="v",
        universe_completeness="partial_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-05",
        instrument_count=1,
        delisted_coverage="partial",
        content_hash="sha256:x",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="internal_research_only",
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert any("calendar" in b for b in d.blockers)


def test_missing_open_session_can_block(tmp_path: Path):
    """Sparse bars vs NSE calendar → missing_bars / quality errors."""
    root = _make_pkg(tmp_path)
    # Only one day — many missing open sessions in coverage if quality expands
    (root / "bars" / "AAA.csv").write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02T00:00:00Z,100,101,99,100,1\n",
        encoding="utf-8",
    )
    write_checksums(root, label="package")
    elig, facts, blockers, _ = certify_research_package(root)
    assert elig == "development_only"


def test_future_corporate_action_quality(tmp_path: Path):
    root = _make_pkg(tmp_path)
    cas = json.loads((root / "corporate_actions.json").read_text())
    cas.append(
        {
            "action_id": "future",
            "instrument_id": "NSE:AAA",
            "symbol": "AAA",
            "action_type": "dividend",
            "ex_date": "2099-01-01",
            "cash_amount": 1.0,
            "source": "t",
            "verified": True,
        }
    )
    (root / "corporate_actions.json").write_text(json.dumps(cas), encoding="utf-8")
    write_checksums(root, label="package")
    elig, facts, blockers, _ = certify_research_package(root)
    assert facts is not None
    assert (
        facts.error_count > 0
        or any("future" in c for c in facts.quality_error_codes)
        or elig == "development_only"
    )


def test_modified_pit_membership_changes_coverage(tmp_path: Path):
    root = _make_pkg(tmp_path)
    elig1, facts1, _, meta1 = certify_research_package(root)
    assert meta1.get("universe_resolution", {}).get("source") == "package"
    # Remove membership → fallback to repository/synthetic
    shutil.rmtree(root / "universe")
    write_checksums(root, label="package")
    elig2, facts2, _, meta2 = certify_research_package(root)
    assert elig1 == "development_only" or elig2 == "development_only"
    assert meta2.get("universe_resolution", {}).get("source") in {
        "repository",
        "synthetic_fallback",
    }
    assert meta1.get("universe_resolution", {}).get("source") != meta2.get(
        "universe_resolution", {}
    ).get("source")


def test_vendor_import_forbids_eligibility_extras(tmp_path: Path):
    with pytest.raises(ValueError, match="forbidden"):
        write_package_json(
            tmp_path / "x",
            package_id="a",
            package_version="1",
            provider="p",
            source_grade="paid",
            license_status="internal_research_only",
            extras={"accepted": True},
        )


def test_audit_format_includes_facts_hash():
    from quantfund.data.packages.readiness import (
        audit_research_package,
        format_readiness_report,
    )

    text = format_readiness_report(audit_research_package(FIXTURE))
    assert "Facts hash:" in text
    assert "Source grade:" in text
    assert "RESEARCH_ELIGIBLE: FALSE" in text


def test_no_eligibility_gate_weakened_constant():
    """Sanity: synthetic still cannot pass even with perfect CA/delisted/PIT fields."""
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="synthetic",
        source_grade="synthetic",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="v",
        universe_completeness="full_pit",
        corporate_action_coverage="full_verified",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-05",
        instrument_count=10,
        delisted_coverage="complete",
        content_hash="sha256:x",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,  # even if forged True
        provenance_complete=True,
        license_status="redistributable",
        extras={"synthetic": True},
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_package_local_membership_preferred_over_repo(tmp_path: Path):
    root = _make_pkg(tmp_path)
    res = resolve_package_universe(
        root,
        instruments=LocalResearchPackageProvider(root).get_instruments(),
        start=date(2024, 1, 2),
        end=date(2024, 1, 5),
        allow_repository_fallback=True,
    )
    assert res.source == "package"


def test_cert_report_false_without_package():
    from quantfund.data.packages.cert_report import format_package_certification_summary

    text = format_package_certification_summary(
        eligibility="development_only",
        facts=None,
        blockers=["research_package_not_configured"],
        meta={},
    )
    assert "RESEARCH_ELIGIBLE: FALSE" in text
    assert "Blockers:" in text


def test_materialize_creates_layout(tmp_path: Path):
    bars = tmp_path / "b"
    bars.mkdir()
    _bars_csv(bars / "AAA.csv")
    out = materialize_research_package(
        tmp_path / "out",
        package_id="m",
        package_version="1",
        provider="p",
        source_grade="paid",
        license_status="internal_research_only",
        instruments=[_instrument()],
        bars_by_symbol={"AAA": bars / "AAA.csv"},
        exchange_authority=True,
        write_checksums=True,
    )
    assert Path(out["package_root"]).joinpath("package.json").exists()
    assert Path(out["package_root"]).joinpath("bars" / Path("AAA.csv")).exists() or (
        Path(out["package_root"]) / "bars" / "AAA.csv"
    ).exists()


def test_prohibited_license_fails_validator(tmp_path: Path):
    root = _make_pkg(tmp_path, license_status="prohibited")
    v = validate_research_package(root)
    assert v.valid is False

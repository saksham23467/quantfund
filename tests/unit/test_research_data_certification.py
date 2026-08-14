"""Regression tests for the research data-acquisition / certification layer.

The certification engine composes the UNMODIFIED ResearchEligibilityChecker.
These tests build in-memory contract fixtures (not fabricated certified data) to
prove the gates fail closed on every missing/unknown fact and only pass when a
genuinely authoritative, provenance-complete package is supplied.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from quantfund.data.grades import SourceGrade
from quantfund.data.ingest.checksums import hash_json
from quantfund.data.providers.capabilities import (
    CoverageQuality,
    LicenseStatus,
    ProviderCapabilities,
)
from quantfund.research.certification import certify_dataset
from quantfund.research.certification.immutability import (
    verify_immutable,
    write_certified_package,
)
from quantfund.research.certification.universe_certification import membership_state
from quantfund.research.data_contract.models import (
    CalendarSessionRecord,
    CorporateActionRecord,
    DelistingRecord,
    IdentityRecord,
    MembershipRecord,
    OHLCVBar,
    ResearchDatasetManifest,
    ResearchDatasetPackage,
    SessionType,
    SourceProvenance,
    SourceType,
    TerminalEventType,
)

DT = datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc)
PROV = SourceProvenance(
    source_name="Licensed Vendor X",
    source_type=SourceType.LICENSED_VENDOR,
    source_license="VENDOR_LICENSE_2026",
    retrieved_at=DT,
    source_ref="vendor://feed/nse/daily",
)
OPEN_DATES = [date(2026, 1, d) for d in (5, 6, 7, 8, 9)]  # Mon..Fri


def research_caps() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id="licensed_vendor_x",
        provider_name="Licensed Vendor X",
        source_grade=SourceGrade.EXCHANGE,
        exchange_authority=True,
        corporate_action_quality=CoverageQuality.COMPLETE,
        delisted_coverage=CoverageQuality.COMPLETE,
        universe_membership_quality=CoverageQuality.COMPLETE,
        identity_coverage=CoverageQuality.COMPLETE,
        supports_daily_bars=True,
        supports_corporate_actions=True,
        supports_pit_universe=True,
        supports_instrument_master=True,
        supports_delisted_instruments=True,
        supports_provenance=True,
        supports_licensing_evidence=True,
        license_status=LicenseStatus.VERIFIED,
        redistribution_allowed=False,
    )


def non_exchange_caps() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id="zerodha",
        provider_name="Zerodha (broker)",
        source_grade=SourceGrade.NON_EXCHANGE,
        exchange_authority=False,
        supports_daily_bars=True,
        license_status=LicenseStatus.INTERNAL_RESEARCH_ONLY,
    )


def _bar(symbol, isin, d, close=100.0):
    return OHLCVBar(
        symbol=symbol,
        isin=isin,
        instrument_id=f"NSE:{isin}",
        instrument_token=abs(hash(symbol)) % 100000,
        date=d,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
        provenance=PROV,
    )


def good_manifest(**over) -> ResearchDatasetManifest:
    base = dict(
        dataset_id="licensed_nse_daily_demo",
        dataset_version="v1",
        source_name="Licensed Vendor X",
        source_type=SourceType.LICENSED_VENDOR,
        source_license="VENDOR_LICENSE_2026",
        source_grade=SourceGrade.EXCHANGE,
        data_class="RESEARCH_DATA",
        download_timestamp=DT,
        coverage_start=date(2026, 1, 5),
        coverage_end=date(2026, 1, 9),
        exchange="NSE",
        currency="INR",
        exchange_authority=True,
        license_status="verified",
    )
    base.update(over)
    return ResearchDatasetManifest(**base)


def good_package(**over) -> ResearchDatasetPackage:
    good_isin = "INE111A01011"
    old_isin = "INE222B01019"
    ohlcv = [_bar("GOODCO", good_isin, d) for d in OPEN_DATES]
    ohlcv += [_bar("OLDCO", old_isin, d) for d in OPEN_DATES[:3]]  # delisted Jan 7

    identity = [
        IdentityRecord(
            isin=good_isin,
            exchange="NSE",
            instrument_id=f"NSE:{good_isin}",
            symbol="GOODCO",
            valid_from=date(2020, 1, 1),
            valid_to=None,
            provenance=PROV,
        ),
        IdentityRecord(
            isin=old_isin,
            exchange="NSE",
            instrument_id=f"NSE:{old_isin}",
            symbol="OLDCO",
            valid_from=date(2018, 1, 1),
            valid_to=date(2026, 1, 7),
            provenance=PROV,
        ),
    ]
    membership = [
        MembershipRecord(
            universe_id="NIFTY_DEMO",
            universe_version="2026.1",
            symbol="GOODCO",
            isin=good_isin,
            member_from=date(2019, 1, 1),
            member_to=None,
            provenance=PROV,
        ),
        MembershipRecord(
            universe_id="NIFTY_DEMO",
            universe_version="2026.1",
            symbol="OLDCO",
            isin=old_isin,
            member_from=date(2018, 6, 1),
            member_to=date(2026, 1, 7),
            provenance=PROV,
        ),
    ]
    delistings = [
        DelistingRecord(
            isin=old_isin,
            symbol="OLDCO",
            delisting_date=date(2026, 1, 7),
            terminal_event_type=TerminalEventType.DELISTED,
            provenance=PROV,
        )
    ]
    calendar = [
        CalendarSessionRecord(
            exchange="NSE",
            session_date=d,
            is_open=True,
            session_type=SessionType.OPEN_SESSION,
            provenance=PROV,
        )
        for d in OPEN_DATES
    ]
    corporate_actions = [
        CorporateActionRecord(
            isin=good_isin,
            symbol="GOODCO",
            ex_date=date(2026, 1, 6),
            action_type="dividend",
            cash_amount=5.0,
            source="vendor_ca_ledger",
            provenance=PROV,
        )
    ]
    fields = dict(
        manifest=good_manifest(),
        ohlcv=ohlcv,
        identity=identity,
        membership=membership,
        delistings=delistings,
        calendar=calendar,
        corporate_actions=corporate_actions,
    )
    fields.update(over)
    return ResearchDatasetPackage(**fields)


def certify(pkg, caps=None, immutable=True):
    return certify_dataset(pkg, caps or research_caps(), immutable=immutable)


# --- Sanity: the good package must certify RESEARCH_ELIGIBLE ---------------


def test_good_package_is_research_eligible():
    cert = certify(good_package())
    assert cert.research_eligible is True
    assert cert.verdict == "RESEARCH_ELIGIBLE"


# --- 1. Missing ISIN --------------------------------------------------------


def test_missing_isin_fails():
    pkg = good_package()
    ohlcv = [b.model_copy(update={"isin": None}) for b in pkg.ohlcv if b.symbol == "GOODCO"]
    ohlcv += [b for b in pkg.ohlcv if b.symbol != "GOODCO"]
    pkg = pkg.model_copy(update={"ohlcv": ohlcv, "identity": [
        r for r in pkg.identity if r.symbol != "GOODCO"
    ]})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert any("identity" in b or "identity_issues" in b for b in cert.blockers)


# --- 2. Missing membership --------------------------------------------------


def test_missing_membership_fails():
    pkg = good_package().model_copy(update={"membership": []})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.metrics["universe_completeness"] == "none"


# --- 3. Unknown membership --------------------------------------------------


def test_unknown_membership_fails():
    pkg = good_package()
    pkg = pkg.model_copy(update={"membership": [
        r for r in pkg.membership if r.symbol != "GOODCO"
    ]})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.metrics["unknown_membership_session_count"] > 0


# --- 4. Missing delisting ---------------------------------------------------


def test_missing_delisting_fails():
    pkg = good_package().model_copy(update={"delistings": []})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.metrics["delisted_coverage"] == "unknown"


# --- 5. Current universe used historically ---------------------------------


def test_current_universe_used_historically_fails():
    pkg = good_package()
    snapshot = [
        r.model_copy(update={"member_from": date(2026, 1, 9), "member_to": None})
        for r in pkg.membership
    ]
    pkg = pkg.model_copy(update={"membership": snapshot})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.metrics["universe_completeness"] == "current_snapshot_only"


# --- 6. Duplicate bars ------------------------------------------------------


def test_duplicate_bars_fail():
    pkg = good_package()
    dup = pkg.ohlcv[0]
    pkg = pkg.model_copy(update={"ohlcv": list(pkg.ohlcv) + [dup]})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.sub_results["calendar"].metrics["duplicate_bars"] > 0


# --- 7. Calendar mismatch (unexpected bar not in calendar) ------------------


def test_calendar_mismatch_unexpected_bar_fails():
    pkg = good_package()
    stray = _bar("GOODCO", "INE111A01011", date(2026, 1, 12))
    pkg = pkg.model_copy(update={"ohlcv": list(pkg.ohlcv) + [stray]})
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.sub_results["calendar"].metrics["unexpected_bars"] > 0


# --- 8. Closed-session bar --------------------------------------------------


def test_closed_session_bar_fails():
    pkg = good_package()
    closed = CalendarSessionRecord(
        exchange="NSE",
        session_date=date(2026, 1, 3),
        is_open=False,
        session_type=SessionType.CLOSED_SESSION,
        provenance=PROV,
    )
    stray = _bar("GOODCO", "INE111A01011", date(2026, 1, 3))
    pkg = pkg.model_copy(update={
        "calendar": list(pkg.calendar) + [closed],
        "ohlcv": list(pkg.ohlcv) + [stray],
    })
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert cert.sub_results["calendar"].metrics["closed_session_bars"] > 0


# --- 9. Missing session fails unless explained by authoritative calendar ----


def test_missing_session_fails_unless_explained():
    pkg = good_package()
    # Drop GOODCO's Jan 8 bar => missing open session for an active symbol.
    ohlcv = [b for b in pkg.ohlcv if not (b.symbol == "GOODCO" and b.date == date(2026, 1, 8))]
    missing_pkg = pkg.model_copy(update={"ohlcv": ohlcv})
    assert certify(missing_pkg).research_eligible is False

    # Explained: authoritative calendar marks Jan 8 CLOSED -> no longer missing.
    cal = [c for c in pkg.calendar if c.session_date != date(2026, 1, 8)]
    cal.append(CalendarSessionRecord(
        exchange="NSE",
        session_date=date(2026, 1, 8),
        is_open=False,
        session_type=SessionType.CLOSED_SESSION,
        provenance=PROV,
    ))
    explained = missing_pkg.model_copy(update={"calendar": cal})
    cert = certify(explained)
    assert cert.sub_results["calendar"].metrics["missing_sessions"] == 0


# --- 10. Fake exchange authority (manifest lies, capabilities don't back) ---


def test_fake_exchange_authority_fails():
    # Manifest claims EXCHANGE grade but the provider capability cannot satisfy
    # the research source bar => capability_source_bar_ok=false.
    cert = certify(good_package(), caps=non_exchange_caps())
    assert cert.research_eligible is False
    assert cert.metrics["capability_source_bar_ok"] is False


# --- 11. Zerodha-only dataset remains DEVELOPMENT_ONLY ----------------------


def test_zerodha_only_dataset_is_development_only():
    manifest = good_manifest(
        source_name="zerodha_historical_api",
        source_type=SourceType.BROKER_REDISTRIBUTED,
        source_grade=SourceGrade.NON_EXCHANGE,
        data_class="DEVELOPMENT_DATA",
        exchange_authority=False,
        license_status="internal_research_only",
    )
    pkg = good_package(manifest=manifest)
    cert = certify(pkg, caps=non_exchange_caps())
    assert cert.verdict == "DEVELOPMENT_ONLY"
    assert cert.research_eligible is False


# --- 12. RAW prices remain unchanged ---------------------------------------


def test_raw_prices_unchanged_by_certification():
    pkg = good_package()
    before = [(b.symbol, b.date, b.close) for b in pkg.ohlcv]
    certify(pkg)
    after = [(b.symbol, b.date, b.close) for b in pkg.ohlcv]
    assert before == after


# --- 13. Corporate actions remain separately traceable ----------------------


def test_corporate_actions_separately_traceable():
    pkg = good_package()
    assert pkg.corporate_actions and all(
        ca.source and ca.provenance.source_name for ca in pkg.corporate_actions
    )
    # CA ledger is a distinct collection from RAW OHLCV.
    assert not any(isinstance(x, OHLCVBar) for x in pkg.corporate_actions)
    cert = certify(pkg)
    assert cert.sub_results["corporate_actions"].metrics["raw_series_separate"] is True


# --- 14. Dataset hash reproducibility ---------------------------------------


def test_dataset_hash_reproducible():
    h1 = hash_json(good_package().canonical_dict())
    h2 = hash_json(good_package().canonical_dict())
    assert h1 == h2


# --- 15. Certification reproducibility --------------------------------------


def test_certification_reproducible():
    c1 = certify(good_package())
    c2 = certify(good_package())
    assert c1.content_hash == c2.content_hash
    assert c1.verdict == c2.verdict
    assert c1.metrics == c2.metrics


# --- 16. Dataset immutability -----------------------------------------------


def test_dataset_immutability(tmp_path):
    pkg = good_package()
    cert = certify(pkg)
    out = write_certified_package(pkg, cert, root=tmp_path)
    assert verify_immutable(out) is True
    with pytest.raises(FileExistsError):
        write_certified_package(pkg, cert, root=tmp_path)
    # Tamper detection.
    (out / "package.json").write_text("tampered", encoding="utf-8")
    assert verify_immutable(out) is False


# --- 17. Delisted constituent survives while historically valid -------------


def test_delisted_constituent_survives_while_valid():
    pkg = good_package()
    cert = certify(pkg)
    assert cert.research_eligible is True  # OLDCO present, no post-delisting bars
    assert cert.sub_results["delisting"].metrics["post_delisting_bars"] == 0

    # A bar AFTER the terminal event must fail.
    bad = pkg.model_copy(update={
        "ohlcv": list(pkg.ohlcv) + [_bar("OLDCO", "INE222B01019", date(2026, 1, 8))]
    })
    cert_bad = certify(bad)
    assert cert_bad.research_eligible is False
    assert cert_bad.sub_results["delisting"].metrics["post_delisting_bars"] > 0


# --- 18. Pre-membership dates return FALSE / UNKNOWN appropriately ----------


def test_pre_membership_and_unknown_states():
    by_symbol = {
        "OLDCO": [
            MembershipRecord(
                universe_id="NIFTY_DEMO",
                universe_version="2026.1",
                symbol="OLDCO",
                isin="INE222B01019",
                member_from=date(2018, 6, 1),
                member_to=date(2026, 1, 7),
                provenance=PROV,
            )
        ]
    }
    # Before member_from => FALSE (known, not a member).
    assert membership_state("OLDCO", date(2018, 1, 1), by_symbol) == "FALSE"
    # Inside interval => TRUE.
    assert membership_state("OLDCO", date(2020, 1, 1), by_symbol) == "TRUE"
    # No ledger for symbol => UNKNOWN (never assume today's roster).
    assert membership_state("NEWSYM", date(2020, 1, 1), by_symbol) == "UNKNOWN"


# --- 19. Ticker change does not break identity ------------------------------


def test_ticker_change_preserves_identity():
    isin = "INE333C01018"
    ohlcv = [
        _bar("OLDNAME", isin, date(2026, 1, 5)),
        _bar("OLDNAME", isin, date(2026, 1, 6)),
        _bar("NEWNAME", isin, date(2026, 1, 7)),
        _bar("NEWNAME", isin, date(2026, 1, 8)),
        _bar("NEWNAME", isin, date(2026, 1, 9)),
    ]
    identity = [
        IdentityRecord(
            isin=isin, exchange="NSE", instrument_id=f"NSE:{isin}", symbol="OLDNAME",
            valid_from=date(2020, 1, 1), valid_to=date(2026, 1, 6), provenance=PROV,
        ),
        IdentityRecord(
            isin=isin, exchange="NSE", instrument_id=f"NSE:{isin}", symbol="NEWNAME",
            valid_from=date(2026, 1, 7), valid_to=None, provenance=PROV,
        ),
    ]
    pkg = ResearchDatasetPackage(manifest=good_manifest(), ohlcv=ohlcv, identity=identity)
    from quantfund.research.certification import certify_identity

    res = certify_identity(pkg)
    assert res.metrics["instrument_identity_coverage"] == 1.0
    assert res.metrics["instrument_identity_issues"] == 0


# --- 20. Missing provider license -> fail -----------------------------------


def test_missing_provider_license_fails():
    manifest = good_manifest(source_license="", license_status="unknown")
    pkg = good_package(manifest=manifest)
    cert = certify(pkg)
    assert cert.research_eligible is False
    assert any("license" in b.lower() or "provenance" in b.lower() for b in cert.blockers)

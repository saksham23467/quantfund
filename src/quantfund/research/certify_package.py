"""Shared research-package certification path for Phase 7/10/10.5.

Uses existing validators + ResearchEligibilityChecker. Never fabricates
RESEARCH_ELIGIBLE from package booleans. Prefer package-local PIT membership.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.certification import (
    build_dataset_certification,
    certify,
    verify_facts_integrity,
    write_certification,
)
from quantfund.data.corporate_actions.coverage import derive_ca_coverage_report
from quantfund.data.instruments.coverage import measure_delisted_coverage
from quantfund.data.packages.ingest import ingest_configured_research_package
from quantfund.data.packages.membership import resolve_package_universe
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.ingest.checksums import directory_checksum
from quantfund.data.providers.package_validator import resolve_configured_research_package
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.universe.coverage import compute_membership_coverage


def certify_research_package(
    package_root: Path | None = None,
    *,
    write_cert_path: Path | None = None,
) -> tuple[str, DatasetCertificationFacts | None, list[str], dict[str, Any]]:
    """Validate + measure + certify a configured research package."""
    blockers: list[str] = []
    root = package_root or resolve_configured_research_package()
    if root is None:
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            None,
            ["research_package_not_configured"],
            {"configured": False},
        )

    ingest = ingest_configured_research_package(package_root=root, allow_invalid=False)
    meta: dict[str, Any] = {
        "configured": True,
        "package_root": str(root),
        "valid": bool(ingest.ok),
    }
    if not ingest.ok or ingest.provider is None or ingest.validation is None:
        blockers.extend(ingest.blockers or ["package_validation_failed"])
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            None,
            blockers,
            meta,
        )

    provider = ingest.provider
    validation = ingest.validation
    caps = provider.capabilities()
    prov = provider.provenance()
    le = provider.license_evidence()

    calendar = NSECalendarProvider()
    instruments = provider.get_instruments()
    actions = provider.get_corporate_actions()
    terminal = provider.get_terminal_events()
    symbols = [i.symbol for i in instruments]
    bars: list[Any] = []
    try:
        for sym in symbols:
            bars.extend(provider.get_history(sym))
    except Exception as exc:  # noqa: BLE001 — fail closed on corrupt OHLC / bar payload
        blockers.append(f"ohlc_load_failed:{type(exc).__name__}")
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            None,
            blockers,
            meta,
        )

    if not bars:
        blockers.append("no_bars_in_package")
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            None,
            blockers,
            meta,
        )

    start = min(b.timestamp.date() for b in bars)
    end = max(b.timestamp.date() for b in bars)

    try:
        uni_res = resolve_package_universe(
            root,
            instruments=instruments,
            start=start,
            end=end,
        )
    except ValueError as exc:
        blockers.append(str(exc))
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            None,
            blockers,
            meta,
        )

    universe = uni_res.universe
    meta["universe_resolution"] = uni_res.to_dict()
    for n in uni_res.notes:
        meta.setdefault("universe_notes", []).append(n)

    mem_cov = compute_membership_coverage(
        universe,
        calendar=calendar,
        start=start,
        end=end,
        symbols=symbols,
    )
    ca_report = derive_ca_coverage_report(
        actions, source_grade=caps.source_grade.value
    )
    delisted = measure_delisted_coverage(
        instruments=instruments,
        events=terminal,
        coverage_start=start,
        coverage_end=end,
    )

    live_hash = directory_checksum(root)
    if (
        validation.content_hash
        and live_hash
        and validation.content_hash != live_hash
    ):
        blockers.append(
            f"package_content_hash_drift:validated={validation.content_hash} "
            f"live={live_hash}"
        )
        meta["package_hash"] = validation.content_hash
        meta["live_package_hash"] = live_hash
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            None,
            blockers,
            meta,
        )

    quality = run_quality_checks(
        bars,
        calendar=calendar,
        universe=universe,
        actions=actions,
        instruments=instruments,
        terminal_events=terminal,
        provider_capabilities=caps,
        expected_package_hash=validation.content_hash,
        observed_package_hash=validation.content_hash,
        dataset_id="research_package",
        source=caps.provider_id,
        start=start,
        end=end,
        asof_date=end,  # detect future membership / future CA leakage
    )

    facts = DatasetCertificationFacts(
        dataset_id="research_package",
        dataset_version="certified",
        source=str(prov.source),
        source_grade=caps.source_grade.value,
        calendar_id=calendar.calendar_id,
        calendar_version=calendar.calendar_version,
        calendar_verified=calendar.verified,
        universe_id=universe.universe_id,
        universe_version=universe.universe_version,
        universe_completeness=universe.completeness.value,
        corporate_action_coverage=ca_report.overall,
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start=start.isoformat(),
        date_coverage_end=end.isoformat(),
        instrument_count=len(instruments),
        delisted_coverage=delisted.level,
        missing_sessions=quality.missing_sessions,
        missing_bars=quality.missing_bars,
        duplicate_bars=quality.duplicate_bars,
        invalid_ohlc=quality.invalid_ohlc,
        error_count=quality.error_count,
        warning_count=quality.warning_count,
        content_hash=validation.content_hash or "sha256:unknown",
        quality_error_codes=quality.error_codes(),
        unknown_membership_session_count=mem_cov.unknown_membership_sessions,
        instrument_identity_issues=quality.instrument_identity_problems,
        membership_coverage_ratio=mem_cov.membership_coverage_ratio,
        capability_source_bar_ok=caps.can_satisfy_research_eligibility_source_bar(),
        provenance_complete=prov.is_complete_for_research(),
        license_status=le.license_status.value,
        capability_attestation_hash=caps.attestation_hash(),
        package_content_hash=validation.content_hash,
        ca_coverage_breakdown=ca_report.to_dict(),
        extras={
            "synthetic": caps.source_grade.value == "synthetic"
            or bool(validation.manifest and validation.manifest.is_synthetic()),
            "delisted_coverage_report": delisted.to_dict(),
            "exchange_authority": caps.exchange_authority,
            "research_eligibility": "derived",
            "universe_source": uni_res.source,
            "membership_path": str(uni_res.membership_path)
            if uni_res.membership_path
            else None,
            "ca_by_type": {
                k: v
                for k, v in (ca_report.to_dict() if hasattr(ca_report, "to_dict") else {}).items()
            },
        },
    )

    decision = certify(facts)
    cert = build_dataset_certification(
        facts=facts,
        decision=decision,
        provenance=prov.to_manifest_dict(),
        license_evidence=le.to_dict(),
    )

    # Integrity: facts_hash must recompute identically
    if not verify_facts_integrity(facts, cert.facts_hash):
        blockers.append("facts_hash_mismatch_internal")
        return (
            EligibilityLevel.DEVELOPMENT_ONLY.value,
            facts,
            blockers,
            meta,
        )

    if write_cert_path is not None:
        write_certification(write_cert_path, facts=facts, decision=decision)

    pkg_meta = getattr(provider, "_meta", {}) or {}
    meta.update(
        {
            "package_hash": validation.content_hash,
            "facts_hash": cert.facts_hash,
            "source_grade": facts.source_grade,
            "exchange_authority": caps.exchange_authority,
            "license_status": facts.license_status,
            "calendar_id": facts.calendar_id,
            "calendar_version": facts.calendar_version,
            "calendar_verified": facts.calendar_verified,
            "universe_version": facts.universe_version,
            "ca_coverage": facts.corporate_action_coverage,
            "delisted_coverage": facts.delisted_coverage,
            "pit_coverage": facts.universe_completeness,
            "membership_coverage_ratio": facts.membership_coverage_ratio,
            "package_id": pkg_meta.get("package_id"),
            "package_version": pkg_meta.get("package_version"),
            "vendor": pkg_meta.get("vendor") or pkg_meta.get("provider"),
            "provider": pkg_meta.get("provider"),
            "coverage_start": pkg_meta.get("coverage_start") or facts.date_coverage_start,
            "coverage_end": pkg_meta.get("coverage_end") or facts.date_coverage_end,
            "test_fixture_only": bool(pkg_meta.get("test_fixture_only")),
            "limitations": list(pkg_meta.get("limitations") or []),
            "identity_resolved_ratio": (
                1.0
                if facts.instrument_count and facts.instrument_identity_issues == 0
                else max(
                    0.0,
                    1.0
                    - (
                        facts.instrument_identity_issues
                        / max(facts.instrument_count, 1)
                    ),
                )
            ),
            "identity_ambiguous": 0,
            "identity_unknown": facts.instrument_identity_issues,
            "quality_report": {
                "error_count": facts.error_count,
                "warning_count": facts.warning_count,
                "unknown_membership_session_count": facts.unknown_membership_session_count,
                "quality_error_codes": list(facts.quality_error_codes),
            },
            "certification": cert.to_dict(),
            "certification_timestamp": cert.certified_at.isoformat(),
        }
    )
    if decision.level == EligibilityLevel.DEVELOPMENT_ONLY:
        blockers.extend(decision.blockers)
    return decision.level.value, facts, blockers, meta


def reverify_certification_artifact(
    cert_path: Path,
    *,
    package_root: Path | None = None,
) -> list[str]:
    """Reload certification and ensure facts_hash still matches recomputed facts.

    Optionally re-certify package and compare hashes for tamper detection.
    """
    from quantfund.data.certification import facts_hash, load_and_verify_certification

    issues: list[str] = []
    try:
        facts, ok = load_and_verify_certification(cert_path)
    except Exception as exc:  # noqa: BLE001
        return [f"certification_load_failed:{exc}"]
    if not ok:
        issues.append("facts_hash_mismatch")

    if package_root is not None:
        elig, new_facts, blockers, meta = certify_research_package(package_root)
        if new_facts is None:
            issues.extend(blockers or ["recertify_failed"])
            return issues
        if facts_hash(new_facts) != facts_hash(facts):
            issues.append("package_changed_after_certification")
        stored_level = None
        try:
            import json

            raw = json.loads(
                Path(cert_path).with_suffix(".json").read_text(encoding="utf-8")
                if Path(cert_path).suffix != ".json"
                else Path(cert_path).read_text(encoding="utf-8")
            )
            stored_level = (raw.get("decision") or {}).get("level")
        except Exception:  # noqa: BLE001
            stored_level = None
        if stored_level and elig != stored_level:
            issues.append(f"eligibility_drift:stored={stored_level} now={elig}")
        _ = meta
    return issues

"""Validate external research packages before they enter the dataset builder.

Package may declare capabilities; it must NOT declare final eligibility.
Forged exchange-grade claims on synthetic/yfinance packages are rejected.
Phase 7: hardened structure, checksum, security, license, and schema checks.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.data.grades import SourceGrade
from quantfund.data.ingest.checksums import directory_checksum, verify_checksums
from quantfund.data.packages.contract import ResearchPackageManifest, SCHEMA_VERSION
from quantfund.data.packages.license import (
    RESEARCH_REJECTED_LICENSE_STATUSES,
    LicenseEvidence,
    PackageLicenseStatus,
    parse_license_evidence,
)
from quantfund.data.providers.capabilities import (
    CoverageQuality,
    LicenseStatus,
    ProviderCapabilities,
)


@dataclass
class PackageValidationIssue:
    path: str
    code: str
    message: str


@dataclass
class PackageValidationResult:
    valid: bool
    errors: list[PackageValidationIssue] = field(default_factory=list)
    warnings: list[PackageValidationIssue] = field(default_factory=list)
    capabilities: ProviderCapabilities | None = None
    package_meta: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None
    license_evidence: LicenseEvidence | None = None
    manifest: ResearchPackageManifest | None = None

    def raise_if_invalid(self) -> None:
        if not self.valid:
            msgs = "; ".join(f"{e.code}: {e.message}" for e in self.errors)
            raise ValueError(f"Research package invalid: {msgs}")


_EXECUTABLE_SUFFIXES = {
    ".exe",
    ".so",
    ".dylib",
    ".dll",
    ".sh",
    ".bash",
    ".py",
    ".pyc",
    ".bin",
}
_DANGEROUS_NAMES = {"__pycache__", ".git", "node_modules"}


class ResearchPackageValidator:
    """Structural + checksum + capability + security consistency checks."""

    REQUIRED_FILES = ("package.json",)

    def validate(self, package_root: Path) -> PackageValidationResult:
        root = Path(package_root)
        errors: list[PackageValidationIssue] = []
        warnings: list[PackageValidationIssue] = []

        if not root.is_dir():
            return PackageValidationResult(
                valid=False,
                errors=[
                    PackageValidationIssue(
                        "package_root", "missing_dir", f"not a directory: {root}"
                    )
                ],
            )

        # Resolve and reject path escape / symlink root tricks
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as exc:
            return PackageValidationResult(
                valid=False,
                errors=[
                    PackageValidationIssue(
                        "package_root", "unresolvable_path", str(exc)
                    )
                ],
            )

        meta_path = resolved_root / "package.json"
        if not meta_path.exists():
            errors.append(
                PackageValidationIssue("package.json", "missing_file", "package.json required")
            )
            return PackageValidationResult(valid=False, errors=errors)

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(
                PackageValidationIssue("package.json", "invalid_json", str(exc))
            )
            return PackageValidationResult(valid=False, errors=errors)

        # Package must not assert eligibility decisions
        for banned_key in (
            "research_eligibility",
            "research_eligible",
            "eligibility",
            "accepted",
        ):
            if banned_key in meta:
                errors.append(
                    PackageValidationIssue(
                        "package.json",
                        "eligibility_assertion_forbidden",
                        f"package must not declare {banned_key}; eligibility is derived",
                    )
                )

        # Schema / contract parse
        manifest: ResearchPackageManifest | None = None
        try:
            # Fill defaults for Phase 3.5 packages missing Phase 7 fields
            contract_payload = dict(meta)
            contract_payload.setdefault("package_id", meta.get("provider", "unknown"))
            contract_payload.setdefault("package_version", "0.0.0")
            contract_payload.setdefault("provider", meta.get("provider", "unknown"))
            contract_payload.setdefault("schema_version", SCHEMA_VERSION)
            if "exchange_authority" not in contract_payload:
                contract_payload["exchange_authority"] = bool(
                    (meta.get("capabilities") or {}).get("exchange_authority", False)
                )
            if "license_status" not in contract_payload:
                contract_payload["license_status"] = (
                    (meta.get("capabilities") or {}).get("license_status") or "unknown"
                )
            if "synthetic" not in contract_payload:
                contract_payload["synthetic"] = (
                    str(meta.get("source_grade", "")) == "synthetic"
                    or "synthetic" in str(meta.get("source", "")).lower()
                )
            manifest = ResearchPackageManifest.model_validate(contract_payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                PackageValidationIssue(
                    "package.json", "invalid_manifest", str(exc)
                )
            )

        try:
            grade = SourceGrade(meta["source_grade"])
        except Exception as exc:  # noqa: BLE001
            errors.append(
                PackageValidationIssue(
                    "package.json.source_grade", "invalid_source_grade", str(exc)
                )
            )
            return PackageValidationResult(
                valid=False, errors=errors, package_meta=meta, manifest=manifest
            )

        # Security walk
        seen_rel: set[str] = set()
        for path in resolved_root.rglob("*"):
            try:
                rel = path.relative_to(resolved_root).as_posix()
            except ValueError:
                errors.append(
                    PackageValidationIssue(
                        str(path),
                        "path_traversal",
                        "path escapes package root",
                    )
                )
                continue
            if ".." in Path(rel).parts:
                errors.append(
                    PackageValidationIssue(rel, "path_traversal", " '..' in relative path")
                )
            if path.is_symlink():
                try:
                    target = path.resolve(strict=False)
                    if not str(target).startswith(str(resolved_root)):
                        errors.append(
                            PackageValidationIssue(
                                rel, "symlink_escape", f"symlink points outside package: {target}"
                            )
                        )
                    else:
                        warnings.append(
                            PackageValidationIssue(
                                rel, "symlink_present", "symlinks discouraged in research packages"
                            )
                        )
                except OSError as exc:
                    errors.append(
                        PackageValidationIssue(rel, "symlink_unresolvable", str(exc))
                    )
            if path.is_file():
                if rel in seen_rel:
                    errors.append(
                        PackageValidationIssue(rel, "duplicate_path", "duplicate relative path")
                    )
                seen_rel.add(rel)
                suffix = path.suffix.lower()
                if suffix in _EXECUTABLE_SUFFIXES or path.name in _DANGEROUS_NAMES:
                    errors.append(
                        PackageValidationIssue(
                            rel,
                            "unexpected_executable_content",
                            f"disallowed content type/name: {path.name}",
                        )
                    )
                try:
                    mode = path.stat().st_mode
                    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                        # Data files should not be executable
                        if suffix in {".csv", ".json", ".parquet", ".txt", ".md", ".sha256"}:
                            warnings.append(
                                PackageValidationIssue(
                                    rel, "executable_bit", "data file has execute bit set"
                                )
                            )
                        elif suffix in _EXECUTABLE_SUFFIXES:
                            pass  # already errored
                except OSError:
                    pass

        caps_raw = dict(meta.get("capabilities") or {})
        try:
            # Map Phase 7 license vocabulary onto ProviderCapabilities.LicenseStatus
            lic_raw = str(
                meta.get("license_status")
                or caps_raw.get("license_status")
                or "unknown"
            )
            if lic_raw in {e.value for e in LicenseStatus}:
                cap_license = LicenseStatus(lic_raw)
            else:
                cap_license = LicenseStatus.UNKNOWN

            caps = ProviderCapabilities(
                provider_id=str(meta.get("package_id") or meta.get("provider") or "unknown"),
                provider_name=str(meta.get("provider_name") or meta.get("provider") or "unknown"),
                source_grade=grade,
                historical_depth=str(caps_raw.get("historical_depth", "unknown")),
                corporate_action_quality=CoverageQuality(
                    caps_raw.get("corporate_action_quality", "unknown")
                ),
                delisted_coverage=CoverageQuality(caps_raw.get("delisted_coverage", "unknown")),
                universe_membership_quality=CoverageQuality(
                    caps_raw.get("universe_membership_quality", "unknown")
                ),
                identity_coverage=CoverageQuality(caps_raw.get("identity_coverage", "unknown")),
                exchange_authority=bool(
                    meta.get("exchange_authority", caps_raw.get("exchange_authority", False))
                ),
                supports_instrument_master=bool(
                    caps_raw.get("supports_instrument_master", False)
                ),
                supports_symbol_isin_mapping=bool(
                    caps_raw.get("supports_symbol_isin_mapping", False)
                ),
                supports_historical_identifiers=bool(
                    caps_raw.get("supports_historical_identifiers", False)
                ),
                supports_daily_bars=bool(caps_raw.get("supports_daily_bars", True)),
                supports_corporate_actions=bool(
                    caps_raw.get("supports_corporate_actions", False)
                ),
                supports_pit_universe=bool(caps_raw.get("supports_pit_universe", False)),
                supports_delisted_instruments=bool(
                    caps_raw.get("supports_delisted_instruments", False)
                ),
                supports_provenance=bool(caps_raw.get("supports_provenance", True)),
                supports_licensing_evidence=bool(
                    caps_raw.get("supports_licensing_evidence", False)
                ),
                supported_exchanges=list(
                    caps_raw.get("supported_exchanges")
                    or meta.get("exchanges")
                    or []
                ),
                supported_date_range=dict(
                    caps_raw.get("supported_date_range")
                    or (
                        {
                            "start": meta["coverage_start"],
                            "end": meta["coverage_end"],
                        }
                        if meta.get("coverage_start") and meta.get("coverage_end")
                        else {}
                    )
                ),
                redistribution_allowed=caps_raw.get("redistribution_allowed"),
                license_status=cap_license,
                authority_evidence_refs=list(caps_raw.get("authority_evidence_refs") or []),
                licensing_notes=str(meta.get("licensing_notes", "")),
                usage_notes=str(meta.get("usage_notes", "")),
                limitations=list(meta.get("limitations") or []),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                PackageValidationIssue(
                    "package.json.capabilities", "invalid_capabilities", str(exc)
                )
            )
            return PackageValidationResult(
                valid=False, errors=errors, package_meta=meta, manifest=manifest
            )

        # LICENSE.json optional sidecar
        license_json = None
        lic_path = resolved_root / "LICENSE.json"
        if lic_path.exists():
            try:
                license_json = json.loads(lic_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(
                    PackageValidationIssue("LICENSE.json", "invalid_json", str(exc))
                )

        # Forgery: synthetic/yfinance cannot claim exchange authority or research source bar
        pid = caps.provider_id.lower()
        source = str(meta.get("source", "")).lower()
        synthetic_flag = bool(
            (manifest.is_synthetic() if manifest else False)
            or grade == SourceGrade.SYNTHETIC
            or "synthetic" in pid
            or source == "synthetic_fixture"
        )
        if synthetic_flag:
            if caps.exchange_authority or meta.get("source_grade") == "exchange":
                errors.append(
                    PackageValidationIssue(
                        "capabilities",
                        "forged_exchange_grade",
                        "synthetic package cannot claim exchange_authority or source_grade=exchange",
                    )
                )
            if grade != SourceGrade.SYNTHETIC:
                errors.append(
                    PackageValidationIssue(
                        "source_grade",
                        "synthetic_grade_mismatch",
                        "synthetic fixtures must declare source_grade=synthetic",
                    )
                )

        if pid == "yfinance" or source == "yfinance" or grade == SourceGrade.NON_EXCHANGE:
            if caps.exchange_authority or grade in {SourceGrade.EXCHANGE, SourceGrade.PAID}:
                errors.append(
                    PackageValidationIssue(
                        "capabilities",
                        "forged_exchange_grade",
                        "yfinance/non_exchange cannot claim exchange/paid research source bar",
                    )
                )

        # Provenance sidecar
        prov_path = resolved_root / "provenance.json"
        provenance = dict(meta.get("provenance") or {})
        if prov_path.exists():
            try:
                side = json.loads(prov_path.read_text(encoding="utf-8"))
                # Contradictory authority
                if (
                    side.get("exchange_authority") is False
                    and caps.exchange_authority
                ):
                    errors.append(
                        PackageValidationIssue(
                            "provenance.json",
                            "contradictory_authority",
                            "provenance.exchange_authority=false but capabilities claim true",
                        )
                    )
                if side.get("source_grade") and side["source_grade"] != meta.get(
                    "source_grade"
                ):
                    errors.append(
                        PackageValidationIssue(
                            "provenance.json",
                            "contradictory_provenance",
                            "provenance.source_grade mismatches package.json",
                        )
                    )
                provenance = {**provenance, **side}
            except json.JSONDecodeError as exc:
                errors.append(
                    PackageValidationIssue("provenance.json", "invalid_json", str(exc))
                )

        # Checksums
        checksum_path = resolved_root / "checksums.sha256"
        content_hash = None
        if checksum_path.exists():
            try:
                if not verify_checksums(resolved_root):
                    errors.append(
                        PackageValidationIssue(
                            "checksums.sha256",
                            "checksum_mismatch",
                            "package checksum verification failed",
                        )
                    )
            except FileNotFoundError as exc:
                errors.append(
                    PackageValidationIssue("checksums.sha256", "checksum_error", str(exc))
                )
        try:
            content_hash = directory_checksum(resolved_root)
        except Exception:  # noqa: BLE001
            warnings.append(
                PackageValidationIssue(
                    "package_root", "hash_skipped", "could not compute content hash"
                )
            )

        license_evidence = parse_license_evidence(
            package_meta=meta,
            license_json=license_json,
            package_hash=content_hash,
        )
        if license_evidence.license_status.value in RESEARCH_REJECTED_LICENSE_STATUSES:
            if license_evidence.license_status == PackageLicenseStatus.PROHIBITED:
                errors.append(
                    PackageValidationIssue(
                        "license_status",
                        "license_prohibited",
                        "package license_status=prohibited — refuse ingest",
                    )
                )
            elif license_evidence.license_status == PackageLicenseStatus.EXPIRED:
                errors.append(
                    PackageValidationIssue(
                        "license_status",
                        "license_expired",
                        "package license_status=expired — refuse research ingest",
                    )
                )
            # unknown: warning at package level; eligibility still blocks research
            elif license_evidence.license_status == PackageLicenseStatus.UNKNOWN:
                warnings.append(
                    PackageValidationIssue(
                        "license_status",
                        "license_unknown",
                        "license_status=unknown — cannot become research_eligible",
                    )
                )

        # Capability claims without supporting files → error for research-capable grades
        research_grade = grade in {SourceGrade.EXCHANGE, SourceGrade.PAID} or grade in {
            "exchange",
            "paid",
        }
        has_instruments = (
            (resolved_root / "instruments.json").exists()
            or (resolved_root / "instruments.parquet").exists()
            or (resolved_root / "instruments").is_dir()
        )
        if caps.supports_instrument_master or caps.supports_symbol_isin_mapping:
            if not has_instruments:
                issue = PackageValidationIssue(
                    "instruments",
                    "capability_without_data",
                    "instrument capability claimed but no instruments payload",
                )
                (errors if research_grade else warnings).append(issue)

        if not has_instruments:
            issue = PackageValidationIssue(
                "instruments",
                "missing_instruments",
                "no instruments.json/parquet/dir found",
            )
            (errors if research_grade else warnings).append(issue)

        bars_dir = resolved_root / "bars"
        if not bars_dir.exists():
            issue = PackageValidationIssue(
                "bars", "missing_bars_dir", "bars/ directory missing"
            )
            (errors if research_grade else warnings).append(issue)
        elif caps.supports_daily_bars is False:
            warnings.append(
                PackageValidationIssue(
                    "capabilities",
                    "capability_contradiction",
                    "bars/ present but supports_daily_bars=false",
                )
            )

        # Optional schema validation for CA / terminal ledgers
        ca_path = resolved_root / "corporate_actions.json"
        if ca_path.exists():
            try:
                from quantfund.data.corporate_actions.models import CorporateAction

                ca_raw = json.loads(ca_path.read_text(encoding="utf-8"))
                if not isinstance(ca_raw, list):
                    errors.append(
                        PackageValidationIssue(
                            "corporate_actions.json",
                            "invalid_ca_payload",
                            "corporate_actions.json must be a JSON array",
                        )
                    )
                else:
                    for i, row in enumerate(ca_raw):
                        CorporateAction.model_validate(row)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    PackageValidationIssue(
                        "corporate_actions.json", "invalid_corporate_actions", str(exc)
                    )
                )

        te_path = resolved_root / "terminal_events.json"
        if te_path.exists():
            try:
                from quantfund.data.instruments.delisted import TerminalEvent

                te_raw = json.loads(te_path.read_text(encoding="utf-8"))
                if not isinstance(te_raw, list):
                    errors.append(
                        PackageValidationIssue(
                            "terminal_events.json",
                            "invalid_terminal_payload",
                            "terminal_events.json must be a JSON array",
                        )
                    )
                else:
                    for row in te_raw:
                        TerminalEvent.model_validate(row)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    PackageValidationIssue(
                        "terminal_events.json", "invalid_terminal_events", str(exc)
                    )
                )

        # Package-local PIT membership (when present or claimed)
        from quantfund.data.packages.membership import discover_package_membership_path

        mem_path = discover_package_membership_path(resolved_root)
        if caps.supports_pit_universe and mem_path is None:
            warnings.append(
                PackageValidationIssue(
                    "universe",
                    "pit_capability_without_membership",
                    "supports_pit_universe=true but no universe/membership file found",
                )
            )
        if mem_path is not None:
            try:
                from datetime import date as _date

                from quantfund.data.universe.import_membership import (
                    build_universe_from_membership_file,
                )
                from quantfund.data.universe.models import UniverseCompleteness

                # Structural load + overlap audit (dates are placeholders for audit window)
                build_universe_from_membership_file(
                    mem_path,
                    universe_id="package",
                    universe_version="validate",
                    effective_start=_date(2000, 1, 1),
                    effective_end=_date(2100, 1, 1),
                    source="package_validate",
                    completeness=UniverseCompleteness.PARTIAL_PIT,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    PackageValidationIssue(
                        str(mem_path.relative_to(resolved_root)),
                        "invalid_membership",
                        str(exc),
                    )
                )

        valid = len(errors) == 0
        return PackageValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            capabilities=caps,
            package_meta=meta,
            content_hash=content_hash,
            license_evidence=license_evidence,
            manifest=manifest,
        )


def validate_research_package(package_root: Path) -> PackageValidationResult:
    return ResearchPackageValidator().validate(package_root)


def resolve_configured_research_package() -> Path | None:
    """Return QUANTFUND_RESEARCH_PACKAGE path if set and exists."""
    raw = os.environ.get("QUANTFUND_RESEARCH_PACKAGE")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        return None
    return path

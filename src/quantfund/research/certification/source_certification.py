"""Source-grade / data-class / license certification."""

from __future__ import annotations

from quantfund.data.grades import SourceGrade
from quantfund.data.providers.capabilities import LicenseStatus, ProviderCapabilities
from quantfund.research.certification.results import CertResult
from quantfund.research.data_contract.models import ResearchDatasetManifest


def certify_source(
    manifest: ResearchDatasetManifest,
    capabilities: ProviderCapabilities,
) -> CertResult:
    blockers: list[str] = []

    if manifest.data_class.strip().upper() == "DEVELOPMENT_DATA":
        blockers.append("data_class=DEVELOPMENT_DATA (permanently development-only)")

    if manifest.source_grade in {SourceGrade.NON_EXCHANGE, SourceGrade.SYNTHETIC}:
        blockers.append(
            f"source_grade={manifest.source_grade.value} is not exchange/paid grade"
        )

    capability_source_bar_ok = capabilities.can_satisfy_research_eligibility_source_bar()
    if not capability_source_bar_ok:
        blockers.append("capability_source_bar_ok=false (provider source bar unmet)")

    license_status = manifest.license_status or capabilities.license_status.value
    if license_status in {
        LicenseStatus.PROHIBITED.value,
        LicenseStatus.EXPIRED.value,
    }:
        blockers.append(f"license_status={license_status}")
    if license_status in {LicenseStatus.UNKNOWN.value, "unknown", ""}:
        blockers.append("license_status=unknown (research requires known license)")

    if not manifest.source_license.strip():
        blockers.append("missing source_license (provider license required)")

    return CertResult(
        dimension="source",
        passed=not blockers,
        metrics={
            "source_grade": manifest.source_grade.value,
            "data_class": manifest.data_class,
            "capability_source_bar_ok": capability_source_bar_ok,
            "license_status": license_status,
            "exchange_authority": manifest.exchange_authority,
        },
        blockers=blockers,
    )

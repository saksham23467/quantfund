"""License / provenance evidence for research packages (Phase 7)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PackageLicenseStatus(str, Enum):
    """Eligibility-facing license states (Phase 7 vocabulary)."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"
    EXPIRED = "expired"
    # Phase 5 compatibility (treated as known / research-usable when not prohibited)
    INTERNAL_RESEARCH_ONLY = "internal_research_only"
    REDISTRIBUTABLE = "redistributable"


RESEARCH_ALLOWED_LICENSE_STATUSES = frozenset(
    {
        PackageLicenseStatus.VERIFIED.value,
        PackageLicenseStatus.INTERNAL_RESEARCH_ONLY.value,
        PackageLicenseStatus.REDISTRIBUTABLE.value,
    }
)

RESEARCH_REJECTED_LICENSE_STATUSES = frozenset(
    {
        PackageLicenseStatus.UNKNOWN.value,
        PackageLicenseStatus.PROHIBITED.value,
        PackageLicenseStatus.EXPIRED.value,
    }
)


class LicenseEvidence(BaseModel):
    """Explicit license attestation — never inferred from provider name alone."""

    model_config = ConfigDict(frozen=True)

    license_status: PackageLicenseStatus = PackageLicenseStatus.UNKNOWN
    license_reference: str | None = None
    legal_source: str | None = None
    redistribution_allowed: bool | None = None
    research_use_allowed: bool | None = None
    exchange_authority: bool = False
    acquisition_method: str = "unknown"
    acquisition_timestamp: str | None = None
    package_hash: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    notes: str = ""

    def research_license_ok(self) -> bool:
        if self.license_status.value in RESEARCH_REJECTED_LICENSE_STATUSES:
            return False
        if self.research_use_allowed is False:
            return False
        return self.license_status.value in RESEARCH_ALLOWED_LICENSE_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def parse_license_evidence(
    *,
    package_meta: dict[str, Any],
    license_json: dict[str, Any] | None = None,
    package_hash: str | None = None,
) -> LicenseEvidence:
    """Build LicenseEvidence from LICENSE.json and/or package.json fields."""
    merged = dict(package_meta.get("capabilities") or {})
    if license_json:
        merged = {**merged, **license_json}
    status_raw = (
        (license_json or {}).get("license_status")
        or package_meta.get("license_status")
        or merged.get("license_status")
        or "unknown"
    )
    try:
        status = PackageLicenseStatus(str(status_raw))
    except ValueError:
        status = PackageLicenseStatus.UNKNOWN

    return LicenseEvidence(
        license_status=status,
        license_reference=(license_json or {}).get("license_reference")
        or package_meta.get("license_ref"),
        legal_source=(license_json or {}).get("legal_source")
        or package_meta.get("provider"),
        redistribution_allowed=merged.get("redistribution_allowed"),
        research_use_allowed=(license_json or {}).get("research_use_allowed"),
        exchange_authority=bool(
            (license_json or {}).get("exchange_authority")
            if license_json and "exchange_authority" in license_json
            else package_meta.get("capabilities", {}).get("exchange_authority", False)
        ),
        acquisition_method=str(
            (license_json or {}).get("acquisition_method")
            or package_meta.get("acquisition_method")
            or "unknown"
        ),
        acquisition_timestamp=(license_json or {}).get("acquisition_timestamp")
        or package_meta.get("acquisition_timestamp")
        or package_meta.get("created_at"),
        package_hash=package_hash,
        evidence_refs=list(
            (license_json or {}).get("evidence_refs")
            or merged.get("authority_evidence_refs")
            or []
        ),
        notes=str(
            (license_json or {}).get("notes") or package_meta.get("licensing_notes") or ""
        ),
    )

"""Ingest path for QUANTFUND_RESEARCH_PACKAGE → validated local provider.

Does not fabricate research eligibility. Validation failures fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantfund.data.packages.license import LicenseEvidence
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.providers.package_validator import (
    PackageValidationResult,
    resolve_configured_research_package,
    validate_research_package,
)


@dataclass
class ResearchPackageIngestResult:
    configured: bool
    package_root: Path | None
    validation: PackageValidationResult | None
    provider: LocalResearchPackageProvider | None
    license_evidence: LicenseEvidence | None
    blockers: list[str]

    @property
    def ok(self) -> bool:
        return bool(
            self.configured
            and self.validation is not None
            and self.validation.valid
            and self.provider is not None
        )


def ingest_configured_research_package(
    *,
    package_root: Path | None = None,
    allow_invalid: bool = False,
) -> ResearchPackageIngestResult:
    """Resolve env/package path, validate, and load provider.

    If QUANTFUND_RESEARCH_PACKAGE is unset and no explicit path is given,
    returns configured=False with blocker research_package_not_configured.
    """
    root = package_root
    if root is None:
        root = resolve_configured_research_package()
    if root is None:
        return ResearchPackageIngestResult(
            configured=False,
            package_root=None,
            validation=None,
            provider=None,
            license_evidence=None,
            blockers=["research_package_not_configured"],
        )

    validation = validate_research_package(root)
    blockers: list[str] = []
    if not validation.valid:
        blockers.extend(f"{e.code}:{e.message}" for e in validation.errors)
        if not allow_invalid:
            return ResearchPackageIngestResult(
                configured=True,
                package_root=root,
                validation=validation,
                provider=None,
                license_evidence=validation.license_evidence,
                blockers=blockers or ["package_validation_failed"],
            )

    provider = LocalResearchPackageProvider(
        root, validate=False, allow_invalid=allow_invalid
    )
    provider._validation = validation  # reuse already-computed validation
    return ResearchPackageIngestResult(
        configured=True,
        package_root=root,
        validation=validation,
        provider=provider,
        license_evidence=validation.license_evidence,
        blockers=blockers,
    )

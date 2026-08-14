"""Explicit provider capability declarations — never auto-promote to research-grade."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.grades import SourceGrade


class CoverageQuality(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    COMPLETE = "complete"
    UNKNOWN = "unknown"


class LicenseStatus(str, Enum):
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"
    EXPIRED = "expired"
    VERIFIED = "verified"
    INTERNAL_RESEARCH_ONLY = "internal_research_only"
    REDISTRIBUTABLE = "redistributable"


class ProviderCapabilities(BaseModel):
    """What a provider claims to supply. Evaluated separately from schema validity."""

    model_config = ConfigDict(frozen=True)

    provider_id: str
    provider_name: str
    source_grade: SourceGrade
    historical_depth: str = "unknown"
    corporate_action_quality: CoverageQuality = CoverageQuality.UNKNOWN
    delisted_coverage: CoverageQuality = CoverageQuality.UNKNOWN
    universe_membership_quality: CoverageQuality = CoverageQuality.UNKNOWN
    identity_coverage: CoverageQuality = CoverageQuality.UNKNOWN
    exchange_authority: bool = False
    supports_instrument_master: bool = False
    supports_symbol_isin_mapping: bool = False
    supports_historical_identifiers: bool = False
    # Phase 7 explicit capability declarations (evidence must back claims)
    supports_daily_bars: bool = False
    supports_corporate_actions: bool = False
    supports_pit_universe: bool = False
    supports_delisted_instruments: bool = False
    supports_provenance: bool = False
    supports_licensing_evidence: bool = False
    supported_exchanges: list[str] = Field(default_factory=list)
    supported_date_range: dict[str, str] = Field(default_factory=dict)
    redistribution_allowed: bool | None = None
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    authority_evidence_refs: list[str] = Field(default_factory=list)
    licensing_notes: str = ""
    usage_notes: str = ""
    limitations: list[str] = Field(default_factory=list)

    def can_satisfy_research_eligibility_source_bar(self) -> bool:
        """Source-grade bar only — full eligibility still requires calendar/universe/CA/quality."""
        if self.provider_id in {"yfinance", "synthetic", "synthetic_fixture"}:
            return False
        if self.source_grade in {SourceGrade.NON_EXCHANGE, SourceGrade.SYNTHETIC}:
            return False
        if self.license_status in {LicenseStatus.PROHIBITED, LicenseStatus.EXPIRED}:
            return False
        return self.source_grade in {SourceGrade.EXCHANGE, SourceGrade.PAID} and (
            self.exchange_authority or self.source_grade == SourceGrade.PAID
        )

    def attestation_payload(self) -> dict:
        return self.model_dump(mode="json")

    def attestation_hash(self) -> str:
        # Lazy import avoids circular import via data.ingest → providers.roles
        from quantfund.data.ingest.checksums import hash_json

        return hash_json(self.attestation_payload())


def yfinance_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id="yfinance",
        provider_name="Yahoo Finance (yfinance)",
        source_grade=SourceGrade.NON_EXCHANGE,
        historical_depth="vendor_dependent",
        corporate_action_quality=CoverageQuality.PARTIAL,
        delisted_coverage=CoverageQuality.NONE,
        universe_membership_quality=CoverageQuality.NONE,
        identity_coverage=CoverageQuality.PARTIAL,
        exchange_authority=False,
        license_status=LicenseStatus.UNKNOWN,
        redistribution_allowed=False,
        supported_exchanges=[],
        licensing_notes=(
            "Yahoo Finance terms apply. Not an NSE/BSE authority. "
            "Do not redistribute bulk Yahoo data if prohibited by Yahoo ToS."
        ),
        usage_notes="Development prototyping only. Never research_eligible by itself.",
        limitations=[
            "non_exchange source_grade",
            "survivorship / delisting incomplete",
            "corporate actions may be incomplete or incorrect for India",
            "no official NIFTY membership",
        ],
    )


def unconfigured_research_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id="unconfigured_research",
        provider_name="Unconfigured ResearchProvider",
        source_grade=SourceGrade.EXCHANGE,
        historical_depth="none",
        corporate_action_quality=CoverageQuality.NONE,
        delisted_coverage=CoverageQuality.NONE,
        universe_membership_quality=CoverageQuality.NONE,
        identity_coverage=CoverageQuality.NONE,
        exchange_authority=False,
        license_status=LicenseStatus.UNKNOWN,
        licensing_notes="No provider configured.",
        limitations=["No exchange-grade feed configured — refuses to fabricate bars."],
    )


def synthetic_capabilities(*, package_id: str = "synthetic") -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id=package_id,
        provider_name="Synthetic fixture package",
        source_grade=SourceGrade.SYNTHETIC,
        historical_depth="fixture",
        corporate_action_quality=CoverageQuality.PARTIAL,
        delisted_coverage=CoverageQuality.NONE,
        universe_membership_quality=CoverageQuality.PARTIAL,
        identity_coverage=CoverageQuality.PARTIAL,
        exchange_authority=False,
        supports_instrument_master=True,
        supports_symbol_isin_mapping=True,
        supports_historical_identifiers=True,
        supports_daily_bars=True,
        supports_corporate_actions=True,
        supports_pit_universe=True,
        supports_delisted_instruments=False,
        supports_provenance=True,
        supports_licensing_evidence=True,
        license_status=LicenseStatus.REDISTRIBUTABLE,
        redistribution_allowed=True,
        limitations=["synthetic — never research_eligible"],
    )


FORBIDDEN_RESEARCH_PROVIDER_IDS = frozenset(
    {"yfinance", "synthetic", "synthetic_fixture", "unconfigured_research"}
)

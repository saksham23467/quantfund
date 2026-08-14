"""Market-data adapters.

- ``UnconfiguredLicensedMarketDataProvider``: placeholder for a licensed /
  exchange-authoritative OHLCV feed. None is configured, so every capability
  fails closed.
- ``ZerodhaDevelopmentMarketDataProvider``: honest non_exchange adapter. Useful
  for development/paper only; it is NEVER research-grade and does not supply
  authoritative identity/membership/delisting/CA/calendar data.
"""

from __future__ import annotations

from datetime import date

from quantfund.data.grades import SourceGrade
from quantfund.data.providers.capabilities import (
    CoverageQuality,
    LicenseStatus,
    ProviderCapabilities,
    unconfigured_research_capabilities,
)
from quantfund.research.data_contract.models import OHLCVBar
from quantfund.research.providers.base import (
    ProviderAvailability,
    ResearchDataProvider,
    ResearchDataUnavailable,
)


class UnconfiguredLicensedMarketDataProvider(ResearchDataProvider):
    provider_id = "unconfigured_licensed_market_data"

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()


class ZerodhaDevelopmentMarketDataProvider(ResearchDataProvider):
    """Non-exchange broker adapter. Development/paper only — not research-grade."""

    provider_id = "zerodha"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="zerodha",
            provider_name="Zerodha Historical API (broker-redistributed)",
            source_grade=SourceGrade.NON_EXCHANGE,
            historical_depth="broker_dependent",
            corporate_action_quality=CoverageQuality.UNKNOWN,
            delisted_coverage=CoverageQuality.UNKNOWN,
            universe_membership_quality=CoverageQuality.NONE,
            identity_coverage=CoverageQuality.PARTIAL,
            exchange_authority=False,
            supports_daily_bars=True,
            license_status=LicenseStatus.INTERNAL_RESEARCH_ONLY,
            redistribution_allowed=False,
            licensing_notes=(
                "Broker account data. Not an exchange authority. Remains "
                "non_exchange / DEVELOPMENT_DATA and can never be research_eligible."
            ),
            limitations=[
                "non_exchange source_grade",
                "no authoritative ISIN/security master",
                "no PIT index membership",
                "no terminal-event ledger",
            ],
        )

    def availability(self) -> ProviderAvailability:
        # Broker bars exist but are non_exchange; identity/membership/etc. do not.
        return ProviderAvailability(daily_bars=True)

    def get_daily_bars(
        self, symbols: list[str], *, start: date, end: date
    ) -> list[OHLCVBar]:
        # Intentionally not wired into research certification: broker bars are
        # non_exchange and must be ingested via the existing development package
        # path, not promoted here.
        raise ResearchDataUnavailable(
            "zerodha bars are non_exchange (DEVELOPMENT_DATA); not exposed as "
            "research-grade OHLCV — use the development package pipeline instead"
        )

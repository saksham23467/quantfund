"""PIT index-membership adapter.

No authoritative dated membership ledger is configured, so this fails closed.
It must NEVER backfill history from today's constituents.
"""

from __future__ import annotations

from quantfund.data.providers.capabilities import (
    ProviderCapabilities,
    unconfigured_research_capabilities,
)
from quantfund.research.data_contract.models import DelistingRecord, MembershipRecord
from quantfund.research.providers.base import (
    ProviderAvailability,
    ResearchDataProvider,
    ResearchDataUnavailable,
)


class UnconfiguredUniverseProvider(ResearchDataProvider):
    provider_id = "unconfigured_universe"

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()

    def get_index_membership(self, universe_id: str) -> list[MembershipRecord]:
        raise ResearchDataUnavailable(
            f"no authoritative PIT membership ledger configured for {universe_id!r} "
            "(dated member_from/member_to intervals); refusing to backfill from "
            "today's constituents"
        )


class UnconfiguredDelistingProvider(ResearchDataProvider):
    provider_id = "unconfigured_delistings"

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()

    def get_delistings(self) -> list[DelistingRecord]:
        raise ResearchDataUnavailable(
            "no authoritative terminal-event ledger configured "
            "(delisted/merged/acquired/suspended/expired with dates)"
        )

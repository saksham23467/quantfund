"""Corporate-action adapter.

No authoritative verified CA ledger is configured, so this fails closed. CA data
must remain separate from RAW execution prices; adjustment factors are never
invented.
"""

from __future__ import annotations

from quantfund.data.providers.capabilities import (
    ProviderCapabilities,
    unconfigured_research_capabilities,
)
from quantfund.research.data_contract.models import CorporateActionRecord
from quantfund.research.providers.base import (
    ProviderAvailability,
    ResearchDataProvider,
    ResearchDataUnavailable,
)


class UnconfiguredCorporateActionProvider(ResearchDataProvider):
    provider_id = "unconfigured_corporate_actions"

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()

    def get_corporate_actions(self) -> list[CorporateActionRecord]:
        raise ResearchDataUnavailable(
            "no authoritative verified corporate-action ledger configured"
        )

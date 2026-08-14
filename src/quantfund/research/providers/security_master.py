"""Security-master adapter (symbol <-> ISIN <-> instrument_id, historical).

No authoritative historical security master is configured, so this fails closed.
"""

from __future__ import annotations

from quantfund.data.providers.capabilities import (
    ProviderCapabilities,
    unconfigured_research_capabilities,
)
from quantfund.research.data_contract.models import IdentityRecord
from quantfund.research.providers.base import (
    ProviderAvailability,
    ResearchDataProvider,
    ResearchDataUnavailable,
)


class UnconfiguredSecurityMasterProvider(ResearchDataProvider):
    provider_id = "unconfigured_security_master"

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()

    def get_security_master(self) -> list[IdentityRecord]:
        raise ResearchDataUnavailable(
            "no authoritative historical security master configured "
            "(symbol<->ISIN<->instrument_id with validity ranges)"
        )

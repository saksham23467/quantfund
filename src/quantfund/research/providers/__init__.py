"""Research data source adapters.

The :class:`ResearchDataProvider` interface defines the six authoritative
capabilities required for research-grade certification. Concrete adapters are
implemented ONLY where a real, licensed/exchange source is available. When no
such source is configured, providers fail closed (raise
:class:`ResearchDataUnavailable`) rather than fabricate data.

The Zerodha adapter remains ``source_grade=non_exchange`` and is useful for
development / connectivity / paper trading only — never research-grade.
"""

from quantfund.research.providers.base import (
    ProviderAvailability,
    ResearchDataProvider,
    ResearchDataUnavailable,
)
from quantfund.research.providers.calendar import UnconfiguredCalendarProvider
from quantfund.research.providers.corporate_actions import (
    UnconfiguredCorporateActionProvider,
)
from quantfund.research.providers.licensed_market_data import (
    UnconfiguredLicensedMarketDataProvider,
    ZerodhaDevelopmentMarketDataProvider,
)
from quantfund.research.providers.security_master import (
    UnconfiguredSecurityMasterProvider,
)
from quantfund.research.providers.universe import (
    UnconfiguredDelistingProvider,
    UnconfiguredUniverseProvider,
)

__all__ = [
    "ProviderAvailability",
    "ResearchDataProvider",
    "ResearchDataUnavailable",
    "UnconfiguredCalendarProvider",
    "UnconfiguredCorporateActionProvider",
    "UnconfiguredDelistingProvider",
    "UnconfiguredLicensedMarketDataProvider",
    "UnconfiguredSecurityMasterProvider",
    "UnconfiguredUniverseProvider",
    "ZerodhaDevelopmentMarketDataProvider",
]

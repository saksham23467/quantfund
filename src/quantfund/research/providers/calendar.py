"""Authoritative trading-session calendar adapter.

An authoritative NSE session/holiday reference is required for calendar
certification. None is wired as a research provider here, so this fails closed.
(The repo's development NSECalendarProvider exists but is not an exchange
authority for certification purposes.)
"""

from __future__ import annotations

from datetime import date

from quantfund.data.providers.capabilities import (
    ProviderCapabilities,
    unconfigured_research_capabilities,
)
from quantfund.research.data_contract.models import CalendarSessionRecord
from quantfund.research.providers.base import (
    ProviderAvailability,
    ResearchDataProvider,
    ResearchDataUnavailable,
)


class UnconfiguredCalendarProvider(ResearchDataProvider):
    provider_id = "unconfigured_calendar"

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()

    def get_calendar(
        self, exchange: str, *, start: date, end: date
    ) -> list[CalendarSessionRecord]:
        raise ResearchDataUnavailable(
            f"no authoritative {exchange} trading-session reference configured"
        )

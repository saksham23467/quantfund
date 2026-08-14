"""ResearchDataProvider interface + fail-closed defaults."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quantfund.data.providers.capabilities import ProviderCapabilities
from quantfund.research.data_contract.models import (
    CalendarSessionRecord,
    CorporateActionRecord,
    DelistingRecord,
    IdentityRecord,
    MembershipRecord,
    OHLCVBar,
)


class ResearchDataUnavailable(RuntimeError):
    """Raised when a capability has no authoritative source configured.

    Fail-closed: callers must surface this as a coverage gap, never paper over
    it with inferred/fabricated data.
    """


@dataclass(frozen=True)
class ProviderAvailability:
    """Which authoritative capabilities a provider can actually satisfy."""

    daily_bars: bool = False
    security_master: bool = False
    index_membership: bool = False
    delistings: bool = False
    calendar: bool = False
    corporate_actions: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "daily_bars": self.daily_bars,
            "security_master": self.security_master,
            "index_membership": self.index_membership,
            "delistings": self.delistings,
            "calendar": self.calendar,
            "corporate_actions": self.corporate_actions,
        }


class ResearchDataProvider:
    """Adapter interface for authoritative / licensed research data.

    Subclasses override only the capabilities they genuinely provide. Every
    unimplemented capability raises :class:`ResearchDataUnavailable`.
    """

    provider_id: str = "abstract_research_provider"

    def capabilities(self) -> ProviderCapabilities:  # pragma: no cover - abstract
        raise NotImplementedError

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability()

    def get_daily_bars(
        self, symbols: list[str], *, start: date, end: date
    ) -> list[OHLCVBar]:
        raise ResearchDataUnavailable(f"{self.provider_id}: daily_bars unavailable")

    def get_security_master(self) -> list[IdentityRecord]:
        raise ResearchDataUnavailable(f"{self.provider_id}: security_master unavailable")

    def get_index_membership(self, universe_id: str) -> list[MembershipRecord]:
        raise ResearchDataUnavailable(
            f"{self.provider_id}: index_membership unavailable"
        )

    def get_delistings(self) -> list[DelistingRecord]:
        raise ResearchDataUnavailable(f"{self.provider_id}: delistings unavailable")

    def get_calendar(
        self, exchange: str, *, start: date, end: date
    ) -> list[CalendarSessionRecord]:
        raise ResearchDataUnavailable(f"{self.provider_id}: calendar unavailable")

    def get_corporate_actions(self) -> list[CorporateActionRecord]:
        raise ResearchDataUnavailable(
            f"{self.provider_id}: corporate_actions unavailable"
        )

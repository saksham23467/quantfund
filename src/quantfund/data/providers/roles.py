"""Provider role abstraction — keep vendor SDKs out of the research engine.

FeatureEngine / Strategy / ResearchRunner / BacktestEngine depend only on
DataProvider (+ optional graded/research interfaces), never on vendor SDKs.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import date, datetime

from quantfund.data.corporate_actions.models import CorporateAction
from quantfund.data.grades import SourceGrade
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.base import DataProvider
from quantfund.data.providers.capabilities import (
    ProviderCapabilities,
    unconfigured_research_capabilities,
    yfinance_capabilities,
)
from quantfund.data.providers.provenance import ProvenanceRecord


class GradedDataProvider(DataProvider):
    """DataProvider that exposes an explicit source_grade and capabilities."""

    @property
    @abstractmethod
    def source_grade(self) -> SourceGrade:
        """Exchange / paid / non_exchange / synthetic grade label."""

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Explicit capability declaration — not inferred from successful fetches."""

    @property
    def can_claim_research_eligible(self) -> bool:
        return self.capabilities().can_satisfy_research_eligibility_source_bar()


class DevelopmentProvider(GradedDataProvider):
    """Non-exchange / synthetic sources for prototyping only."""

    @property
    def source_grade(self) -> SourceGrade:
        return SourceGrade.NON_EXCHANGE

    @property
    def can_claim_research_eligible(self) -> bool:
        return False

    def capabilities(self) -> ProviderCapabilities:
        return yfinance_capabilities().model_copy(
            update={"provider_id": self.name, "provider_name": self.name}
        )


class ResearchProvider(GradedDataProvider):
    """Vendor-neutral research feed interface.

    Concrete NSE-grade / paid / local-package adapters implement this without
    changing FeatureEngine, Strategy, ResearchRunner, or BacktestEngine.
    """

    @abstractmethod
    def provenance(self) -> ProvenanceRecord:
        """Provenance for the currently loaded package / session."""

    def get_instrument_master(self) -> list[Instrument]:
        """Instrument master (may equal get_instruments())."""
        return self.get_instruments()

    def get_corporate_actions(
        self,
        *,
        symbol: str | None = None,
        instrument_id: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateAction]:
        """Corporate actions known to this provider. Default: none (explicit)."""
        return []

    def get_delisted_instruments(self) -> list[Instrument]:
        """Instruments with delisting_date set. Default: none (explicit)."""
        return [i for i in self.get_instrument_master() if i.delisting_date is not None]

    def get_symbol_mappings(self) -> dict[str, dict[str, str]]:
        """Map instrument_id → {provider: symbol, ...}."""
        out: dict[str, dict[str, str]] = {}
        for inst in self.get_instrument_master():
            iid = inst.instrument_id or inst.symbol
            mapping = dict(inst.provider_symbols)
            if inst.provider_symbol:
                mapping.setdefault(self.name, inst.provider_symbol)
            out[iid] = mapping
        return out


class UnconfiguredResearchProvider(ResearchProvider):
    """Placeholder until an exchange-grade feed is configured.

    Explicitly refuses to invent research bars.
    """

    def __init__(self, *, provider_name: str = "unconfigured_research") -> None:
        self._name = provider_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def source_grade(self) -> SourceGrade:
        # Declares intended role, but capabilities.exchange_authority=False
        # so can_claim_research_eligible remains False.
        return SourceGrade.EXCHANGE

    def capabilities(self) -> ProviderCapabilities:
        return unconfigured_research_capabilities()

    @property
    def can_claim_research_eligible(self) -> bool:
        return False

    def provenance(self) -> ProvenanceRecord:
        return ProvenanceRecord(
            source=self._name,
            provider=self._name,
            download_timestamp=datetime.now().astimezone(),
            limitations=["No provider configured"],
        )

    def get_instruments(self) -> list[Instrument]:
        return []

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        raise NotImplementedError(
            "No exchange-grade ResearchProvider configured. "
            "Do not fabricate research bars; label missing data explicitly."
        )

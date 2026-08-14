"""StrategyGenerator abstraction — provider-independent, untrusted output."""

from __future__ import annotations

from abc import ABC, abstractmethod

from quantfund.ai.models import GenerationRequest
from quantfund.strategies.spec.models import StrategySpec


class StrategyGenerator(ABC):
    """Produce StrategySpec candidates. Must not evaluate or accept them."""

    @property
    @abstractmethod
    def generator_type(self) -> str:
        ...

    @abstractmethod
    def generate(self, request: GenerationRequest) -> list[StrategySpec]:
        """Return candidate specs. Must not access TEST or evaluation results."""

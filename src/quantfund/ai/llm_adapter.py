"""LLM strategy generator interface — UNTRUSTED, not connected.

No OpenAI/Gemini/Anthropic SDK. Future providers plug in here; every response
must still pass JSON → StrategySpec → StrategySpecValidator → interpreter.
"""

from __future__ import annotations

from quantfund.ai.generator import StrategyGenerator
from quantfund.ai.models import GenerationRequest
from quantfund.strategies.spec.models import StrategySpec


class LLMStrategyGenerator(StrategyGenerator):
    """Stub adapter. Refuses to call any network LLM in Phase 4."""

    def __init__(self, *, provider_name: str = "unconnected_llm") -> None:
        self._provider_name = provider_name

    @property
    def generator_type(self) -> str:
        return "llm_adapter_unconnected"

    def generate(self, request: GenerationRequest) -> list[StrategySpec]:
        raise NotImplementedError(
            f"LLMStrategyGenerator ({self._provider_name}) is not connected. "
            "Phase 4 uses MockStrategyGenerator only. "
            "When connected later, raw model output must be treated as untrusted "
            "data and validated before interpretation — never executed as code."
        )

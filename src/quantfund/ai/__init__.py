"""AI strategy factory — generation only. Untrusted output → validator → interpreter.

Never contains brokers, live trading, credentials, or acceptance authority.
"""

from quantfund.ai.genealogy import StrategyGenealogy, canonical_strategy_hash
from quantfund.ai.generator import StrategyGenerator
from quantfund.ai.mock_generator import MockStrategyGenerator
from quantfund.ai.models import GenerationRequest, PipelineBatchResult
from quantfund.ai.pipeline import StrategyResearchPipeline

__all__ = [
    "GenerationRequest",
    "MockStrategyGenerator",
    "PipelineBatchResult",
    "StrategyGenealogy",
    "StrategyGenerator",
    "StrategyResearchPipeline",
    "canonical_strategy_hash",
]

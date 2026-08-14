"""Broker adapters (Phase 9B). Strategy / ResearchRunner must not import this package."""

from quantfund.brokers.base import (
    BrokerExecutionAdapter,
    BrokerFill,
    BrokerOrderRequest,
    UnsupportedBrokerOrderError,
)
from quantfund.brokers.intent_store import ExecutionIntentStore

__all__ = [
    "BrokerExecutionAdapter",
    "BrokerFill",
    "BrokerOrderRequest",
    "ExecutionIntentStore",
    "UnsupportedBrokerOrderError",
]

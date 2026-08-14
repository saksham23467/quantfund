"""Phase 9 live execution boundary — DRY_RUN + MockBroker only.

No real broker SDK. No network order path. Real orders sent: always 0.
Paper fills remain owned by quantfund.paper.PaperExecutionAdapter.
"""

from quantfund.execution.broker_adapter import (
    ALLOWED_BROKER_ADAPTER_IDS,
    BrokerAdapter,
    assert_mock_only,
)
from quantfund.execution.capabilities import BrokerCapabilities, CapabilityError
from quantfund.execution.gateway import ExecutionGateway, ExecutionMode, GatewayConfig
from quantfund.execution.live_eligibility import (
    LiveAuthorization,
    LiveEligibilityDecision,
    LiveTradingEligibilityGate,
)
from quantfund.execution.live_orders import BrokerOrderState, make_client_order_id
from quantfund.execution.mock_broker import MockBehavior, MockBrokerAdapter
from quantfund.execution.operator_approval import OperatorApprovalGate

__all__ = [
    "ALLOWED_BROKER_ADAPTER_IDS",
    "BrokerAdapter",
    "BrokerCapabilities",
    "BrokerOrderState",
    "CapabilityError",
    "ExecutionGateway",
    "ExecutionMode",
    "GatewayConfig",
    "LiveAuthorization",
    "LiveEligibilityDecision",
    "LiveTradingEligibilityGate",
    "MockBehavior",
    "MockBrokerAdapter",
    "OperatorApprovalGate",
    "assert_mock_only",
    "make_client_order_id",
]

"""Public memory Gateway contract and no-key Fake implementation."""

from memscope.memory_gateway.errors import (
    GatewayConflictError,
    GatewayProtocolError,
    GatewayRateLimitedError,
    GatewayTimeoutError,
    GatewayUnavailableError,
)
from memscope.memory_gateway.fake import FakeMemoryGateway, GatewayOperation
from memscope.memory_gateway.memos import MemosMemoryGateway
from memscope.memory_gateway.models import (
    GatewayAdd,
    GatewayEvidence,
    GatewayMessage,
    GatewaySearch,
)
from memscope.memory_gateway.protocol import MemoryGateway
from memscope.memory_gateway.receipt_store import (
    GatewayReceipt,
    GatewayReceiptStore,
    ReceiptStatus,
)

__all__ = [
    "FakeMemoryGateway",
    "GatewayAdd",
    "GatewayConflictError",
    "GatewayEvidence",
    "GatewayMessage",
    "GatewayOperation",
    "GatewayProtocolError",
    "GatewayRateLimitedError",
    "GatewayReceipt",
    "GatewayReceiptStore",
    "GatewaySearch",
    "GatewayTimeoutError",
    "GatewayUnavailableError",
    "MemoryGateway",
    "MemosMemoryGateway",
    "ReceiptStatus",
]

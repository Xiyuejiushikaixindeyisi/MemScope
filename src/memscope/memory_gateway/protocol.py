"""Provider-independent asynchronous memory Gateway port."""

from collections.abc import Sequence
from typing import Protocol

from memscope.memory_gateway.models import GatewayAdd, GatewayEvidence, GatewaySearch


class MemoryGateway(Protocol):
    """Operations required from Fake and future real memory providers."""

    async def is_ready(self) -> bool:
        """Return whether Add and Search can currently be attempted."""

        ...  # pragma: no cover - structural protocol signature

    async def add(self, request: GatewayAdd, *, timeout_seconds: float) -> None:
        """Synchronously make an idempotent Add visible to Search."""

        ...  # pragma: no cover - structural protocol signature

    async def search(
        self,
        request: GatewaySearch,
        *,
        timeout_seconds: float,
    ) -> Sequence[GatewayEvidence]:
        """Return ranked evidence for exactly one user and logical Cube."""

        ...  # pragma: no cover - structural protocol signature

    async def close(self) -> None:
        """Release resources and reject subsequent work."""

        ...  # pragma: no cover - structural protocol signature

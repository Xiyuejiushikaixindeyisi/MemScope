"""Application-facing persistence port for raw Add data."""

from typing import Protocol

from memscope.operations import AddCommand
from memscope.raw_store.models import PersistedAdd, PreparedAdd, StoredAddResponse


class RawStore(Protocol):
    """Asynchronous persistence boundary used by future orchestration."""

    async def is_ready(self) -> bool:
        """Return whether the store can safely read its current schema."""

        ...  # pragma: no cover - structural protocol signature

    async def prepare_add(self, command: AddCommand) -> PreparedAdd:
        """Atomically persist a new Add or classify its exact replay."""

        ...  # pragma: no cover - structural protocol signature

    async def complete_add(
        self,
        request_id: str,
        payload_sha256: str,
        response: StoredAddResponse,
    ) -> None:
        """Atomically retain a successful response and complete its outbox."""

        ...  # pragma: no cover - structural protocol signature

    async def load_add(self, user_id: str, request_id: str) -> PersistedAdd | None:
        """Load one request only when it belongs to the exact user."""

        ...  # pragma: no cover - structural protocol signature

    async def close(self) -> None:
        """Prevent new operations; already-running transactions may finish."""

        ...  # pragma: no cover - structural protocol signature

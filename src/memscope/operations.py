"""Framework-independent application port for the contest adapter."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Protocol

from memscope.errors import MemScopeError


def _require_nonblank(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


@dataclass(frozen=True, slots=True)
class MemoryMessage:
    """One ordered conversation message accepted by Add."""

    role: str
    content: str
    timestamp: int | None = None

    def __post_init__(self) -> None:
        _require_nonblank("role", self.role)
        _require_nonblank("content", self.content)
        if self.timestamp is not None and (
            isinstance(self.timestamp, bool) or not isinstance(self.timestamp, int)
        ):
            raise TypeError("timestamp must be an integer or None")


@dataclass(frozen=True, slots=True)
class AddCommand:
    """Validated Add input passed beyond the HTTP boundary."""

    request_id: str
    user_id: str
    session_id: str
    messages: tuple[MemoryMessage, ...]

    def __post_init__(self) -> None:
        _require_nonblank("request_id", self.request_id)
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("session_id", self.session_id)
        if not self.messages:
            raise ValueError("messages must not be empty")


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Validated Search input passed beyond the HTTP boundary."""

    query: str
    user_id: str
    top_k: int
    options: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _require_nonblank("query", self.query)
        _require_nonblank("user_id", self.user_id)
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int):
            raise TypeError("top_k must be an integer")
        if not 1 <= self.top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        if self.options is not None and not all(isinstance(option, str) for option in self.options):
            raise TypeError("options must contain only strings")


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    """One ranked memory evidence item returned by the application layer."""

    id: str
    content: str
    score: float | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_nonblank("id", self.id)
        _require_nonblank("content", self.content)
        if self.score is not None and not isfinite(self.score):
            raise ValueError("score must be finite")
        if self.created_at is not None and self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")


class ContestOperations(Protocol):
    """Application operations required by the contest HTTP adapter."""

    async def is_ready(self) -> bool:
        """Return whether the complete configured memory path is ready."""

        ...  # pragma: no cover - structural protocol signature

    async def add(self, command: AddCommand) -> None:
        """Persist an Add command before returning successfully."""

        ...  # pragma: no cover - structural protocol signature

    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]:
        """Return evidence in descending application-defined relevance order."""

        ...  # pragma: no cover - structural protocol signature


class ServiceUnavailableError(MemScopeError):
    """Raised when no complete memory operation path is currently available."""

    def __init__(self) -> None:
        super().__init__(
            code="service.unavailable",
            message="Memory service is currently unavailable",
            retryable=True,
        )


class UnavailableContestOperations:
    """Safe default that never claims persistence or retrieval success."""

    async def is_ready(self) -> bool:
        return False

    async def add(self, command: AddCommand) -> None:
        del command
        raise ServiceUnavailableError()

    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]:
        del query
        raise ServiceUnavailableError()

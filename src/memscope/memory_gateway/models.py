"""Framework- and provider-independent Memory Gateway value objects."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


def _require_nonblank(name: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_exact_integer(name: str, value: int, *, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} is below its minimum")


def _require_sha256(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("payload_sha256 must be a string")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("payload_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class GatewayMessage:
    """One exact, provenance-bearing message sent to a memory provider."""

    message_id: str
    request_position: int
    role: str
    content: str
    timestamp_ms: int | None = None

    def __post_init__(self) -> None:
        _require_nonblank("message_id", self.message_id)
        _require_exact_integer("request_position", self.request_position, minimum=0)
        _require_nonblank("role", self.role)
        _require_nonblank("content", self.content)
        if self.timestamp_ms is not None:
            _require_exact_integer("timestamp_ms", self.timestamp_ms, minimum=-(2**63))
            if self.timestamp_ms > 2**63 - 1:
                raise ValueError("timestamp_ms is above its maximum")


@dataclass(frozen=True, slots=True)
class GatewayAdd:
    """One synchronous, idempotent memory write request."""

    request_id: str
    payload_sha256: str
    user_id: str
    session_id: str
    cube_id: str
    session_start_position: int
    messages: tuple[GatewayMessage, ...]

    def __post_init__(self) -> None:
        _require_nonblank("request_id", self.request_id)
        _require_sha256(self.payload_sha256)
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("session_id", self.session_id)
        _require_nonblank("cube_id", self.cube_id)
        _require_exact_integer("session_start_position", self.session_start_position, minimum=0)
        if not isinstance(self.messages, tuple):
            raise TypeError("messages must be a tuple")
        if not self.messages:
            raise ValueError("messages must not be empty")
        positions = tuple(message.request_position for message in self.messages)
        if positions != tuple(range(len(self.messages))):
            raise ValueError("message request positions must be contiguous")
        message_ids = tuple(message.message_id for message in self.messages)
        if len(set(message_ids)) != len(message_ids):
            raise ValueError("message IDs must be unique")


@dataclass(frozen=True, slots=True)
class GatewaySearch:
    """One user- and Cube-isolated evidence query."""

    query: str
    user_id: str
    cube_id: str
    top_k: int
    options: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _require_nonblank("query", self.query)
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("cube_id", self.cube_id)
        _require_exact_integer("top_k", self.top_k, minimum=1)
        if self.top_k > 100:
            raise ValueError("top_k must not exceed 100")
        if self.options is not None:
            if not isinstance(self.options, tuple):
                raise TypeError("options must be a tuple or None")
            if not all(isinstance(option, str) for option in self.options):
                raise TypeError("options must contain strings")


@dataclass(frozen=True, slots=True)
class GatewayEvidence:
    """One ranked evidence item with mandatory isolation provenance."""

    id: str
    content: str
    user_id: str
    cube_id: str
    score: float | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_nonblank("id", self.id)
        _require_nonblank("content", self.content)
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("cube_id", self.cube_id)
        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, int | float):
                raise TypeError("score must be a number or None")
            if not isfinite(self.score):
                raise ValueError("score must be finite")
        if self.created_at is not None:
            if not isinstance(self.created_at, datetime):
                raise TypeError("created_at must be a datetime or None")
            if self.created_at.utcoffset() is None:
                raise ValueError("created_at must include a timezone")

"""Framework- and backend-independent Raw Store value objects."""

from dataclasses import dataclass
from enum import StrEnum


def _require_nonblank(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("payload_sha256 must be a lowercase SHA-256 digest")


class AddDisposition(StrEnum):
    """Result of preparing an Add request in persistent storage."""

    NEW = "new"
    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class StoredAddResponse:
    """Successful Add response retained for exact idempotent replay."""

    success: bool
    request_id: str
    user_id: str
    session_id: str

    def __post_init__(self) -> None:
        if self.success is not True:
            raise ValueError("stored Add response must be successful")
        _require_nonblank("request_id", self.request_id)
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("session_id", self.session_id)


@dataclass(frozen=True, slots=True)
class UserCube:
    """Stable logical mapping from one external user to one Cube."""

    user_id: str
    cube_id: str
    status: str

    def __post_init__(self) -> None:
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("cube_id", self.cube_id)
        if self.status != "reserved":
            raise ValueError("unsupported user Cube status")


@dataclass(frozen=True, slots=True)
class PreparedAdd:
    """Persistent preparation outcome consumed by future orchestration."""

    disposition: AddDisposition
    payload_sha256: str
    cube: UserCube
    session_start_position: int
    response: StoredAddResponse | None

    def __post_init__(self) -> None:
        _require_sha256(self.payload_sha256)
        if isinstance(self.session_start_position, bool) or not isinstance(
            self.session_start_position, int
        ):
            raise TypeError("session_start_position must be an integer")
        if self.session_start_position < 0:
            raise ValueError("session_start_position must not be negative")
        if self.disposition is AddDisposition.COMPLETED and self.response is None:
            raise ValueError("completed preparation requires a stored response")
        if self.disposition is not AddDisposition.COMPLETED and self.response is not None:
            raise ValueError("only completed preparation may include a response")


@dataclass(frozen=True, slots=True)
class PersistedMessage:
    """One exact Raw Store message with request and session ordering."""

    message_id: str
    request_position: int
    session_position: int
    role: str
    content: str
    timestamp_ms: int | None

    def __post_init__(self) -> None:
        _require_nonblank("message_id", self.message_id)
        if isinstance(self.request_position, bool) or not isinstance(self.request_position, int):
            raise TypeError("request_position must be an integer")
        if isinstance(self.session_position, bool) or not isinstance(self.session_position, int):
            raise TypeError("session_position must be an integer")
        if self.request_position < 0 or self.session_position < 0:
            raise ValueError("message positions must not be negative")
        _require_nonblank("role", self.role)
        _require_nonblank("content", self.content)
        if self.timestamp_ms is not None and (
            isinstance(self.timestamp_ms, bool) or not isinstance(self.timestamp_ms, int)
        ):
            raise TypeError("timestamp_ms must be an integer or None")


@dataclass(frozen=True, slots=True)
class PersistedAdd:
    """One persisted Add request and all of its ordered raw messages."""

    request_id: str
    payload_sha256: str
    user_id: str
    session_id: str
    status: str
    messages: tuple[PersistedMessage, ...]
    response: StoredAddResponse | None

    def __post_init__(self) -> None:
        _require_nonblank("request_id", self.request_id)
        _require_sha256(self.payload_sha256)
        _require_nonblank("user_id", self.user_id)
        _require_nonblank("session_id", self.session_id)
        if self.status not in {"pending", "completed"}:
            raise ValueError("unsupported persisted Add status")
        if not self.messages:
            raise ValueError("persisted Add requires messages")
        if self.status == "completed" and self.response is None:
            raise ValueError("completed persisted Add requires a response")
        if self.status == "pending" and self.response is not None:
            raise ValueError("pending persisted Add cannot include a response")

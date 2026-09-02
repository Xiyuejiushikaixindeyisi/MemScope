"""Tests for framework-independent Raw Store value objects and errors."""

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from memscope.errors import MemScopeError
from memscope.raw_store.errors import (
    IdempotencyConflictError,
    MigrationError,
    RawStoreInvariantError,
    RawStoreUnavailableError,
)
from memscope.raw_store.models import (
    AddDisposition,
    PersistedAdd,
    PersistedMessage,
    PreparedAdd,
    StoredAddResponse,
    UserCube,
)
from memscope.raw_store.protocol import RawStore

_DIGEST = "a" * 64


def _response() -> StoredAddResponse:
    return StoredAddResponse(True, "request", "user", "session")


def _cube() -> UserCube:
    return UserCube("user", "cube", "reserved")


def _message() -> PersistedMessage:
    return PersistedMessage("message", 0, 3, "user", "content", None)


def test_valid_models_are_frozen_and_preserve_values() -> None:
    response = _response()
    prepared = PreparedAdd(AddDisposition.COMPLETED, _DIGEST, _cube(), response)
    persisted = PersistedAdd(
        "request", _DIGEST, "user", "session", "completed", (_message(),), response
    )

    assert prepared.response is response
    assert persisted.messages[0].session_position == 3
    with pytest.raises(FrozenInstanceError):
        response.success = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: StoredAddResponse(False, "request", "user", "session"),
        lambda: StoredAddResponse(True, " ", "user", "session"),
        lambda: StoredAddResponse(True, "request", " ", "session"),
        lambda: StoredAddResponse(True, "request", "user", " "),
        lambda: UserCube(" ", "cube", "reserved"),
        lambda: UserCube("user", " ", "reserved"),
        lambda: UserCube("user", "cube", "created"),
        lambda: PreparedAdd(AddDisposition.NEW, "bad", _cube(), None),
        lambda: PreparedAdd(AddDisposition.COMPLETED, _DIGEST, _cube(), None),
        lambda: PreparedAdd(AddDisposition.PENDING, _DIGEST, _cube(), _response()),
        lambda: PersistedMessage(" ", 0, 0, "user", "content", None),
        lambda: PersistedMessage("message", -1, 0, "user", "content", None),
        lambda: PersistedMessage("message", 0, -1, "user", "content", None),
        lambda: PersistedMessage("message", 0, 0, " ", "content", None),
        lambda: PersistedMessage("message", 0, 0, "user", " ", None),
        lambda: PersistedAdd(" ", _DIGEST, "user", "session", "pending", (_message(),), None),
        lambda: PersistedAdd(
            "request", "z" * 64, "user", "session", "pending", (_message(),), None
        ),
        lambda: PersistedAdd("request", _DIGEST, " ", "session", "pending", (_message(),), None),
        lambda: PersistedAdd("request", _DIGEST, "user", " ", "pending", (_message(),), None),
        lambda: PersistedAdd("request", _DIGEST, "user", "session", "other", (_message(),), None),
        lambda: PersistedAdd("request", _DIGEST, "user", "session", "pending", (), None),
        lambda: PersistedAdd(
            "request", _DIGEST, "user", "session", "completed", (_message(),), None
        ),
        lambda: PersistedAdd(
            "request", _DIGEST, "user", "session", "pending", (_message(),), _response()
        ),
    ],
)
def test_models_reject_invalid_combinations(factory: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "args",
    [
        ("message", True, 0, "user", "content", None),
        ("message", 0, False, "user", "content", None),
        ("message", 0, 0, "user", "content", True),
    ],
)
def test_persisted_message_requires_exact_integer_types(args: tuple[object, ...]) -> None:
    with pytest.raises(TypeError):
        PersistedMessage(*args)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (IdempotencyConflictError(), "request.conflict", False),
        (RawStoreUnavailableError(), "storage.unavailable", True),
        (RawStoreInvariantError(), "storage.invariant_failed", False),
        (MigrationError(), "storage.migration_failed", False),
    ],
)
def test_raw_store_errors_have_fixed_safe_metadata(
    error: MemScopeError, code: str, retryable: bool
) -> None:
    assert error.code == code
    assert error.retryable is retryable
    assert "secret" not in str(error)


async def test_raw_store_protocol_signatures_are_structural_only() -> None:
    marker = object()
    protocol = cast("Any", RawStore)

    assert await protocol.is_ready(marker) is None
    assert await protocol.prepare_add(marker, object()) is None
    assert await protocol.complete_add(marker, "request", _DIGEST, _response()) is None
    assert await protocol.load_add(marker, "user", "request") is None
    assert await protocol.close(marker) is None

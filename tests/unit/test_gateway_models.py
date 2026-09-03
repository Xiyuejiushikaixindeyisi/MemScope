"""Validation tests for provider-independent Gateway value objects."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from memscope.memory_gateway import GatewayAdd, GatewayEvidence, GatewayMessage, GatewaySearch


def _message(**changes: object) -> GatewayMessage:
    values = {
        "message_id": "message-1",
        "request_position": 0,
        "role": "user",
        "content": "exact content",
        "timestamp_ms": 0,
        **changes,
    }
    return GatewayMessage(**values)  # type: ignore[arg-type]


def _add(**changes: object) -> GatewayAdd:
    values = {
        "request_id": "request-1",
        "payload_sha256": "a" * 64,
        "user_id": "user-1",
        "session_id": "session-1",
        "cube_id": "cube-1",
        "session_start_position": 0,
        "messages": (_message(),),
        **changes,
    }
    return GatewayAdd(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("message_id", " ", ValueError),
        ("message_id", 1, TypeError),
        ("request_position", True, TypeError),
        ("request_position", -1, ValueError),
        ("role", "", ValueError),
        ("content", "\t", ValueError),
        ("timestamp_ms", True, TypeError),
        ("timestamp_ms", -(2**63) - 1, ValueError),
        ("timestamp_ms", 2**63, ValueError),
    ],
)
def test_gateway_message_rejects_invalid_values(
    field: str, value: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        _message(**{field: value})


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"request_id": ""}, ValueError),
        ({"payload_sha256": 1}, TypeError),
        ({"payload_sha256": "A" * 64}, ValueError),
        ({"payload_sha256": "0" * 63}, ValueError),
        ({"user_id": " "}, ValueError),
        ({"session_id": ""}, ValueError),
        ({"cube_id": ""}, ValueError),
        ({"session_start_position": True}, TypeError),
        ({"session_start_position": -1}, ValueError),
        ({"messages": [_message()]}, TypeError),
        ({"messages": ()}, ValueError),
        ({"messages": (_message(request_position=1),)}, ValueError),
        ({"messages": (_message(), replace(_message(), request_position=1))}, ValueError),
    ],
)
def test_gateway_add_rejects_invalid_values(
    changes: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        _add(**changes)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"query": ""}, ValueError),
        ({"user_id": " "}, ValueError),
        ({"cube_id": 1}, TypeError),
        ({"top_k": True}, TypeError),
        ({"top_k": 0}, ValueError),
        ({"top_k": 101}, ValueError),
        ({"options": []}, TypeError),
        ({"options": ("a", 1)}, TypeError),
    ],
)
def test_gateway_search_rejects_invalid_values(
    changes: dict[str, object], error: type[Exception]
) -> None:
    values = {"query": "fact", "user_id": "u", "cube_id": "c", "top_k": 3, **changes}
    with pytest.raises(error):
        GatewaySearch(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"id": ""}, ValueError),
        ({"content": 1}, TypeError),
        ({"user_id": " "}, ValueError),
        ({"cube_id": ""}, ValueError),
        ({"score": True}, TypeError),
        ({"score": float("inf")}, ValueError),
        ({"created_at": "today"}, TypeError),
        ({"created_at": datetime(2026, 1, 1)}, ValueError),
    ],
)
def test_gateway_evidence_rejects_invalid_values(
    changes: dict[str, object], error: type[Exception]
) -> None:
    values = {"id": "m", "content": "fact", "user_id": "u", "cube_id": "c", **changes}
    with pytest.raises(error):
        GatewayEvidence(**values)  # type: ignore[arg-type]


def test_gateway_models_accept_valid_boundary_values() -> None:
    messages = (
        _message(timestamp_ms=-(2**63)),
        _message(message_id="message-2", request_position=1, timestamp_ms=2**63 - 1),
    )
    request = _add(messages=messages)
    search = GatewaySearch("fact", "u", "c", 100, ())
    evidence = GatewayEvidence("m", "fact", "u", "c", 1, datetime.now(UTC))

    assert request.messages == messages
    assert search.options == ()
    assert evidence.score == 1

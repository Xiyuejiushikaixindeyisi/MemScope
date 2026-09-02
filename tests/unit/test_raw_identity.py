"""Tests for versioned Raw Store payload and identity algorithms."""

from dataclasses import replace

import pytest

from memscope.operations import AddCommand, MemoryMessage
from memscope.raw_store.identity import (
    canonical_add_payload,
    cube_id_for_user,
    message_id_for_position,
    payload_sha256,
)


def _command() -> AddCommand:
    return AddCommand(
        request_id="req-α",
        user_id="user-1",
        session_id="session-1",
        messages=(
            MemoryMessage(role="user", content=" hello ", timestamp=None),
            MemoryMessage(role="assistant", content="答", timestamp=1704067208000),
        ),
    )


def test_canonical_payload_and_digest_match_golden_vector() -> None:
    command = _command()

    assert canonical_add_payload(command).decode() == (
        '{"messages":[{"content":" hello ","role":"user","timestamp":null},'
        '{"content":"答","role":"assistant","timestamp":1704067208000}],'
        '"request_id":"req-α","schema":"memscope.add.v1",'
        '"session_id":"session-1","user_id":"user-1"}'
    )
    assert payload_sha256(command) == (
        "09b554696bdca5e5790f1a8123440524ca63a0748c3674f66efc335195707d3f"
    )


@pytest.mark.parametrize(
    "changed",
    [
        replace(_command(), request_id="other"),
        replace(_command(), user_id="other"),
        replace(_command(), session_id="other"),
        replace(_command(), messages=tuple(reversed(_command().messages))),
        replace(
            _command(),
            messages=(replace(_command().messages[0], content="hello"), _command().messages[1]),
        ),
        replace(
            _command(),
            messages=(replace(_command().messages[0], role="assistant"), _command().messages[1]),
        ),
        replace(
            _command(),
            messages=(replace(_command().messages[0], timestamp=0), _command().messages[1]),
        ),
    ],
)
def test_payload_digest_covers_every_exact_field_and_message_order(changed: AddCommand) -> None:
    assert payload_sha256(changed) != payload_sha256(_command())


def test_ids_match_golden_vectors_and_do_not_embed_external_values() -> None:
    cube_id = cube_id_for_user("user-1")
    message_id = message_id_for_position("req-α", 0)

    assert cube_id == ("cube_v1_c6c289e49e9c05b2145860387b73bcb18df43fb09a1e4a4a9713c76c88bb541b")
    assert message_id == ("msg_v1_4bc93e6a9be61d2a821fadd77e5a16ad79b500326e2667f640c5661cffd385e8")
    assert "user-1" not in cube_id
    assert "req-α" not in message_id
    assert cube_id_for_user("user-1") == cube_id
    assert cube_id_for_user("user-2") != cube_id
    assert message_id_for_position("req-α", 1) != message_id


@pytest.mark.parametrize("position", [-1, -100])
def test_message_id_rejects_negative_position(position: int) -> None:
    with pytest.raises(ValueError):
        message_id_for_position("request", position)


@pytest.mark.parametrize("position", [True, 1.2, "1"])
def test_message_id_rejects_non_integer_position(position: object) -> None:
    with pytest.raises(TypeError):
        message_id_for_position("request", position)  # type: ignore[arg-type]

"""Deterministic Fake Memory Gateway tests."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from memscope.memory_gateway import (
    FakeMemoryGateway,
    GatewayAdd,
    GatewayConflictError,
    GatewayMessage,
    GatewayOperation,
    GatewayProtocolError,
    GatewayRateLimitedError,
    GatewaySearch,
    GatewayTimeoutError,
    GatewayUnavailableError,
)


def _add(
    *,
    request_id: str = "request-1",
    user_id: str = "user-1",
    cube_id: str = "cube-1",
    message_id: str = "message-1",
    content: str = "The SSH port is 2222",
    timestamp_ms: int | None = 0,
) -> GatewayAdd:
    return GatewayAdd(
        request_id=request_id,
        payload_sha256="a" * 64,
        user_id=user_id,
        session_id="session-1",
        cube_id=cube_id,
        session_start_position=0,
        messages=(GatewayMessage(message_id, 0, "user", content, timestamp_ms),),
    )


def _search(
    *, query: str = "ssh port", user_id: str = "user-1", cube_id: str = "cube-1", top_k: int = 10
) -> GatewaySearch:
    return GatewaySearch(query, user_id, cube_id, top_k, ("A", "B"))


async def test_add_search_exact_replay_order_score_and_timestamp() -> None:
    gateway = FakeMemoryGateway()
    first = _add()
    second = _add(
        request_id="request-2",
        message_id="message-2",
        content="port only",
        timestamp_ms=None,
    )

    await gateway.add(first)
    await gateway.add(first)
    await gateway.add(second)
    evidence = await gateway.search(_search())

    assert [item.id for item in evidence] == ["message-1", "message-2"]
    assert [item.score for item in evidence] == [1.0, 0.5]
    assert evidence[0].created_at == datetime(1970, 1, 1, tzinfo=UTC)
    assert evidence[1].created_at is None
    assert evidence[0].content == first.messages[0].content


async def test_search_isolated_empty_stable_tie_and_top_k() -> None:
    gateway = FakeMemoryGateway()
    await gateway.add(_add(content="alpha", message_id="m1"))
    await gateway.add(_add(request_id="r2", content="alpha", message_id="m2"))
    await gateway.add(_add(request_id="other", user_id="user-2", cube_id="cube-2", message_id="m3"))

    assert [item.id for item in await gateway.search(_search(query="alpha", top_k=1))] == ["m1"]
    assert await gateway.search(_search(query="!!!")) == ()
    assert await gateway.search(_search(user_id="user-2", cube_id="cube-1")) == ()


async def test_search_skips_nonmatching_content_and_shared_exact_message_is_not_duplicated() -> (
    None
):
    gateway = FakeMemoryGateway()
    first = _add(content="alpha")
    shared = _add(request_id="request-2", content="alpha")
    irrelevant = _add(request_id="request-3", message_id="irrelevant", content="beta")
    await gateway.add(first)
    await gateway.add(shared)
    await gateway.add(irrelevant)

    assert [item.id for item in await gateway.search(_search(query="alpha"))] == ["message-1"]


@pytest.mark.parametrize(
    "changed",
    [
        replace(_add(), payload_sha256="b" * 64),
        _add(request_id="r2", user_id="user-1", cube_id="other-cube", message_id="m2"),
        _add(request_id="r2", user_id="other-user", cube_id="cube-1", message_id="m2"),
        _add(request_id="r2", message_id="message-1", content="different"),
    ],
)
async def test_add_identity_conflicts_are_fail_closed(changed: GatewayAdd) -> None:
    gateway = FakeMemoryGateway()
    await gateway.add(_add())

    with pytest.raises(GatewayConflictError):
        await gateway.add(changed)

    assert [item.id for item in await gateway.search(_search())] == ["message-1"]


async def test_concurrent_exact_add_is_unique_and_close_is_idempotent() -> None:
    gateway = FakeMemoryGateway()
    request = _add()
    await asyncio.gather(*(gateway.add(request) for _ in range(20)))

    assert len(await gateway.search(_search())) == 1
    await gateway.close()
    await gateway.close()
    assert await gateway.is_ready() is False
    with pytest.raises(GatewayUnavailableError):
        await gateway.add(_add(request_id="later"))
    with pytest.raises(GatewayUnavailableError):
        await gateway.search(_search())


@pytest.mark.parametrize(
    ("operation", "error_type"),
    [
        (GatewayOperation.READINESS, GatewayRateLimitedError),
        (GatewayOperation.ADD, GatewayTimeoutError),
        (GatewayOperation.SEARCH, GatewayProtocolError),
    ],
)
async def test_fault_injector_preserves_typed_error(
    operation: GatewayOperation, error_type: type[Exception]
) -> None:
    def inject(actual: GatewayOperation) -> None:
        if actual is operation:
            raise error_type()

    gateway = FakeMemoryGateway(fault_injector=inject)
    with pytest.raises(error_type):
        if operation is GatewayOperation.READINESS:
            await gateway.is_ready()
        elif operation is GatewayOperation.ADD:
            await gateway.add(_add())
        else:
            await gateway.search(_search())


async def test_extreme_timestamp_is_reported_as_protocol_error() -> None:
    gateway = FakeMemoryGateway()
    await gateway.add(_add(timestamp_ms=2**63 - 1))

    with pytest.raises(GatewayProtocolError):
        await gateway.search(_search())

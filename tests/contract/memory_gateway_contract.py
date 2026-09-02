"""Reusable behavioral contract for Fake and future real Gateway factories."""

from collections.abc import Awaitable, Callable

import pytest

from memscope.memory_gateway import (
    GatewayAdd,
    GatewayConflictError,
    GatewayMessage,
    GatewaySearch,
    MemoryGateway,
)

GatewayFactory = Callable[[], Awaitable[MemoryGateway]]


async def assert_memory_gateway_contract(factory: GatewayFactory) -> None:
    gateway = await factory()
    request = GatewayAdd(
        "contract-request",
        "f" * 64,
        "contract-user",
        "contract-session",
        "contract-cube",
        (GatewayMessage("contract-message", 0, "user", "alpha beta", None),),
    )
    other = GatewayAdd(
        "other-request",
        "e" * 64,
        "other-user",
        "other-session",
        "other-cube",
        (GatewayMessage("other-message", 0, "user", "alpha beta", None),),
    )
    assert await gateway.is_ready() is True
    await gateway.add(request)
    await gateway.add(request)
    await gateway.add(other)

    evidence = await gateway.search(GatewaySearch("alpha", "contract-user", "contract-cube", 10))
    assert [(item.id, item.content) for item in evidence] == [("contract-message", "alpha beta")]
    assert all(
        item.user_id == "contract-user" and item.cube_id == "contract-cube" for item in evidence
    )
    with pytest.raises(GatewayConflictError):
        await gateway.add(
            GatewayAdd(
                request.request_id,
                "0" * 64,
                request.user_id,
                request.session_id,
                request.cube_id,
                request.messages,
            )
        )
    await gateway.close()
    assert await gateway.is_ready() is False

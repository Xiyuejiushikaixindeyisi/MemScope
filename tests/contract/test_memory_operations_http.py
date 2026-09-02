"""ASGI contract through Adapter, MemoryOperations, Raw Store and Fake Gateway."""

from pathlib import Path

import httpx

from memscope.app import create_app
from memscope.application import MemoryOperations
from memscope.memory_gateway import (
    FakeMemoryGateway,
    GatewayOperation,
    GatewayTimeoutError,
)
from memscope.raw_store.sqlite import SqliteRawStore
from tests.support import make_settings


def _add_payload(
    request_id: str = "request-1", user_id: str = "user-1", content: str = "SSH port 2222"
) -> dict[str, object]:
    return {
        "request_id": request_id,
        "user_id": user_id,
        "session_id": "session-1",
        "messages": [{"role": "user", "content": content, "timestamp": 0}],
    }


async def test_explicit_fake_path_is_ready_synchronous_searchable_and_idempotent(
    tmp_path: Path,
) -> None:
    store = await SqliteRawStore.open(tmp_path / "memory.db", busy_timeout_ms=1000)
    gateway = FakeMemoryGateway()
    application = create_app(
        make_settings(), operations=MemoryOperations(raw_store=store, gateway=gateway)
    )
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200
        first = await client.post("/add", json=_add_payload())
        replay = await client.post("/add", json=_add_payload())
        search = await client.post(
            "/search", json={"query": "SSH port", "user_id": "user-1", "top_k": 1}
        )

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert search.status_code == 200
    assert len(search.json()["data"]) == 1
    assert search.json()["data"][0]["content"] == "SSH port 2222"
    await gateway.close()
    await store.close()


async def test_http_conflict_is_409_and_users_are_isolated(tmp_path: Path) -> None:
    store = await SqliteRawStore.open(tmp_path / "memory.db", busy_timeout_ms=1000)
    gateway = FakeMemoryGateway()
    application = create_app(
        make_settings(), operations=MemoryOperations(raw_store=store, gateway=gateway)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        await client.post("/add", json=_add_payload())
        conflict = await client.post("/add", json=_add_payload(content="changed"))
        await client.post("/add", json=_add_payload("request-2", "user-2", "SSH port 9999"))
        search = await client.post(
            "/search", json={"query": "SSH port", "user_id": "user-1", "top_k": 100}
        )

    assert conflict.status_code == 409
    assert conflict.json()["error"] == {
        "code": "request.conflict",
        "message": "Request identifier conflicts with an existing request",
        "retryable": False,
    }
    assert [item["content"] for item in search.json()["data"]] == ["SSH port 2222"]
    await gateway.close()
    await store.close()


async def test_gateway_failure_leaves_pending_and_same_id_retry_converges(tmp_path: Path) -> None:
    attempts = 0

    def fail_first_add(operation: GatewayOperation) -> None:
        nonlocal attempts
        if operation is GatewayOperation.ADD:
            attempts += 1
            if attempts == 1:
                raise GatewayTimeoutError()

    store = await SqliteRawStore.open(tmp_path / "memory.db", busy_timeout_ms=1000)
    gateway = FakeMemoryGateway(fault_injector=fail_first_add)
    application = create_app(
        make_settings(), operations=MemoryOperations(raw_store=store, gateway=gateway)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        failed = await client.post("/add", json=_add_payload())
        pending = await store.load_add("user-1", "request-1")
        recovered = await client.post("/add", json=_add_payload())
        completed = await store.load_add("user-1", "request-1")
        search = await client.post(
            "/search", json={"query": "SSH", "user_id": "user-1", "top_k": 10}
        )

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "gateway.timeout"
    assert pending is not None and pending.status == "pending"
    assert recovered.status_code == 200
    assert completed is not None and completed.status == "completed"
    assert [item["content"] for item in search.json()["data"]] == ["SSH port 2222"]
    assert attempts == 2
    await gateway.close()
    await store.close()

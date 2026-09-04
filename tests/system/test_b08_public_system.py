"""Public ASGI system evidence across the real Raw, receipt and MemOS Gateway path."""

import asyncio
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from memscope.app import create_app
from memscope.application import MemoryOperations
from memscope.memory_gateway import GatewayReceiptStore, MemosMemoryGateway, ReceiptStatus
from memscope.operations import AddCommand, MemoryMessage
from memscope.raw_store.identity import cube_id_for_user, payload_sha256
from memscope.raw_store.sqlite import SqliteRawStore
from tests.support import make_settings


def _json_response(data: Any, *, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json; charset=utf-8"},
    )


def _envelope(data: Any) -> dict[str, Any]:
    return {"code": 200, "message": "ok", "data": data}


class _PersistentProvider:
    """Process-independent provider state behind reconstructed Gateway clients."""

    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []
        self.calls: Counter[str] = Counter()
        self.failure: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls[path] += 1
        if self.failure == "get_timeout" and path == "/product/get_memory":
            raise httpx.ReadTimeout("injected timeout", request=request)
        if self.failure == "add_rate_limit" and path == "/product/add":
            return _json_response({}, status=429)
        if self.failure == "search_invalid_json" and path == "/product/search":
            return httpx.Response(
                200,
                content=b"not-json",
                headers={"content-type": "application/json"},
            )
        if path == "/health":
            return _json_response({"status": "healthy"})
        payload = json.loads(request.content)
        if path == "/product/get_memory":
            digest = payload["filter"]["memscope_payload_sha256"]
            memories = [
                item
                for item in self.memories
                if item["metadata"]["user_id"] == payload["user_id"]
                and item["metadata"]["memscope_cube_id"] == payload["mem_cube_id"]
                and item["metadata"]["memscope_payload_sha256"] == digest
            ]
            return _json_response(
                _envelope(
                    {
                        "text_mem": [
                            {
                                "cube_id": payload["mem_cube_id"],
                                "memories": memories,
                                "total_nodes": len(memories),
                            }
                        ]
                    }
                )
            )
        if path == "/product/add":
            digest = payload["info"]["memscope_payload_sha256"]
            memory_id = str(uuid.UUID(digest[:32], version=4))
            memory = {
                "id": memory_id,
                "memory": payload["messages"][0]["content"],
                "metadata": {
                    "user_id": payload["user_id"],
                    "session_id": payload["session_id"],
                    "memory_type": "LongTermMemory",
                    "status": "activated",
                    "vector_sync": "success",
                    "memscope_cube_id": payload["writable_cube_ids"][0],
                    "memscope_payload_sha256": digest,
                    "memscope_result_index": 0,
                    "memscope_result_count": 1,
                    "relativity": 0.9,
                },
            }
            self.memories.append(memory)
            return _json_response(
                _envelope(
                    [
                        {
                            "memory_id": memory_id,
                            "memory": memory["memory"],
                            "memory_type": "LongTermMemory",
                            "cube_id": memory["metadata"]["memscope_cube_id"],
                        }
                    ]
                )
            )
        if path == "/product/search":
            memories = [
                item
                for item in self.memories
                if item["metadata"]["user_id"] == payload["user_id"]
                and item["metadata"]["memscope_cube_id"] in payload["readable_cube_ids"]
            ]
            return _json_response(
                _envelope(
                    {
                        "text_mem": [
                            {"cube_id": payload["readable_cube_ids"][0], "memories": memories}
                        ]
                    }
                )
            )
        raise AssertionError(path)

    def seed_partial(self, command: AddCommand) -> None:
        digest = payload_sha256(command)
        self.memories.append(
            {
                "id": str(uuid.UUID(digest[:32], version=4)),
                "memory": command.messages[0].content,
                "metadata": {
                    "user_id": command.user_id,
                    "session_id": command.session_id,
                    "memory_type": "LongTermMemory",
                    "status": "activated",
                    "vector_sync": "success",
                    "memscope_cube_id": cube_id_for_user(command.user_id),
                    "memscope_payload_sha256": digest,
                    "memscope_result_index": 0,
                    "memscope_result_count": 2,
                },
            }
        )


async def _open_system(
    raw_path: Path,
    receipt_path: Path,
    provider: _PersistentProvider,
) -> tuple[httpx.AsyncClient, SqliteRawStore, GatewayReceiptStore, MemosMemoryGateway]:
    raw = await SqliteRawStore.open(raw_path, busy_timeout_ms=5_000)
    receipts = await GatewayReceiptStore.open(receipt_path, busy_timeout_ms=5_000)
    gateway = MemosMemoryGateway(
        base_url="http://memos:8000",
        receipt_store=receipts,
        connect_timeout_seconds=3,
        response_max_bytes=1_048_576,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(provider),
            base_url="http://memos:8000",
        ),
    )
    await gateway.verify_upstream(timeout_seconds=5)
    application = create_app(
        make_settings(),
        operations=MemoryOperations(raw_store=raw, gateway=gateway),
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    )
    return client, raw, receipts, gateway


def _add_payload(request: str, user: str, session: str, content: str) -> dict[str, Any]:
    return {
        "request_id": request,
        "user_id": user,
        "session_id": session,
        "messages": [{"role": "user", "content": content, "timestamp": 1_704_067_200_000}],
    }


async def test_public_concurrency_isolation_and_full_restart_recovery(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.db"
    receipt_path = tmp_path / "receipts.db"
    provider = _PersistentProvider()
    primary = _add_payload("request-a", "user-a", "session-a", "blue bicycle")
    second = _add_payload("request-b", "user-a", "session-b", "green helmet")
    other = _add_payload("request-c", "user-b", "session-c", "red kayak")

    client, raw, _, gateway = await _open_system(raw_path, receipt_path, provider)
    assert (await client.get("/health")).json() == {"status": "ok"}
    first, replay = await asyncio.gather(
        client.post("/add", json=primary),
        client.post("/add", json=primary),
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert provider.calls["/product/add"] == 1

    same_user, other_user = await asyncio.gather(
        client.post("/add", json=second),
        client.post("/add", json=other),
    )
    assert same_user.status_code == other_user.status_code == 200
    primary_search, other_search = await asyncio.gather(
        client.post("/search", json={"query": "equipment", "user_id": "user-a", "top_k": 100}),
        client.post("/search", json={"query": "equipment", "user_id": "user-b", "top_k": 100}),
    )
    assert [item["content"] for item in primary_search.json()["data"]] == [
        "blue bicycle",
        "green helmet",
    ]
    assert [item["content"] for item in other_search.json()["data"]] == ["red kayak"]
    before_restart_ids = {item["id"] for item in primary_search.json()["data"]}
    await client.aclose()
    await gateway.close()
    await raw.close()

    restarted_client, restarted_raw, _, restarted_gateway = await _open_system(
        raw_path,
        receipt_path,
        provider,
    )
    add_calls_before_replay = provider.calls["/product/add"]
    restarted_replay = await restarted_client.post("/add", json=primary)
    restarted_search = await restarted_client.post(
        "/search",
        json={"query": "equipment", "user_id": "user-a", "top_k": 100},
    )
    assert restarted_replay.json() == first.json()
    assert provider.calls["/product/add"] == add_calls_before_replay
    assert {item["id"] for item in restarted_search.json()["data"]} == before_restart_ids
    assert (await restarted_client.get("/health")).status_code == 200
    await restarted_client.aclose()
    await restarted_gateway.close()
    await restarted_raw.close()


async def test_public_failures_are_classified_and_never_become_empty_success(
    tmp_path: Path,
) -> None:
    provider = _PersistentProvider()
    client, raw, receipts, gateway = await _open_system(
        tmp_path / "raw.db",
        tmp_path / "receipts.db",
        provider,
    )
    payload = _add_payload("failure-request", "failure-user", "failure-session", "private fact")
    command = AddCommand(
        request_id="partial-request",
        user_id="partial-user",
        session_id="partial-session",
        messages=(MemoryMessage("user", "partial fact", 1_704_067_200_000),),
    )
    provider.seed_partial(command)
    partial_payload = _add_payload(
        command.request_id,
        command.user_id,
        command.session_id,
        command.messages[0].content,
    )
    add_calls_before_partial = provider.calls["/product/add"]
    partial = await client.post("/add", json=partial_payload)
    assert partial.status_code == 500
    assert partial.json()["error"]["code"] == "gateway.protocol_invalid"
    assert provider.calls["/product/add"] == add_calls_before_partial

    provider.failure = "add_rate_limit"
    rate_limited = await client.post("/add", json=payload)
    assert rate_limited.status_code == 500
    assert rate_limited.json()["error"]["code"] == "gateway.rate_limited"
    provider.failure = "get_timeout"
    timed_out = await client.post("/add", json=payload)
    assert timed_out.status_code == 500
    assert timed_out.json()["error"]["code"] == "gateway.timeout"
    provider.failure = "search_invalid_json"
    invalid_search = await client.post(
        "/search",
        json={"query": "anything", "user_id": "failure-user", "top_k": 10},
    )
    assert invalid_search.status_code == 500
    assert invalid_search.json()["error"]["code"] == "gateway.protocol_invalid"

    raw_state = await raw.load_add("failure-user", "failure-request")
    partial_state = await raw.load_add("partial-user", "partial-request")
    assert raw_state is not None and raw_state.status == "pending"
    assert partial_state is not None and partial_state.status == "pending"
    rate_receipt = await receipts.prepare(
        "failure-request",
        payload_sha256(
            AddCommand(
                request_id="failure-request",
                user_id="failure-user",
                session_id="failure-session",
                messages=(MemoryMessage("user", "private fact", 1_704_067_200_000),),
            )
        ),
    )
    assert rate_receipt.status is ReceiptStatus.PENDING
    await client.aclose()
    await gateway.close()
    await raw.close()

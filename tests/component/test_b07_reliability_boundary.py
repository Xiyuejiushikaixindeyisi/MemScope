"""Composed restart evidence for the frozen B05/B06 reliability boundary."""

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from memscope.application.memory_operations import MemoryOperations
from memscope.memory_gateway import (
    GatewayProtocolError,
    GatewayRateLimitedError,
    GatewayReceiptStore,
    GatewayUnavailableError,
    MemosMemoryGateway,
    ReceiptStatus,
)
from memscope.operations import AddCommand, MemoryMessage, SearchQuery
from memscope.raw_store.errors import RawStoreInvariantError
from memscope.raw_store.identity import cube_id_for_user, payload_sha256
from memscope.raw_store.sqlite import SqliteRawStore

_MEMORY_ID = "11111111-1111-4111-8111-111111111111"
_BUSY_TIMEOUT_MS = 5_000


def _command() -> AddCommand:
    return AddCommand(
        request_id="b07-request-1",
        user_id="b07-user-1",
        session_id="b07-session-1",
        messages=(MemoryMessage("user", "remember the blue bicycle", 1_704_067_200_000),),
    )


def _envelope(data: Any) -> dict[str, Any]:
    return {"code": 200, "message": "ok", "data": data}


def _json_response(data: Any, *, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json; charset=utf-8"},
    )


def _provider_memory(
    command: AddCommand,
    *,
    index: int = 0,
    count: int = 1,
) -> dict[str, Any]:
    return {
        "id": _MEMORY_ID,
        "memory": "the bicycle is blue",
        "metadata": {
            "user_id": command.user_id,
            "session_id": command.session_id,
            "memory_type": "LongTermMemory",
            "status": "activated",
            "vector_sync": "success",
            "memscope_cube_id": cube_id_for_user(command.user_id),
            "memscope_payload_sha256": payload_sha256(command),
            "memscope_result_index": index,
            "memscope_result_count": count,
            "relativity": 0.91,
        },
    }


def _filtered_get(command: AddCommand, memories: list[dict[str, Any]]) -> httpx.Response:
    return _json_response(
        _envelope(
            {
                "text_mem": [
                    {
                        "cube_id": cube_id_for_user(command.user_id),
                        "memories": memories,
                        "total_nodes": len(memories),
                    }
                ]
            }
        )
    )


def _add_result(command: AddCommand) -> httpx.Response:
    return _json_response(
        _envelope(
            [
                {
                    "memory_id": _MEMORY_ID,
                    "memory": "the bicycle is blue",
                    "memory_type": "LongTermMemory",
                    "cube_id": cube_id_for_user(command.user_id),
                }
            ]
        )
    )


async def _components(
    raw_path: Path,
    receipt_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[MemoryOperations, SqliteRawStore, GatewayReceiptStore, MemosMemoryGateway]:
    raw = await SqliteRawStore.open(raw_path, busy_timeout_ms=_BUSY_TIMEOUT_MS)
    receipts = await GatewayReceiptStore.open(
        receipt_path,
        busy_timeout_ms=_BUSY_TIMEOUT_MS,
    )
    gateway = MemosMemoryGateway(
        base_url="http://memos:8000",
        receipt_store=receipts,
        connect_timeout_seconds=3,
        response_max_bytes=1_048_576,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://memos:8000",
        ),
    )
    return MemoryOperations(raw_store=raw, gateway=gateway), raw, receipts, gateway


async def test_completed_receipt_finishes_raw_after_full_restart_without_provider_io(
    tmp_path: Path,
) -> None:
    command = _command()
    digest = payload_sha256(command)
    raw_path = tmp_path / "raw.db"
    receipt_path = tmp_path / "receipts.db"
    calls: list[str] = []
    readbacks = 0

    def first_handler(request: httpx.Request) -> httpx.Response:
        nonlocal readbacks
        calls.append(request.url.path)
        if request.url.path == "/product/get_memory":
            readbacks += 1
            return _filtered_get(
                command,
                [] if readbacks == 1 else [_provider_memory(command)],
            )
        if request.url.path == "/product/add":
            return _add_result(command)
        raise AssertionError(request.url.path)

    operations, raw, receipts, gateway = await _components(
        raw_path,
        receipt_path,
        first_handler,
    )
    connection = sqlite3.connect(raw_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER b07_reject_raw_completion
            BEFORE UPDATE OF status ON add_requests
            WHEN NEW.status = 'completed'
            BEGIN SELECT RAISE(ABORT, 'injected raw completion failure'); END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError):
        await operations.add(command)

    pending = await raw.load_add(command.user_id, command.request_id)
    completed_receipt = await receipts.prepare(command.request_id, digest)
    assert pending is not None and pending.status == "pending"
    assert completed_receipt.status is ReceiptStatus.COMPLETED
    assert completed_receipt.memory_ids == (_MEMORY_ID,)
    assert calls == ["/product/get_memory", "/product/add", "/product/get_memory"]
    await gateway.close()
    await raw.close()

    connection = sqlite3.connect(raw_path)
    try:
        connection.execute("DROP TRIGGER b07_reject_raw_completion")
        connection.commit()
    finally:
        connection.close()

    replay_calls: list[str] = []

    def replay_handler(request: httpx.Request) -> httpx.Response:
        replay_calls.append(request.url.path)
        raise AssertionError("completed receipt must short-circuit all provider I/O")

    replay_operations, replay_raw, replay_receipts, replay_gateway = await _components(
        raw_path,
        receipt_path,
        replay_handler,
    )
    await replay_operations.add(command)

    completed = await replay_raw.load_add(command.user_id, command.request_id)
    receipt = await replay_receipts.prepare(command.request_id, digest)
    assert completed is not None and completed.status == "completed"
    assert completed.response is not None and completed.response.success is True
    assert receipt.status is ReceiptStatus.COMPLETED
    assert replay_calls == []
    await replay_gateway.close()
    await replay_raw.close()


async def test_lost_add_response_reconciles_after_restart_and_remains_searchable(
    tmp_path: Path,
) -> None:
    command = _command()
    digest = payload_sha256(command)
    raw_path = tmp_path / "raw.db"
    receipt_path = tmp_path / "receipts.db"
    committed = False
    calls: list[str] = []

    def first_handler(request: httpx.Request) -> httpx.Response:
        nonlocal committed
        calls.append(request.url.path)
        if request.url.path == "/product/get_memory":
            return _filtered_get(command, [])
        if request.url.path == "/product/add":
            committed = True
            raise httpx.ReadError("response lost after provider commit", request=request)
        raise AssertionError(request.url.path)

    operations, raw, receipts, gateway = await _components(
        raw_path,
        receipt_path,
        first_handler,
    )
    with pytest.raises(GatewayUnavailableError):
        await operations.add(command)
    assert committed is True
    pending = await raw.load_add(command.user_id, command.request_id)
    pending_receipt = await receipts.prepare(command.request_id, digest)
    assert pending is not None and pending.status == "pending"
    assert pending_receipt.status is ReceiptStatus.PENDING
    assert calls == ["/product/get_memory", "/product/add"]
    await gateway.close()
    await raw.close()

    def recovery_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/product/get_memory":
            assert committed is True
            return _filtered_get(command, [_provider_memory(command)])
        if request.url.path == "/product/search":
            return _json_response(
                _envelope(
                    {
                        "text_mem": [
                            {
                                "cube_id": cube_id_for_user(command.user_id),
                                "memories": [_provider_memory(command)],
                            }
                        ]
                    }
                )
            )
        if request.url.path == "/product/add":
            raise AssertionError("reconciliation must not duplicate provider Add")
        raise AssertionError(request.url.path)

    recovery_operations, recovery_raw, recovery_receipts, recovery_gateway = await _components(
        raw_path,
        receipt_path,
        recovery_handler,
    )
    await recovery_operations.add(command)
    evidence = await recovery_operations.search(
        SearchQuery(query="what color is the bicycle?", user_id=command.user_id, top_k=3)
    )

    recovered = await recovery_raw.load_add(command.user_id, command.request_id)
    recovered_receipt = await recovery_receipts.prepare(command.request_id, digest)
    assert recovered is not None and recovered.status == "completed"
    assert recovered_receipt.status is ReceiptStatus.COMPLETED
    assert recovered_receipt.memory_ids == (_MEMORY_ID,)
    assert [(item.id, item.content, item.score) for item in evidence] == [
        (_MEMORY_ID, "the bicycle is blue", 0.91)
    ]
    assert calls == [
        "/product/get_memory",
        "/product/add",
        "/product/get_memory",
        "/product/search",
    ]
    await recovery_gateway.close()
    await recovery_raw.close()


async def test_partial_provenance_fails_closed_and_leaves_both_ledgers_pending(
    tmp_path: Path,
) -> None:
    command = _command()
    digest = payload_sha256(command)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/product/get_memory":
            return _filtered_get(command, [_provider_memory(command, index=0, count=2)])
        raise AssertionError("partial provenance must fail before provider Add or repair")

    operations, raw, receipts, gateway = await _components(
        tmp_path / "raw.db",
        tmp_path / "receipts.db",
        handler,
    )
    with pytest.raises(GatewayProtocolError):
        await operations.add(command)

    raw_state = await raw.load_add(command.user_id, command.request_id)
    receipt_state = await receipts.prepare(command.request_id, digest)
    assert raw_state is not None and raw_state.status == "pending"
    assert receipt_state.status is ReceiptStatus.PENDING
    assert calls == ["/product/get_memory"]
    await gateway.close()
    await raw.close()


async def test_rate_limit_has_one_attempt_per_external_replay_and_no_internal_retry(
    tmp_path: Path,
) -> None:
    command = _command()
    digest = payload_sha256(command)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/product/get_memory":
            return _filtered_get(command, [])
        if request.url.path == "/product/add":
            return _json_response({}, status=429)
        raise AssertionError(request.url.path)

    operations, raw, receipts, gateway = await _components(
        tmp_path / "raw.db",
        tmp_path / "receipts.db",
        handler,
    )
    with pytest.raises(GatewayRateLimitedError):
        await operations.add(command)
    assert calls == ["/product/get_memory", "/product/add"]

    with pytest.raises(GatewayRateLimitedError):
        await operations.add(command)
    assert calls == [
        "/product/get_memory",
        "/product/add",
        "/product/get_memory",
        "/product/add",
    ]

    raw_state = await raw.load_add(command.user_id, command.request_id)
    receipt_state = await receipts.prepare(command.request_id, digest)
    assert raw_state is not None and raw_state.status == "pending"
    assert receipt_state.status is ReceiptStatus.PENDING
    await gateway.close()
    await raw.close()

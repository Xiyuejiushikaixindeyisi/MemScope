"""Wire-contract and failure tests for the Real MemOS Add Gateway."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from memscope.memory_gateway import (
    GatewayAdd,
    GatewayMessage,
    GatewayProtocolError,
    GatewayRateLimitedError,
    GatewayReceiptStore,
    GatewaySearch,
    GatewayTimeoutError,
    GatewayUnavailableError,
    MemosMemoryGateway,
)
from memscope.memory_gateway.memos_models import AddResult, ProviderMemory

_MEMORY_ID = "11111111-1111-4111-8111-111111111111"


def _request(*, timestamp_ms: int | None = 0) -> GatewayAdd:
    return GatewayAdd(
        request_id="request-1",
        payload_sha256="a" * 64,
        user_id="user-1",
        session_id="session-1",
        cube_id="cube-1",
        session_start_position=7,
        messages=(GatewayMessage("message-1", 0, "user", "private fact", timestamp_ms),),
    )


def _envelope(data: Any) -> dict[str, Any]:
    return {"code": 200, "message": "ok", "data": data}


def _provider_memory(*, index: int = 0, count: int = 1) -> dict[str, Any]:
    return {
        "id": _MEMORY_ID,
        "memory": "remembered fact",
        "metadata": {
            "user_id": "user-1",
            "session_id": "session-1",
            "memory_type": "LongTermMemory",
            "status": "activated",
            "vector_sync": "success",
            "memscope_cube_id": "cube-1",
            "memscope_payload_sha256": "a" * 64,
            "memscope_result_index": index,
            "memscope_result_count": count,
        },
    }


def _json_response(data: Any, *, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json; charset=utf-8"},
    )


async def _gateway(
    tmp_path: Path,
    handler: httpx.MockTransport,
    *,
    max_bytes: int = 1_048_576,
) -> MemosMemoryGateway:
    receipt = await GatewayReceiptStore.open(tmp_path / "receipts.db", busy_timeout_ms=5000)
    client = httpx.AsyncClient(transport=handler, base_url="http://memos:8000")
    return MemosMemoryGateway(
        base_url="http://memos:8000",
        receipt_store=receipt,
        connect_timeout_seconds=3,
        response_max_bytes=max_bytes,
        client=client,
    )


async def test_real_gateway_add_maps_payload_verifies_readback_and_replays(tmp_path: Path) -> None:
    calls: list[str] = []
    filtered_reads = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal filtered_reads
        calls.append(request.url.path)
        if request.url.path == "/product/get_memory":
            filtered_reads += 1
            payload = json.loads(request.content)
            assert payload == {
                "mem_cube_id": "cube-1",
                "user_id": "user-1",
                "include_preference": False,
                "include_tool_memory": False,
                "include_skill_memory": False,
                "filter": {"memscope_payload_sha256": "a" * 64},
            }
            memories = [] if filtered_reads == 1 else [_provider_memory()]
            return _json_response(
                _envelope(
                    {
                        "text_mem": [
                            {
                                "cube_id": "cube-1",
                                "memories": memories,
                                "total_nodes": len(memories),
                            }
                        ]
                    }
                )
            )
        if request.url.path == "/product/add":
            payload = json.loads(request.content)
            assert payload["async_mode"] == "sync"
            assert payload["mode"] == "fine"
            assert payload["writable_cube_ids"] == ["cube-1"]
            assert payload["messages"] == [
                {
                    "role": "user",
                    "content": "private fact",
                    "message_id": "message-1",
                    "chat_time": "1970-01-01T00:00:00.000Z",
                }
            ]
            assert payload["info"]["memscope_session_start_position"] == 7
            assert payload["info"]["memscope_source_count"] == 1
            assert "task_id" not in payload
            assert "chat_history" not in payload
            return _json_response(
                _envelope(
                    [
                        {
                            "memory_id": _MEMORY_ID,
                            "memory": "remembered fact",
                            "memory_type": "LongTermMemory",
                            "cube_id": "cube-1",
                        }
                    ]
                )
            )
        raise AssertionError(request.url.path)

    gateway = await _gateway(tmp_path, httpx.MockTransport(handle))
    await gateway.add(_request(), timeout_seconds=5)
    await gateway.add(_request(), timeout_seconds=5)

    assert calls == ["/product/get_memory", "/product/add", "/product/get_memory"]
    assert await gateway.is_ready() is False
    with pytest.raises(GatewayUnavailableError):
        await gateway.search(GatewaySearch("q", "user-1", "cube-1", 1))
    await gateway.close()
    await gateway.close()
    with pytest.raises(GatewayUnavailableError):
        await gateway.add(_request(), timeout_seconds=5)


async def test_pending_receipt_reconciles_provider_without_duplicate_add(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/product/get_memory"
        return _json_response(
            _envelope(
                {
                    "text_mem": [
                        {
                            "cube_id": "cube-1",
                            "memories": [_provider_memory()],
                            "total_nodes": 1,
                        }
                    ]
                }
            )
        )

    gateway = await _gateway(tmp_path, httpx.MockTransport(handle))
    await gateway.add(_request(), timeout_seconds=5)
    await gateway.close()


async def test_valid_empty_add_receipt_replays_without_provider_io(tmp_path: Path) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.path == "/product/get_memory":
            return _json_response(
                _envelope({"text_mem": [{"cube_id": "cube-1", "memories": [], "total_nodes": 0}]})
            )
        assert request.url.path == "/product/add"
        return _json_response(_envelope([]))

    gateway = await _gateway(tmp_path, httpx.MockTransport(handle))
    await gateway.add(_request(timestamp_ms=None), timeout_seconds=5)
    await gateway.add(_request(timestamp_ms=None), timeout_seconds=5)
    assert calls == 2
    await gateway.close()


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, GatewayRateLimitedError),
        (408, GatewayTimeoutError),
        (504, GatewayTimeoutError),
        (500, GatewayUnavailableError),
        (400, GatewayProtocolError),
    ],
)
async def test_http_status_is_translated(
    tmp_path: Path, status: int, error: type[Exception]
) -> None:
    gateway = await _gateway(
        tmp_path,
        httpx.MockTransport(lambda request: _json_response({}, status=status)),
    )
    with pytest.raises(error):
        await gateway.add(_request(), timeout_seconds=5)
    await gateway.close()


@pytest.mark.parametrize("invalid_budget", [0, -1, float("inf"), float("nan"), True])
async def test_real_gateway_rejects_invalid_timeout(tmp_path: Path, invalid_budget: float) -> None:
    gateway = await _gateway(
        tmp_path,
        httpx.MockTransport(lambda request: _json_response({})),
    )
    with pytest.raises(ValueError):
        await gateway.add(_request(), timeout_seconds=invalid_budget)
    await gateway.close()


async def test_health_and_extreme_timestamp_mapping(tmp_path: Path) -> None:
    observed: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.path == "/health":
            return _json_response({"status": "healthy"})
        if request.url.path == "/product/get_memory":
            return _json_response(
                _envelope({"text_mem": [{"cube_id": "cube-1", "memories": [], "total_nodes": 0}]})
            )
        return _json_response(_envelope([]))

    gateway = await _gateway(tmp_path, httpx.MockTransport(handle))
    await gateway.verify_upstream(timeout_seconds=1)
    await gateway.add(_request(timestamp_ms=2**63 - 1), timeout_seconds=5)
    add_payload = json.loads(
        next(item for item in observed if item.url.path == "/product/add").content
    )
    assert add_payload["messages"][0]["chat_time"] == f"unix_ms:{2**63 - 1}"
    await gateway.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"}),
        httpx.Response(200, content=b"{}", headers={"content-type": "text/plain"}),
        httpx.Response(200, content=b"{}", headers={"content-type": "application/json"}),
    ],
)
async def test_malformed_provider_response_fails_closed(
    tmp_path: Path, response: httpx.Response
) -> None:
    gateway = await _gateway(tmp_path, httpx.MockTransport(lambda request: response))
    with pytest.raises(GatewayProtocolError):
        await gateway.add(_request(), timeout_seconds=5)
    await gateway.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_url", ""),
        ("base_url", 1),
        ("connect_timeout_seconds", True),
        ("connect_timeout_seconds", 0),
        ("connect_timeout_seconds", float("inf")),
        ("response_max_bytes", True),
        ("response_max_bytes", 0),
        ("response_max_bytes", 1.5),
    ],
)
async def test_gateway_constructor_rejects_invalid_boundaries(
    tmp_path: Path, field: str, value: Any
) -> None:
    receipt = await GatewayReceiptStore.open(tmp_path / "r.db", busy_timeout_ms=5000)
    kwargs: dict[str, Any] = {
        "base_url": "http://memos:8000",
        "receipt_store": receipt,
        "connect_timeout_seconds": 3,
        "response_max_bytes": 1024,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        MemosMemoryGateway(**kwargs)
    await receipt.close()


async def test_gateway_can_own_default_http_client(tmp_path: Path) -> None:
    receipt = await GatewayReceiptStore.open(tmp_path / "r.db", busy_timeout_ms=5000)
    gateway = MemosMemoryGateway(
        base_url="http://memos:8000/",
        receipt_store=receipt,
        connect_timeout_seconds=3,
        response_max_bytes=1024,
    )
    await gateway.close()


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (httpx.ReadTimeout("slow"), GatewayTimeoutError),
        (TimeoutError(), GatewayTimeoutError),
        (httpx.ConnectError("down"), GatewayUnavailableError),
        (OSError("down"), GatewayUnavailableError),
    ],
)
async def test_transport_failures_are_sanitized(
    tmp_path: Path, raised: Exception, expected: type[Exception]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        del request
        raise raised

    gateway = await _gateway(tmp_path, httpx.MockTransport(handle))
    with pytest.raises(expected) as captured:
        await gateway.add(_request(), timeout_seconds=5)
    assert "slow" not in str(captured.value)
    assert "down" not in str(captured.value)
    await gateway.close()


async def test_oversized_json_response_fails_closed(tmp_path: Path) -> None:
    response = _json_response({"padding": "x" * 100})
    gateway = await _gateway(tmp_path, httpx.MockTransport(lambda request: response), max_bytes=20)
    with pytest.raises(GatewayProtocolError):
        await gateway.add(_request(), timeout_seconds=5)
    await gateway.close()


@pytest.mark.parametrize("health", [None, {}, {"status": "starting"}, {"status": True}])
async def test_upstream_health_requires_exact_healthy_object(tmp_path: Path, health: Any) -> None:
    gateway = await _gateway(
        tmp_path,
        httpx.MockTransport(lambda request: _json_response(health)),
    )
    with pytest.raises(GatewayProtocolError):
        await gateway.verify_upstream(timeout_seconds=1)
    await gateway.close()


def _committed(
    *,
    memory_id: str = _MEMORY_ID,
    user_id: str = "user-1",
    index: int = 0,
    count: int = 1,
    memory: str = "remembered fact",
) -> ProviderMemory:
    return ProviderMemory(
        memory_id=memory_id,
        memory=memory,
        user_id=user_id,
        session_id="session-1",
        cube_id="cube-1",
        memory_type="LongTermMemory",
        status="activated",
        vector_sync="success",
        payload_sha256="a" * 64,
        result_index=index,
        result_count=count,
    )


@pytest.mark.parametrize(
    ("memories", "expected"),
    [
        ((), None),
        ((_committed(count=2),), None),
        ((_committed(index=0, count=2), _committed(index=0, count=2)), None),
        ((_committed(user_id="other"),), None),
        ((_committed(),), ()),
        (
            (_committed(),),
            (AddResult(_MEMORY_ID, "different", "LongTermMemory", "cube-1"),),
        ),
    ],
)
def test_committed_readback_rejects_incomplete_or_mismatched_results(
    memories: tuple[ProviderMemory, ...], expected: tuple[AddResult, ...] | None
) -> None:
    with pytest.raises(GatewayProtocolError):
        MemosMemoryGateway._validate_committed(_request(), memories, expected=expected)


def test_committed_readback_reorders_complete_results() -> None:
    second_id = "22222222-2222-4222-8222-222222222222"
    memories = (
        _committed(memory_id=second_id, index=1, count=2, memory="second"),
        _committed(index=0, count=2),
    )
    assert MemosMemoryGateway._validate_committed(_request(), memories, expected=None) == (
        _MEMORY_ID,
        second_id,
    )


def test_remaining_budget_rejects_expired_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("memscope.memory_gateway.memos.time.monotonic", lambda: 10.0)
    with pytest.raises(GatewayTimeoutError):
        MemosMemoryGateway._remaining(10.0)

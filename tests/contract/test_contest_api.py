"""End-to-end ASGI contract tests for Health, Add and Search."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx
import pytest

from memscope.app import create_app
from memscope.errors import MemScopeError
from memscope.operations import AddCommand, MemoryEvidence, SearchQuery
from tests.support import make_settings

ADD_REQUEST_ID = "eval:run:chunk-0"
USER_ID = "eval:run:user-1"
SESSION_ID = "eval:run:session-1"
SEARCH_QUERY = "What is the SSH port?"

ADD_PAYLOAD = {
    "request_id": ADD_REQUEST_ID,
    "user_id": USER_ID,
    "session_id": SESSION_ID,
    "messages": [
        {"role": "user", "content": "The SSH port is 2222."},
        {"role": "assistant", "content": "Noted.", "timestamp": 1704067208000},
    ],
}
SEARCH_PAYLOAD = {
    "query": SEARCH_QUERY,
    "user_id": USER_ID,
    "top_k": 100,
}


class RecordingOperations:
    def __init__(
        self,
        *,
        ready: bool = True,
        evidence: Sequence[MemoryEvidence] = (),
        add_error: Exception | None = None,
        search_error: Exception | None = None,
        ready_error: Exception | None = None,
        add_gate: asyncio.Event | None = None,
    ) -> None:
        self.ready = ready
        self.evidence = evidence
        self.add_error = add_error
        self.search_error = search_error
        self.ready_error = ready_error
        self.add_gate = add_gate
        self.add_started = asyncio.Event()
        self.add_calls: list[AddCommand] = []
        self.search_calls: list[SearchQuery] = []

    async def is_ready(self) -> bool:
        if self.ready_error is not None:
            raise self.ready_error
        return self.ready

    async def add(self, command: AddCommand) -> None:
        self.add_calls.append(command)
        self.add_started.set()
        if self.add_gate is not None:
            await self.add_gate.wait()
        if self.add_error is not None:
            raise self.add_error

    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]:
        self.search_calls.append(query)
        if self.search_error is not None:
            raise self.search_error
        return self.evidence


def _transport(operations: RecordingOperations, *, raise_app_exceptions: bool = True):  # type: ignore[no-untyped-def]
    application = create_app(make_settings(), operations=operations)
    return httpx.ASGITransport(
        app=application,
        raise_app_exceptions=raise_app_exceptions,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operations", "expected_status"),
    [
        (RecordingOperations(ready=True), 200),
        (RecordingOperations(ready=False), 503),
        (RecordingOperations(ready_error=RuntimeError("private failure")), 503),
    ],
)
async def test_health_reports_complete_readiness_without_authentication(
    operations: RecordingOperations,
    expected_status: int,
) -> None:
    settings = make_settings(contest_auth_mode="shared_key", contest_api_key="secret-key")
    application = create_app(settings, operations=operations)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json() == {"status": "ok"}
    else:
        assert response.json()["error"]["code"] == "service.unavailable"


@pytest.mark.asyncio
async def test_add_maps_ordered_messages_and_echoes_exact_ids() -> None:
    operations = RecordingOperations()
    transport = _transport(operations)
    payload = {**ADD_PAYLOAD, "unknown": "ignored"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/add", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "request_id": ADD_PAYLOAD["request_id"],
        "user_id": ADD_PAYLOAD["user_id"],
        "session_id": ADD_PAYLOAD["session_id"],
    }
    command = operations.add_calls[0]
    assert tuple(message.role for message in command.messages) == ("user", "assistant")
    assert command.messages[0].timestamp is None
    assert command.messages[1].timestamp == 1704067208000


@pytest.mark.asyncio
async def test_add_does_not_respond_before_operation_completion() -> None:
    gate = asyncio.Event()
    operations = RecordingOperations(add_gate=gate)
    transport = _transport(operations)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        request_task = asyncio.create_task(client.post("/add", json=ADD_PAYLOAD))
        await asyncio.wait_for(operations.add_started.wait(), timeout=1)
        assert request_task.done() is False
        gate.set()
        response = await asyncio.wait_for(request_task, timeout=1)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_preserves_order_serializes_optional_fields_and_truncates() -> None:
    evidence = (
        MemoryEvidence(
            id="mem-1",
            content="port 2222",
            score=0.9,
            created_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
        ),
        MemoryEvidence(id="mem-2", content="older port", score=0.5),
        MemoryEvidence(id="mem-3", content="noise"),
    )
    operations = RecordingOperations(evidence=evidence)
    transport = _transport(operations)
    payload = {**SEARCH_PAYLOAD, "top_k": 2, "options": ["A. 22", "B. 2222"]}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/search", json=payload)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == ["mem-1", "mem-2"]
    assert response.json()["data"][0]["created_at"] == "2026-07-01T12:00:00Z"
    assert "created_at" not in response.json()["data"][1]
    assert response.json()["data"][1]["score"] == 0.5
    assert operations.search_calls == [
        SearchQuery(
            query=SEARCH_QUERY,
            user_id=USER_ID,
            top_k=2,
            options=("A. 22", "B. 2222"),
        )
    ]


@pytest.mark.asyncio
async def test_search_empty_result_has_required_envelope() -> None:
    operations = RecordingOperations()
    transport = _transport(operations)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/search", json=SEARCH_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"data": []}


@pytest.mark.asyncio
async def test_search_omits_absent_optional_evidence_fields() -> None:
    operations = RecordingOperations(evidence=(MemoryEvidence(id="mem-1", content="fact"),))
    transport = _transport(operations)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/search", json={**SEARCH_PAYLOAD, "options": []})

    assert response.status_code == 200
    assert response.json() == {"data": [{"id": "mem-1", "content": "fact"}]}
    assert operations.search_calls[0].options == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({"Authorization": "Bearer shared-secret"}, 200),
        ({"Authorization": "Token shared-secret"}, 200),
        ({"X-Api-Key": "shared-secret"}, 200),
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
    ],
)
async def test_add_authentication_carriers(
    headers: dict[str, str],
    expected_status: int,
) -> None:
    operations = RecordingOperations()
    settings = make_settings(contest_auth_mode="shared_key", contest_api_key="shared-secret")
    application = create_app(settings, operations=operations)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/add", json=ADD_PAYLOAD, headers=headers)

    assert response.status_code == expected_status
    assert len(operations.add_calls) == (1 if expected_status == 200 else 0)
    if expected_status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "auth.invalid"
        assert "shared-secret" not in response.text


@pytest.mark.asyncio
async def test_invalid_request_is_sanitized_and_never_calls_operations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    operations = RecordingOperations()
    transport = _transport(operations)
    secret_body_value = "private-query-value"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/search",
            json={"query": secret_body_value, "user_id": "u", "top_k": "100"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "request.invalid",
            "message": "Request validation failed",
            "retryable": False,
        }
    }
    assert operations.search_calls == []
    assert secret_body_value not in response.text
    assert secret_body_value not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_malformed_json_is_sanitized_and_never_calls_operations() -> None:
    operations = RecordingOperations()
    transport = _transport(operations)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/add",
            content=b'{"private":"body",',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request.invalid"
    assert "private" not in response.text
    assert operations.add_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            MemScopeError(code="operation.failed", message="Safe failure", retryable=True),
            500,
            "operation.failed",
        ),
        (RuntimeError("private failure"), 500, "internal.error"),
    ],
)
async def test_operation_failures_use_safe_error_mapping(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    operations = RecordingOperations(search_error=error)
    transport = _transport(operations, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/search", json=SEARCH_PAYLOAD)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert "private failure" not in response.text


@pytest.mark.asyncio
async def test_request_cancellation_does_not_become_success() -> None:
    gate = asyncio.Event()
    operations = RecordingOperations(add_gate=gate)
    transport = _transport(operations)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        request_task = asyncio.create_task(client.post("/add", json=ADD_PAYLOAD))
        await asyncio.wait_for(operations.add_started.wait(), timeout=1)
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

    assert gate.is_set() is False


@pytest.mark.asyncio
async def test_default_runtime_has_registered_routes_without_false_success() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        add = await client.post("/add", json=ADD_PAYLOAD)
        search = await client.post("/search", json=SEARCH_PAYLOAD)

    assert [health.status_code, add.status_code, search.status_code] == [503, 503, 503]
    assert all(
        response.json()["error"]["code"] == "service.unavailable"
        for response in (health, add, search)
    )


@pytest.mark.asyncio
async def test_openapi_declares_exact_contest_methods_and_safe_error_schema() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    schema = response.json()
    assert set(schema["paths"]["/health"]) == {"get"}
    assert set(schema["paths"]["/add"]) == {"post"}
    assert set(schema["paths"]["/search"]) == {"post"}
    assert schema["paths"]["/add"]["post"]["responses"]["422"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/ErrorResponse")

"""Application orchestration tests for Raw Store plus Memory Gateway."""

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from memscope.application.memory_operations import (
    AddTimeoutError,
    MemoryOperationInvariantError,
    MemoryOperations,
)
from memscope.memory_gateway import (
    GatewayAdd,
    GatewayEvidence,
    GatewaySearch,
    GatewayTimeoutError,
    MemoryGateway,
)
from memscope.operations import AddCommand, MemoryMessage, RequestConflictError, SearchQuery
from memscope.raw_store.errors import IdempotencyConflictError, RawStoreUnavailableError
from memscope.raw_store.identity import cube_id_for_user, message_id_for_position
from memscope.raw_store.models import (
    AddDisposition,
    PersistedAdd,
    PreparedAdd,
    StoredAddResponse,
    UserCube,
)


def _command() -> AddCommand:
    return AddCommand(
        "request-1",
        "user-1",
        "session-1",
        (MemoryMessage("user", "fact", 123), MemoryMessage("assistant", "noted")),
    )


def _response(command: AddCommand | None = None) -> StoredAddResponse:
    actual = command or _command()
    return StoredAddResponse(True, actual.request_id, actual.user_id, actual.session_id)


def _prepared(disposition: AddDisposition = AddDisposition.NEW) -> PreparedAdd:
    return PreparedAdd(
        disposition,
        "a" * 64,
        UserCube("user-1", cube_id_for_user("user-1"), "reserved"),
        0,
        _response() if disposition is AddDisposition.COMPLETED else None,
    )


class StubRawStore:
    def __init__(
        self,
        prepared: PreparedAdd | Exception,
        *,
        ready: bool | Exception = True,
        complete_error: Exception | None = None,
    ) -> None:
        self.prepared = prepared
        self.ready = ready
        self.complete_error = complete_error
        self.prepare_calls: list[AddCommand] = []
        self.complete_calls: list[tuple[str, str, StoredAddResponse]] = []

    async def is_ready(self) -> bool:
        if isinstance(self.ready, Exception):
            raise self.ready
        return self.ready

    async def prepare_add(self, command: AddCommand) -> PreparedAdd:
        self.prepare_calls.append(command)
        if isinstance(self.prepared, Exception):
            raise self.prepared
        return self.prepared

    async def complete_add(
        self, request_id: str, payload_sha256: str, response: StoredAddResponse
    ) -> None:
        self.complete_calls.append((request_id, payload_sha256, response))
        if self.complete_error is not None:
            raise self.complete_error

    async def load_add(self, user_id: str, request_id: str) -> PersistedAdd | None:
        del user_id, request_id
        return None

    async def close(self) -> None:
        return None


class StubGateway:
    def __init__(
        self,
        *,
        ready: bool | Exception = True,
        add_error: Exception | None = None,
        search_result: Sequence[GatewayEvidence] | Exception = (),
        add_gate: asyncio.Event | None = None,
    ) -> None:
        self.ready = ready
        self.add_error = add_error
        self.search_result = search_result
        self.add_gate = add_gate
        self.add_started = asyncio.Event()
        self.add_calls: list[GatewayAdd] = []
        self.search_calls: list[GatewaySearch] = []

    async def is_ready(self) -> bool:
        if isinstance(self.ready, Exception):
            raise self.ready
        return self.ready

    async def add(self, request: GatewayAdd, *, timeout_seconds: float) -> None:
        assert 0 < timeout_seconds < 115
        self.add_calls.append(request)
        self.add_started.set()
        if self.add_gate is not None:
            await self.add_gate.wait()
        if self.add_error is not None:
            raise self.add_error

    async def search(self, request: GatewaySearch) -> Sequence[GatewayEvidence]:
        self.search_calls.append(request)
        if isinstance(self.search_result, Exception):
            raise self.search_result
        return self.search_result

    async def close(self) -> None:
        return None


@pytest.mark.parametrize("disposition", [AddDisposition.NEW, AddDisposition.PENDING])
async def test_add_maps_exact_gateway_request_then_completes(disposition: AddDisposition) -> None:
    raw = StubRawStore(_prepared(disposition))
    gateway = StubGateway()
    operations = MemoryOperations(raw_store=raw, gateway=gateway)

    await operations.add(_command())

    sent = gateway.add_calls[0]
    assert sent.request_id == "request-1"
    assert sent.cube_id == cube_id_for_user("user-1")
    assert sent.session_start_position == 0
    assert [(item.message_id, item.request_position) for item in sent.messages] == [
        (message_id_for_position("request-1", 0), 0),
        (message_id_for_position("request-1", 1), 1),
    ]
    assert [(item.role, item.content, item.timestamp_ms) for item in sent.messages] == [
        ("user", "fact", 123),
        ("assistant", "noted", None),
    ]
    assert raw.complete_calls == [("request-1", "a" * 64, _response())]


async def test_completed_replay_does_not_call_gateway_or_complete() -> None:
    raw = StubRawStore(_prepared(AddDisposition.COMPLETED))
    gateway = StubGateway(add_error=AssertionError("must not call"))

    await MemoryOperations(raw_store=raw, gateway=gateway).add(_command())

    assert gateway.add_calls == []
    assert raw.complete_calls == []


async def test_completed_replay_validates_exact_stored_response() -> None:
    prepared = replace(
        _prepared(AddDisposition.COMPLETED),
        response=replace(_response(), user_id="other-user"),
    )

    with pytest.raises(MemoryOperationInvariantError):
        await MemoryOperations(raw_store=StubRawStore(prepared), gateway=StubGateway()).add(
            _command()
        )


async def test_raw_conflict_is_translated_to_application_error() -> None:
    with pytest.raises(RequestConflictError) as captured:
        await MemoryOperations(
            raw_store=StubRawStore(IdempotencyConflictError()), gateway=StubGateway()
        ).add(_command())

    assert captured.value.code == "request.conflict"
    assert "storage" not in str(captured.value)


@pytest.mark.parametrize(
    ("gateway_error", "complete_error", "expected"),
    [
        (GatewayTimeoutError(), None, GatewayTimeoutError),
        (None, RawStoreUnavailableError(), RawStoreUnavailableError),
    ],
)
async def test_add_failure_never_reports_completion(
    gateway_error: Exception | None,
    complete_error: Exception | None,
    expected: type[Exception],
) -> None:
    raw = StubRawStore(_prepared(), complete_error=complete_error)
    gateway = StubGateway(add_error=gateway_error)

    with pytest.raises(expected):
        await MemoryOperations(raw_store=raw, gateway=gateway).add(_command())

    assert len(raw.complete_calls) == (0 if gateway_error is not None else 1)


async def test_search_filters_foreign_provenance_preserves_order_and_maps_fields() -> None:
    cube = cube_id_for_user("user-1")
    created = datetime(2026, 9, 2, tzinfo=UTC)
    gateway = StubGateway(
        search_result=(
            GatewayEvidence("foreign-user", "bad", "other", cube),
            GatewayEvidence("first", "exact", "user-1", cube, 1, created),
            GatewayEvidence("foreign-cube", "bad", "user-1", "other"),
            GatewayEvidence("second", "exact 2", "user-1", cube, 0.5),
        )
    )
    query = SearchQuery("question", "user-1", 2, ("A",))

    result = await MemoryOperations(raw_store=StubRawStore(_prepared()), gateway=gateway).search(
        query
    )

    assert [(item.id, item.content, item.score, item.created_at) for item in result] == [
        ("first", "exact", 1.0, created),
        ("second", "exact 2", 0.5, None),
    ]
    assert gateway.search_calls == [GatewaySearch("question", "user-1", cube, 2, ("A",))]


async def test_search_propagates_typed_gateway_error() -> None:
    with pytest.raises(GatewayTimeoutError):
        await MemoryOperations(
            raw_store=StubRawStore(_prepared()),
            gateway=StubGateway(search_result=GatewayTimeoutError()),
        ).search(SearchQuery("q", "user-1", 1))


@pytest.mark.parametrize(
    ("raw_ready", "gateway_ready", "expected"),
    [
        (True, True, True),
        (False, True, False),
        (True, RuntimeError("private"), False),
        (RuntimeError("private"), True, False),
    ],
)
async def test_readiness_requires_both_dependencies(
    raw_ready: bool | Exception, gateway_ready: bool | Exception, expected: bool
) -> None:
    operations = MemoryOperations(
        raw_store=StubRawStore(_prepared(), ready=raw_ready),
        gateway=StubGateway(ready=gateway_ready),
    )
    assert await operations.is_ready() is expected


async def test_add_cancellation_propagates_without_completion() -> None:
    gate = asyncio.Event()
    raw = StubRawStore(_prepared())
    gateway = StubGateway(add_gate=gate)
    task = asyncio.create_task(MemoryOperations(raw_store=raw, gateway=gateway).add(_command()))
    await gateway.add_started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert raw.complete_calls == []


@pytest.mark.parametrize(
    ("deadline", "warning", "reserve"),
    [
        (115, 0, 5),
        (115, 115, 5),
        (120, 105, 5),
        (115, 105, 0),
        (115, 105, 115),
    ],
)
def test_add_rejects_invalid_timing_configuration(
    deadline: float, warning: float, reserve: float
) -> None:
    with pytest.raises(ValueError):
        MemoryOperations(
            raw_store=StubRawStore(_prepared()),
            gateway=StubGateway(),
            add_deadline_seconds=deadline,
            add_warn_seconds=warning,
            gateway_reserve_seconds=reserve,
        )


async def test_add_fails_before_gateway_when_reserved_budget_is_exhausted() -> None:
    readings = iter((0.0, 20.0))
    raw = StubRawStore(_prepared())
    gateway = StubGateway()
    operations = MemoryOperations(
        raw_store=raw,
        gateway=gateway,
        add_deadline_seconds=10,
        add_warn_seconds=5,
        gateway_reserve_seconds=1,
        clock=lambda: next(readings),
    )

    with pytest.raises(AddTimeoutError) as captured:
        await operations.add(_command())
    assert captured.value.code == "add.timeout"
    assert captured.value.retryable is True
    assert gateway.add_calls == []
    assert raw.complete_calls == []


async def test_add_total_deadline_cancels_slow_gateway_and_cleans_lane(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gate = asyncio.Event()
    raw = StubRawStore(_prepared())
    gateway = StubGateway(add_gate=gate)
    operations = MemoryOperations(
        raw_store=raw,
        gateway=gateway,
        add_deadline_seconds=0.04,
        add_warn_seconds=0.01,
        gateway_reserve_seconds=0.005,
    )

    with pytest.raises(AddTimeoutError):
        await operations.add(_command())

    assert raw.complete_calls == []
    assert await operations._user_lanes.active_lane_count() == 0
    assert any(record.message == "memory_operation_slow" for record in caplog.records)


def test_stub_gateway_satisfies_protocol_shape() -> None:
    gateway: MemoryGateway = StubGateway()
    assert isinstance(gateway, StubGateway)

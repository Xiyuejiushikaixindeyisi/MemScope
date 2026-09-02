"""Persistence, idempotency, isolation and fault tests for SqliteRawStore."""

import asyncio
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from memscope.operations import AddCommand, MemoryMessage
from memscope.raw_store.errors import (
    IdempotencyConflictError,
    RawStoreInvariantError,
    RawStoreUnavailableError,
)
from memscope.raw_store.models import AddDisposition, StoredAddResponse
from memscope.raw_store.sqlite import SqliteRawStore
from tests.support import FIXED_UTC_NOW, fixed_utc_now


def _command(
    *,
    request_id: str = "request-1",
    user_id: str = "user-1",
    session_id: str = "session-1",
    content: str = "first fact",
) -> AddCommand:
    return AddCommand(
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
        messages=(
            MemoryMessage("user", content, 1704067200000),
            MemoryMessage("assistant", "second fact", None),
        ),
    )


def _response(command: AddCommand) -> StoredAddResponse:
    return StoredAddResponse(
        success=True,
        request_id=command.request_id,
        user_id=command.user_id,
        session_id=command.session_id,
    )


def _snapshot(path: Path) -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(path)
    try:
        rows: list[tuple[object, ...]] = []
        queries = (
            ("user_cubes", "SELECT * FROM user_cubes"),
            ("add_requests", "SELECT * FROM add_requests"),
            ("raw_messages", "SELECT * FROM raw_messages"),
            ("memos_outbox", "SELECT * FROM memos_outbox"),
        )
        for table, query in queries:
            rows.extend((table, *row) for row in connection.execute(query))
        return tuple(rows)
    finally:
        connection.close()


async def test_prepare_add_atomically_persists_exact_messages_cube_and_outbox(
    tmp_path: Path,
) -> None:
    path = tmp_path / "memory.db"
    command = _command(content="quote ' and SQL ; -- stays data")
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000, clock=fixed_utc_now)

    prepared = await store.prepare_add(command)
    loaded = await store.load_add(command.user_id, command.request_id)

    assert prepared.disposition is AddDisposition.NEW
    assert prepared.response is None
    assert prepared.cube.user_id == command.user_id
    assert prepared.cube.cube_id.startswith("cube_v1_")
    assert loaded is not None
    assert loaded.status == "pending"
    assert loaded.response is None
    assert [
        (message.request_position, message.session_position) for message in loaded.messages
    ] == [
        (0, 0),
        (1, 1),
    ]
    assert [
        (message.role, message.content, message.timestamp_ms) for message in loaded.messages
    ] == [
        ("user", "quote ' and SQL ; -- stays data", 1704067200000),
        ("assistant", "second fact", None),
    ]

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT status, attempts, last_error_code, next_retry_at FROM memos_outbox"
        ).fetchone() == ("pending", 0, None, None)
        assert connection.execute("SELECT created_at, updated_at FROM add_requests").fetchone() == (
            "2026-09-02T08:30:45.123Z",
            "2026-09-02T08:30:45.123Z",
        )
    finally:
        connection.close()
    await store.close()


async def test_pending_and_completed_replay_have_no_write_side_effects(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000, clock=fixed_utc_now)
    first = await store.prepare_add(command)
    pending_snapshot = _snapshot(path)

    pending = await store.prepare_add(command)

    assert pending.disposition is AddDisposition.PENDING
    assert pending.payload_sha256 == first.payload_sha256
    assert _snapshot(path) == pending_snapshot

    response = _response(command)
    await store.complete_add(command.request_id, first.payload_sha256, response)
    completed_snapshot = _snapshot(path)
    await store.complete_add(command.request_id, first.payload_sha256, response)
    completed = await store.prepare_add(command)

    assert completed.disposition is AddDisposition.COMPLETED
    assert completed.response == response
    assert _snapshot(path) == completed_snapshot
    await store.close()


@pytest.mark.parametrize(
    "changed",
    [
        replace(_command(), user_id="different-user"),
        replace(_command(), session_id="different-session"),
        replace(_command(), messages=tuple(reversed(_command().messages))),
        replace(
            _command(),
            messages=(replace(_command().messages[0], content="different"), _command().messages[1]),
        ),
        replace(
            _command(),
            messages=(replace(_command().messages[0], role="assistant"), _command().messages[1]),
        ),
        replace(
            _command(),
            messages=(replace(_command().messages[0], timestamp=123), _command().messages[1]),
        ),
    ],
)
async def test_different_payload_conflicts_without_mutation(
    tmp_path: Path, changed: AddCommand
) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    await store.prepare_add(_command())
    before = _snapshot(path)

    with pytest.raises(IdempotencyConflictError):
        await store.prepare_add(changed)

    assert _snapshot(path) == before
    await store.close()


async def test_complete_validates_digest_response_and_state(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    prepared = await store.prepare_add(command)

    with pytest.raises(IdempotencyConflictError):
        await store.complete_add(command.request_id, "0" * 64, _response(command))
    with pytest.raises(RawStoreInvariantError):
        await store.complete_add(
            command.request_id,
            prepared.payload_sha256,
            replace(_response(command), user_id="other"),
        )
    with pytest.raises(RawStoreInvariantError):
        await store.complete_add("missing", prepared.payload_sha256, _response(command))
    with pytest.raises(RawStoreInvariantError):
        await store.complete_add(command.request_id, "bad", _response(command))

    await store.complete_add(command.request_id, prepared.payload_sha256, _response(command))
    with pytest.raises(RawStoreInvariantError):
        await store.complete_add(
            command.request_id,
            prepared.payload_sha256,
            StoredAddResponse(True, command.request_id, command.user_id, "different"),
        )
    await store.close()


async def test_multi_chunk_order_restart_and_cross_user_isolation(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    first = _command(request_id="chunk-0")
    second = _command(request_id="chunk-1", content="later")
    other = _command(request_id="other", user_id="user-2", content="same text")
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    first_prepared = await store.prepare_add(first)
    await store.complete_add(first.request_id, first_prepared.payload_sha256, _response(first))
    await store.prepare_add(second)
    await store.prepare_add(other)
    await store.close()

    reopened = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    loaded_first = await reopened.load_add(first.user_id, first.request_id)
    loaded_second = await reopened.load_add(second.user_id, second.request_id)
    loaded_other = await reopened.load_add(other.user_id, other.request_id)

    assert loaded_first is not None and loaded_first.status == "completed"
    assert loaded_first.response == _response(first)
    assert loaded_second is not None
    assert [message.session_position for message in loaded_second.messages] == [2, 3]
    assert loaded_other is not None
    assert [message.session_position for message in loaded_other.messages] == [0, 1]
    assert await reopened.load_add("user-2", first.request_id) is None
    assert await reopened.load_add("user-1", other.request_id) is None
    await reopened.close()


async def test_same_request_and_cube_are_unique_across_concurrent_instances(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    first_store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    second_store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    command = _command()

    first, second = await asyncio.gather(
        first_store.prepare_add(command),
        second_store.prepare_add(command),
    )

    assert {first.disposition, second.disposition} == {
        AddDisposition.NEW,
        AddDisposition.PENDING,
    }
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM add_requests").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM user_cubes").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM raw_messages").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM memos_outbox").fetchone() == (1,)
    finally:
        connection.close()
    await first_store.close()
    await second_store.close()


async def test_same_instance_concurrent_chunks_use_independent_connections(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    commands = [_command(request_id=f"chunk-{index}") for index in range(4)]

    results = await asyncio.gather(*(store.prepare_add(command) for command in commands))

    assert all(result.disposition is AddDisposition.NEW for result in results)
    loaded = [await store.load_add(command.user_id, command.request_id) for command in commands]
    positions = sorted(
        message.session_position
        for request in loaded
        if request is not None
        for message in request.messages
    )
    assert positions == list(range(8))
    await store.close()


async def test_concurrent_different_payload_has_one_new_and_one_conflict(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    stores = [
        await SqliteRawStore.open(path, busy_timeout_ms=5000),
        await SqliteRawStore.open(path, busy_timeout_ms=5000),
    ]

    results = await asyncio.gather(
        stores[0].prepare_add(_command(content="a")),
        stores[1].prepare_add(_command(content="b")),
        return_exceptions=True,
    )

    assert (
        sum(
            not isinstance(result, BaseException) and result.disposition is AddDisposition.NEW
            for result in results
        )
        == 1
    )
    assert sum(isinstance(result, IdempotencyConflictError) for result in results) == 1
    await stores[0].close()
    await stores[1].close()


async def test_transaction_failure_rolls_back_without_orphans(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TRIGGER reject_raw_message BEFORE INSERT ON raw_messages
            BEGIN SELECT RAISE(ABORT, 'private failure detail'); END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError) as captured:
        await store.prepare_add(_command())

    assert "private failure detail" not in str(captured.value)
    connection = sqlite3.connect(path)
    try:
        queries = (
            "SELECT COUNT(*) FROM user_cubes",
            "SELECT COUNT(*) FROM add_requests",
            "SELECT COUNT(*) FROM raw_messages",
            "SELECT COUNT(*) FROM memos_outbox",
        )
        for query in queries:
            assert connection.execute(query).fetchone() == (0,)
    finally:
        connection.close()
    await store.close()


async def test_locked_database_fails_with_bounded_safe_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=100)
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RawStoreUnavailableError) as captured:
            await asyncio.wait_for(store.prepare_add(_command()), timeout=2)
    finally:
        blocker.rollback()
        blocker.close()

    assert captured.value.retryable is True
    assert str(path) not in str(captured.value)
    await store.close()


async def test_cancelled_waiter_finishes_its_private_transaction_and_retry_converges(
    tmp_path: Path,
) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    task = asyncio.create_task(store.prepare_add(_command()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    blocker.rollback()
    blocker.close()

    retry = await store.prepare_add(_command())
    await asyncio.sleep(0.05)

    assert retry.disposition in {AddDisposition.NEW, AddDisposition.PENDING}
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM add_requests").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM raw_messages").fetchone() == (2,)
    finally:
        connection.close()
    await store.close()


async def test_close_is_idempotent_and_rejects_new_operations(tmp_path: Path) -> None:
    store = await SqliteRawStore.open(tmp_path / "memory.db", busy_timeout_ms=5000)

    await store.close()
    await store.close()

    assert await store.is_ready() is False
    with pytest.raises(RawStoreUnavailableError):
        await store.prepare_add(_command())
    with pytest.raises(RawStoreUnavailableError):
        await store.load_add("user", "request")
    with pytest.raises(RawStoreUnavailableError):
        await store.complete_add("request", "a" * 64, _response(_command()))


async def test_corrupt_response_and_missing_messages_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    prepared = await store.prepare_add(command)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE add_requests SET status = 'completed', response_json = 'not-json'"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError):
        await store.load_add(command.user_id, command.request_id)
    with pytest.raises(RawStoreInvariantError):
        await store.prepare_add(command)

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE add_requests SET response_json = ?",
            (
                '{"request_id":"request-1","session_id":"session-1",'
                '"success":true,"user_id":"user-1"}',
            ),
        )
        connection.execute("DELETE FROM raw_messages")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RawStoreInvariantError):
        await store.load_add(command.user_id, command.request_id)

    assert prepared.disposition is AddDisposition.NEW
    await store.close()


@pytest.mark.parametrize(
    "response_json",
    [
        "[]",
        '{"request_id":"request-1","session_id":"session-1","success":false,"user_id":"user-1"}',
        '{"request_id":"request-1","session_id":"session-1","success":true,"user_id":7}',
    ],
)
async def test_malformed_completed_response_shapes_fail_closed(
    tmp_path: Path,
    response_json: str,
) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    await store.prepare_add(command)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE add_requests SET status = 'completed', response_json = ?",
            (response_json,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError):
        await store.load_add(command.user_id, command.request_id)
    await store.close()


@pytest.mark.parametrize("mutation", ["schema", "cube", "status", "response_identity"])
async def test_corrupt_replay_state_fails_closed(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    await store.prepare_add(command)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA ignore_check_constraints = ON")
        if mutation == "schema":
            connection.execute("UPDATE add_requests SET payload_schema_version = 2")
        elif mutation == "cube":
            connection.execute("UPDATE user_cubes SET cube_id = 'wrong-cube'")
            connection.execute("UPDATE add_requests SET cube_id = 'wrong-cube'")
            connection.execute("UPDATE memos_outbox SET cube_id = 'wrong-cube'")
        elif mutation == "status":
            connection.execute("UPDATE add_requests SET status = 'unknown'")
        else:
            connection.execute(
                "UPDATE add_requests SET status = 'completed', response_json = ?",
                (
                    '{"request_id":"request-1","session_id":"session-1",'
                    '"success":true,"user_id":"wrong-user"}',
                ),
            )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError):
        await store.prepare_add(command)
    await store.close()


@pytest.mark.parametrize("mutation", ["response", "outbox", "pending_response", "missing_outbox"])
async def test_corrupt_completion_state_fails_closed(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    prepared = await store.prepare_add(command)
    response = _response(command)
    if mutation in {"response", "outbox"}:
        await store.complete_add(command.request_id, prepared.payload_sha256, response)

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA ignore_check_constraints = ON")
        if mutation == "response":
            connection.execute(
                "UPDATE add_requests SET response_json = ?",
                (
                    '{ "request_id":"request-1","session_id":"session-1",'
                    '"success":true,"user_id":"user-1" }',
                ),
            )
        elif mutation == "outbox":
            connection.execute("UPDATE memos_outbox SET status = 'pending'")
        elif mutation == "pending_response":
            connection.execute("UPDATE add_requests SET response_json = '{}' ")
        else:
            connection.execute("DELETE FROM memos_outbox")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError):
        await store.complete_add(command.request_id, prepared.payload_sha256, response)
    await store.close()


@pytest.mark.parametrize("mutation", ["response_identity", "request_position", "session_position"])
async def test_corrupt_loaded_relationships_fail_closed(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    prepared = await store.prepare_add(command)
    connection = sqlite3.connect(path)
    try:
        if mutation == "response_identity":
            connection.execute(
                "UPDATE add_requests SET status = 'completed', response_json = ?",
                (
                    '{"request_id":"other","session_id":"session-1",'
                    '"success":true,"user_id":"user-1"}',
                ),
            )
        elif mutation == "request_position":
            connection.execute("DELETE FROM raw_messages WHERE request_position = 0")
        else:
            connection.execute(
                "UPDATE raw_messages SET session_position = 3 WHERE request_position = 1"
            )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RawStoreInvariantError):
        await store.load_add(command.user_id, command.request_id)
    assert prepared.disposition is AddDisposition.NEW
    await store.close()


async def test_complete_locked_and_integrity_failures_are_safely_classified(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    command = _command()
    store = await SqliteRawStore.open(path, busy_timeout_ms=100)
    prepared = await store.prepare_add(command)
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RawStoreUnavailableError):
            await store.complete_add(
                command.request_id,
                prepared.payload_sha256,
                _response(command),
            )
    finally:
        blocker.rollback()
        blocker.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TRIGGER reject_complete BEFORE UPDATE ON add_requests
            BEGIN SELECT RAISE(ABORT, 'private completion failure'); END
            """
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RawStoreInvariantError):
        await store.complete_add(
            command.request_id,
            prepared.payload_sha256,
            _response(command),
        )
    await store.close()


async def test_existing_store_readiness_fails_after_ledger_tamper(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE schema_migrations SET checksum = ?", ("0" * 64,))
        connection.commit()
    finally:
        connection.close()

    assert await store.is_ready() is False
    await store.close()


async def test_opening_directory_is_safe_unavailable(tmp_path: Path) -> None:
    with pytest.raises(RawStoreUnavailableError) as captured:
        await SqliteRawStore.open(tmp_path, busy_timeout_ms=5000)

    assert str(tmp_path) not in str(captured.value)


async def test_opening_corrupt_database_is_safe_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"not a sqlite database\x00private-data")

    with pytest.raises(RawStoreUnavailableError) as captured:
        await SqliteRawStore.open(path, busy_timeout_ms=5000)

    assert "private-data" not in str(captured.value)
    assert str(path) not in str(captured.value)


async def test_naive_clock_and_invalid_open_arguments_fail_safely(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(
        path,
        busy_timeout_ms=5000,
        clock=lambda: datetime(2026, 1, 1),
    )
    with pytest.raises(RawStoreInvariantError):
        await store.prepare_add(_command())
    await store.close()

    with pytest.raises(TypeError):
        await SqliteRawStore.open("memory.db", busy_timeout_ms=5000)  # type: ignore[arg-type]
    for invalid_path in (Path("."), Path(":memory:"), Path("file:memory.db")):
        with pytest.raises(ValueError):
            await SqliteRawStore.open(invalid_path, busy_timeout_ms=5000)
    for timeout in (True, 99, 60001):
        with pytest.raises(ValueError):
            await SqliteRawStore.open(tmp_path / "unused.db", busy_timeout_ms=timeout)

    assert FIXED_UTC_NOW.utcoffset() is not None


async def test_every_operation_configures_its_short_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []
    original_connect = sqlite3.connect

    def traced_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = cast("sqlite3.Connection", original_connect(*args, **kwargs))
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr("memscope.raw_store.sqlite.sqlite3.connect", traced_connect)
    store = await SqliteRawStore.open(tmp_path / "memory.db", busy_timeout_ms=4321)
    await store.prepare_add(_command())
    await store.load_add("user-1", "request-1")
    await store.close()

    normalized = {" ".join(statement.upper().split()) for statement in statements}
    assert "PRAGMA FOREIGN_KEYS = ON" in normalized
    assert "PRAGMA BUSY_TIMEOUT = 4321" in normalized
    assert "PRAGMA SYNCHRONOUS = FULL" in normalized
    assert "PRAGMA JOURNAL_MODE = WAL" in normalized
    assert "PRAGMA JOURNAL_MODE" in normalized

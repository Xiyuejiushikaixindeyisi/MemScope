"""SQLite implementation of the Raw Store persistence boundary."""

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Self

from memscope.logging_config import LOGGER_NAME
from memscope.operations import AddCommand
from memscope.raw_store.errors import (
    IdempotencyConflictError,
    MigrationError,
    RawStoreInvariantError,
    RawStoreUnavailableError,
)
from memscope.raw_store.identity import (
    PAYLOAD_SCHEMA_VERSION,
    cube_id_for_user,
    message_id_for_position,
    payload_sha256,
)
from memscope.raw_store.migrations import (
    CURRENT_SCHEMA_VERSION,
    apply_migrations,
    verify_migrations,
)
from memscope.raw_store.models import (
    AddDisposition,
    PersistedAdd,
    PersistedMessage,
    PreparedAdd,
    StoredAddResponse,
    UserCube,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(tz=UTC)


def _timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise RawStoreInvariantError()
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_response(response: StoredAddResponse) -> str:
    return json.dumps(
        {
            "success": response.success,
            "request_id": response.request_id,
            "user_id": response.user_id,
            "session_id": response.session_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _stored_response(value: str | None) -> StoredAddResponse | None:
    if value is None:
        return None
    try:
        decoded = json.loads(value)
        if not isinstance(decoded, dict) or set(decoded) != {
            "success",
            "request_id",
            "user_id",
            "session_id",
        }:
            raise ValueError
        if decoded["success"] is not True:
            raise ValueError
        if not all(
            isinstance(decoded[field], str) for field in ("request_id", "user_id", "session_id")
        ):
            raise ValueError
        return StoredAddResponse(
            success=decoded["success"],
            request_id=decoded["request_id"],
            user_id=decoded["user_id"],
            session_id=decoded["session_id"],
        )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise RawStoreInvariantError() from error


def _is_busy(error: BaseException | None) -> bool:
    return isinstance(error, sqlite3.Error) and getattr(error, "sqlite_errorcode", None) in {
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
    }


class SqliteRawStore:
    """File-backed Raw Store using one short-lived connection per operation."""

    def __init__(
        self,
        database_path: Path,
        *,
        busy_timeout_ms: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._database_path = database_path
        self._busy_timeout_ms = busy_timeout_ms
        self._clock = clock
        self._state_lock = threading.Lock()
        self._closed = False

    @classmethod
    async def open(
        cls,
        database_path: Path,
        *,
        busy_timeout_ms: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> Self:
        """Create or verify a file database before exposing the store."""

        if not isinstance(database_path, Path):
            raise TypeError("database_path must be a Path")
        if str(database_path) in {"", ".", ":memory:"} or str(database_path).startswith("file:"):
            raise ValueError("database_path must be a file path")
        if (
            isinstance(busy_timeout_ms, bool)
            or not isinstance(busy_timeout_ms, int)
            or not 100 <= busy_timeout_ms <= 60_000
        ):
            raise ValueError("busy_timeout_ms must be between 100 and 60000")

        path = database_path.absolute()
        store = cls(path, busy_timeout_ms=busy_timeout_ms, clock=clock)
        started = perf_counter()
        try:
            await asyncio.to_thread(store._initialize)
        except MigrationError as error:
            store._log("open", "unavailable", started, error)
            if _is_busy(error.__cause__):
                raise RawStoreUnavailableError() from error
            raise
        except RawStoreInvariantError as error:
            store._log("open", "unavailable", started, error)
            raise MigrationError() from error
        except (OSError, sqlite3.Error) as error:
            store._log("open", "unavailable", started, error)
            raise RawStoreUnavailableError() from error
        store._log("open", "success", started)
        return store

    async def is_ready(self) -> bool:
        """Probe the database without mutating or migrating it."""

        started = perf_counter()
        if self._is_closed():
            self._log("is_ready", "unavailable", started)
            return False
        try:
            ready = await asyncio.to_thread(self._is_ready_sync)
        except (MigrationError, RawStoreInvariantError, OSError, sqlite3.Error):
            ready = False
        self._log("is_ready", "success" if ready else "unavailable", started)
        return ready

    async def prepare_add(self, command: AddCommand) -> PreparedAdd:
        """Atomically persist a new Add or classify an existing request."""

        self._ensure_open()
        started = perf_counter()
        try:
            result = await asyncio.to_thread(self._prepare_add_sync, command)
        except IdempotencyConflictError as error:
            self._log("prepare_add", "conflict", started, error)
            raise
        except (MigrationError, RawStoreInvariantError) as error:
            self._log("prepare_add", "unavailable", started, error)
            raise
        except sqlite3.IntegrityError as error:
            invariant_error = RawStoreInvariantError()
            self._log("prepare_add", "unavailable", started, invariant_error)
            raise invariant_error from error
        except (OSError, sqlite3.Error) as error:
            unavailable_error = RawStoreUnavailableError()
            self._log("prepare_add", "unavailable", started, unavailable_error)
            raise unavailable_error from error
        self._log("prepare_add", result.disposition.value, started)
        return result

    async def complete_add(
        self,
        request_id: str,
        payload_sha256: str,
        response: StoredAddResponse,
    ) -> None:
        """Atomically complete one request and its durable outbox record."""

        self._ensure_open()
        started = perf_counter()
        try:
            await asyncio.to_thread(
                self._complete_add_sync,
                request_id,
                payload_sha256,
                response,
            )
        except IdempotencyConflictError as error:
            self._log("complete_add", "conflict", started, error)
            raise
        except (MigrationError, RawStoreInvariantError) as error:
            self._log("complete_add", "unavailable", started, error)
            raise
        except sqlite3.IntegrityError as error:
            invariant_error = RawStoreInvariantError()
            self._log("complete_add", "unavailable", started, invariant_error)
            raise invariant_error from error
        except (OSError, sqlite3.Error) as error:
            unavailable_error = RawStoreUnavailableError()
            self._log("complete_add", "unavailable", started, unavailable_error)
            raise unavailable_error from error
        self._log("complete_add", "completed", started)

    async def load_add(self, user_id: str, request_id: str) -> PersistedAdd | None:
        """Load one request while enforcing its external user boundary."""

        self._ensure_open()
        started = perf_counter()
        try:
            result = await asyncio.to_thread(self._load_add_sync, user_id, request_id)
        except (MigrationError, RawStoreInvariantError) as error:
            self._log("load_add", "unavailable", started, error)
            raise
        except sqlite3.IntegrityError as error:
            invariant_error = RawStoreInvariantError()
            self._log("load_add", "unavailable", started, invariant_error)
            raise invariant_error from error
        except (OSError, sqlite3.Error) as error:
            unavailable_error = RawStoreUnavailableError()
            self._log("load_add", "unavailable", started, unavailable_error)
            raise unavailable_error from error
        self._log("load_add", "success", started)
        return result

    async def close(self) -> None:
        """Idempotently prevent new work; there is no shared connection to close."""

        started = perf_counter()
        with self._state_lock:
            self._closed = True
        self._log("close", "success", started)

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect(initialize=True)
        try:
            apply_migrations(connection)
            self._verify_database(connection, quick_check=True)
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def _is_ready_sync(self) -> bool:
        with self._connection() as connection:
            self._verify_database(connection, quick_check=True)
        return True

    def _connect(self, *, initialize: bool = False) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            connection.execute("PRAGMA synchronous = FULL")
            journal_pragma = "PRAGMA journal_mode = WAL" if initialize else "PRAGMA journal_mode"
            row = connection.execute(journal_pragma).fetchone()
            if row is None or str(row[0]).lower() != "wal":
                raise RawStoreInvariantError()
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            self._verify_database(connection, quick_check=False)
            connection.row_factory = sqlite3.Row
            yield connection
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    @staticmethod
    def _verify_database(connection: sqlite3.Connection, *, quick_check: bool) -> None:
        verify_migrations(connection)
        if quick_check:
            row = connection.execute("PRAGMA quick_check").fetchone()
            if row is None or row[0] != "ok":
                raise RawStoreInvariantError()

    def _prepare_add_sync(self, command: AddCommand) -> PreparedAdd:
        digest = payload_sha256(command)
        cube_id = cube_id_for_user(command.user_id)
        now = _timestamp(self._clock())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT request_id, payload_schema_version, payload_sha256, user_id, session_id,
                       cube_id, status, response_json
                FROM add_requests WHERE request_id = ?
                """,
                (command.request_id,),
            ).fetchone()
            if existing is not None:
                result = self._classify_existing(
                    connection,
                    existing,
                    digest,
                    expected_message_count=len(command.messages),
                )
                connection.commit()
                return result

            connection.execute(
                """
                INSERT OR IGNORE INTO user_cubes (
                    user_id, cube_id, mapping_version, status, created_at, updated_at
                ) VALUES (?, ?, 1, 'reserved', ?, ?)
                """,
                (command.user_id, cube_id, now, now),
            )
            cube_row = connection.execute(
                "SELECT user_id, cube_id, status FROM user_cubes WHERE user_id = ?",
                (command.user_id,),
            ).fetchone()
            if (
                cube_row is None
                or cube_row["cube_id"] != cube_id
                or cube_row["status"] != "reserved"
            ):
                raise RawStoreInvariantError()

            position_row = connection.execute(
                """
                SELECT COALESCE(MAX(session_position), -1) + 1
                FROM raw_messages WHERE user_id = ? AND session_id = ?
                """,
                (command.user_id, command.session_id),
            ).fetchone()
            if position_row is None or not isinstance(position_row[0], int):
                raise RawStoreInvariantError()
            first_session_position = position_row[0]

            connection.execute(
                """
                INSERT INTO add_requests (
                    request_id, payload_schema_version, payload_sha256, user_id,
                    session_id, cube_id, status, response_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                (
                    command.request_id,
                    PAYLOAD_SCHEMA_VERSION,
                    digest,
                    command.user_id,
                    command.session_id,
                    cube_id,
                    now,
                    now,
                ),
            )
            for request_position, message in enumerate(command.messages):
                connection.execute(
                    """
                    INSERT INTO raw_messages (
                        message_id, request_id, user_id, session_id, request_position,
                        session_position, role, content, timestamp_ms, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id_for_position(command.request_id, request_position),
                        command.request_id,
                        command.user_id,
                        command.session_id,
                        request_position,
                        first_session_position + request_position,
                        message.role,
                        message.content,
                        message.timestamp,
                        now,
                    ),
                )
            connection.execute(
                """
                INSERT INTO memos_outbox (
                    request_id, cube_id, status, attempts, last_error_code,
                    next_retry_at, created_at, updated_at
                ) VALUES (?, ?, 'pending', 0, NULL, NULL, ?, ?)
                """,
                (command.request_id, cube_id, now, now),
            )
            connection.commit()

        return PreparedAdd(
            disposition=AddDisposition.NEW,
            payload_sha256=digest,
            cube=UserCube(user_id=command.user_id, cube_id=cube_id, status="reserved"),
            session_start_position=first_session_position,
            response=None,
        )

    @staticmethod
    def _classify_existing(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        digest: str,
        *,
        expected_message_count: int,
    ) -> PreparedAdd:
        if row["payload_schema_version"] != PAYLOAD_SCHEMA_VERSION:
            raise RawStoreInvariantError()
        if row["payload_sha256"] != digest:
            raise IdempotencyConflictError()
        cube_row = connection.execute(
            "SELECT user_id, cube_id, status FROM user_cubes WHERE user_id = ?",
            (row["user_id"],),
        ).fetchone()
        if (
            cube_row is None
            or cube_row["cube_id"] != cube_id_for_user(row["user_id"])
            or cube_row["cube_id"] != row["cube_id"]
            or cube_row["status"] != "reserved"
        ):
            raise RawStoreInvariantError()
        status = row["status"]
        if status == "pending":
            disposition = AddDisposition.PENDING
            response = None
        elif status == "completed":
            disposition = AddDisposition.COMPLETED
            response = _stored_response(row["response_json"])
            if (
                response is None
                or response.request_id != row["request_id"]
                or response.user_id != row["user_id"]
                or response.session_id != row["session_id"]
            ):
                raise RawStoreInvariantError()
        else:
            raise RawStoreInvariantError()
        position_row = connection.execute(
            """
            SELECT COUNT(*) AS message_count,
                   MIN(request_position) AS first_request_position,
                   MAX(request_position) AS last_request_position,
                   MIN(session_position) AS first_session_position,
                   MAX(session_position) AS last_session_position
            FROM raw_messages WHERE request_id = ?
            """,
            (row["request_id"],),
        ).fetchone()
        if (
            position_row is None
            or position_row["message_count"] != expected_message_count
            or position_row["first_request_position"] != 0
            or position_row["last_request_position"] != expected_message_count - 1
            or not isinstance(position_row["first_session_position"], int)
            or position_row["last_session_position"]
            != position_row["first_session_position"] + expected_message_count - 1
        ):
            raise RawStoreInvariantError()
        return PreparedAdd(
            disposition=disposition,
            payload_sha256=digest,
            cube=UserCube(
                user_id=cube_row["user_id"],
                cube_id=cube_row["cube_id"],
                status=cube_row["status"],
            ),
            session_start_position=position_row["first_session_position"],
            response=response,
        )

    def _complete_add_sync(
        self,
        request_id: str,
        digest: str,
        response: StoredAddResponse,
    ) -> None:
        if (
            not request_id.strip()
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise RawStoreInvariantError()
        encoded_response = _canonical_response(response)
        now = _timestamp(self._clock())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT payload_sha256, user_id, session_id, status, response_json
                FROM add_requests WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                raise RawStoreInvariantError()
            if row["payload_sha256"] != digest:
                raise IdempotencyConflictError()
            if (
                response.request_id != request_id
                or response.user_id != row["user_id"]
                or response.session_id != row["session_id"]
            ):
                raise RawStoreInvariantError()
            if row["status"] == "completed":
                if row["response_json"] != encoded_response:
                    raise RawStoreInvariantError()
                outbox = connection.execute(
                    "SELECT status FROM memos_outbox WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if outbox is None or outbox["status"] != "completed":
                    raise RawStoreInvariantError()
                connection.commit()
                return
            if row["status"] != "pending" or row["response_json"] is not None:
                raise RawStoreInvariantError()

            request_update = connection.execute(
                """
                UPDATE add_requests
                SET status = 'completed', response_json = ?, updated_at = ?
                WHERE request_id = ? AND status = 'pending'
                """,
                (encoded_response, now, request_id),
            )
            outbox_update = connection.execute(
                """
                UPDATE memos_outbox
                SET status = 'completed', updated_at = ?
                WHERE request_id = ? AND status = 'pending'
                """,
                (now, request_id),
            )
            if request_update.rowcount != 1 or outbox_update.rowcount != 1:
                raise RawStoreInvariantError()
            connection.commit()

    def _load_add_sync(self, user_id: str, request_id: str) -> PersistedAdd | None:
        with self._connection() as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT request_id, payload_sha256, user_id, session_id, status, response_json
                FROM add_requests WHERE request_id = ? AND user_id = ?
                """,
                (request_id, user_id),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            message_rows = connection.execute(
                """
                SELECT message_id, request_position, session_position,
                       role, content, timestamp_ms
                FROM raw_messages
                WHERE request_id = ? AND user_id = ?
                ORDER BY request_position
                """,
                (request_id, user_id),
            ).fetchall()
            response = _stored_response(row["response_json"])
            connection.commit()
        messages = tuple(
            PersistedMessage(
                message_id=message["message_id"],
                request_position=message["request_position"],
                session_position=message["session_position"],
                role=message["role"],
                content=message["content"],
                timestamp_ms=message["timestamp_ms"],
            )
            for message in message_rows
        )
        try:
            if response is not None and (
                response.request_id != row["request_id"]
                or response.user_id != row["user_id"]
                or response.session_id != row["session_id"]
            ):
                raise ValueError("stored response identity mismatch")
            if tuple(message.request_position for message in messages) != tuple(
                range(len(messages))
            ):
                raise ValueError("stored request positions are not contiguous")
            if messages and tuple(message.session_position for message in messages) != tuple(
                range(messages[0].session_position, messages[0].session_position + len(messages))
            ):
                raise ValueError("stored session positions are not contiguous")
            return PersistedAdd(
                request_id=row["request_id"],
                payload_sha256=row["payload_sha256"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                status=row["status"],
                messages=messages,
                response=response,
            )
        except (TypeError, ValueError) as error:
            raise RawStoreInvariantError() from error

    def _ensure_open(self) -> None:
        if self._is_closed():
            raise RawStoreUnavailableError()

    def _is_closed(self) -> bool:
        with self._state_lock:
            return self._closed

    @staticmethod
    def _log(
        operation: str,
        result: str,
        started: float,
        error: BaseException | None = None,
    ) -> None:
        extra: dict[str, Any] = {
            "storage_operation": operation,
            "storage_result": result,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "raw_store_duration_ms": round((perf_counter() - started) * 1000, 3),
        }
        if isinstance(error, MigrationError | RawStoreInvariantError | RawStoreUnavailableError):
            extra["error_code"] = error.code
            extra["retryable"] = error.retryable
        _LOGGER.info("raw_store_operation_completed", extra=extra)

"""Durable, content-free delivery receipts for Real Gateway Add idempotency."""

import asyncio
import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from memscope.memory_gateway.errors import (
    GatewayConflictError,
    GatewayProtocolError,
    GatewayUnavailableError,
)

_SCHEMA_VERSION = 1
_MIGRATION_SQL = """
CREATE TABLE gateway_receipts (
    request_id TEXT PRIMARY KEY NOT NULL,
    payload_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
    result_count INTEGER,
    memory_ids_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (status = 'pending' AND result_count IS NULL AND memory_ids_json IS NULL)
        OR
        (status = 'completed' AND result_count >= 0 AND memory_ids_json IS NOT NULL)
    )
) STRICT;
""".strip()
_MIGRATION_SHA256 = hashlib.sha256(_MIGRATION_SQL.encode()).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise GatewayProtocolError()
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_identity(request_id: str, payload_sha256: str) -> None:
    if not isinstance(request_id, str) or not request_id.strip():
        raise GatewayProtocolError()
    if (
        not isinstance(payload_sha256, str)
        or len(payload_sha256) != 64
        or any(character not in "0123456789abcdef" for character in payload_sha256)
    ):
        raise GatewayProtocolError()


class ReceiptStatus(StrEnum):
    """Persistent provider-delivery state."""

    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class GatewayReceipt:
    """One validated, content-free receipt snapshot."""

    request_id: str
    payload_sha256: str
    status: ReceiptStatus
    memory_ids: tuple[str, ...] | None

    def __post_init__(self) -> None:
        _validate_identity(self.request_id, self.payload_sha256)
        if self.status is ReceiptStatus.PENDING and self.memory_ids is not None:
            raise GatewayProtocolError()
        if self.status is ReceiptStatus.COMPLETED and self.memory_ids is None:
            raise GatewayProtocolError()


class GatewayReceiptStore:
    """SQLite receipt ledger isolated from the canonical Raw Store."""

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
        clock: Callable[[], datetime] = _utc_now,
    ) -> Self:
        """Create or validate the receipt database before exposing it."""

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
        store = cls(database_path.absolute(), busy_timeout_ms=busy_timeout_ms, clock=clock)
        try:
            await asyncio.to_thread(store._initialize)
        except GatewayProtocolError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise GatewayUnavailableError() from error
        return store

    async def is_ready(self) -> bool:
        """Return whether the ledger is open and its schema is intact."""

        if self._is_closed():
            return False
        try:
            return await asyncio.to_thread(self._is_ready_sync)
        except (GatewayProtocolError, OSError, sqlite3.Error):
            return False

    async def prepare(self, request_id: str, payload_sha256: str) -> GatewayReceipt:
        """Insert a pending receipt or return an exact existing receipt."""

        self._ensure_open()
        _validate_identity(request_id, payload_sha256)
        try:
            return await asyncio.to_thread(self._prepare_sync, request_id, payload_sha256)
        except (GatewayConflictError, GatewayProtocolError):
            raise
        except (OSError, sqlite3.Error) as error:
            raise GatewayUnavailableError() from error

    async def complete(
        self,
        request_id: str,
        payload_sha256: str,
        memory_ids: tuple[str, ...],
    ) -> None:
        """Atomically publish an exact provider result set."""

        self._ensure_open()
        _validate_identity(request_id, payload_sha256)
        if not isinstance(memory_ids, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in memory_ids
        ):
            raise GatewayProtocolError()
        if len(set(memory_ids)) != len(memory_ids):
            raise GatewayProtocolError()
        try:
            await asyncio.to_thread(
                self._complete_sync,
                request_id,
                payload_sha256,
                memory_ids,
            )
        except (GatewayConflictError, GatewayProtocolError):
            raise
        except (OSError, sqlite3.Error) as error:
            raise GatewayUnavailableError() from error

    async def close(self) -> None:
        """Idempotently reject future operations."""

        with self._state_lock:
            self._closed = True

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect(initialize=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_receipt_migrations (
                    version INTEGER PRIMARY KEY NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                ) STRICT
                """
            )
            row = connection.execute(
                "SELECT checksum FROM gateway_receipt_migrations WHERE version = ?",
                (_SCHEMA_VERSION,),
            ).fetchone()
            if row is None:
                connection.execute(_MIGRATION_SQL)
                connection.execute(
                    """
                    INSERT INTO gateway_receipt_migrations(version, checksum, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    (_SCHEMA_VERSION, _MIGRATION_SHA256, _timestamp(self._clock())),
                )
            elif row[0] != _MIGRATION_SHA256:
                raise GatewayProtocolError()
            self._verify(connection, quick_check=True)
            connection.commit()
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def _connect(self, *, initialize: bool = False) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        try:
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            connection.execute("PRAGMA synchronous = FULL")
            journal = "PRAGMA journal_mode = WAL" if initialize else "PRAGMA journal_mode"
            row = connection.execute(journal).fetchone()
            if row is None or str(row[0]).lower() != "wal":
                raise GatewayProtocolError()
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            self._verify(connection, quick_check=False)
            connection.row_factory = sqlite3.Row
            yield connection
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    @staticmethod
    def _verify(connection: sqlite3.Connection, *, quick_check: bool) -> None:
        rows = connection.execute(
            "SELECT version, checksum FROM gateway_receipt_migrations ORDER BY version"
        ).fetchall()
        if [tuple(row) for row in rows] != [(_SCHEMA_VERSION, _MIGRATION_SHA256)]:
            raise GatewayProtocolError()
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='gateway_receipts'"
        ).fetchone()
        if table is None or tuple(table) != (1,):
            raise GatewayProtocolError()
        if quick_check:
            check = connection.execute("PRAGMA quick_check").fetchone()
            if check is None or check[0] != "ok":
                raise GatewayProtocolError()

    def _is_ready_sync(self) -> bool:
        with self._connection() as connection:
            self._verify(connection, quick_check=True)
        return True

    def _prepare_sync(self, request_id: str, payload_sha256: str) -> GatewayReceipt:
        now = _timestamp(self._clock())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_id, payload_sha256, status, result_count, memory_ids_json
                FROM gateway_receipts WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO gateway_receipts(
                        request_id, payload_sha256, status, result_count, memory_ids_json,
                        created_at, updated_at
                    ) VALUES (?, ?, 'pending', NULL, NULL, ?, ?)
                    """,
                    (request_id, payload_sha256, now, now),
                )
                connection.commit()
                return GatewayReceipt(request_id, payload_sha256, ReceiptStatus.PENDING, None)
            receipt = self._decode_row(row)
            if receipt.payload_sha256 != payload_sha256:
                raise GatewayConflictError()
            connection.commit()
            return receipt

    def _complete_sync(
        self,
        request_id: str,
        payload_sha256: str,
        memory_ids: tuple[str, ...],
    ) -> None:
        encoded = json.dumps(memory_ids, ensure_ascii=False, separators=(",", ":"))
        now = _timestamp(self._clock())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_id, payload_sha256, status, result_count, memory_ids_json
                FROM gateway_receipts WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                raise GatewayProtocolError()
            receipt = self._decode_row(row)
            if receipt.payload_sha256 != payload_sha256:
                raise GatewayConflictError()
            if receipt.status is ReceiptStatus.COMPLETED:
                if receipt.memory_ids != memory_ids:
                    raise GatewayProtocolError()
                connection.commit()
                return
            changed = connection.execute(
                """
                UPDATE gateway_receipts
                SET status='completed', result_count=?, memory_ids_json=?, updated_at=?
                WHERE request_id=? AND status='pending'
                """,
                (len(memory_ids), encoded, now, request_id),
            )
            if changed.rowcount != 1:
                raise GatewayProtocolError()
            connection.commit()

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> GatewayReceipt:
        try:
            status = ReceiptStatus(row["status"])
            memory_ids: tuple[str, ...] | None
            if status is ReceiptStatus.PENDING:
                if row["result_count"] is not None or row["memory_ids_json"] is not None:
                    raise ValueError
                memory_ids = None
            else:
                decoded = json.loads(row["memory_ids_json"])
                if (
                    not isinstance(decoded, list)
                    or not all(isinstance(item, str) and item.strip() for item in decoded)
                    or len(decoded) != row["result_count"]
                    or len(set(decoded)) != len(decoded)
                ):
                    raise ValueError
                memory_ids = tuple(decoded)
            return GatewayReceipt(
                request_id=row["request_id"],
                payload_sha256=row["payload_sha256"],
                status=status,
                memory_ids=memory_ids,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise GatewayProtocolError() from error

    def _ensure_open(self) -> None:
        if self._is_closed():
            raise GatewayUnavailableError()

    def _is_closed(self) -> bool:
        with self._state_lock:
            return self._closed

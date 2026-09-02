"""Small, forward-only and checksum-verified SQLite migrations."""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from memscope.raw_store.errors import MigrationError

_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable schema transition."""

    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        """Return a deterministic digest of the migration identity and SQL."""

        source = json.dumps(
            [self.version, self.name, list(self.statements)],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(source).hexdigest()


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="raw_store_v1",
        statements=(
            """
            CREATE TABLE user_cubes (
                user_id TEXT PRIMARY KEY,
                cube_id TEXT NOT NULL UNIQUE,
                mapping_version INTEGER NOT NULL CHECK (mapping_version = 1),
                status TEXT NOT NULL CHECK (status = 'reserved'),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (user_id, cube_id)
            )
            """,
            """
            CREATE TABLE add_requests (
                request_id TEXT PRIMARY KEY,
                payload_schema_version INTEGER NOT NULL
                    CHECK (payload_schema_version = 1),
                payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                cube_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
                response_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (request_id, user_id, session_id),
                UNIQUE (request_id, cube_id),
                FOREIGN KEY (user_id, cube_id)
                    REFERENCES user_cubes (user_id, cube_id) ON DELETE RESTRICT,
                CHECK (
                    (status = 'pending' AND response_json IS NULL)
                    OR (status = 'completed' AND response_json IS NOT NULL)
                )
            )
            """,
            """
            CREATE TABLE raw_messages (
                row_id INTEGER PRIMARY KEY,
                message_id TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                request_position INTEGER NOT NULL CHECK (request_position >= 0),
                session_position INTEGER NOT NULL CHECK (session_position >= 0),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp_ms INTEGER,
                ingested_at TEXT NOT NULL,
                UNIQUE (request_id, request_position),
                UNIQUE (user_id, session_id, session_position),
                FOREIGN KEY (request_id, user_id, session_id)
                    REFERENCES add_requests (request_id, user_id, session_id)
                    ON DELETE RESTRICT
            )
            """,
            """
            CREATE TABLE memos_outbox (
                request_id TEXT PRIMARY KEY,
                cube_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                last_error_code TEXT,
                next_retry_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (request_id, cube_id)
                    REFERENCES add_requests (request_id, cube_id) ON DELETE RESTRICT
            )
            """,
            """
            CREATE INDEX idx_raw_messages_user_session_order
            ON raw_messages (user_id, session_id, session_position)
            """,
            """
            CREATE INDEX idx_add_requests_user_created
            ON add_requests (user_id, created_at)
            """,
            """
            CREATE INDEX idx_memos_outbox_status_retry
            ON memos_outbox (status, next_retry_at)
            """,
        ),
    ),
)

CURRENT_SCHEMA_VERSION = MIGRATIONS[-1].version


def _utc_timestamp() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_catalog(migrations: Sequence[Migration]) -> None:
    expected = 1
    names: set[str] = set()
    for migration in migrations:
        if migration.version != expected or not migration.name or not migration.statements:
            raise MigrationError()
        if migration.name in names:
            raise MigrationError()
        names.add(migration.name)
        expected += 1


def _read_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
        raise MigrationError()
    return cast("int", row[0])


def verify_migrations(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> None:
    """Verify ledger continuity, checksums and SQLite user_version."""

    _validate_catalog(migrations)
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    if len(rows) > len(migrations):
        raise MigrationError()
    for index, row in enumerate(rows):
        migration = migrations[index]
        if tuple(row) != (migration.version, migration.name, migration.checksum):
            raise MigrationError()
    if _read_user_version(connection) != len(rows):
        raise MigrationError()


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> None:
    """Atomically verify and apply all outstanding forward migrations."""

    try:
        _validate_catalog(migrations)
        connection.execute("BEGIN EXCLUSIVE")
        connection.execute(_LEDGER_SQL)
        verify_migrations(connection, migrations)
        applied = _read_user_version(connection)
        for migration in migrations[applied:]:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (migration.version, migration.name, migration.checksum, _utc_timestamp()),
            )
            connection.execute(f"PRAGMA user_version = {migration.version}")
        verify_migrations(connection, migrations)
        connection.commit()
    except MigrationError:
        connection.rollback()
        raise
    except sqlite3.Error as error:
        connection.rollback()
        raise MigrationError() from error

"""Component tests for atomic and checksum-verified SQLite migrations."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from memscope.raw_store.errors import MigrationError, RawStoreUnavailableError
from memscope.raw_store.migrations import (
    MIGRATIONS,
    Migration,
    apply_migrations,
    verify_migrations,
)
from memscope.raw_store.sqlite import SqliteRawStore
from tests.support import fixed_utc_now


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, isolation_level=None)


async def test_new_database_has_expected_schema_pragmas_and_checksum(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "memory.db"

    store = await SqliteRawStore.open(path, busy_timeout_ms=1234, clock=fixed_utc_now)
    assert await store.is_ready() is True
    await store.close()

    connection = _connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "schema_migrations",
            "user_cubes",
            "add_requests",
            "raw_messages",
            "memos_outbox",
        } <= tables
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchone() == (1, "raw_store_v1", MIGRATIONS[0].checksum)
    finally:
        connection.close()


async def test_reopen_is_idempotent_and_concurrent_open_is_serialized(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"

    first, second = await asyncio.gather(
        SqliteRawStore.open(path, busy_timeout_ms=5000),
        SqliteRawStore.open(path, busy_timeout_ms=5000),
    )
    await first.close()
    await second.close()
    reopened = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    await reopened.close()

    connection = _connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (1,)
    finally:
        connection.close()


@pytest.mark.parametrize("mutation", ["checksum", "future", "gap"])
async def test_open_fails_closed_for_invalid_migration_ledger(
    tmp_path: Path, mutation: str
) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=5000)
    await store.close()
    connection = _connect(path)
    try:
        if mutation == "checksum":
            connection.execute("UPDATE schema_migrations SET checksum = ?", ("0" * 64,))
        elif mutation == "future":
            connection.execute("PRAGMA user_version = 2")
        else:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DELETE FROM schema_migrations")
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum, applied_at)
                VALUES (2, 'future', ?, '2026-09-02T00:00:00.000Z')
                """,
                ("0" * 64,),
            )
            connection.execute("PRAGMA user_version = 2")
    finally:
        connection.close()

    with pytest.raises(MigrationError):
        await SqliteRawStore.open(path, busy_timeout_ms=5000)


def test_failed_migration_rolls_back_schema_and_ledger() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    broken = Migration(
        version=1,
        name="broken",
        statements=("CREATE TABLE partial_write (value TEXT)", "NOT VALID SQL"),
    )

    with pytest.raises(MigrationError):
        apply_migrations(connection, (broken,))

    assert (
        connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []
    )
    assert connection.execute("PRAGMA user_version").fetchone() == (0,)
    connection.close()


@pytest.mark.parametrize(
    "catalog",
    [
        (Migration(2, "gap", ("SELECT 1",)),),
        (Migration(1, "", ("SELECT 1",)),),
        (Migration(1, "empty", ()),),
        (
            Migration(1, "duplicate", ("SELECT 1",)),
            Migration(2, "duplicate", ("SELECT 1",)),
        ),
    ],
)
def test_invalid_migration_catalog_fails_before_writing(
    catalog: tuple[Migration, ...],
) -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)

    with pytest.raises(MigrationError):
        apply_migrations(connection, catalog)

    assert (
        connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []
    )
    connection.close()


def test_verify_rejects_more_ledger_rows_than_known_migrations() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT, checksum TEXT, applied_at TEXT
        )
        """
    )
    connection.executemany(
        "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
        (
            (1, "raw_store_v1", MIGRATIONS[0].checksum, "time"),
            (2, "future", "0" * 64, "time"),
        ),
    )
    connection.execute("PRAGMA user_version = 2")

    with pytest.raises(MigrationError):
        verify_migrations(connection)

    connection.close()


async def test_locked_migration_open_is_classified_as_retryable_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    store = await SqliteRawStore.open(path, busy_timeout_ms=100)
    await store.close()
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RawStoreUnavailableError):
            await SqliteRawStore.open(path, busy_timeout_ms=100)
    finally:
        blocker.rollback()
        blocker.close()

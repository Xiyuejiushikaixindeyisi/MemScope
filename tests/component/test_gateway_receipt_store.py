"""Durability and invariant tests for the private Gateway receipt ledger."""

import sqlite3
from pathlib import Path

import pytest

from memscope.memory_gateway import (
    GatewayConflictError,
    GatewayProtocolError,
    GatewayReceiptStore,
    GatewayUnavailableError,
    ReceiptStatus,
)
from tests.support import fixed_utc_now


async def test_receipt_prepare_complete_replay_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "receipts.db"
    store = await GatewayReceiptStore.open(path, busy_timeout_ms=5000, clock=fixed_utc_now)

    pending = await store.prepare("request-1", "a" * 64)
    assert pending.status is ReceiptStatus.PENDING
    assert pending.memory_ids is None
    assert await store.prepare("request-1", "a" * 64) == pending

    ids = (
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    )
    await store.complete("request-1", "a" * 64, ids)
    await store.complete("request-1", "a" * 64, ids)
    completed = await store.prepare("request-1", "a" * 64)
    assert completed.status is ReceiptStatus.COMPLETED
    assert completed.memory_ids == ids
    assert await store.is_ready() is True
    await store.close()

    reopened = await GatewayReceiptStore.open(path, busy_timeout_ms=5000)
    assert (await reopened.prepare("request-1", "a" * 64)).memory_ids == ids
    await reopened.close()
    assert await reopened.is_ready() is False
    with pytest.raises(GatewayUnavailableError):
        await reopened.prepare("request-2", "b" * 64)


async def test_receipt_conflicts_and_invalid_completion_fail_closed(tmp_path: Path) -> None:
    store = await GatewayReceiptStore.open(tmp_path / "r.db", busy_timeout_ms=5000)
    await store.prepare("request-1", "a" * 64)

    with pytest.raises(GatewayConflictError):
        await store.prepare("request-1", "b" * 64)
    with pytest.raises(GatewayConflictError):
        await store.complete("request-1", "b" * 64, ())
    with pytest.raises(GatewayProtocolError):
        await store.complete("missing", "a" * 64, ())
    with pytest.raises(GatewayProtocolError):
        await store.complete("request-1", "a" * 64, ("duplicate", "duplicate"))
    with pytest.raises(GatewayProtocolError):
        await store.complete("request-1", "a" * 64, ("",))

    await store.complete("request-1", "a" * 64, ())
    with pytest.raises(GatewayProtocolError):
        await store.complete("request-1", "a" * 64, ("different",))
    await store.close()


@pytest.mark.parametrize(
    ("path", "busy_limit"),
    [(Path(":" + "memory:"), 5000), (Path("ok.db"), 99)],
)
async def test_receipt_open_rejects_unsafe_parameters(path: Path, busy_limit: int) -> None:
    with pytest.raises(ValueError):
        await GatewayReceiptStore.open(path, busy_timeout_ms=busy_limit)


async def test_receipt_detects_migration_checksum_tampering(tmp_path: Path) -> None:
    path = tmp_path / "r.db"
    store = await GatewayReceiptStore.open(path, busy_timeout_ms=5000)
    await store.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE gateway_receipt_migrations SET checksum='bad'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(GatewayProtocolError):
        await GatewayReceiptStore.open(path, busy_timeout_ms=5000)

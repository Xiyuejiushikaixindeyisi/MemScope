"""Resource construction and failure-cleanup tests for the B05 runtime."""

from pathlib import Path
from typing import Any

import pytest

import memscope.runtime as runtime
from memscope.application.memory_operations import MemoryOperations
from memscope.settings import AppSettings
from tests.support import make_settings


class _Raw:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def close(self) -> None:
        self.events.append("raw.close")


class _Receipt:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def close(self) -> None:
        self.events.append("receipt.close")


class _Gateway:
    def __init__(
        self,
        *,
        receipt_store: _Receipt,
        events: list[str],
        verify_error: BaseException | None = None,
        **kwargs: Any,
    ) -> None:
        self.receipt = receipt_store
        self.events = events
        self.verify_error = verify_error
        self.kwargs = kwargs

    async def verify_upstream(self, *, timeout_seconds: float) -> None:
        self.events.append(f"gateway.verify:{timeout_seconds}")
        if self.verify_error is not None:
            raise self.verify_error

    async def close(self) -> None:
        self.events.append("gateway.close")
        await self.receipt.close()


def _settings(tmp_path: Path) -> AppSettings:
    return make_settings(
        app_profile="memos_add",
        memos_base_url="http://memos:8000",
        database_path=tmp_path / "raw.db",
        memos_gateway_receipt_path=tmp_path / "receipt.db",
    )


async def test_open_runtime_wires_settings_and_closes_in_reverse_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    raw = _Raw(events)
    receipt = _Receipt(events)
    observed: dict[str, Any] = {}

    class RawFactory:
        @staticmethod
        async def open(path: Path, *, busy_timeout_ms: int) -> _Raw:
            observed["raw"] = (path, busy_timeout_ms)
            return raw

    class ReceiptFactory:
        @staticmethod
        async def open(path: Path, *, busy_timeout_ms: int) -> _Receipt:
            observed["receipt"] = (path, busy_timeout_ms)
            return receipt

    def gateway_factory(**kwargs: Any) -> _Gateway:
        observed["gateway"] = kwargs
        return _Gateway(events=events, **kwargs)

    monkeypatch.setattr(runtime, "SqliteRawStore", RawFactory)
    monkeypatch.setattr(runtime, "GatewayReceiptStore", ReceiptFactory)
    monkeypatch.setattr(runtime, "MemosMemoryGateway", gateway_factory)
    settings = _settings(tmp_path)

    resources = await runtime.open_runtime(settings)

    assert isinstance(resources.operations, MemoryOperations)
    assert observed["raw"] == (settings.database_path, 5000)
    assert observed["receipt"] == (settings.memos_gateway_receipt_path, 5000)
    assert observed["gateway"] == {
        "base_url": "http://memos:8000",
        "receipt_store": receipt,
        "connect_timeout_seconds": 3.0,
        "response_max_bytes": 1_048_576,
    }
    assert events == ["gateway.verify:5.0"]

    await resources.close()
    assert events == ["gateway.verify:5.0", "gateway.close", "receipt.close", "raw.close"]


@pytest.mark.parametrize("profile", ["core"])
async def test_open_runtime_rejects_non_memos_profile(profile: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await runtime.open_runtime(
            make_settings(app_profile=profile, database_path=tmp_path / "r.db")
        )


async def test_receipt_open_failure_closes_raw(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    raw = _Raw(events)

    class RawFactory:
        open = staticmethod(lambda *args, **kwargs: _async_value(raw))

    class ReceiptFactory:
        open = staticmethod(lambda *args, **kwargs: _async_error(RuntimeError("receipt")))

    monkeypatch.setattr(runtime, "SqliteRawStore", RawFactory)
    monkeypatch.setattr(runtime, "GatewayReceiptStore", ReceiptFactory)

    with pytest.raises(RuntimeError, match="receipt"):
        await runtime.open_runtime(_settings(tmp_path))
    assert events == ["raw.close"]


async def test_gateway_construction_failure_closes_receipt_and_raw(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    raw = _Raw(events)
    receipt = _Receipt(events)

    class RawFactory:
        open = staticmethod(lambda *args, **kwargs: _async_value(raw))

    class ReceiptFactory:
        open = staticmethod(lambda *args, **kwargs: _async_value(receipt))

    def fail_gateway(**kwargs: Any) -> None:
        del kwargs
        raise RuntimeError("gateway")

    monkeypatch.setattr(runtime, "SqliteRawStore", RawFactory)
    monkeypatch.setattr(runtime, "GatewayReceiptStore", ReceiptFactory)
    monkeypatch.setattr(runtime, "MemosMemoryGateway", fail_gateway)

    with pytest.raises(RuntimeError, match="gateway"):
        await runtime.open_runtime(_settings(tmp_path))
    assert events == ["receipt.close", "raw.close"]


async def test_gateway_verification_failure_closes_gateway_and_raw(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    raw = _Raw(events)
    receipt = _Receipt(events)

    class RawFactory:
        open = staticmethod(lambda *args, **kwargs: _async_value(raw))

    class ReceiptFactory:
        open = staticmethod(lambda *args, **kwargs: _async_value(receipt))

    monkeypatch.setattr(runtime, "SqliteRawStore", RawFactory)
    monkeypatch.setattr(runtime, "GatewayReceiptStore", ReceiptFactory)
    monkeypatch.setattr(
        runtime,
        "MemosMemoryGateway",
        lambda **kwargs: _Gateway(
            events=events,
            verify_error=RuntimeError("health"),
            **kwargs,
        ),
    )

    with pytest.raises(RuntimeError, match="health"):
        await runtime.open_runtime(_settings(tmp_path))
    assert events == ["gateway.verify:5.0", "gateway.close", "receipt.close", "raw.close"]


async def _async_value(value: Any) -> Any:
    return value


async def _async_error(error: BaseException) -> Any:
    raise error

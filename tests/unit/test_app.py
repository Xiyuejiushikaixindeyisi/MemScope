"""Tests for the dependency-injectable application factory."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

import memscope.app as app_module
from memscope.app import create_app
from memscope.operations import (
    AddCommand,
    MemoryEvidence,
    MemoryMessage,
    SearchQuery,
    UnavailableContestOperations,
)
from tests.support import make_settings


def test_create_app_uses_explicit_settings(capsys: pytest.CaptureFixture[str]) -> None:
    settings = make_settings(host="127.0.0.1", port=9001)

    application = create_app(settings)

    assert application.state.settings is settings
    assert application.title == "MemScope"
    payload = json.loads(capsys.readouterr().err)
    assert payload["event"] == "application_initialized"


def test_create_app_loads_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9010")

    application = create_app()

    assert application.state.settings.port == 9010


def test_create_app_instances_do_not_share_state() -> None:
    first = create_app(make_settings(port=9011))
    second = create_app(make_settings(port=9012))

    assert first is not second
    assert first.state.settings.port == 9011
    assert second.state.settings.port == 9012
    assert isinstance(first.state.operations, UnavailableContestOperations)
    assert first.state.operations is not second.state.operations


async def test_memos_profile_installs_and_closes_lifespan_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    operations = UnavailableContestOperations()

    @dataclass
    class Resources:
        operations: UnavailableContestOperations
        closed: bool = False

        async def close(self) -> None:
            self.closed = True

    resources = Resources(operations)

    async def fake_open(settings: object) -> Resources:
        assert settings is configured
        return resources

    monkeypatch.setattr(app_module, "open_runtime", fake_open)
    configured = make_settings(
        app_profile="memos_add",
        memos_base_url="http://memos:8000",
        database_path=tmp_path / "raw.db",
        memos_gateway_receipt_path=tmp_path / "receipt.db",
    )
    application = create_app(configured)

    async with application.router.lifespan_context(application):
        assert application.state.operations is operations
    assert resources.closed is True
    assert isinstance(application.state.operations, UnavailableContestOperations)


async def test_state_operations_proxy_tracks_replaced_application_state() -> None:
    class Operations:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def is_ready(self) -> bool:
            self.calls.append("ready")
            return True

        async def add(self, command: AddCommand) -> None:
            self.calls.append(command.request_id)

        async def search(self, query: SearchQuery) -> tuple[MemoryEvidence, ...]:
            self.calls.append(query.query)
            return ()

    application = create_app(make_settings())
    operations = Operations()
    application.state.operations = operations
    proxy = app_module._StateOperations(application)

    assert await proxy.is_ready() is True
    await proxy.add(AddCommand("request", "user", "session", (MemoryMessage("user", "fact"),)))
    assert await proxy.search(SearchQuery("query", "user", 1)) == ()
    assert operations.calls == ["ready", "request", "query"]

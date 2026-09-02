"""Tests for the dependency-injectable application factory."""

import json

import pytest

from memscope.app import create_app
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

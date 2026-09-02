"""Tests for centralized application settings."""

from typing import Any

import pytest
from pydantic import ValidationError

from memscope.errors import ConfigurationError
from memscope.settings import AppProfile, LogFormat, load_settings
from tests.support import make_settings


def test_settings_defaults_are_safe_for_b00() -> None:
    settings = make_settings()

    assert settings.app_profile is AppProfile.CORE
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.log_level == "INFO"
    assert settings.log_format is LogFormat.JSON


def test_settings_load_environment_and_normalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PROFILE", "core")
    monkeypatch.setenv("HOST", " 127.0.0.1 ")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", " debug ")
    monkeypatch.setenv("LOG_FORMAT", "console")

    settings = load_settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.log_format is LogFormat.CONSOLE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "   "),
        ("port", 0),
        ("port", 65536),
        ("log_level", "TRACE"),
        ("log_level", 10),
        ("app_profile", "mock"),
        ("log_format", "xml"),
    ],
)
def test_settings_reject_invalid_values(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: value})


def test_load_settings_redacts_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    sensitive_invalid_value = "not-a-port-secret-value"
    monkeypatch.setenv("PORT", sensitive_invalid_value)

    with pytest.raises(ConfigurationError) as captured:
        load_settings()

    assert captured.value.fields == ("port",)
    assert sensitive_invalid_value not in str(captured.value)


def test_safe_summary_is_an_explicit_non_secret_allowlist() -> None:
    settings = make_settings(host="localhost", port=8123)

    assert settings.safe_summary() == {
        "app_profile": "core",
        "host": "localhost",
        "port": 8123,
        "log_level": "INFO",
        "log_format": "json",
    }

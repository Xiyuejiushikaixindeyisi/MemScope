"""Tests for centralized application settings."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from memscope.errors import ConfigurationError
from memscope.settings import (
    AppProfile,
    ContestAuthMode,
    LogFormat,
    MemosSearchDedup,
    MemosSearchMode,
    load_settings,
)
from tests.support import make_settings


def test_settings_defaults_are_safe_for_core_profile() -> None:
    settings = make_settings()

    assert settings.app_profile is AppProfile.CORE
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.log_level == "INFO"
    assert settings.log_format is LogFormat.JSON
    assert settings.contest_auth_mode is ContestAuthMode.NONE
    assert settings.contest_api_key is None
    assert settings.database_path == Path("data/memory.db")
    assert settings.sqlite_busy_timeout_ms == 5000
    assert settings.memos_base_url is None
    assert settings.memos_gateway_receipt_path == Path("data/gateway-receipts.db")
    assert settings.add_deadline_seconds == 115
    assert settings.add_warn_seconds == 105
    assert settings.search_deadline_seconds == 55
    assert settings.search_warn_seconds == 50
    assert settings.memos_search_mode is MemosSearchMode.FAST
    assert settings.memos_search_relativity == 0
    assert settings.memos_search_dedup is MemosSearchDedup.EXACT
    assert settings.memos_search_rerank is True


def test_settings_load_environment_and_normalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PROFILE", "core")
    monkeypatch.setenv("HOST", " 127.0.0.1 ")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", " debug ")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("DATABASE_PATH", "/var/local/memscope-test.db")
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "1200")

    settings = load_settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.log_format is LogFormat.CONSOLE
    assert settings.database_path == Path("/var/local/memscope-test.db")
    assert settings.sqlite_busy_timeout_ms == 1200


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
        ("database_path", ""),
        ("database_path", "   "),
        ("database_path", ":memory:"),
        ("database_path", "file:memory.db"),
        ("database_path", Path(".")),
        ("database_path", 123),
        ("sqlite_busy_timeout_ms", 99),
        ("sqlite_busy_timeout_ms", 60001),
        ("memos_base_url", "ftp://private.example/path"),
        ("memos_base_url", "https://user:secret@example.test"),
        ("memos_gateway_receipt_path", ":memory:"),
        ("add_deadline_seconds", float("inf")),
        ("memos_response_max_bytes", 100),
        ("search_deadline_seconds", float("nan")),
        ("memos_search_mode", "slow"),
        ("memos_search_dedup", "fuzzy"),
        ("memos_search_relativity", float("nan")),
        ("memos_search_relativity", True),
        ("memos_search_relativity", -0.1),
        ("memos_search_relativity", 1.1),
        ("memos_search_rerank", "yes"),
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


def test_shared_key_auth_configuration_is_valid_and_secret() -> None:
    settings = make_settings(contest_auth_mode="shared_key", contest_api_key="private-key")

    assert settings.contest_auth_mode is ContestAuthMode.SHARED_KEY
    assert settings.contest_api_key is not None
    assert settings.contest_api_key.get_secret_value() == "private-key"
    assert "private-key" not in repr(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"contest_auth_mode": "shared_key"},
        {"contest_auth_mode": "none", "contest_api_key": "unexpected"},
        {"contest_auth_mode": "shared_key", "contest_api_key": ""},
        {"contest_auth_mode": "shared_key", "contest_api_key": " padded "},
    ],
)
def test_settings_reject_invalid_auth_combinations(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_load_settings_redacts_invalid_auth_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "unexpected-secret"
    monkeypatch.setenv("CONTEST_AUTH_MODE", "none")
    monkeypatch.setenv("CONTEST_API_KEY", secret)

    with pytest.raises(ConfigurationError) as captured:
        load_settings()

    assert secret not in str(captured.value)


def test_safe_summary_is_an_explicit_non_secret_allowlist() -> None:
    settings = make_settings(host="localhost", port=8123)

    assert settings.safe_summary() == {
        "app_profile": "core",
        "host": "localhost",
        "port": 8123,
        "log_level": "INFO",
        "log_format": "json",
        "contest_auth_mode": "none",
        "contest_api_key_configured": False,
        "database_path_kind": "relative",
        "sqlite_busy_timeout_ms": 5000,
        "memos_base_url_configured": False,
        "memos_base_url_scheme": "none",
        "memos_gateway_receipt_path_kind": "relative",
        "add_deadline_seconds": 115.0,
        "add_warn_seconds": 105.0,
        "memos_deadline_reserve_seconds": 5.0,
        "memos_connect_timeout_seconds": 3.0,
        "memos_response_max_bytes": 1048576,
        "search_deadline_seconds": 55.0,
        "search_warn_seconds": 50.0,
        "memos_search_mode": "fast",
        "memos_search_relativity": 0.0,
        "memos_search_dedup": "exact",
        "memos_search_rerank": True,
    }


def test_safe_summary_reports_only_database_path_kind() -> None:
    secret_path = Path("/var/local/private-user/database.db")
    settings = make_settings(database_path=secret_path)

    summary = settings.safe_summary()

    assert summary["database_path_kind"] == "absolute"
    assert str(secret_path) not in repr(summary)


def test_memos_add_profile_requires_origin_and_separate_databases() -> None:
    with pytest.raises(ValidationError):
        make_settings(app_profile="memos_add")
    with pytest.raises(ValidationError):
        make_settings(
            app_profile="memos_add",
            memos_base_url="http://memos:8000",
            database_path="same.db",
            memos_gateway_receipt_path="same.db",
        )

    settings = make_settings(
        app_profile="memos_add",
        memos_base_url=" https://memos.example/ ",
        database_path="raw.db",
        memos_gateway_receipt_path="receipts.db",
    )
    assert settings.app_profile is AppProfile.MEMOS_ADD
    assert settings.memos_base_url == "https://memos.example"
    assert settings.safe_summary()["memos_base_url_scheme"] == "https"
    assert "memos.example" not in repr(settings.safe_summary())


@pytest.mark.parametrize(
    "overrides",
    [
        {"add_warn_seconds": 115},
        {"add_deadline_seconds": 120},
        {"memos_deadline_reserve_seconds": 115},
        {"memos_connect_timeout_seconds": 0},
        {"search_warn_seconds": 55},
        {"search_deadline_seconds": 60},
    ],
)
def test_settings_reject_invalid_deadline_relationships(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)

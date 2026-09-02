"""Typed factories for deterministic test configuration."""

from datetime import UTC, datetime
from typing import Any

from memscope.settings import AppSettings

FIXED_UTC_NOW = datetime(2026, 9, 2, 8, 30, 45, 123000, tzinfo=UTC)


def fixed_utc_now() -> datetime:
    """Return one stable timezone-aware instant for persistence tests."""

    return FIXED_UTC_NOW


def make_settings(**overrides: Any) -> AppSettings:
    """Construct Settings without consulting a developer's local .env file."""

    return AppSettings(_env_file=None, **overrides)  # type: ignore[call-arg]

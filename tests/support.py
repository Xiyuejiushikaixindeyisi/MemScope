"""Typed factories for deterministic test configuration."""

from typing import Any

from memscope.settings import AppSettings


def make_settings(**overrides: Any) -> AppSettings:
    """Construct Settings without consulting a developer's local .env file."""

    return AppSettings(_env_file=None, **overrides)  # type: ignore[call-arg]

"""Central, typed application settings."""

from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from memscope.errors import ConfigurationError


class AppProfile(StrEnum):
    """Profiles delivered by the current batch."""

    CORE = "core"


class LogFormat(StrEnum):
    """Supported log renderers."""

    JSON = "json"
    CONSOLE = "console"


class ContestAuthMode(StrEnum):
    """Contest endpoint authentication modes."""

    NONE = "none"
    SHARED_KEY = "shared_key"


class AppSettings(BaseSettings):
    """Validated settings for the MemScope application."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        frozen=True,
    )

    app_profile: AppProfile = AppProfile.CORE
    host: str = "0.0.0.0"  # noqa: S104 - intentional service bind default
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON
    contest_auth_mode: ContestAuthMode = ContestAuthMode.NONE
    contest_api_key: SecretStr | None = None
    database_path: Path = Path("data/memory.db")
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=100, le=60_000)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("host must not be empty")
        return normalized

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("log level must be a string")
        normalized = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError("unsupported log level")
        return normalized

    @field_validator("contest_api_key", mode="before")
    @classmethod
    def validate_contest_api_key(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not value.strip():
                return None
            if value != value.strip():
                raise ValueError("contest API key must not have surrounding whitespace")
        return value

    @field_validator("database_path", mode="before")
    @classmethod
    def validate_database_path(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized or normalized == ":memory:" or normalized.startswith("file:"):
                raise ValueError("database path must be a file path")
            return normalized
        if isinstance(value, Path):
            rendered = str(value)
            if rendered in {"", ".", ":memory:"} or rendered.startswith("file:"):
                raise ValueError("database path must be a file path")
            return value
        raise ValueError("database path must be a string or Path")

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> Self:
        if self.contest_auth_mode is ContestAuthMode.NONE and self.contest_api_key is not None:
            raise ValueError("contest API key requires shared_key auth mode")
        if self.contest_auth_mode is ContestAuthMode.SHARED_KEY and self.contest_api_key is None:
            raise ValueError("shared_key auth mode requires a contest API key")
        return self

    def safe_summary(self) -> dict[str, str | int | bool]:
        """Return an explicit allowlist of non-secret settings for diagnostics."""

        return {
            "app_profile": self.app_profile.value,
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "log_format": self.log_format.value,
            "contest_auth_mode": self.contest_auth_mode.value,
            "contest_api_key_configured": self.contest_api_key is not None,
            "database_path_kind": "absolute" if self.database_path.is_absolute() else "relative",
            "sqlite_busy_timeout_ms": self.sqlite_busy_timeout_ms,
        }


def load_settings() -> AppSettings:
    """Load settings while removing raw input values from validation failures."""

    try:
        return AppSettings()
    except ValidationError as error:
        fields = (
            ".".join(str(location) for location in issue["loc"])
            for issue in error.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(fields) from None

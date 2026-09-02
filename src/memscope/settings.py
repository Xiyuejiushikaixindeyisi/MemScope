"""Central, typed application settings."""

from enum import StrEnum
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from memscope.errors import ConfigurationError


class AppProfile(StrEnum):
    """Profiles delivered by the current batch."""

    CORE = "core"


class LogFormat(StrEnum):
    """Supported log renderers."""

    JSON = "json"
    CONSOLE = "console"


class AppSettings(BaseSettings):
    """Validated settings for the B00 application shell."""

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

    def safe_summary(self) -> dict[str, str | int]:
        """Return an explicit allowlist of non-secret settings for diagnostics."""

        return {
            "app_profile": self.app_profile.value,
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "log_format": self.log_format.value,
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

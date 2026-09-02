"""Internal, transport-independent error types."""

from collections.abc import Iterable


class MemScopeError(RuntimeError):
    """Base class for errors that may cross internal component boundaries."""

    def __init__(self, *, code: str, message: str, retryable: bool = False) -> None:
        if not code.strip():
            raise ValueError("error code must not be empty")
        if not message.strip():
            raise ValueError("error message must not be empty")

        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ConfigurationError(MemScopeError):
    """Raised when application settings cannot be safely constructed."""

    def __init__(self, fields: Iterable[str]) -> None:
        normalized_fields = tuple(sorted({field.strip() for field in fields if field.strip()}))
        self.fields = normalized_fields or ("unknown",)
        joined_fields = ", ".join(self.fields)
        super().__init__(
            code="configuration.invalid",
            message=f"Invalid application configuration for field(s): {joined_fields}",
            retryable=False,
        )

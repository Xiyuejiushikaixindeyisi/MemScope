"""Pydantic models for the public contest HTTP contract."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _RequestModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _validate_nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


class MessageInput(_RequestModel):
    """One ordered Add message."""

    role: str
    content: str
    timestamp: int | None = None

    validate_role = field_validator("role")(_validate_nonblank)
    validate_content = field_validator("content")(_validate_nonblank)


class AddRequest(_RequestModel):
    """Public Add request."""

    request_id: str
    user_id: str
    session_id: str
    messages: list[MessageInput] = Field(min_length=1)

    validate_ids = field_validator("request_id", "user_id", "session_id")(_validate_nonblank)


class SearchRequest(_RequestModel):
    """Public Search request."""

    query: str
    user_id: str
    top_k: int = Field(ge=1, le=100)
    options: list[str] | None = None

    validate_strings = field_validator("query", "user_id")(_validate_nonblank)


class HealthResponse(_ResponseModel):
    """Small stable response for a ready service."""

    status: Literal["ok"] = "ok"


class AddResponse(_ResponseModel):
    """Successful synchronous Add acknowledgement."""

    success: Literal[True] = True
    request_id: str
    user_id: str
    session_id: str

    validate_ids = field_validator("request_id", "user_id", "session_id")(_validate_nonblank)


class EvidenceResponse(_ResponseModel):
    """One JSON-safe evidence item returned by Search."""

    id: str
    content: str
    score: float | None = Field(default=None, allow_inf_nan=False)
    created_at: datetime | None = None

    validate_strings = field_validator("id", "content")(_validate_nonblank)

    @model_validator(mode="after")
    def validate_created_at_timezone(self) -> Self:
        if self.created_at is not None and self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return self


class SearchResponse(_ResponseModel):
    """Search response envelope required by the evaluator."""

    data: tuple[EvidenceResponse, ...]


class ErrorBody(_ResponseModel):
    """Safe stable details for an HTTP failure."""

    code: str
    message: str
    retryable: bool


class ErrorResponse(_ResponseModel):
    """Top-level HTTP failure envelope."""

    error: ErrorBody

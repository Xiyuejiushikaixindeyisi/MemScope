"""Pydantic models for the deliberately small Mock Model HTTP subset."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator


class _MockRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")


class ChatMessage(_MockRequest):
    role: StrictStr = Field(min_length=1)
    content: StrictStr = Field(min_length=1)

    @field_validator("role", "content")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class ChatCompletionRequest(_MockRequest):
    model: StrictStr = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    stream: StrictBool = False

    @field_validator("model")
    @classmethod
    def reject_blank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be blank")
        return value

    @field_validator("stream")
    @classmethod
    def reject_streaming(cls, value: bool) -> bool:
        if value:
            raise ValueError("streaming is not supported")
        return value


class EmbeddingRequest(_MockRequest):
    model: StrictStr = Field(min_length=1)
    input: StrictStr | list[StrictStr]

    @field_validator("model")
    @classmethod
    def reject_blank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be blank")
        return value

    @field_validator("input")
    @classmethod
    def reject_empty_list(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, list) and not value:
            raise ValueError("input list must not be empty")
        return value


class ResponseMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    role: Literal["assistant"] = "assistant"
    content: str


class ChatChoice(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    index: int
    message: ResponseMessage
    finish_reason: Literal["stop"] = "stop"


class Usage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int = 0
    model: str
    choices: tuple[ChatChoice, ...]
    usage: Usage = Field(default_factory=Usage)


class EmbeddingItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    object: Literal["embedding"] = "embedding"
    index: int
    embedding: tuple[float, ...]


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    object: Literal["list"] = "list"
    data: tuple[EmbeddingItem, ...]
    model: str
    usage: Usage = Field(default_factory=Usage)


class MockErrorBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message: str
    type: str
    code: str


class MockErrorResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    error: MockErrorBody


def safe_error_payload(*, status_code: int, code: str) -> dict[str, Any]:
    """Create one content-free, OpenAI-shaped test error payload."""

    message = "Mock model request failed" if status_code >= 500 else "Mock model request invalid"
    error_type = "server_error" if status_code >= 500 else "invalid_request_error"
    return MockErrorResponse(
        error=MockErrorBody(message=message, type=error_type, code=code)
    ).model_dump(mode="json")

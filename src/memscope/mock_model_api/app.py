"""Independent ASGI application implementing the Mock Model API subset."""

import asyncio
import hashlib
import json
import logging
from time import perf_counter
from typing import Annotated, Literal, cast

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse, Response

from memscope.logging_config import LOGGER_NAME
from memscope.mock_model_api.deterministic import deterministic_embedding
from memscope.mock_model_api.models import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingItem,
    EmbeddingRequest,
    EmbeddingResponse,
    ResponseMessage,
    safe_error_payload,
)

_LOGGER = logging.getLogger(LOGGER_NAME)
_FAILURE_HEADER = "X-MemScope-Mock-Failure"
_FAILURES = frozenset(
    {"rate_limit", "upstream_error", "timeout", "invalid_json", "dimension_mismatch"}
)
FailureHeader = Annotated[list[str] | None, Header(alias=_FAILURE_HEADER)]
MockFailure = Literal[
    "rate_limit", "upstream_error", "timeout", "invalid_json", "dimension_mismatch"
]


def _safe_json_response(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=safe_error_payload(status_code=status_code, code=code),
    )


def _request_id(prefix: str, values: tuple[str, ...]) -> str:
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"mock-{prefix}-{digest[:24]}"


def _failure_values(request: Request) -> list[str]:
    return request.headers.getlist(_FAILURE_HEADER)


async def _apply_failure(
    request: Request,
    *,
    endpoint: str,
    timeout_delay_ms: int,
) -> tuple[MockFailure | None, Response | None]:
    values = _failure_values(request)
    if not values:
        return None, None
    if len(values) != 1 or values[0] not in _FAILURES:
        return None, _safe_json_response(400, "mock.failure.invalid")
    failure = cast("MockFailure", values[0])
    if failure == "rate_limit":
        return "rate_limit", _safe_json_response(429, "mock.rate_limited")
    if failure == "upstream_error":
        return "upstream_error", _safe_json_response(500, "mock.upstream_error")
    if failure == "timeout":
        await asyncio.sleep(timeout_delay_ms / 1000)
        return "timeout", None
    if failure == "invalid_json":
        return "invalid_json", Response(
            content=b'{"broken"',
            status_code=200,
            media_type="application/json",
        )
    if endpoint != "embeddings":
        return None, _safe_json_response(400, "mock.failure.unsupported")
    return "dimension_mismatch", None


def _log(endpoint: str, result: str, started: float) -> None:
    _LOGGER.info(
        "mock_model_operation_completed",
        extra={
            "model_endpoint": endpoint,
            "model_result": result,
            "model_duration_ms": round((perf_counter() - started) * 1000, 3),
        },
    )


def create_mock_model_app(
    *,
    chat_content: str = '{"memories":[]}',
    embedding_dimension: int = 16,
    timeout_delay_ms: int = 100,
) -> FastAPI:
    """Create an isolated deterministic Mock Model ASGI application."""

    if not isinstance(chat_content, str):
        raise TypeError("chat_content must be a string")
    try:
        decoded_content = json.loads(chat_content)
    except json.JSONDecodeError as error:
        raise ValueError("chat_content must contain valid JSON") from error
    canonical_content = json.dumps(
        decoded_content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if (
        isinstance(embedding_dimension, bool)
        or not isinstance(embedding_dimension, int)
        or not 1 <= embedding_dimension <= 4096
    ):
        raise ValueError("embedding_dimension must be between 1 and 4096")
    if (
        isinstance(timeout_delay_ms, bool)
        or not isinstance(timeout_delay_ms, int)
        or not 10 <= timeout_delay_ms <= 5000
    ):
        raise ValueError("timeout_delay_ms must be between 10 and 5000")

    application = FastAPI(
        title="MemScope Mock Model API",
        description="Deterministic no-key model protocol subset for integration tests.",
        version="1",
    )

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, error: RequestValidationError) -> Response:
        del error
        endpoint = "chat" if request.url.path.endswith("chat/completions") else "embeddings"
        started = perf_counter()
        _log(endpoint, "invalid_request", started)
        return _safe_json_response(422, "request.invalid")

    @application.get("/health")
    async def health() -> dict[str, str]:
        started = perf_counter()
        _log("health", "success", started)
        return {"status": "ok"}

    @application.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(
        payload: ChatCompletionRequest,
        request: Request,
        failure_header: FailureHeader = None,
    ) -> ChatCompletionResponse | Response:
        del failure_header
        started = perf_counter()
        failure, response = await _apply_failure(
            request,
            endpoint="chat",
            timeout_delay_ms=timeout_delay_ms,
        )
        if response is not None:
            _log("chat", failure or "invalid_failure", started)
            return response
        result = ChatCompletionResponse(
            id=_request_id(
                "chatcmpl",
                (payload.model, *(f"{item.role}\0{item.content}" for item in payload.messages)),
            ),
            model=payload.model,
            choices=(ChatChoice(index=0, message=ResponseMessage(content=canonical_content)),),
        )
        _log("chat", failure or "success", started)
        return result

    @application.post("/v1/embeddings", response_model=EmbeddingResponse)
    async def embeddings(
        payload: EmbeddingRequest,
        request: Request,
        failure_header: FailureHeader = None,
    ) -> EmbeddingResponse | Response:
        del failure_header
        started = perf_counter()
        failure, response = await _apply_failure(
            request,
            endpoint="embeddings",
            timeout_delay_ms=timeout_delay_ms,
        )
        if response is not None:
            _log("embeddings", failure or "invalid_failure", started)
            return response
        inputs = [payload.input] if isinstance(payload.input, str) else payload.input
        dimension = embedding_dimension + (1 if failure == "dimension_mismatch" else 0)
        result = EmbeddingResponse(
            data=tuple(
                EmbeddingItem(
                    index=index,
                    embedding=deterministic_embedding(item, dimension),
                )
                for index, item in enumerate(inputs)
            ),
            model=payload.model,
        )
        _log("embeddings", failure or "success", started)
        return result

    return application

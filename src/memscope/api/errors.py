"""Sanitized HTTP error mapping and request completion logging."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from memscope.api.auth import AuthenticationError
from memscope.api.models import ErrorBody, ErrorResponse
from memscope.errors import MemScopeError
from memscope.logging_config import LOGGER_NAME
from memscope.operations import ServiceUnavailableError

_CONTEST_PATHS = frozenset({"/health", "/add", "/search"})
_logger = logging.getLogger(LOGGER_NAME)


def _safe_path(request: Request) -> str:
    path = request.url.path
    return path if path in _CONTEST_PATHS else "<unmatched>"


def _response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
    headers: dict[str, str] | None = None,
    exception: BaseException | None = None,
) -> JSONResponse:
    log_extra = {
        "http_method": request.method,
        "http_path": _safe_path(request),
        "status_code": status_code,
        "error_code": code,
        "retryable": retryable,
    }
    _logger.log(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "http_request_failed",
        extra=log_extra,
        exc_info=exception,
    )
    payload = ErrorResponse(
        error=ErrorBody(code=code, message=message, retryable=retryable)
    ).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


def install_error_handlers(application: FastAPI) -> None:
    """Install one centralized set of sanitized exception handlers."""

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, error: RequestValidationError) -> Response:
        del error
        return _response(
            request=request,
            status_code=422,
            code="request.invalid",
            message="Request validation failed",
            retryable=False,
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, error: StarletteHTTPException) -> Response:
        mapping = {
            404: ("http.not_found", "Resource not found"),
            405: ("http.method_not_allowed", "Method not allowed"),
        }
        code, message = mapping.get(error.status_code, ("http.error", "HTTP request failed"))
        return _response(
            request=request,
            status_code=error.status_code,
            code=code,
            message=message,
            retryable=False,
        )

    @application.exception_handler(MemScopeError)
    async def handle_memscope(request: Request, error: MemScopeError) -> Response:
        if isinstance(error, AuthenticationError):
            status_code = 401
            headers = {"WWW-Authenticate": "Bearer"}
        elif isinstance(error, ServiceUnavailableError):
            status_code = 503
            headers = None
        else:
            status_code = 500
            headers = None
        return _response(
            request=request,
            status_code=status_code,
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            headers=headers,
            exception=error if status_code >= 500 else None,
        )

    @application.exception_handler(Exception)
    async def handle_unknown(request: Request, error: Exception) -> Response:
        return _response(
            request=request,
            status_code=500,
            code="internal.error",
            message="Internal server error",
            retryable=False,
            exception=error,
        )


def install_request_logging(application: FastAPI) -> None:
    """Log bounded HTTP metadata for contest paths without request content."""

    @application.middleware("http")
    async def log_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            if request.url.path in _CONTEST_PATHS:
                _logger.info(
                    "http_request_completed",
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "status_code": status_code,
                        "total_duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                )

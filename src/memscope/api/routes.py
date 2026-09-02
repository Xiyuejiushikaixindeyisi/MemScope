"""FastAPI routes adapting the contest contract to application operations."""

import logging
from typing import Any

from fastapi import APIRouter, Request

from memscope.api.auth import authenticate
from memscope.api.models import (
    AddRequest,
    AddResponse,
    ErrorResponse,
    EvidenceResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
)
from memscope.logging_config import LOGGER_NAME
from memscope.operations import (
    AddCommand,
    ContestOperations,
    MemoryEvidence,
    MemoryMessage,
    SearchQuery,
    ServiceUnavailableError,
)
from memscope.settings import AppSettings

_logger = logging.getLogger(LOGGER_NAME)


def _error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    return {
        status_code: {"model": ErrorResponse, "description": "Sanitized error response"}
        for status_code in status_codes
    }


def _to_evidence_response(evidence: MemoryEvidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=evidence.id,
        content=evidence.content,
        score=evidence.score,
        created_at=evidence.created_at,
    )


def create_contest_router(*, settings: AppSettings, operations: ContestOperations) -> APIRouter:
    """Create the public contest router with explicit dependencies."""

    router = APIRouter()

    @router.get(
        "/health",
        response_model=HealthResponse,
        responses=_error_responses(503),
    )
    async def health() -> HealthResponse:
        try:
            ready = await operations.is_ready()
        except Exception as error:
            raise ServiceUnavailableError() from error
        if not ready:
            raise ServiceUnavailableError()
        return HealthResponse()

    @router.post(
        "/add",
        response_model=AddResponse,
        responses=_error_responses(401, 422, 500, 503),
    )
    async def add(payload: AddRequest, request: Request) -> AddResponse:
        authenticate(request.headers, settings)
        command = AddCommand(
            request_id=payload.request_id,
            user_id=payload.user_id,
            session_id=payload.session_id,
            messages=tuple(
                MemoryMessage(
                    role=message.role,
                    content=message.content,
                    timestamp=message.timestamp,
                )
                for message in payload.messages
            ),
        )
        await operations.add(command)
        return AddResponse(
            request_id=payload.request_id,
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

    @router.post(
        "/search",
        response_model=SearchResponse,
        response_model_exclude_none=True,
        responses=_error_responses(401, 422, 500, 503),
    )
    async def search(payload: SearchRequest, request: Request) -> SearchResponse:
        authenticate(request.headers, settings)
        query = SearchQuery(
            query=payload.query,
            user_id=payload.user_id,
            top_k=payload.top_k,
            options=tuple(payload.options) if payload.options is not None else None,
        )
        evidence = await operations.search(query)
        if len(evidence) > payload.top_k:
            _logger.warning("search_result_truncated")
        return SearchResponse(
            data=tuple(_to_evidence_response(item) for item in evidence[: payload.top_k])
        )

    return router

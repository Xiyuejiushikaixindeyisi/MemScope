"""ContestOperations implementation composing Raw Store and Memory Gateway."""

import asyncio
import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Any

from memscope.errors import MemScopeError
from memscope.logging_config import LOGGER_NAME
from memscope.memory_gateway.models import GatewayAdd, GatewayMessage, GatewaySearch
from memscope.memory_gateway.protocol import MemoryGateway
from memscope.operations import (
    AddCommand,
    MemoryEvidence,
    RequestConflictError,
    SearchQuery,
)
from memscope.raw_store.errors import IdempotencyConflictError
from memscope.raw_store.identity import cube_id_for_user, message_id_for_position
from memscope.raw_store.models import AddDisposition, PreparedAdd, StoredAddResponse
from memscope.raw_store.protocol import RawStore

_LOGGER = logging.getLogger(LOGGER_NAME)


class MemoryOperationInvariantError(MemScopeError):
    """A composed dependency violated its accepted application contract."""

    def __init__(self) -> None:
        super().__init__(
            code="application.invariant_failed",
            message="Memory operation invariant failed",
            retryable=False,
        )


class MemoryOperations:
    """Production-shaped orchestration usable with Fake and future real Gateway implementations."""

    def __init__(self, *, raw_store: RawStore, gateway: MemoryGateway) -> None:
        self._raw_store = raw_store
        self._gateway = gateway

    async def is_ready(self) -> bool:
        started = perf_counter()
        results = await asyncio.gather(
            self._raw_store.is_ready(),
            self._gateway.is_ready(),
            return_exceptions=True,
        )
        ready = all(result is True for result in results)
        self._log("readiness", "success" if ready else "unavailable", started)
        return ready

    async def add(self, command: AddCommand) -> None:
        started = perf_counter()
        try:
            prepared = await self._raw_store.prepare_add(command)
        except IdempotencyConflictError as error:
            conflict = RequestConflictError()
            self._log("add", "conflict", started, conflict)
            raise conflict from error

        if prepared.disposition is AddDisposition.COMPLETED:
            self._validate_completed(command, prepared)
            self._log("add", "completed", started)
            return

        request = GatewayAdd(
            request_id=command.request_id,
            payload_sha256=prepared.payload_sha256,
            user_id=command.user_id,
            session_id=command.session_id,
            cube_id=prepared.cube.cube_id,
            messages=tuple(
                GatewayMessage(
                    message_id=message_id_for_position(command.request_id, position),
                    request_position=position,
                    role=message.role,
                    content=message.content,
                    timestamp_ms=message.timestamp,
                )
                for position, message in enumerate(command.messages)
            ),
        )
        try:
            await self._gateway.add(request)
            response = StoredAddResponse(
                success=True,
                request_id=command.request_id,
                user_id=command.user_id,
                session_id=command.session_id,
            )
            await self._raw_store.complete_add(
                command.request_id,
                prepared.payload_sha256,
                response,
            )
        except MemScopeError as error:
            self._log("add", "failed", started, error)
            raise
        self._log("add", prepared.disposition.value, started)

    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]:
        started = perf_counter()
        cube_id = cube_id_for_user(query.user_id)
        try:
            gateway_evidence = await self._gateway.search(
                GatewaySearch(
                    query=query.query,
                    user_id=query.user_id,
                    cube_id=cube_id,
                    top_k=query.top_k,
                    options=query.options,
                )
            )
        except MemScopeError as error:
            self._log("search", "failed", started, error)
            raise
        result = tuple(
            MemoryEvidence(
                id=evidence.id,
                content=evidence.content,
                score=float(evidence.score) if evidence.score is not None else None,
                created_at=evidence.created_at,
            )
            for evidence in gateway_evidence
            if evidence.user_id == query.user_id and evidence.cube_id == cube_id
        )[: query.top_k]
        self._log(
            "search",
            "filtered" if len(result) != len(gateway_evidence) else "success",
            started,
        )
        return result

    @staticmethod
    def _validate_completed(command: AddCommand, prepared: PreparedAdd) -> None:
        response = prepared.response
        if (
            response is None
            or response.success is not True
            or response.request_id != command.request_id
            or response.user_id != command.user_id
            or response.session_id != command.session_id
        ):
            raise MemoryOperationInvariantError()

    @staticmethod
    def _log(
        operation: str,
        result: str,
        started: float,
        error: MemScopeError | None = None,
    ) -> None:
        extra: dict[str, Any] = {
            "component_operation": operation,
            "component_result": result,
            "component_duration_ms": round((perf_counter() - started) * 1000, 3),
        }
        if error is not None:
            extra["error_code"] = error.code
            extra["retryable"] = error.retryable
        _LOGGER.info("memory_operation_completed", extra=extra)

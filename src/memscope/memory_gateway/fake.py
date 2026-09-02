"""Deterministic, in-process Fake implementation of MemoryGateway."""

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any

from memscope.errors import MemScopeError
from memscope.logging_config import LOGGER_NAME
from memscope.memory_gateway.errors import (
    GatewayConflictError,
    GatewayProtocolError,
    GatewayUnavailableError,
)
from memscope.memory_gateway.models import (
    GatewayAdd,
    GatewayEvidence,
    GatewayMessage,
    GatewaySearch,
)

_LOGGER = logging.getLogger(LOGGER_NAME)
_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


class GatewayOperation(StrEnum):
    """Operations available to deterministic test fault injectors."""

    READINESS = "readiness"
    ADD = "add"
    SEARCH = "search"


FaultInjector = Callable[[GatewayOperation], None]


@dataclass(frozen=True, slots=True)
class _StoredEvidence:
    message: GatewayMessage
    user_id: str
    cube_id: str
    sequence: int


class FakeMemoryGateway:
    """Non-durable Gateway Fake for contract and orchestration tests only."""

    def __init__(self, *, fault_injector: FaultInjector | None = None) -> None:
        self._fault_injector = fault_injector
        self._lock = asyncio.Lock()
        self._closed = False
        self._requests: dict[str, GatewayAdd] = {}
        self._messages: dict[str, _StoredEvidence] = {}
        self._evidence: list[_StoredEvidence] = []
        self._user_cubes: dict[str, str] = {}
        self._cube_users: dict[str, str] = {}

    async def is_ready(self) -> bool:
        started = perf_counter()
        try:
            self._inject(GatewayOperation.READINESS)
            async with self._lock:
                ready = not self._closed
        except MemScopeError as error:
            self._log("readiness", "failed", started, error)
            raise
        self._log("readiness", "success" if ready else "unavailable", started)
        return ready

    async def add(self, request: GatewayAdd) -> None:
        started = perf_counter()
        try:
            self._inject(GatewayOperation.ADD)
            async with self._lock:
                self._ensure_open()
                existing = self._requests.get(request.request_id)
                if existing is not None:
                    if existing != request:
                        raise GatewayConflictError()
                    self._log("add", "completed", started)
                    return

                if self._user_cubes.get(request.user_id, request.cube_id) != request.cube_id:
                    raise GatewayConflictError()
                if self._cube_users.get(request.cube_id, request.user_id) != request.user_id:
                    raise GatewayConflictError()
                for message in request.messages:
                    stored = self._messages.get(message.message_id)
                    if stored is not None and (
                        stored.message != message
                        or stored.user_id != request.user_id
                        or stored.cube_id != request.cube_id
                    ):
                        raise GatewayConflictError()

                self._user_cubes[request.user_id] = request.cube_id
                self._cube_users[request.cube_id] = request.user_id
                self._requests[request.request_id] = request
                for message in request.messages:
                    if message.message_id in self._messages:
                        continue
                    stored = _StoredEvidence(
                        message=message,
                        user_id=request.user_id,
                        cube_id=request.cube_id,
                        sequence=len(self._evidence),
                    )
                    self._messages[message.message_id] = stored
                    self._evidence.append(stored)
        except MemScopeError as error:
            self._log("add", "failed", started, error)
            raise
        self._log("add", "success", started)

    async def search(self, request: GatewaySearch) -> Sequence[GatewayEvidence]:
        started = perf_counter()
        try:
            self._inject(GatewayOperation.SEARCH)
            async with self._lock:
                self._ensure_open()
                candidates = tuple(
                    evidence
                    for evidence in self._evidence
                    if evidence.user_id == request.user_id and evidence.cube_id == request.cube_id
                )
        except MemScopeError as error:
            self._log("search", "failed", started, error)
            raise

        query_tokens = frozenset(_TOKEN_PATTERN.findall(request.query.casefold()))
        if not query_tokens:
            self._log("search", "success", started)
            return ()
        scored: list[tuple[float, _StoredEvidence]] = []
        for evidence in candidates:
            content_tokens = frozenset(_TOKEN_PATTERN.findall(evidence.message.content.casefold()))
            score = len(query_tokens & content_tokens) / len(query_tokens)
            if score > 0:
                scored.append((score, evidence))
        scored.sort(key=lambda item: (-item[0], item[1].sequence))
        try:
            result = tuple(
                GatewayEvidence(
                    id=evidence.message.message_id,
                    content=evidence.message.content,
                    user_id=evidence.user_id,
                    cube_id=evidence.cube_id,
                    score=score,
                    created_at=self._created_at(evidence.message.timestamp_ms),
                )
                for score, evidence in scored[: request.top_k]
            )
        except (OSError, OverflowError, ValueError) as error:
            protocol_error = GatewayProtocolError()
            self._log("search", "unavailable", started, protocol_error)
            raise protocol_error from error
        self._log("search", "success", started)
        return result

    async def close(self) -> None:
        started = perf_counter()
        async with self._lock:
            self._closed = True
        self._log("close", "success", started)

    def _inject(self, operation: GatewayOperation) -> None:
        if self._fault_injector is not None:
            self._fault_injector(operation)

    def _ensure_open(self) -> None:
        if self._closed:
            raise GatewayUnavailableError()

    @staticmethod
    def _created_at(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

    @staticmethod
    def _log(
        operation: str,
        result: str,
        started: float,
        error: BaseException | None = None,
    ) -> None:
        extra: dict[str, Any] = {
            "component_operation": operation,
            "component_result": result,
            "gateway_duration_ms": round((perf_counter() - started) * 1000, 3),
        }
        if isinstance(error, MemScopeError):
            extra["error_code"] = error.code
            extra["retryable"] = error.retryable
        _LOGGER.info("memory_gateway_operation_completed", extra=extra)

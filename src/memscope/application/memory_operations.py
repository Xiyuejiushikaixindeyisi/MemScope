"""ContestOperations implementation composing Raw Store and Memory Gateway."""

import asyncio
import logging
from collections.abc import Sequence
from math import isfinite
from time import perf_counter
from typing import Any, Protocol

from memscope.application.user_lanes import UserLanes
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


class MonotonicClock(Protocol):
    """Small clock seam for deterministic deadline tests."""

    def __call__(self) -> float: ...


class AddTimeoutError(MemScopeError):
    """The complete Add operation exhausted its accepted time budget."""

    def __init__(self) -> None:
        super().__init__(
            code="add.timeout",
            message="Add operation timed out",
            retryable=True,
        )


class SearchTimeoutError(MemScopeError):
    """The complete Search operation exhausted its accepted time budget."""

    def __init__(self) -> None:
        super().__init__(
            code="search.timeout",
            message="Search operation timed out",
            retryable=True,
        )


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

    def __init__(
        self,
        *,
        raw_store: RawStore,
        gateway: MemoryGateway,
        add_deadline_seconds: float = 115.0,
        add_warn_seconds: float = 105.0,
        search_deadline_seconds: float = 55.0,
        search_warn_seconds: float = 50.0,
        gateway_reserve_seconds: float = 5.0,
        clock: MonotonicClock = perf_counter,
        user_lanes: UserLanes | None = None,
    ) -> None:
        if not 0 < add_warn_seconds < add_deadline_seconds < 120:
            raise ValueError("Add timing must satisfy 0 < warning < deadline < 120")
        if not 0 < gateway_reserve_seconds < add_deadline_seconds:
            raise ValueError("Gateway reserve must be positive and below the Add deadline")
        search_timings = (search_warn_seconds, search_deadline_seconds)
        if (
            any(
                isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value)
                for value in search_timings
            )
            or not 0 < search_warn_seconds < search_deadline_seconds < 60
        ):
            raise ValueError("Search timing must satisfy 0 < warning < deadline < 60")
        self._raw_store = raw_store
        self._gateway = gateway
        self._add_deadline_seconds = add_deadline_seconds
        self._add_warn_seconds = add_warn_seconds
        self._gateway_reserve_seconds = gateway_reserve_seconds
        self._search_deadline_seconds = search_deadline_seconds
        self._search_warn_seconds = search_warn_seconds
        self._clock = clock
        self._user_lanes = user_lanes or UserLanes()

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
        deadline = self._clock() + self._add_deadline_seconds
        loop = asyncio.get_running_loop()
        warning = loop.call_later(self._add_warn_seconds, self._log_warning, "add")
        try:
            async with asyncio.timeout(self._add_deadline_seconds):
                async with self._user_lanes.acquire(command.user_id):
                    await self._add_in_lane(command, deadline=deadline, started=started)
        except TimeoutError as error:
            timeout = AddTimeoutError()
            self._log("add", "timeout", started, timeout)
            raise timeout from error
        finally:
            warning.cancel()

    async def _add_in_lane(
        self,
        command: AddCommand,
        *,
        deadline: float,
        started: float,
    ) -> None:
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
            session_start_position=prepared.session_start_position,
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
            remaining = deadline - self._clock() - self._gateway_reserve_seconds
            if remaining <= 0:
                raise AddTimeoutError()
            await self._gateway.add(request, timeout_seconds=remaining)
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

    @staticmethod
    def _log_warning(operation: str) -> None:
        _LOGGER.warning(
            "memory_operation_slow",
            extra={"component_operation": operation, "component_result": "warning"},
        )

    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]:
        started = perf_counter()
        deadline = self._clock() + self._search_deadline_seconds
        cube_id = cube_id_for_user(query.user_id)
        loop = asyncio.get_running_loop()
        warning = loop.call_later(self._search_warn_seconds, self._log_warning, "search")
        try:
            async with asyncio.timeout(self._search_deadline_seconds):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError
                gateway_evidence = await self._gateway.search(
                    GatewaySearch(
                        query=query.query,
                        user_id=query.user_id,
                        cube_id=cube_id,
                        top_k=query.top_k,
                        options=query.options,
                    ),
                    timeout_seconds=remaining,
                )
                result = tuple(
                    MemoryEvidence(
                        id=evidence.id,
                        content=evidence.content,
                        score=(float(evidence.score) if evidence.score is not None else None),
                        created_at=evidence.created_at,
                    )
                    for evidence in gateway_evidence
                    if evidence.user_id == query.user_id and evidence.cube_id == cube_id
                )[: query.top_k]
                if deadline - self._clock() <= 0:
                    raise TimeoutError
        except TimeoutError as error:
            timeout = SearchTimeoutError()
            self._log("search", "timeout", started, timeout)
            raise timeout from error
        except MemScopeError as error:
            self._log("search", "failed", started, error)
            raise
        finally:
            warning.cancel()
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

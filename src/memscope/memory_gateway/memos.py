"""Real asynchronous Gateway for the pinned MemOS Product API."""

import json
import math
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from memscope.memory_gateway.errors import (
    GatewayProtocolError,
    GatewayRateLimitedError,
    GatewayTimeoutError,
    GatewayUnavailableError,
)
from memscope.memory_gateway.memos_models import (
    AddResult,
    ProviderMemory,
    envelope_data,
    memories_from_filtered_get,
    parse_add_results,
)
from memscope.memory_gateway.models import GatewayAdd, GatewayEvidence, GatewaySearch
from memscope.memory_gateway.receipt_store import GatewayReceiptStore, ReceiptStatus


class MemosMemoryGateway:
    """Synchronous Add-only MemOS adapter with durable replay receipts."""

    def __init__(
        self,
        *,
        base_url: str,
        receipt_store: GatewayReceiptStore,
        connect_timeout_seconds: float,
        response_max_bytes: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must not be blank")
        if (
            isinstance(connect_timeout_seconds, bool)
            or not isinstance(connect_timeout_seconds, int | float)
            or not math.isfinite(connect_timeout_seconds)
            or connect_timeout_seconds <= 0
        ):
            raise ValueError("connect timeout must be finite and positive")
        if (
            isinstance(response_max_bytes, bool)
            or not isinstance(response_max_bytes, int)
            or response_max_bytes <= 0
        ):
            raise ValueError("response_max_bytes must be positive")
        self._receipt_store = receipt_store
        self._connect_timeout_seconds = connect_timeout_seconds
        self._response_max_bytes = response_max_bytes
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"))
        self._closed = False

    async def verify_upstream(self, *, timeout_seconds: float) -> None:
        """Verify only MemOS process health during application startup."""

        body = await self._post_json("/health", None, timeout_seconds=timeout_seconds, method="GET")
        if not isinstance(body, dict) or body.get("status") != "healthy":
            raise GatewayProtocolError()

    async def is_ready(self) -> bool:
        """B05 remains publicly unready until the B06 Search path exists."""

        return False

    async def add(self, request: GatewayAdd, *, timeout_seconds: float) -> None:
        """Perform or reconcile exactly one synchronous Product Add."""

        self._ensure_open()
        self._validate_timeout(timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        receipt = await self._receipt_store.prepare(request.request_id, request.payload_sha256)
        if receipt.status is ReceiptStatus.COMPLETED:
            return

        reconciled = await self._reconcile(request, deadline=deadline)
        if reconciled is not None:
            await self._receipt_store.complete(
                request.request_id,
                request.payload_sha256,
                reconciled,
            )
            return

        payload = self._add_payload(request, deadline=deadline)
        body = await self._post_json(
            "/product/add",
            payload,
            timeout_seconds=self._remaining(deadline),
        )
        results = parse_add_results(envelope_data(body), cube_id=request.cube_id)
        if results:
            readback = await self._readback_result_set(
                request,
                deadline=deadline,
            )
            ordered_ids = self._validate_committed(request, readback, expected=results)
        else:
            ordered_ids = ()
        await self._receipt_store.complete(
            request.request_id,
            request.payload_sha256,
            ordered_ids,
        )

    async def search(self, request: GatewaySearch) -> tuple[GatewayEvidence, ...]:
        """Search is deliberately unavailable until B06."""

        del request
        raise GatewayUnavailableError()

    async def close(self) -> None:
        """Idempotently close owned resources."""

        if self._closed:
            return
        self._closed = True
        await self._client.aclose()
        await self._receipt_store.close()

    async def _reconcile(
        self,
        request: GatewayAdd,
        *,
        deadline: float,
    ) -> tuple[str, ...] | None:
        memories = await self._readback_result_set(request, deadline=deadline)
        if not memories:
            return None
        return self._validate_committed(request, memories, expected=None)

    async def _readback_result_set(
        self,
        request: GatewayAdd,
        *,
        deadline: float,
    ) -> tuple[ProviderMemory, ...]:
        """Read one tenant-scoped Add result set by its durable payload marker."""

        payload = {
            "mem_cube_id": request.cube_id,
            "user_id": request.user_id,
            "include_preference": False,
            "include_tool_memory": False,
            "include_skill_memory": False,
            "filter": {"memscope_payload_sha256": request.payload_sha256},
        }
        body = await self._post_json(
            "/product/get_memory",
            payload,
            timeout_seconds=self._remaining(deadline),
        )
        return memories_from_filtered_get(envelope_data(body), cube_id=request.cube_id)

    @staticmethod
    def _validate_committed(
        request: GatewayAdd,
        memories: tuple[ProviderMemory, ...],
        *,
        expected: tuple[AddResult, ...] | None,
    ) -> tuple[str, ...]:
        if not memories:
            raise GatewayProtocolError()
        counts = {item.result_count for item in memories}
        if len(counts) != 1:
            raise GatewayProtocolError()
        count = next(iter(counts))
        if count != len(memories):
            raise GatewayProtocolError()
        by_index = {item.result_index: item for item in memories}
        if len(by_index) != len(memories) or set(by_index) != set(range(count)):
            raise GatewayProtocolError()
        ordered = tuple(by_index[index] for index in range(count))
        for item in ordered:
            if (
                item.user_id != request.user_id
                or item.session_id != request.session_id
                or item.cube_id != request.cube_id
                or item.payload_sha256 != request.payload_sha256
            ):
                raise GatewayProtocolError()
        if expected is not None:
            if len(expected) != count:
                raise GatewayProtocolError()
            for result, memory in zip(expected, ordered, strict=True):
                if (
                    result.memory_id != memory.memory_id
                    or result.memory != memory.memory
                    or result.memory_type != memory.memory_type
                ):
                    raise GatewayProtocolError()
        return tuple(item.memory_id for item in ordered)

    @staticmethod
    def _add_payload(request: GatewayAdd, *, deadline: float) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            encoded: dict[str, Any] = {
                "role": message.role,
                "content": message.content,
                "message_id": message.message_id,
            }
            if message.timestamp_ms is not None:
                encoded["chat_time"] = MemosMemoryGateway._chat_time(message.timestamp_ms)
            messages.append(encoded)
        return {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "writable_cube_ids": [request.cube_id],
            "async_mode": "sync",
            "mode": "fine",
            "messages": messages,
            "info": {
                "memscope_add_schema": "v1",
                "memscope_payload_sha256": request.payload_sha256,
                "memscope_session_start_position": request.session_start_position,
                "memscope_source_count": len(request.messages),
                "memscope_deadline_unix_ms": int(
                    (time.time() + max(deadline - time.monotonic(), 0)) * 1000
                ),
            },
        }

    @staticmethod
    def _chat_time(timestamp_ms: int) -> str:
        try:
            value = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return f"unix_ms:{timestamp_ms}"
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    async def _post_json(
        self,
        path: str,
        payload: Any,
        *,
        timeout_seconds: float,
        method: str = "POST",
    ) -> Any:
        self._validate_timeout(timeout_seconds)
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(self._connect_timeout_seconds, timeout_seconds),
        )
        try:
            if method == "GET":
                response = await self._client.get(path, timeout=timeout)
            else:
                response = await self._client.post(path, json=payload, timeout=timeout)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise GatewayTimeoutError() from error
        except (httpx.HTTPError, OSError) as error:
            raise GatewayUnavailableError() from error
        if response.status_code == 429:
            raise GatewayRateLimitedError()
        if response.status_code in {408, 504}:
            raise GatewayTimeoutError()
        if response.status_code >= 500:
            raise GatewayUnavailableError()
        if response.status_code != 200:
            raise GatewayProtocolError()
        content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0].strip()
        if content_type != "application/json" or len(response.content) > self._response_max_bytes:
            raise GatewayProtocolError()
        try:
            return json.loads(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GatewayProtocolError() from error

    @staticmethod
    def _validate_timeout(timeout_seconds: float) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GatewayTimeoutError()
        return remaining

    def _ensure_open(self) -> None:
        if self._closed:
            raise GatewayUnavailableError()

"""Cancellation-safe, process-local ordered lanes keyed by logical user."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass(slots=True)
class _Lane:
    lock: asyncio.Lock
    references: int = 0


class UserLanes:
    """Serialize work for one key without retaining inactive locks forever."""

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._lanes: dict[str, _Lane] = {}

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        """Acquire one keyed lane and release its bookkeeping on every exit path."""

        if not isinstance(key, str):
            raise TypeError("lane key must be a string")
        if not key.strip():
            raise ValueError("lane key must not be blank")
        async with self._guard:
            lane = self._lanes.setdefault(key, _Lane(asyncio.Lock()))
            lane.references += 1

        acquired = False
        try:
            await lane.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                lane.lock.release()
            async with self._guard:
                lane.references -= 1
                if lane.references == 0:
                    if lane.lock.locked():  # pragma: no cover - defensive invariant
                        raise RuntimeError("unreferenced lane remains locked")
                    self._lanes.pop(key, None)

    async def active_lane_count(self) -> int:
        """Expose bounded state for tests and diagnostics without revealing keys."""

        async with self._guard:
            return len(self._lanes)

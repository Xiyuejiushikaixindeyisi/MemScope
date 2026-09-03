"""Concurrency and cancellation tests for process-local user lanes."""

import asyncio

import pytest

from memscope.application.user_lanes import UserLanes


@pytest.mark.parametrize("key", [None, 1])
async def test_lane_rejects_non_string_keys(key: object) -> None:
    lanes = UserLanes()
    with pytest.raises(TypeError):
        async with lanes.acquire(key):  # type: ignore[arg-type]
            raise AssertionError("unreachable")


@pytest.mark.parametrize("key", ["", "   "])
async def test_lane_rejects_blank_keys(key: str) -> None:
    lanes = UserLanes()
    with pytest.raises(ValueError):
        async with lanes.acquire(key):
            raise AssertionError("unreachable")


async def test_same_key_is_ordered_and_inactive_lane_is_removed() -> None:
    lanes = UserLanes()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first() -> None:
        async with lanes.acquire("user-1"):
            order.append("first-enter")
            first_entered.set()
            await release_first.wait()
            order.append("first-exit")

    async def second() -> None:
        await first_entered.wait()
        async with lanes.acquire("user-1"):
            order.append("second-enter")

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await first_entered.wait()
    await asyncio.sleep(0)
    assert await lanes.active_lane_count() == 1
    assert order == ["first-enter"]
    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert order == ["first-enter", "first-exit", "second-enter"]
    assert await lanes.active_lane_count() == 0


async def test_different_keys_can_run_concurrently() -> None:
    lanes = UserLanes()
    both_entered = asyncio.Event()
    entered = 0

    async def worker(key: str) -> None:
        nonlocal entered
        async with lanes.acquire(key):
            entered += 1
            if entered == 2:
                both_entered.set()
            await both_entered.wait()

    await asyncio.wait_for(
        asyncio.gather(worker("user-1"), worker("user-2")),
        timeout=1,
    )
    assert await lanes.active_lane_count() == 0


async def test_cancelled_waiter_does_not_leak_lane_reference() -> None:
    lanes = UserLanes()
    release = asyncio.Event()
    holder_entered = asyncio.Event()

    async def holder() -> None:
        async with lanes.acquire("user-1"):
            holder_entered.set()
            await release.wait()

    async def waiter() -> None:
        async with lanes.acquire("user-1"):
            raise AssertionError("cancelled waiter entered the lane")

    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task
    assert await lanes.active_lane_count() == 1

    release.set()
    await holder_task
    assert await lanes.active_lane_count() == 0

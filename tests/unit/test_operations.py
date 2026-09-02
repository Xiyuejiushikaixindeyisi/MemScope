"""Tests for the framework-independent application port defaults."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from memscope.operations import (
    AddCommand,
    MemoryEvidence,
    MemoryMessage,
    SearchQuery,
    ServiceUnavailableError,
    UnavailableContestOperations,
)


def test_operation_models_are_frozen() -> None:
    message = MemoryMessage(role="user", content="fact")

    with pytest.raises(FrozenInstanceError):
        message.role = "assistant"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "arguments"),
    [
        (MemoryMessage, {"role": " ", "content": "fact"}),
        (MemoryMessage, {"role": "user", "content": ""}),
        (MemoryMessage, {"role": "user", "content": "fact", "timestamp": True}),
        (
            AddCommand,
            {"request_id": "", "user_id": "u", "session_id": "s", "messages": ()},
        ),
        (
            AddCommand,
            {"request_id": "r", "user_id": " ", "session_id": "s", "messages": ()},
        ),
        (
            AddCommand,
            {"request_id": "r", "user_id": "u", "session_id": " ", "messages": ()},
        ),
        (
            AddCommand,
            {"request_id": "r", "user_id": "u", "session_id": "s", "messages": ()},
        ),
        (SearchQuery, {"query": "", "user_id": "u", "top_k": 1}),
        (SearchQuery, {"query": "q", "user_id": " ", "top_k": 1}),
        (SearchQuery, {"query": "q", "user_id": "u", "top_k": True}),
        (SearchQuery, {"query": "q", "user_id": "u", "top_k": 101}),
        (SearchQuery, {"query": "q", "user_id": "u", "top_k": 1, "options": (1,)}),
        (MemoryEvidence, {"id": "", "content": "fact"}),
        (MemoryEvidence, {"id": "m", "content": " "}),
        (MemoryEvidence, {"id": "m", "content": "fact", "score": float("inf")}),
        (
            MemoryEvidence,
            {"id": "m", "content": "fact", "created_at": datetime(2026, 1, 1)},
        ),
    ],
)
def test_operation_models_reject_invalid_internal_values(
    factory: type[Any], arguments: dict[str, Any]
) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory(**arguments)


@pytest.mark.asyncio
async def test_unavailable_operations_never_claim_success() -> None:
    operations = UnavailableContestOperations()
    add = AddCommand("r", "u", "s", (MemoryMessage("user", "fact"),))
    search = SearchQuery("query", "u", 100)

    assert await operations.is_ready() is False
    with pytest.raises(ServiceUnavailableError):
        await operations.add(add)
    with pytest.raises(ServiceUnavailableError):
        await operations.search(search)

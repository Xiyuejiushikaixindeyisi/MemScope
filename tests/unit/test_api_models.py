"""Tests for strict public contest request and response models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memscope.api.models import (
    AddRequest,
    AddResponse,
    EvidenceResponse,
    SearchRequest,
    SearchResponse,
)


def test_add_request_preserves_values_order_and_ignores_unknown_fields() -> None:
    request = AddRequest.model_validate(
        {
            "request_id": " request-1 ",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [
                {"role": "system", "content": " first ", "unknown": "ignored"},
                {"role": "custom", "content": "second", "timestamp": 123},
            ],
            "metadata": {"ignored": True},
        }
    )

    assert request.request_id == " request-1 "
    assert tuple(message.role for message in request.messages) == ("system", "custom")
    assert request.messages[0].content == " first "
    assert request.messages[1].timestamp == 123
    assert "metadata" not in request.model_dump()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"request_id": "", "user_id": "u", "session_id": "s", "messages": [{}]},
        {"request_id": "r", "user_id": " ", "session_id": "s", "messages": []},
        {
            "request_id": "r",
            "user_id": "u",
            "session_id": "s",
            "messages": [{"role": "user", "content": " "}],
        },
        {
            "request_id": 1,
            "user_id": "u",
            "session_id": "s",
            "messages": [{"role": "user", "content": "content"}],
        },
        {
            "request_id": "r",
            "user_id": "u",
            "session_id": "s",
            "messages": [{"role": "user", "content": "content", "timestamp": True}],
        },
    ],
)
def test_add_request_rejects_invalid_contract(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AddRequest.model_validate(payload)


def test_search_request_preserves_optional_options() -> None:
    missing = SearchRequest(query="q", user_id="u", top_k=100)
    explicit_null = SearchRequest(query="q", user_id="u", top_k=1, options=None)
    options = SearchRequest(query="q", user_id="u", top_k=2, options=["", "B"])

    assert missing.options is None
    assert explicit_null.options is None
    assert options.options == ["", "B"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", " "),
        ("user_id", ""),
        ("top_k", 0),
        ("top_k", 101),
        ("top_k", True),
        ("top_k", "100"),
        ("options", [1]),
    ],
)
def test_search_request_rejects_invalid_contract(field: str, value: object) -> None:
    payload: dict[str, object] = {"query": "q", "user_id": "u", "top_k": 100}
    payload[field] = value

    with pytest.raises(ValidationError):
        SearchRequest.model_validate(payload)


def test_success_responses_have_exact_json_shapes() -> None:
    add = AddResponse(request_id="r", user_id="u", session_id="s")
    search = SearchResponse(data=())

    assert add.model_dump(mode="json") == {
        "success": True,
        "request_id": "r",
        "user_id": "u",
        "session_id": "s",
    }
    assert search.model_dump(mode="json") == {"data": []}


def test_evidence_accepts_finite_score_and_aware_time() -> None:
    created_at = datetime(2026, 7, 1, 12, tzinfo=UTC)

    evidence = EvidenceResponse(id="mem-1", content="fact", score=0.5, created_at=created_at)

    assert evidence.created_at == created_at


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": " "},
        {"content": ""},
        {"score": float("nan")},
        {"score": float("inf")},
        {"created_at": datetime(2026, 7, 1, 12)},
    ],
)
def test_evidence_rejects_invalid_output(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {"id": "mem-1", "content": "fact"}
    payload.update(overrides)

    with pytest.raises(ValidationError):
        EvidenceResponse.model_validate(payload)

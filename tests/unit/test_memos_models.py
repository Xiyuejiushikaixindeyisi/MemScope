"""Fail-closed parsing tests for the pinned MemOS response shapes."""

from copy import deepcopy
from typing import Any

import pytest

from memscope.memory_gateway.errors import GatewayProtocolError
from memscope.memory_gateway.memos_models import (
    envelope_data,
    memories_from_by_ids,
    memories_from_filtered_get,
    parse_add_results,
    parse_provider_memory,
)

ID_1 = "11111111-1111-4111-8111-111111111111"
ID_2 = "22222222-2222-4222-8222-222222222222"


def _add_item(memory_id: str = ID_1) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "memory": "fact",
        "memory_type": "LongTermMemory",
        "cube_id": "cube-1",
    }


def _provider() -> dict[str, Any]:
    return {
        "id": ID_1,
        "memory": "fact",
        "metadata": {
            "user_id": "user-1",
            "session_id": "session-1",
            "memory_type": "LongTermMemory",
            "status": "activated",
            "vector_sync": "success",
            "memscope_cube_id": "cube-1",
            "memscope_payload_sha256": "a" * 64,
            "memscope_result_index": 0,
            "memscope_result_count": 1,
        },
    }


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"code": True, "message": "ok", "data": []},
        {"code": "200", "message": "ok", "data": []},
        {"code": 201, "message": "ok", "data": []},
        {"code": 200, "message": "", "data": []},
        {"code": 200, "message": "ok"},
    ],
)
def test_envelope_rejects_non_exact_success(value: Any) -> None:
    with pytest.raises(GatewayProtocolError):
        envelope_data(value)


def test_envelope_returns_data_without_coercion() -> None:
    data = {"exact": [1]}
    assert envelope_data({"code": 200, "message": "ok", "data": data}) is data


@pytest.mark.parametrize(
    "value",
    [
        {},
        [None],
        [{**_add_item(), "memory_type": "unknown"}],
        [{**_add_item(), "cube_id": "other"}],
        [{**_add_item(), "memory_id": "not-a-uuid"}],
        [{**_add_item(), "memory": "   "}],
        [_add_item(), _add_item()],
    ],
)
def test_add_results_reject_malformed_or_ambiguous_values(value: Any) -> None:
    with pytest.raises(GatewayProtocolError):
        parse_add_results(value, cube_id="cube-1")


def test_add_results_accept_empty_and_distinct_ordered_values() -> None:
    assert parse_add_results([], cube_id="cube-1") == ()
    parsed = parse_add_results([_add_item(ID_1), _add_item(ID_2)], cube_id="cube-1")
    assert [item.memory_id for item in parsed] == [ID_1, ID_2]


@pytest.mark.parametrize(
    ("path", "invalid"),
    [
        (("metadata",), None),
        (("metadata", "memory_type"), "unknown"),
        (("metadata", "status"), "deleted"),
        (("metadata", "vector_sync"), "failed"),
        (("metadata", "memscope_result_index"), True),
        (("metadata", "memscope_result_index"), "0"),
        (("metadata", "memscope_result_index"), -1),
        (("metadata", "memscope_result_index"), 1),
        (("metadata", "memscope_result_count"), True),
        (("metadata", "memscope_result_count"), "1"),
        (("metadata", "memscope_result_count"), 0),
        (("metadata", "memscope_payload_sha256"), "short"),
        (("metadata", "memscope_payload_sha256"), "A" * 64),
        (("id",), "invalid"),
        (("memory",), ""),
        (("metadata", "user_id"), ""),
        (("metadata", "session_id"), None),
        (("metadata", "memscope_cube_id"), " "),
    ],
)
def test_provider_memory_rejects_invalid_required_fields(
    path: tuple[str, ...], invalid: Any
) -> None:
    value = deepcopy(_provider())
    target = value
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = invalid
    with pytest.raises(GatewayProtocolError):
        parse_provider_memory(value)


def test_provider_memory_accepts_resolving_status() -> None:
    value = _provider()
    value["metadata"]["status"] = "resolving"
    assert parse_provider_memory(value).status == "resolving"


@pytest.mark.parametrize("value", [None, {}, {"memories": None}, {"memories": [None]}])
def test_memories_by_ids_requires_exact_list(value: Any) -> None:
    with pytest.raises(GatewayProtocolError):
        memories_from_by_ids(value)


def test_memories_by_ids_parses_order() -> None:
    second = _provider()
    second["id"] = ID_2
    parsed = memories_from_by_ids({"memories": [_provider(), second]})
    assert [item.memory_id for item in parsed] == [
        ID_1,
        ID_2,
    ]


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"text_mem": None},
        {"text_mem": [None]},
        {"text_mem": [{"cube_id": "other", "memories": [], "total_nodes": 0}]},
        {"text_mem": [{"cube_id": "cube-1", "memories": None, "total_nodes": 0}]},
        {"text_mem": [{"cube_id": "cube-1", "memories": [], "total_nodes": True}]},
        {"text_mem": [{"cube_id": "cube-1", "memories": [], "total_nodes": "0"}]},
        {"text_mem": [{"cube_id": "cube-1", "memories": [], "total_nodes": 1}]},
    ],
)
def test_filtered_get_rejects_invalid_group_shape(value: Any) -> None:
    with pytest.raises(GatewayProtocolError):
        memories_from_filtered_get(value, cube_id="cube-1")


def test_filtered_get_flattens_valid_groups() -> None:
    assert (
        memories_from_filtered_get(
            {
                "text_mem": [
                    {"cube_id": "cube-1", "memories": [_provider()], "total_nodes": 1},
                    {"cube_id": "cube-1", "memories": [], "total_nodes": 0},
                ]
            },
            cube_id="cube-1",
        )[0].memory_id
        == ID_1
    )

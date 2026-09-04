"""Strict parsing helpers for the pinned MemOS Product API responses."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any
from uuid import UUID

from memscope.memory_gateway.errors import GatewayProtocolError
from memscope.memory_gateway.models import GatewayEvidence

SUPPORTED_MEMORY_TYPES = frozenset(
    {
        "WorkingMemory",
        "LongTermMemory",
        "UserMemory",
        "OuterMemory",
        "RawFileMemory",
        "ToolSchemaMemory",
        "ToolTrajectoryMemory",
        "SkillMemory",
        "PreferenceMemory",
        "Context",
    }
)

SEARCH_MEMORY_TYPES = frozenset({"WorkingMemory", "LongTermMemory", "UserMemory"})


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GatewayProtocolError()
    return value


def _nonblank(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatewayProtocolError()
    return value


def _uuid(value: Any) -> str:
    rendered = _nonblank(value)
    try:
        UUID(rendered)
    except ValueError as error:
        raise GatewayProtocolError() from error
    return rendered


def envelope_data(value: Any) -> Any:
    """Return data from an exact successful Product API envelope."""

    body = _object(value)
    code = body.get("code")
    if isinstance(code, bool) or not isinstance(code, int) or code != 200:
        raise GatewayProtocolError()
    _nonblank(body.get("message"))
    if "data" not in body:
        raise GatewayProtocolError()
    return body["data"]


@dataclass(frozen=True, slots=True)
class AddResult:
    """One validated Product Add result item."""

    memory_id: str
    memory: str
    memory_type: str
    cube_id: str


def parse_add_results(data: Any, *, cube_id: str) -> tuple[AddResult, ...]:
    """Validate Product Add result list without retaining unknown fields."""

    if not isinstance(data, list):
        raise GatewayProtocolError()
    results: list[AddResult] = []
    for value in data:
        item = _object(value)
        memory_type = _nonblank(item.get("memory_type"))
        if memory_type not in SUPPORTED_MEMORY_TYPES:
            raise GatewayProtocolError()
        actual_cube = _nonblank(item.get("cube_id"))
        if actual_cube != cube_id:
            raise GatewayProtocolError()
        results.append(
            AddResult(
                memory_id=_uuid(item.get("memory_id")),
                memory=_nonblank(item.get("memory")),
                memory_type=memory_type,
                cube_id=actual_cube,
            )
        )
    if len({item.memory_id for item in results}) != len(results):
        raise GatewayProtocolError()
    return tuple(results)


@dataclass(frozen=True, slots=True)
class ProviderMemory:
    """Readback fields required to prove one Add result is committed."""

    memory_id: str
    memory: str
    user_id: str
    session_id: str
    cube_id: str
    memory_type: str
    status: str
    vector_sync: str
    payload_sha256: str
    result_index: int
    result_count: int


def parse_provider_memory(value: Any) -> ProviderMemory:
    """Parse one graph readback item and its flattened provenance markers."""

    item = _object(value)
    metadata = _object(item.get("metadata"))
    memory_type = _nonblank(metadata.get("memory_type"))
    if memory_type not in SUPPORTED_MEMORY_TYPES:
        raise GatewayProtocolError()
    status = _nonblank(metadata.get("status"))
    if status not in {"activated", "resolving"}:
        raise GatewayProtocolError()
    vector_sync = _nonblank(metadata.get("vector_sync"))
    if vector_sync != "success":
        raise GatewayProtocolError()
    index = metadata.get("memscope_result_index")
    count = metadata.get("memscope_result_count")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count <= 0
        or index >= count
    ):
        raise GatewayProtocolError()
    payload_sha256 = _nonblank(metadata.get("memscope_payload_sha256"))
    if len(payload_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in payload_sha256
    ):
        raise GatewayProtocolError()
    return ProviderMemory(
        memory_id=_uuid(item.get("id")),
        memory=_nonblank(item.get("memory")),
        user_id=_nonblank(metadata.get("user_id")),
        session_id=_nonblank(metadata.get("session_id")),
        cube_id=_nonblank(metadata.get("memscope_cube_id")),
        memory_type=memory_type,
        status=status,
        vector_sync=vector_sync,
        payload_sha256=payload_sha256,
        result_index=index,
        result_count=count,
    )


def memories_from_by_ids(data: Any) -> tuple[ProviderMemory, ...]:
    """Parse `/get_memory_by_ids` data."""

    body = _object(data)
    values = body.get("memories")
    if not isinstance(values, list):
        raise GatewayProtocolError()
    return tuple(parse_provider_memory(value) for value in values)


def memories_from_filtered_get(data: Any, *, cube_id: str) -> tuple[ProviderMemory, ...]:
    """Parse text-memory groups from `/get_memory` reconciliation data."""

    body = _object(data)
    groups = body.get("text_mem")
    if not isinstance(groups, list):
        raise GatewayProtocolError()
    values: list[ProviderMemory] = []
    for raw_group in groups:
        group = _object(raw_group)
        if _nonblank(group.get("cube_id")) != cube_id:
            raise GatewayProtocolError()
        memories = group.get("memories")
        total = group.get("total_nodes")
        if (
            not isinstance(memories, list)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or total != len(memories)
        ):
            raise GatewayProtocolError()
        values.extend(parse_provider_memory(value) for value in memories)
    return tuple(values)


def _search_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    rendered = value.strip()
    if rendered.endswith("Z"):
        rendered = f"{rendered[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError:
        return None
    if parsed.utcoffset() is None:
        return None
    return parsed


def _valid_search_provenance(metadata: dict[str, Any]) -> bool:
    payload_sha256 = metadata.get("memscope_payload_sha256")
    index = metadata.get("memscope_result_index")
    count = metadata.get("memscope_result_count")
    return (
        isinstance(payload_sha256, str)
        and len(payload_sha256) == 64
        and all(character in "0123456789abcdef" for character in payload_sha256)
        and not isinstance(index, bool)
        and isinstance(index, int)
        and index >= 0
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count > 0
        and index < count
        and metadata.get("vector_sync") == "success"
    )


def evidence_from_search(
    data: Any,
    *,
    user_id: str,
    cube_id: str,
) -> tuple[GatewayEvidence, ...]:
    """Return trusted text evidence while preserving the Product Search order."""

    body = _object(data)
    groups = body.get("text_mem")
    if not isinstance(groups, list):
        raise GatewayProtocolError()

    results: list[GatewayEvidence] = []
    observed_ids: dict[str, str] = {}
    accepted_ids: set[str] = set()
    seen_content: set[str] = set()
    for raw_group in groups:
        group = _object(raw_group)
        actual_cube = _nonblank(group.get("cube_id"))
        memories = group.get("memories")
        if not isinstance(memories, list):
            raise GatewayProtocolError()
        if actual_cube != cube_id:
            continue
        for raw_item in memories:
            item = _object(raw_item)
            memory_id = _nonblank(item.get("id"))
            content = _nonblank(item.get("memory"))
            previous = observed_ids.get(memory_id)
            if previous is not None and previous != content:
                raise GatewayProtocolError()
            observed_ids.setdefault(memory_id, content)
            metadata = _object(item.get("metadata"))
            score_value = metadata.get("relativity")
            if score_value is not None and (
                isinstance(score_value, bool)
                or not isinstance(score_value, int | float)
                or not isfinite(score_value)
            ):
                continue
            if (
                metadata.get("user_id") != user_id
                or metadata.get("memscope_cube_id") != cube_id
                or metadata.get("status") != "activated"
                or metadata.get("memory_type") not in SEARCH_MEMORY_TYPES
                or not _valid_search_provenance(metadata)
            ):
                continue

            normalized_content = content.strip()
            if memory_id in accepted_ids:
                continue
            accepted_ids.add(memory_id)
            if normalized_content in seen_content:
                continue
            seen_content.add(normalized_content)
            results.append(
                GatewayEvidence(
                    id=memory_id,
                    content=content,
                    user_id=user_id,
                    cube_id=cube_id,
                    score=float(score_value) if score_value is not None else None,
                    created_at=_search_time(metadata.get("created_at")),
                )
            )
    return tuple(results)

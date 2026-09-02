"""Versioned, deterministic identities for Raw Store records."""

import hashlib
import json
from typing import Any

from memscope.operations import AddCommand

PAYLOAD_SCHEMA = "memscope.add.v1"
PAYLOAD_SCHEMA_VERSION = 1
CUBE_ID_PREFIX = "cube_v1_"
MESSAGE_ID_PREFIX = "msg_v1_"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_add_payload(command: AddCommand) -> bytes:
    """Serialize every normalized Add field into the v1 canonical payload."""

    return _canonical_json(
        {
            "schema": PAYLOAD_SCHEMA,
            "request_id": command.request_id,
            "user_id": command.user_id,
            "session_id": command.session_id,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                    "timestamp": message.timestamp,
                }
                for message in command.messages
            ],
        }
    )


def payload_sha256(command: AddCommand) -> str:
    """Return the canonical v1 Add payload digest."""

    return hashlib.sha256(canonical_add_payload(command)).hexdigest()


def cube_id_for_user(user_id: str) -> str:
    """Return the stable logical Cube ID for one exact external user ID."""

    return CUBE_ID_PREFIX + hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def message_id_for_position(request_id: str, request_position: int) -> str:
    """Return the stable message ID for a position within an Add request."""

    if isinstance(request_position, bool) or not isinstance(request_position, int):
        raise TypeError("request_position must be an integer")
    if request_position < 0:
        raise ValueError("request_position must not be negative")
    identity = _canonical_json([request_id, request_position])
    return MESSAGE_ID_PREFIX + hashlib.sha256(identity).hexdigest()

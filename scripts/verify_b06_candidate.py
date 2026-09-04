#!/usr/bin/env python3
"""Verify an already-running B06 Add/Search/Health candidate over public HTTP."""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any
from urllib.parse import urlsplit


def _request(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None,
    timeout: float,
    api_key: str | None,
) -> tuple[int, dict[str, Any], float]:
    headers = {"Accept": "application/json"}
    body = None
    method = "GET"
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
        method = "POST"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(  # noqa: S310 -- caller validates HTTP(S) origin.
        f"{base_url}{path}", data=body, headers=headers, method=method
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(  # noqa: S310 -- request uses validated HTTP(S).
            request, timeout=timeout
        ) as response:
            status = response.status
            raw = response.read(2_000_000)
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read(2_000_000)
    elapsed = time.monotonic() - started
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{path} returned invalid JSON") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{path} returned a non-object JSON body")
    return status, parsed, elapsed


def _expect_success(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None,
    timeout: float,
    api_key: str | None,
) -> tuple[dict[str, Any], float]:
    status, body, elapsed = _request(
        base_url, path, payload=payload, timeout=timeout, api_key=api_key
    )
    if status != 200:
        code = body.get("error", {}).get("code") if isinstance(body.get("error"), dict) else None
        raise RuntimeError(f"{path} failed with HTTP {status}, code={code!r}")
    return body, elapsed


def _search_data(body: dict[str, Any], *, top_k: int) -> list[dict[str, Any]]:
    data = body.get("data")
    if not isinstance(data, list) or len(data) > top_k:
        raise RuntimeError("Search returned an invalid or oversized data array")
    for item in data:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"].strip()
            or not isinstance(item.get("content"), str)
            or not item["content"].strip()
        ):
            raise RuntimeError("Search returned an invalid evidence item")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--require-hit", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.strip().rstrip("/")
    parsed_url = urlsplit(base_url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        raise SystemExit("--base-url must be an HTTP(S) origin without credentials")

    api_key = os.getenv("CONTEST_API_KEY") or None
    run_id = uuid.uuid4().hex
    user_id = f"b06-smoke-user-{run_id}"
    other_user = f"b06-smoke-other-{run_id}"
    marker = f"b06-marker-{run_id}"
    add_payload = {
        "request_id": f"b06-smoke-add-{run_id}",
        "user_id": user_id,
        "session_id": f"b06-smoke-session-a-{run_id}",
        "messages": [{"role": "user", "content": f"Remember this marker: {marker}."}],
    }
    second_add = {
        "request_id": f"b06-smoke-add-2-{run_id}",
        "user_id": user_id,
        "session_id": f"b06-smoke-session-b-{run_id}",
        "messages": [{"role": "user", "content": "The marker belongs to a second session."}],
    }
    search_payload = {
        "query": f"What marker should be remembered? {marker}",
        "user_id": user_id,
        "top_k": 100,
        "options": [marker, "unrelated"],
    }

    health, health_seconds = _expect_success(
        base_url, "/health", payload=None, timeout=10, api_key=None
    )
    if health != {"status": "ok"}:
        raise RuntimeError("Health returned an unexpected body")
    first, add_seconds = _expect_success(
        base_url, "/add", payload=add_payload, timeout=119, api_key=api_key
    )
    replay, replay_seconds = _expect_success(
        base_url, "/add", payload=add_payload, timeout=119, api_key=api_key
    )
    _expect_success(base_url, "/add", payload=second_add, timeout=119, api_key=api_key)
    if first != replay or first.get("request_id") != add_payload["request_id"]:
        raise RuntimeError("Add replay did not return the same acknowledgement")

    search, search_seconds = _expect_success(
        base_url, "/search", payload=search_payload, timeout=59, api_key=api_key
    )
    evidence = _search_data(search, top_k=100)
    if args.require_hit and not evidence:
        raise RuntimeError("Search returned no evidence for the smoke marker")
    isolated, isolated_seconds = _expect_success(
        base_url,
        "/search",
        payload={**search_payload, "user_id": other_user},
        timeout=59,
        api_key=api_key,
    )
    if _search_data(isolated, top_k=100):
        raise RuntimeError("Cross-user Search returned evidence")
    if add_seconds >= 120 or search_seconds >= 60 or isolated_seconds >= 60:
        raise RuntimeError("A public operation exceeded its contest deadline")

    print(
        json.dumps(
            {
                "status": "passed",
                "health_seconds": round(health_seconds, 3),
                "add_seconds": round(add_seconds, 3),
                "replay_seconds": round(replay_seconds, 3),
                "search_seconds": round(search_seconds, 3),
                "isolated_search_seconds": round(isolated_seconds, 3),
                "evidence_count": len(evidence),
                "evidence_characters": sum(len(item["content"]) for item in evidence),
                "require_hit": args.require_hit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

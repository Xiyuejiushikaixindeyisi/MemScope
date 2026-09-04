#!/usr/bin/env python3
"""Verify an already-running MemScope system without controlling its lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_SCHEMA = "memscope.b08.system-report.v1"
_STATE_SCHEMA = "memscope.b08.restart-state.v1"
_MAX_RESPONSE_BYTES = 2_000_000
_ADD_TIMEOUT_SECONDS = 119.0
_SEARCH_TIMEOUT_SECONDS = 59.0
_HEALTH_TIMEOUT_SECONDS = 10.0
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class VerificationError(RuntimeError):
    """A safely classified public-system verification failure."""

    def __init__(self, classification: str, message: str) -> None:
        self.classification = classification
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HttpResult:
    """One bounded public HTTP observation."""

    status: int
    body: dict[str, Any]
    seconds: float


def _validate_origin(value: str) -> str:
    origin = value.strip().rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise VerificationError(
            "validation",
            "base URL must be an HTTP(S) origin without credentials, path, query or fragment",
        )
    return origin


def _validate_commit(value: str) -> str:
    candidate = value.strip()
    if _COMMIT_PATTERN.fullmatch(candidate) is None:
        raise VerificationError("validation", "candidate commit must be 40 lowercase hex digits")
    return candidate


def _error_code(body: dict[str, Any]) -> str | None:
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def _classify_http(status: int, body: dict[str, Any]) -> str:
    code = _error_code(body)
    if status == 422 or code == "request.invalid":
        return "validation"
    if status == 409 or code == "request.conflict":
        return "conflict"
    if status == 429 or code == "gateway.rate_limited":
        return "rate_limited"
    if status in {408, 504} or code in {"add.timeout", "search.timeout", "gateway.timeout"}:
        return "timeout"
    if status == 503 or code == "service.unavailable":
        return "readiness_unavailable"
    if code in {"gateway.unavailable", "storage.unavailable"}:
        return "provider_unavailable"
    if code in {
        "gateway.protocol_invalid",
        "application.invariant_failed",
        "storage.invariant_failed",
        "storage.migration_failed",
    }:
        return "protocol_invalid"
    return "unclassified"


def _request(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None,
    timeout: float,
    api_key: str | None,
) -> HttpResult:
    headers = {"Accept": "application/json"}
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
        method = "POST"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(  # noqa: S310 -- origin is validated by _validate_origin.
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status_code = response.status
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        status_code = error.code
        raw = error.read(_MAX_RESPONSE_BYTES + 1)
    except TimeoutError as error:
        raise VerificationError("timeout", f"{path} exceeded its client timeout") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise VerificationError("timeout", f"{path} exceeded its client timeout") from error
        raise VerificationError("provider_unavailable", f"{path} could not be reached") from error
    except OSError as error:
        raise VerificationError("provider_unavailable", f"{path} could not be reached") from error
    elapsed = time.monotonic() - started
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise VerificationError("protocol_invalid", f"{path} returned an oversized response")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("protocol_invalid", f"{path} returned invalid JSON") from error
    if not isinstance(parsed, dict):
        raise VerificationError("protocol_invalid", f"{path} returned non-object JSON")
    return HttpResult(status_code, parsed, elapsed)


def _check_deadline(path: str, seconds: float) -> None:
    if path == "/add" and seconds >= 120:
        raise VerificationError("timeout", "Add reached or exceeded 120 seconds")
    if path == "/search" and seconds >= 60:
        raise VerificationError("timeout", "Search reached or exceeded 60 seconds")


def _expect_success(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None,
    timeout: float,
    api_key: str | None,
) -> HttpResult:
    result = _request(
        base_url,
        path,
        payload=payload,
        timeout=timeout,
        api_key=api_key,
    )
    _check_deadline(path, result.seconds)
    if result.status != 200:
        classification = _classify_http(result.status, result.body)
        raise VerificationError(classification, f"{path} failed with HTTP {result.status}")
    return result


def _expect_error(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any],
    status: int,
    code: str,
    api_key: str | None,
) -> float:
    result = _request(
        base_url,
        path,
        payload=payload,
        timeout=_ADD_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    if result.status != status or _error_code(result.body) != code:
        raise VerificationError(
            "unclassified",
            f"{path} did not return expected HTTP {status} and error code",
        )
    return result.seconds


def _health(base_url: str) -> float:
    result = _expect_success(
        base_url,
        "/health",
        payload=None,
        timeout=_HEALTH_TIMEOUT_SECONDS,
        api_key=None,
    )
    if result.body != {"status": "ok"}:
        raise VerificationError("protocol_invalid", "Health returned an unexpected body")
    return result.seconds


def _add_payload(run_id: str, suffix: str, *, user_suffix: str = "primary") -> dict[str, Any]:
    return {
        "request_id": f"b08-add-{suffix}-{run_id}",
        "user_id": f"b08-user-{user_suffix}-{run_id}",
        "session_id": f"b08-session-{suffix}-{run_id}",
        "messages": [
            {
                "role": "user",
                "content": f"B08 synthetic verification marker {run_id} {suffix}",
                "timestamp": 1_704_067_200_000,
            }
        ],
    }


def _search_payload(run_id: str, user_id: str) -> dict[str, Any]:
    return {
        "query": f"Recall the B08 synthetic marker {run_id}",
        "user_id": user_id,
        "top_k": 100,
        "options": [f"b08-marker-{run_id}", "unrelated"],
    }


def _validate_add(result: HttpResult, payload: dict[str, Any]) -> None:
    expected = {
        "success": True,
        "request_id": payload["request_id"],
        "user_id": payload["user_id"],
        "session_id": payload["session_id"],
    }
    if result.body != expected:
        raise VerificationError("protocol_invalid", "Add returned an unexpected body")


def _evidence_ids(result: HttpResult, *, require_hit: bool) -> tuple[str, ...]:
    data = result.body.get("data")
    if not isinstance(data, list) or len(data) > 100:
        raise VerificationError("protocol_invalid", "Search returned an invalid data array")
    ids: list[str] = []
    for item in data:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"].strip()
            or not isinstance(item.get("content"), str)
            or not item["content"].strip()
        ):
            raise VerificationError("protocol_invalid", "Search returned invalid evidence")
        ids.append(item["id"])
    if len(set(ids)) != len(ids):
        raise VerificationError("duplicate_recovery_invariant", "Search returned duplicate IDs")
    if require_hit and not ids:
        raise VerificationError("protocol_invalid", "Search returned no evidence for test data")
    return tuple(ids)


def _percentiles(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise VerificationError("validation", "latency samples must not be empty")
    ordered = sorted(values)

    def nearest_rank(percent: float) -> float:
        index = max(0, math.ceil(percent * len(ordered)) - 1)
        return round(ordered[index], 6)

    return {
        "samples": len(ordered),
        "p50": nearest_rank(0.50),
        "p95": nearest_rank(0.95),
        "p99": nearest_rank(0.99),
        "max": round(ordered[-1], 6),
    }


def _parallel_successes(
    calls: Sequence[Callable[[], HttpResult]],
    *,
    workers: int,
) -> list[HttpResult]:
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="b08-verify") as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result() for future in futures]


def _fingerprint(run_id: str) -> str:
    return hashlib.sha256(run_id.encode()).hexdigest()[:16]


def _report(
    *,
    phase: str,
    candidate_commit: str,
    run_id: str,
    timings: dict[str, dict[str, float | int]],
    counts: dict[str, int],
    checks: list[str],
) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "phase": phase,
        "status": "passed",
        "candidate_commit": candidate_commit,
        "run_fingerprint": _fingerprint(run_id),
        "timings_seconds": timings,
        "counts": counts,
        "expected_failure_classifications": ["validation", "conflict"],
        "checks": checks,
    }


def exercise(
    *,
    base_url: str,
    candidate_commit: str,
    samples: int,
    concurrency: int,
    require_hit: bool,
    api_key: str | None,
) -> dict[str, Any]:
    """Run a bounded public exercise without retrying failed calls."""

    run_id = uuid.uuid4().hex
    health_seconds = _health(base_url)
    first_payload = _add_payload(run_id, "primary")
    first = _expect_success(
        base_url,
        "/add",
        payload=first_payload,
        timeout=_ADD_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    _validate_add(first, first_payload)
    replay = _expect_success(
        base_url,
        "/add",
        payload=first_payload,
        timeout=_ADD_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    _validate_add(replay, first_payload)
    if replay.body != first.body:
        raise VerificationError("duplicate_recovery_invariant", "Add replay body changed")

    second_payload = _add_payload(run_id, "second-session")
    second = _expect_success(
        base_url,
        "/add",
        payload=second_payload,
        timeout=_ADD_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    _validate_add(second, second_payload)
    validation_seconds = _expect_error(
        base_url,
        "/add",
        payload={},
        status=422,
        code="request.invalid",
        api_key=api_key,
    )
    conflicting = json.loads(json.dumps(first_payload))
    conflicting["messages"][0]["content"] = "B08 deliberately conflicting synthetic content"
    conflict_seconds = _expect_error(
        base_url,
        "/add",
        payload=conflicting,
        status=409,
        code="request.conflict",
        api_key=api_key,
    )

    search_payload = _search_payload(run_id, str(first_payload["user_id"]))
    search = _expect_success(
        base_url,
        "/search",
        payload=search_payload,
        timeout=_SEARCH_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    evidence_ids = _evidence_ids(search, require_hit=require_hit)
    isolated_payload = {
        **search_payload,
        "user_id": f"b08-isolated-{run_id}",
    }
    isolated = _expect_success(
        base_url,
        "/search",
        payload=isolated_payload,
        timeout=_SEARCH_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    if _evidence_ids(isolated, require_hit=False):
        raise VerificationError("isolation_breach", "cross-user Search returned evidence")

    replay_calls = [
        partial(
            _expect_success,
            base_url,
            "/add",
            payload=first_payload,
            timeout=_ADD_TIMEOUT_SECONDS,
            api_key=api_key,
        )
        for _ in range(concurrency)
    ]
    concurrent_replays = _parallel_successes(replay_calls, workers=concurrency)
    for result in concurrent_replays:
        _validate_add(result, first_payload)
        if result.body != first.body:
            raise VerificationError("duplicate_recovery_invariant", "concurrent replay changed")

    add_payloads = [
        _add_payload(run_id, f"concurrent-{index}", user_suffix=f"parallel-{index}")
        for index in range(samples)
    ]
    add_calls = [
        partial(
            _expect_success,
            base_url,
            "/add",
            payload=payload,
            timeout=_ADD_TIMEOUT_SECONDS,
            api_key=api_key,
        )
        for payload in add_payloads
    ]
    concurrent_adds = _parallel_successes(add_calls, workers=concurrency)
    for payload, result in zip(add_payloads, concurrent_adds, strict=True):
        _validate_add(result, payload)

    search_calls = [
        partial(
            _expect_success,
            base_url,
            "/search",
            payload=search_payload,
            timeout=_SEARCH_TIMEOUT_SECONDS,
            api_key=api_key,
        )
        for _ in range(samples)
    ]
    concurrent_searches = _parallel_successes(search_calls, workers=concurrency)
    for result in concurrent_searches:
        _evidence_ids(result, require_hit=require_hit)

    return _report(
        phase="exercise",
        candidate_commit=candidate_commit,
        run_id=run_id,
        timings={
            "health": _percentiles([health_seconds]),
            "initial_add": _percentiles([first.seconds]),
            "replay_add": _percentiles([replay.seconds]),
            "cross_session_add": _percentiles([second.seconds]),
            "validation": _percentiles([validation_seconds]),
            "conflict": _percentiles([conflict_seconds]),
            "search": _percentiles([search.seconds]),
            "isolated_search": _percentiles([isolated.seconds]),
            "concurrent_replay": _percentiles([item.seconds for item in concurrent_replays]),
            "concurrent_add": _percentiles([item.seconds for item in concurrent_adds]),
            "concurrent_search": _percentiles([item.seconds for item in concurrent_searches]),
        },
        counts={
            "initial_evidence": len(evidence_ids),
            "concurrent_adds": len(concurrent_adds),
            "concurrent_replays": len(concurrent_replays),
            "concurrent_searches": len(concurrent_searches),
            "cross_user_evidence": 0,
            "unclassified_failures": 0,
        },
        checks=[
            "exact public Health",
            "Add, exact replay and cross-session Add",
            "Search hit policy and cross-user isolation",
            "validation and conflict error envelopes",
            "bounded same-request replay and cross-user Add/Search concurrency",
            "public Add/Search contest deadlines",
        ],
    )


def _state_digest(state: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in state.items() if key != "integrity_sha256"}
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    descriptor = -1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError as error:
        raise VerificationError("validation", "output file could not be written") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_restart_state(path: Path, candidate_commit: str) -> dict[str, Any]:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise VerificationError("validation", "restart state permissions must be 0600")
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except VerificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("validation", "restart state could not be read") from error
    if not isinstance(decoded, dict):
        raise VerificationError("validation", "restart state must be a JSON object")
    required = {
        "schema": str,
        "candidate_commit": str,
        "run_id": str,
        "add_payload": dict,
        "search_payload": dict,
        "other_user_id": str,
        "add_response": dict,
        "evidence_ids": list,
        "integrity_sha256": str,
    }
    if any(not isinstance(decoded.get(key), expected) for key, expected in required.items()):
        raise VerificationError("validation", "restart state has an invalid shape")
    if decoded["schema"] != _STATE_SCHEMA or decoded["candidate_commit"] != candidate_commit:
        raise VerificationError("validation", "restart state identity does not match candidate")
    if decoded["integrity_sha256"] != _state_digest(decoded):
        raise VerificationError("validation", "restart state integrity check failed")
    evidence_ids = decoded["evidence_ids"]
    if not evidence_ids or not all(isinstance(item, str) and item.strip() for item in evidence_ids):
        raise VerificationError("validation", "restart state requires prior evidence IDs")
    return decoded


def prepare_restart(
    *,
    base_url: str,
    candidate_commit: str,
    state_path: Path,
    api_key: str | None,
) -> dict[str, Any]:
    """Seed one restart checkpoint without controlling the deployment."""

    run_id = uuid.uuid4().hex
    health_seconds = _health(base_url)
    add_payload = _add_payload(run_id, "restart")
    added = _expect_success(
        base_url,
        "/add",
        payload=add_payload,
        timeout=_ADD_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    _validate_add(added, add_payload)
    search_payload = _search_payload(run_id, str(add_payload["user_id"]))
    searched = _expect_success(
        base_url,
        "/search",
        payload=search_payload,
        timeout=_SEARCH_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    evidence_ids = _evidence_ids(searched, require_hit=True)
    other_user_id = f"b08-restart-isolated-{run_id}"
    isolated = _expect_success(
        base_url,
        "/search",
        payload={**search_payload, "user_id": other_user_id},
        timeout=_SEARCH_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    if _evidence_ids(isolated, require_hit=False):
        raise VerificationError("isolation_breach", "cross-user Search returned evidence")
    state: dict[str, Any] = {
        "schema": _STATE_SCHEMA,
        "candidate_commit": candidate_commit,
        "run_id": run_id,
        "add_payload": add_payload,
        "search_payload": search_payload,
        "other_user_id": other_user_id,
        "add_response": added.body,
        "evidence_ids": list(evidence_ids),
    }
    state["integrity_sha256"] = _state_digest(state)
    _write_private_json(state_path, state)
    return _report(
        phase="prepare-restart",
        candidate_commit=candidate_commit,
        run_id=run_id,
        timings={
            "health": _percentiles([health_seconds]),
            "initial_add": _percentiles([added.seconds]),
            "search": _percentiles([searched.seconds]),
            "isolated_search": _percentiles([isolated.seconds]),
        },
        counts={
            "initial_evidence": len(evidence_ids),
            "cross_user_evidence": 0,
            "unclassified_failures": 0,
        },
        checks=[
            "restart checkpoint Add is committed",
            "checkpoint is searchable before restart",
            "cross-user Search is empty before restart",
            "mode-0600 integrity-protected state written",
        ],
    )


def verify_restart(
    *,
    base_url: str,
    candidate_commit: str,
    state_path: Path,
    api_key: str | None,
) -> dict[str, Any]:
    """Verify a checkpoint after an independently controlled restart."""

    state = _read_restart_state(state_path, candidate_commit)
    run_id = str(state["run_id"])
    health_seconds = _health(base_url)
    replay = _expect_success(
        base_url,
        "/add",
        payload=state["add_payload"],
        timeout=_ADD_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    if replay.body != state["add_response"]:
        raise VerificationError("duplicate_recovery_invariant", "restart replay body changed")
    searched = _expect_success(
        base_url,
        "/search",
        payload=state["search_payload"],
        timeout=_SEARCH_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    evidence_ids = set(_evidence_ids(searched, require_hit=True))
    prior_ids = set(state["evidence_ids"])
    retained = len(evidence_ids & prior_ids)
    if retained == 0:
        raise VerificationError(
            "duplicate_recovery_invariant",
            "no pre-restart evidence identity survived restart",
        )
    isolated_payload = {
        **state["search_payload"],
        "user_id": state["other_user_id"],
    }
    isolated = _expect_success(
        base_url,
        "/search",
        payload=isolated_payload,
        timeout=_SEARCH_TIMEOUT_SECONDS,
        api_key=api_key,
    )
    if _evidence_ids(isolated, require_hit=False):
        raise VerificationError("isolation_breach", "cross-user Search returned evidence")
    return _report(
        phase="verify-restart",
        candidate_commit=candidate_commit,
        run_id=run_id,
        timings={
            "restart_health": _percentiles([health_seconds]),
            "restart_replay": _percentiles([replay.seconds]),
            "restart_search": _percentiles([searched.seconds]),
            "restart_isolated_search": _percentiles([isolated.seconds]),
        },
        counts={
            "retained_evidence_ids": retained,
            "cross_user_evidence": 0,
            "unclassified_failures": 0,
        },
        checks=[
            "public readiness recovered after operator restart",
            "exact Add replay retained its acknowledgement",
            "pre-restart evidence identity remained searchable",
            "cross-user Search remained empty",
        ],
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--report", type=Path)
    subparsers = parser.add_subparsers(dest="phase", required=True)
    exercise_parser = subparsers.add_parser("exercise")
    exercise_parser.add_argument("--samples", type=int, default=5)
    exercise_parser.add_argument("--concurrency", type=int, default=2)
    exercise_parser.add_argument("--require-hit", action="store_true")
    for phase in ("prepare-restart", "verify-restart"):
        phase_parser = subparsers.add_parser(phase)
        phase_parser.add_argument("--state", type=Path, required=True)
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    base_url = _validate_origin(args.base_url)
    candidate_commit = _validate_commit(args.candidate_commit)
    api_key = os.getenv("CONTEST_API_KEY") or None
    if args.phase == "exercise":
        if not 1 <= args.samples <= 30 or not 1 <= args.concurrency <= 8:
            raise VerificationError(
                "validation",
                "samples must be 1..30 and concurrency must be 1..8",
            )
        return exercise(
            base_url=base_url,
            candidate_commit=candidate_commit,
            samples=args.samples,
            concurrency=args.concurrency,
            require_hit=args.require_hit,
            api_key=api_key,
        )
    if args.phase == "prepare-restart":
        return prepare_restart(
            base_url=base_url,
            candidate_commit=candidate_commit,
            state_path=args.state,
            api_key=api_key,
        )
    if args.phase == "verify-restart":
        return verify_restart(
            base_url=base_url,
            candidate_commit=candidate_commit,
            state_path=args.state,
            api_key=api_key,
        )
    raise VerificationError("validation", "unsupported verification phase")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = _run(args)
        if args.report is not None:
            _write_private_json(args.report, result)
    except VerificationError as error:
        print(
            json.dumps(
                {
                    "schema": _SCHEMA,
                    "status": "failed",
                    "classification": error.classification,
                    "message": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

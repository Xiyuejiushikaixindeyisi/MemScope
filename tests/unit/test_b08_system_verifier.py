"""Deterministic tests for the standard-library B08 public verifier."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


def _load_verifier() -> Any:
    path = Path(__file__).parents[2] / "scripts" / "verify_b08_system.py"
    spec = importlib.util.spec_from_file_location("memscope_b08_verifier", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load B08 verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()

_COMMIT = "d281aa03b5b90f9e9903033fd9f1fc822011a490"


class _FixtureState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.adds: dict[str, dict[str, Any]] = {}
        self.memories: dict[str, list[dict[str, Any]]] = {}
        self.paths: list[str] = []


def _handler(state: _FixtureState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _reply(self, status_code: int, body: dict[str, Any]) -> None:
            encoded = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
            with state.lock:
                state.paths.append(self.path)
            if self.path == "/health":
                self._reply(200, {"status": "ok"})
                return
            self._reply(404, {"error": {"code": "http.not_found"}})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
            length = int(self.headers.get("Content-Length", "0"))
            decoded = json.loads(self.rfile.read(length))
            with state.lock:
                state.paths.append(self.path)
                if self.path == "/add":
                    self._add(decoded)
                    return
                if self.path == "/search":
                    self._search(decoded)
                    return
            self._reply(404, {"error": {"code": "http.not_found"}})

        def _add(self, payload: Any) -> None:
            if not isinstance(payload, dict) or not all(
                key in payload for key in ("request_id", "user_id", "session_id", "messages")
            ):
                self._reply(
                    422,
                    {
                        "error": {
                            "code": "request.invalid",
                            "message": "Request validation failed",
                            "retryable": False,
                        }
                    },
                )
                return
            request_id = str(payload["request_id"])
            existing = state.adds.get(request_id)
            if existing is not None and existing != payload:
                self._reply(
                    409,
                    {
                        "error": {
                            "code": "request.conflict",
                            "message": "Request identifier conflicts",
                            "retryable": False,
                        }
                    },
                )
                return
            if existing is None:
                state.adds[request_id] = payload
                user_id = str(payload["user_id"])
                memory_id = hashlib.sha256(request_id.encode()).hexdigest()
                state.memories.setdefault(user_id, []).append(
                    {
                        "id": memory_id,
                        "content": "synthetic fixture evidence",
                        "score": 0.9,
                    }
                )
            self._reply(
                200,
                {
                    "success": True,
                    "request_id": request_id,
                    "user_id": payload["user_id"],
                    "session_id": payload["session_id"],
                },
            )

        def _search(self, payload: Any) -> None:
            if not isinstance(payload, dict) or not isinstance(payload.get("user_id"), str):
                self._reply(422, {"error": {"code": "request.invalid"}})
                return
            top_k = int(payload.get("top_k", 10))
            self._reply(200, {"data": state.memories.get(payload["user_id"], [])[:top_k]})

    return Handler


@pytest.fixture
def public_fixture() -> Iterator[tuple[str, _FixtureState]]:
    state = _FixtureState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    address = cast("tuple[str, int]", server.server_address)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{address[1]}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_percentiles_and_http_failure_classification() -> None:
    assert verifier._percentiles([0.4, 0.1, 0.3, 0.2]) == {
        "samples": 4,
        "p50": 0.2,
        "p95": 0.4,
        "p99": 0.4,
        "max": 0.4,
    }
    assert verifier._classify_http(422, {"error": {"code": "request.invalid"}}) == "validation"
    assert verifier._classify_http(409, {"error": {"code": "request.conflict"}}) == "conflict"
    assert verifier._classify_http(429, {}) == "rate_limited"
    assert verifier._classify_http(500, {"error": {"code": "gateway.timeout"}}) == "timeout"
    assert verifier._classify_http(503, {}) == "readiness_unavailable"
    assert verifier._classify_http(500, {}) == "unclassified"


def test_exercise_covers_concurrency_and_emits_no_payload_content(
    public_fixture: tuple[str, _FixtureState],
) -> None:
    base_url, state = public_fixture
    report = verifier.exercise(
        base_url=base_url,
        candidate_commit=_COMMIT,
        samples=3,
        concurrency=2,
        require_hit=True,
        api_key="fixture-key",
    )

    assert report["schema"] == "memscope.b08.system-report.v1"
    assert report["status"] == "passed"
    assert report["counts"] == {
        "initial_evidence": 2,
        "concurrent_adds": 3,
        "concurrent_replays": 2,
        "concurrent_searches": 3,
        "cross_user_evidence": 0,
        "unclassified_failures": 0,
    }
    encoded = json.dumps(report)
    assert "fixture-key" not in encoded
    assert "synthetic verification marker" not in encoded
    assert "b08-user-" not in encoded
    assert state.paths.count("/add") == 10


def test_restart_checkpoint_is_private_integrity_checked_and_replayable(
    public_fixture: tuple[str, _FixtureState],
    tmp_path: Path,
) -> None:
    base_url, _ = public_fixture
    state_path = tmp_path / "restart.json"

    prepared = verifier.prepare_restart(
        base_url=base_url,
        candidate_commit=_COMMIT,
        state_path=state_path,
        api_key=None,
    )
    verified = verifier.verify_restart(
        base_url=base_url,
        candidate_commit=_COMMIT,
        state_path=state_path,
        api_key=None,
    )

    assert prepared["phase"] == "prepare-restart"
    assert verified["phase"] == "verify-restart"
    assert verified["counts"]["retained_evidence_ids"] == 1
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600

    tampered = json.loads(state_path.read_text())
    tampered["candidate_commit"] = "0" * 40
    state_path.write_text(json.dumps(tampered))
    state_path.chmod(0o600)
    with pytest.raises(verifier.VerificationError, match="identity") as captured:
        verifier.verify_restart(
            base_url=base_url,
            candidate_commit=_COMMIT,
            state_path=state_path,
            api_key=None,
        )
    assert captured.value.classification == "validation"


def test_cli_rejects_unsafe_origin_and_workload_bounds(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        verifier.main(
            [
                "--base-url",
                "http://user:password@example.invalid/path",
                "--candidate-commit",
                _COMMIT,
                "exercise",
            ]
        )
        == 1
    )
    first_error = json.loads(capsys.readouterr().err)
    assert first_error["classification"] == "validation"
    assert "password" not in first_error["message"]

    assert (
        verifier.main(
            [
                "--candidate-commit",
                _COMMIT,
                "exercise",
                "--samples",
                "31",
                "--concurrency",
                "9",
            ]
        )
        == 1
    )
    second_error = json.loads(capsys.readouterr().err)
    assert second_error["classification"] == "validation"

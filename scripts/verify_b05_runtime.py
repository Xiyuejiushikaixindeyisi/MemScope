#!/usr/bin/env python3
"""Verify B05 Real Add in a disposable, no-key, clean-room Compose project."""

from __future__ import annotations

import argparse
import base64
import json
import math
import platform
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLEAN_ROOM_PATHS = (
    ".dockerignore",
    "README.md",
    "compose.yaml",
    "docker",
    "pyproject.toml",
    "src",
    "third_party",
)
SERVICES = ("neo4j", "qdrant", "mock-model", "memos", "memory-api")
PRIVATE_SERVICES = ("neo4j", "qdrant", "mock-model", "memos")
DEFAULT_EXTRACTION = json.dumps(
    {
        "memory list": [
            {
                "key": "fixture",
                "memory_type": "UserMemory",
                "tags": [],
                "value": "deterministic fixture memory",
            }
        ],
        "summary": "fixture",
    },
    separators=(",", ":"),
)
EMPTY_EXTRACTION = '{"memory list":[],"summary":""}'
INVALID_EXTRACTION = '{"wrong":[]}'


class VerificationError(RuntimeError):
    """A required B05 runtime invariant was not demonstrated."""


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: float = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        raise VerificationError(
            f"command failed with exit code {result.returncode}: {' '.join(command)}\n{output}"
        )
    return result


def _copy_clean_room(destination: Path) -> None:
    for relative in CLEAN_ROOM_PATHS:
        source = ROOT / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _write_override(path: Path) -> None:
    path.write_text(
        """services:
  mock-model:
    image: memscope/memory-api:0.0.0-b05
    init: true
    restart: unless-stopped
    stop_grace_period: 30s
    mem_limit: 256m
    cpus: 0.5
    pids_limit: 128
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    command: ["python", "-m", "uvicorn", "memscope.mock_model_api.memos_main:app",
              "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]
    environment:
      B05_MOCK_EMBEDDING_DIMENSION: "16"
      B05_MOCK_EXTRACTION_JSON: '${B05_MOCK_EXTRACTION_JSON:?set extraction}'
      B05_MOCK_CHAT_DELAY_MS: '${B05_MOCK_CHAT_DELAY_MS:-0}'
    healthcheck:
      test: ["CMD", "python", "-c",
             "import json,urllib.request; r=urllib.request.urlopen(\
'http://127.0.0.1:9000/health',timeout=2); assert r.status == 200 and \
json.load(r).get('status') == 'ok'"]
      interval: 2s
      timeout: 3s
      retries: 20
      start_period: 3s
    networks: [backend]
  memos:
    depends_on:
      mock-model:
        condition: service_healthy
        restart: true
""",
        encoding="utf-8",
    )


def _write_env(
    path: Path,
    *,
    password: str,
    public_port: int,
    extraction: str,
    chat_delay_ms: int = 0,
    pip_index_url: str,
) -> None:
    path.write_text(
        "\n".join(
            (
                f"NEO4J_PASSWORD={password}",
                "MEMSCOPE_MODEL_PROFILE=mock",
                "MEMRADER_MODEL=mock-chat",
                "MEMRADER_API_BASE=http://mock-model:9000/v1",
                "MEMRADER_API_KEY=EMPTY",
                "MOS_EMBEDDER_MODEL=mock-embedding",
                "MOS_EMBEDDER_API_BASE=http://mock-model:9000/v1",
                "MOS_EMBEDDER_API_KEY=EMPTY",
                "EMBEDDING_DIMENSION=16",
                f"MEMSCOPE_PUBLIC_PORT={public_port}",
                "ADD_DEADLINE_SECONDS=4",
                "ADD_WARN_SECONDS=3",
                "MEMOS_DEADLINE_RESERVE_SECONDS=0.5",
                f"B04_PIP_INDEX_URL={pip_index_url}",
                f"B05_MOCK_EXTRACTION_JSON={extraction}",
                f"B05_MOCK_CHAT_DELAY_MS={chat_delay_ms}",
                "",
            )
        ),
        encoding="utf-8",
    )


def _compose(root: Path, override: Path, env_file: Path, project: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "--file",
        str(root / "compose.yaml"),
        "--file",
        str(override),
        "--env-file",
        str(env_file),
        "--project-name",
        project,
    ]


def _container_id(compose: list[str], root: Path, service: str) -> str:
    value = _run([*compose, "ps", "--quiet", service], cwd=root).stdout.strip()
    if not value or "\n" in value:
        raise VerificationError(f"could not resolve exactly one {service} container")
    return value


def _wait_healthy(
    compose: list[str], root: Path, services: tuple[str, ...], timeout: float
) -> None:
    deadline = time.monotonic() + timeout
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        for service in services:
            container = _container_id(compose, root, service)
            last[service] = _run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                    container,
                ],
                cwd=root,
            ).stdout.strip()
        if all(value == "healthy" for value in last.values()):
            return
        time.sleep(1)
    raise VerificationError(f"services did not become healthy: {last}")


def _exec_python(compose: list[str], root: Path, source: str, *arguments: str) -> str:
    return _run(
        [*compose, "exec", "-T", "memory-api", "python", "-c", source, *arguments],
        cwd=root,
        timeout=125,
    ).stdout.strip()


def _api_request(
    compose: list[str], root: Path, method: str, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode() if payload is not None else ""
    source = (
        "import base64,json,sys,time,urllib.error,urllib.request;"
        "method,path,encoded=sys.argv[1:4];"
        "data=base64.b64decode(encoded) if encoded else None;"
        "request=urllib.request.Request('http://127.0.0.1:8080'+path,data=data,method=method,"
        "headers={'Content-Type':'application/json'});"
        "started=time.monotonic();"
        "\ntry:\n response=urllib.request.urlopen(request,timeout=119);"
        " status=response.status; body=response.read()"
        "\nexcept urllib.error.HTTPError as error:\n status=error.code; body=error.read()"
        "\nprint(json.dumps({'status':status,'body':json.loads(body),'seconds':time.monotonic()-started}))"
    )
    decoded = json.loads(_exec_python(compose, root, source, method, path, encoded))
    if not isinstance(decoded, dict):
        raise VerificationError("memory-api response was not a JSON object")
    return decoded


def _add_payload(request: str, user: str, session: str, content: str) -> dict[str, Any]:
    return {
        "request_id": request,
        "user_id": user,
        "session_id": session,
        "messages": [{"role": "user", "content": content, "timestamp": 1704067200000}],
    }


def _assert_add_success(response: dict[str, Any], payload: dict[str, Any]) -> None:
    expected = {
        "success": True,
        "request_id": payload["request_id"],
        "user_id": payload["user_id"],
        "session_id": payload["session_id"],
    }
    if response["status"] != 200 or response["body"] != expected:
        raise VerificationError(f"unexpected Add response: {response}")


def _raw_status(compose: list[str], root: Path, request_id: str) -> str | None:
    source = (
        "import json,sqlite3,sys;"
        "c=sqlite3.connect('/var/lib/memscope/raw.db');"
        "row=c.execute('SELECT status FROM add_requests WHERE request_id=?',"
        "(sys.argv[1],)).fetchone();"
        "print(json.dumps(row[0] if row else None))"
    )
    decoded = json.loads(_exec_python(compose, root, source, request_id))
    if decoded is not None and not isinstance(decoded, str):
        raise VerificationError("Raw request status was not text or null")
    return decoded


def _neo4j_counts(compose: list[str], root: Path) -> list[dict[str, Any]]:
    command = (
        'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" --format plain '
        '"MATCH (n:Memory) RETURN n.user_id AS user, n.user_name AS cube, '
        'count(n) AS count ORDER BY user"'
    )
    output = _run(
        [*compose, "exec", "-T", "neo4j", "sh", "-c", command], cwd=root, timeout=30
    ).stdout.splitlines()
    result = []
    for line in output[1:]:
        if not line.strip():
            continue
        user, cube, count = [part.strip() for part in line.rsplit(",", maxsplit=2)]
        result.append({"user": json.loads(user), "cube": json.loads(cube), "count": int(count)})
    return result


def _set_mock(
    compose: list[str],
    root: Path,
    env_file: Path,
    *,
    password: str,
    port: int,
    extraction: str,
    delay_ms: int,
    pip_index_url: str,
    health_timeout: float,
) -> None:
    _write_env(
        env_file,
        password=password,
        public_port=port,
        extraction=extraction,
        chat_delay_ms=delay_ms,
        pip_index_url=pip_index_url,
    )
    _run(
        [*compose, "up", "--detach", "--no-deps", "--force-recreate", "mock-model"],
        cwd=root,
        timeout=60,
    )
    _wait_healthy(compose, root, ("mock-model",), health_timeout)


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    rank = max(0, math.ceil(percentage * len(ordered)) - 1)
    return ordered[rank]


def _assert_runtime_controls(compose: list[str], root: Path, public_port: int) -> None:
    for service in SERVICES:
        container = _container_id(compose, root, service)
        uid = _run([*compose, "exec", "-T", service, "id", "-u"], cwd=root).stdout.strip()
        if uid == "0":
            raise VerificationError(f"{service} runs as root")
        inspect = json.loads(
            _run(
                ["docker", "inspect", "--format", "{{json .HostConfig}}", container], cwd=root
            ).stdout
        )
        if inspect.get("Memory", 0) <= 0 or inspect.get("NanoCpus", 0) <= 0:
            raise VerificationError(f"{service} resource ceilings are not active")
        if inspect.get("PidsLimit", 0) <= 0:
            raise VerificationError(f"{service} PID ceiling is not active")
        expected_bindings = 1 if service == "memory-api" else 0
        bindings = inspect.get("PortBindings") or {}
        actual_bindings = sum(len(value or []) for value in bindings.values())
        if actual_bindings != expected_bindings:
            raise VerificationError(f"{service} has unexpected configured host port bindings")
        if service == "memory-api":
            published = bindings.get("8080/tcp", [])
            if len(published) != 1 or published[0].get("HostPort") != str(public_port):
                raise VerificationError("memory-api does not bind the selected public port")
            live = json.loads(
                _run(
                    ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container],
                    cwd=root,
                ).stdout
            )
            if not live.get("8080/tcp"):
                raise VerificationError(
                    "Docker runtime did not activate memory-api port publishing"
                )


def verify(args: argparse.Namespace) -> dict[str, Any]:
    if shutil.which("docker") is None:
        raise VerificationError("Docker CLI is unavailable")
    project = args.project_name or f"memscope_b05_gate_{secrets.token_hex(4)}"
    if not project.startswith("memscope_b05_gate_"):
        raise VerificationError("project name must start with memscope_b05_gate_")
    password = f"B05-{secrets.token_urlsafe(24)}"
    canary = f"B05_CONTENT_{secrets.token_hex(16)}"
    timings: dict[str, Any] = {}
    images: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="memscope-b05-clean-room-") as name:
        root = Path(name)
        _copy_clean_room(root)
        env_file = root / "b05.env"
        override = root / "b05.mock.yaml"
        _write_override(override)
        _write_env(
            env_file,
            password=password,
            public_port=args.public_port,
            extraction=DEFAULT_EXTRACTION,
            pip_index_url=args.pip_index_url,
        )
        compose = _compose(root, override, env_file, project)
        try:
            _run([*compose, "config", "--quiet"], cwd=root)
            started = time.monotonic()
            if not args.skip_build:
                _run([*compose, "build"], cwd=root, timeout=args.build_timeout)
            timings["build_seconds"] = round(time.monotonic() - started, 3)
            started = time.monotonic()
            _run([*compose, "up", "--detach"], cwd=root, timeout=180)
            _wait_healthy(compose, root, SERVICES, args.health_timeout)
            timings["cold_start_seconds"] = round(time.monotonic() - started, 3)

            health = _api_request(compose, root, "GET", "/health")
            search = _api_request(
                compose,
                root,
                "POST",
                "/search",
                {"query": "q", "user_id": "b05-user-a", "top_k": 1},
            )
            if health["status"] != 503 or search["status"] != 503:
                raise VerificationError("B05 Health/Search boundary is not closed")

            first = _add_payload("b05-add-1", "b05-user-a", "b05-session-a", canary)
            _assert_add_success(_api_request(compose, root, "POST", "/add", first), first)
            replay = _api_request(compose, root, "POST", "/add", first)
            _assert_add_success(replay, first)

            second = _add_payload("b05-add-2", "b05-user-b", "b05-session-b", canary)
            _assert_add_success(_api_request(compose, root, "POST", "/add", second), second)
            counts = {item["user"]: item for item in _neo4j_counts(compose, root)}
            if counts["b05-user-a"]["count"] != 1 or counts["b05-user-b"]["count"] != 1:
                raise VerificationError("two-user memory counts are not isolated")
            if counts["b05-user-a"]["cube"] == counts["b05-user-b"]["cube"]:
                raise VerificationError("two users share one logical Cube")

            samples = []
            for index in range(args.samples):
                payload = _add_payload(
                    f"b05-latency-{index}",
                    f"b05-latency-user-{index}",
                    f"b05-latency-session-{index}",
                    f"latency fixture {index}",
                )
                response = _api_request(compose, root, "POST", "/add", payload)
                _assert_add_success(response, payload)
                samples.append(float(response["seconds"]))
            timings["add_seconds"] = {
                "samples": len(samples),
                "p50": round(statistics.median(samples), 6),
                "p95": round(_percentile(samples, 0.95), 6),
                "p99": round(_percentile(samples, 0.99), 6),
                "max": round(max(samples), 6),
            }

            _set_mock(
                compose,
                root,
                env_file,
                password=password,
                port=args.public_port,
                extraction=EMPTY_EXTRACTION,
                delay_ms=0,
                pip_index_url=args.pip_index_url,
                health_timeout=args.health_timeout,
            )
            empty = _add_payload("b05-empty", "b05-empty-user", "b05-empty-session", "neutral")
            _assert_add_success(_api_request(compose, root, "POST", "/add", empty), empty)
            if any(item["user"] == "b05-empty-user" for item in _neo4j_counts(compose, root)):
                raise VerificationError("valid-empty extraction created a fallback node")

            _set_mock(
                compose,
                root,
                env_file,
                password=password,
                port=args.public_port,
                extraction=INVALID_EXTRACTION,
                delay_ms=0,
                pip_index_url=args.pip_index_url,
                health_timeout=args.health_timeout,
            )
            invalid = _add_payload(
                "b05-invalid", "b05-invalid-user", "b05-invalid-session", "invalid schema"
            )
            invalid_result = _api_request(compose, root, "POST", "/add", invalid)
            if (
                invalid_result["status"] != 500
                or _raw_status(compose, root, "b05-invalid") != "pending"
            ):
                raise VerificationError("invalid extraction did not fail with Raw pending")
            if any(item["user"] == "b05-invalid-user" for item in _neo4j_counts(compose, root)):
                raise VerificationError("invalid extraction created a fallback node")

            _set_mock(
                compose,
                root,
                env_file,
                password=password,
                port=args.public_port,
                extraction=DEFAULT_EXTRACTION,
                delay_ms=6000,
                pip_index_url=args.pip_index_url,
                health_timeout=args.health_timeout,
            )
            slow = _add_payload("b05-slow", "b05-slow-user", "b05-slow-session", "slow")
            slow_result = _api_request(compose, root, "POST", "/add", slow)
            if slow_result["status"] != 500 or slow_result["seconds"] >= 5:
                raise VerificationError("model delay did not respect the Add-wide deadline")
            if _raw_status(compose, root, "b05-slow") != "pending":
                raise VerificationError("timed-out Add did not leave Raw pending")

            _run([*compose, "restart", "memos", "memory-api"], cwd=root, timeout=120)
            _wait_healthy(compose, root, ("memos", "memory-api"), args.health_timeout)
            _assert_add_success(_api_request(compose, root, "POST", "/add", first), first)
            counts_after = {item["user"]: item for item in _neo4j_counts(compose, root)}
            if counts_after["b05-user-a"]["count"] != 1:
                raise VerificationError("restart/replay duplicated provider memory")

            logs = _run([*compose, "logs", "--no-color"], cwd=root).stdout
            for forbidden in (password, canary):
                if forbidden in logs:
                    raise VerificationError("sensitive canary appeared in aggregate logs")

            _assert_runtime_controls(compose, root, args.public_port)
            for service in SERVICES:
                container = _container_id(compose, root, service)
                image_id = _run(
                    ["docker", "inspect", "--format", "{{.Image}}", container], cwd=root
                ).stdout.strip()
                detail = _run(
                    [
                        "docker",
                        "image",
                        "inspect",
                        "--format",
                        "{{json .}}",
                        image_id,
                    ],
                    cwd=root,
                ).stdout
                metadata = json.loads(detail)
                images[service] = {"id": metadata["Id"], "size": metadata["Size"]}
        except Exception as error:
            safe = str(error).replace(password, "<redacted>").replace(canary, "<redacted>")
            raise VerificationError(safe) from error
        finally:
            _run(
                [*compose, "down", "--volumes", "--remove-orphans"],
                cwd=root,
                timeout=120,
                check=False,
            )

    report = {
        "gate": "B05 Gate 2 runtime evidence",
        "status": "passed",
        "project_name": project,
        "platform": f"{sys.platform}/{platform.machine()}",
        "timings": timings,
        "images": images,
        "checks": [
            "clean-room config/build and five-service startup",
            "public Health/Search remain 503",
            "non-empty Add, exact replay and two-user Cube isolation",
            "valid-empty and invalid-schema fail-closed behavior",
            "model-delay Add-wide deadline",
            "restart persistence without duplicate provider memory",
            "non-root/resource/port/log controls",
            "secret and content canary absent from aggregate logs",
        ],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name")
    parser.add_argument("--public-port", type=int, default=18080)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--pip-index-url", default="https://pypi.org/simple")
    parser.add_argument("--build-timeout", type=float, default=1800)
    parser.add_argument("--health-timeout", type=float, default=180)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.public_port <= 65535 or args.samples < 1:
        print("verification failed: invalid port or sample count", file=sys.stderr)
        return 2
    try:
        report = verify(args)
    except (VerificationError, subprocess.TimeoutExpired) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

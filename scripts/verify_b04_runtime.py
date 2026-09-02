#!/usr/bin/env python3
"""Verify the approved B04 three-service runtime in an isolated Compose project."""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLEAN_ROOM_PATHS = (
    ".dockerignore",
    "compose.yaml",
    "docker",
    "third_party",
)


class VerificationError(RuntimeError):
    """Raised when a B04 lifecycle invariant is not met."""


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: float = 120.0,
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


def _compose_prefix(root: Path, env_file: Path, project_name: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "--file",
        str(root / "compose.yaml"),
        "--env-file",
        str(env_file),
        "--project-name",
        project_name,
    ]


def _copy_clean_room(source_root: Path, destination: Path) -> None:
    for relative in CLEAN_ROOM_PATHS:
        source = source_root / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _service_container_id(compose: list[str], root: Path, service: str) -> str:
    result = _run([*compose, "ps", "--quiet", service], cwd=root)
    container_id = result.stdout.strip()
    if not container_id:
        raise VerificationError(f"Compose did not return a container for service {service!r}")
    return container_id


def _wait_healthy(
    compose: list[str], root: Path, services: tuple[str, ...], timeout: float
) -> None:
    deadline = time.monotonic() + timeout
    last_status: dict[str, str] = {}
    while time.monotonic() < deadline:
        all_healthy = True
        for service in services:
            container_id = _service_container_id(compose, root, service)
            result = _run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                    container_id,
                ],
                cwd=root,
            )
            status = result.stdout.strip()
            last_status[service] = status
            all_healthy = all_healthy and status == "healthy"
        if all_healthy:
            return
        time.sleep(1.0)
    raise VerificationError(f"services did not become healthy in {timeout:.0f}s: {last_status}")


def _exec_memos_python(compose: list[str], root: Path, source: str) -> str:
    result = _run(
        [*compose, "exec", "-T", "memos", "python", "-c", source],
        cwd=root,
        timeout=30.0,
    )
    return result.stdout.strip()


def _exec_neo4j(compose: list[str], root: Path, query: str) -> str:
    command = f'cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain {json.dumps(query)}'
    result = _run(
        [*compose, "exec", "-T", "neo4j", "sh", "-c", command],
        cwd=root,
        timeout=30.0,
    )
    return result.stdout.strip()


def _probe_aggregate(compose: list[str], root: Path) -> None:
    _exec_memos_python(
        compose,
        root,
        "import json, urllib.request; "
        "m=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)); "
        "assert m.get('status') == 'healthy'; "
        "q=urllib.request.urlopen('http://qdrant:6333/readyz', timeout=3); "
        "assert q.status == 200",
    )
    neo4j_output = _exec_neo4j(compose, root, "RETURN 1 AS ready;")
    if "1" not in neo4j_output:
        raise VerificationError(f"unexpected Neo4j readiness response: {neo4j_output!r}")


def _assert_no_published_ports(compose: list[str], root: Path) -> None:
    for service in ("memos", "neo4j", "qdrant"):
        container_id = _service_container_id(compose, root, service)
        output = _run(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container_id],
            cwd=root,
        ).stdout.strip()
        ports = json.loads(output or "{}")
        if any(bindings for bindings in ports.values()):
            raise VerificationError(f"service {service!r} unexpectedly publishes a host port")


def _resolved_container_images(compose: list[str], root: Path) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for service in ("memos", "neo4j", "qdrant"):
        container_id = _service_container_id(compose, root, service)
        image_id = _run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Image}}",
                container_id,
            ],
            cwd=root,
        ).stdout.strip()
        resolved[service] = _run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}} {{.Os}}/{{.Architecture}}",
                image_id,
            ],
            cwd=root,
        ).stdout.strip()
    return resolved


def _assert_internal_network(compose: list[str], root: Path) -> None:
    project = compose[compose.index("--project-name") + 1]
    network_id = _run(
        [
            "docker",
            "network",
            "ls",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.network=backend",
        ],
        cwd=root,
    ).stdout.strip()
    if not network_id or "\n" in network_id:
        raise VerificationError("could not resolve exactly one B04 backend network")
    internal = _run(
        ["docker", "network", "inspect", "--format", "{{.Internal}}", network_id], cwd=root
    ).stdout.strip()
    if internal != "true":
        raise VerificationError("B04 backend network is not internal")


def _create_persistence_markers(compose: list[str], root: Path) -> None:
    _exec_memos_python(
        compose,
        root,
        "from pathlib import Path; "
        "Path('/var/lib/memos/b04-persistence-marker').write_text('persisted', encoding='utf-8')",
    )
    _exec_memos_python(
        compose,
        root,
        "import json, urllib.request; "
        "data=json.dumps({'vectors': {'size': 1, 'distance': 'Cosine'}}).encode(); "
        "req=urllib.request.Request('http://qdrant:6333/collections/b04_persistence_probe', "
        "data=data, method='PUT', headers={'Content-Type':'application/json'}); "
        "assert urllib.request.urlopen(req, timeout=5).status == 200",
    )
    _exec_neo4j(
        compose,
        root,
        "MERGE (n:B04Probe {id: 'restart'}) SET n.value = 'persisted' RETURN n.value;",
    )


def _assert_persistence_markers(compose: list[str], root: Path) -> None:
    marker = _exec_memos_python(
        compose,
        root,
        "from pathlib import Path; "
        "assert Path('/var/lib/memos/b04-persistence-marker').read_text(encoding='utf-8') "
        "== 'persisted'",
    )
    if marker:
        raise VerificationError(f"unexpected MemOS marker output: {marker!r}")
    _exec_memos_python(
        compose,
        root,
        "import json, urllib.request; "
        "d=json.load(urllib.request.urlopen("
        "'http://qdrant:6333/collections/b04_persistence_probe', timeout=5)); "
        "assert d.get('result', {}).get('status') in {'green', 'yellow'}",
    )
    neo4j_output = _exec_neo4j(
        compose,
        root,
        "MATCH (n:B04Probe {id: 'restart'}) RETURN n.value AS value;",
    )
    if "persisted" not in neo4j_output:
        raise VerificationError("Neo4j marker was not retained across Compose restart")


def _assert_memos_collection(compose: list[str], root: Path, expected_dimension: int) -> None:
    output = _exec_memos_python(
        compose,
        root,
        "import json, urllib.request; "
        "d=json.load(urllib.request.urlopen("
        "'http://qdrant:6333/collections/neo4j_vec_db', timeout=5)); "
        "p=d.get('result', {}).get('config', {}).get('params', {}); "
        "print(json.dumps(p.get('vectors'))) ",
    )
    vectors = json.loads(output)
    actual_dimension = vectors.get("size") if isinstance(vectors, dict) else None
    if actual_dimension != expected_dimension:
        raise VerificationError(
            "MemOS Qdrant collection dimension is "
            f"{actual_dimension!r}, expected {expected_dimension}"
        )


def _assert_fault_recovery(compose: list[str], root: Path, health_timeout: float) -> None:
    _run([*compose, "stop", "qdrant"], cwd=root, timeout=60.0)
    try:
        _probe_aggregate(compose, root)
    except (VerificationError, subprocess.TimeoutExpired):
        pass
    else:
        raise VerificationError("aggregate readiness remained successful while Qdrant was stopped")
    _run([*compose, "start", "qdrant"], cwd=root, timeout=60.0)
    _wait_healthy(compose, root, ("qdrant",), health_timeout)
    _probe_aggregate(compose, root)


def verify_lifecycle(args: argparse.Namespace) -> dict[str, Any]:
    if shutil.which("docker") is None:
        raise VerificationError("Docker CLI is not installed; lifecycle verification cannot run")
    version = _run(["docker", "compose", "version", "--short"], cwd=REPOSITORY_ROOT)
    docker_server = _run(["docker", "version", "--format", "{{json .Server}}"], cwd=REPOSITORY_ROOT)
    project_name = args.project_name or f"memscope_b04_gate_{secrets.token_hex(4)}"
    if not project_name.startswith("memscope_b04_gate_"):
        raise VerificationError("project name must start with 'memscope_b04_gate_'")

    timings: dict[str, float] = {}
    resolved_images: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="memscope-b04-clean-room-") as clean_room_name:
        clean_room = Path(clean_room_name)
        _copy_clean_room(REPOSITORY_ROOT, clean_room)
        env_file = clean_room / "b04.env"
        neo4j_password = secrets.token_urlsafe(24)
        env_file.write_text(
            f"NEO4J_PASSWORD={neo4j_password}\n"
            f"B04_BOOTSTRAP_EMBEDDING_DIMENSION={args.embedding_dimension}\n",
            encoding="utf-8",
        )
        compose = _compose_prefix(clean_room, env_file, project_name)
        try:
            try:
                _run([*compose, "config", "--quiet"], cwd=clean_room)

                started = time.monotonic()
                _run([*compose, "build", "--pull"], cwd=clean_room, timeout=args.build_timeout)
                timings["build_seconds"] = round(time.monotonic() - started, 3)

                started = time.monotonic()
                _run([*compose, "up", "--detach"], cwd=clean_room, timeout=120.0)
                _wait_healthy(
                    compose,
                    clean_room,
                    ("neo4j", "qdrant", "memos"),
                    args.health_timeout,
                )
                timings["cold_start_seconds"] = round(time.monotonic() - started, 3)

                _probe_aggregate(compose, clean_room)
                _assert_memos_collection(compose, clean_room, args.embedding_dimension)
                _assert_no_published_ports(compose, clean_room)
                _assert_internal_network(compose, clean_room)
                resolved_images = _resolved_container_images(compose, clean_room)
                _create_persistence_markers(compose, clean_room)

                started = time.monotonic()
                _run([*compose, "restart"], cwd=clean_room, timeout=120.0)
                _wait_healthy(
                    compose,
                    clean_room,
                    ("neo4j", "qdrant", "memos"),
                    args.health_timeout,
                )
                timings["restart_seconds"] = round(time.monotonic() - started, 3)
                _probe_aggregate(compose, clean_room)
                _assert_persistence_markers(compose, clean_room)
                _assert_fault_recovery(compose, clean_room, args.health_timeout)

                logs = _run([*compose, "logs", "--no-color"], cwd=clean_room).stdout
                if neo4j_password in logs:
                    raise VerificationError("generated Neo4j password appeared in runtime logs")
            except Exception as exc:
                log_result = _run(
                    [*compose, "logs", "--no-color", "--tail", "200"],
                    cwd=clean_room,
                    timeout=30.0,
                    check=False,
                )
                safe_logs = "\n".join((log_result.stdout, log_result.stderr)).replace(
                    neo4j_password, "<redacted>"
                )
                raise VerificationError(f"{exc}\nlast Compose logs:\n{safe_logs.strip()}") from exc
        finally:
            _run(
                [*compose, "down", "--volumes", "--remove-orphans"],
                cwd=clean_room,
                timeout=120.0,
                check=False,
            )

    report: dict[str, Any] = {
        "gate": "B04 Gate 2 runtime evidence",
        "status": "passed",
        "compose_version": version.stdout.strip(),
        "docker_server": json.loads(docker_server.stdout),
        "project_name": project_name,
        "platform": f"{sys.platform}/{platform.machine()}",
        "resolved_container_images": resolved_images,
        "embedding_dimension": args.embedding_dimension,
        "timings": timings,
        "checks": [
            "clean-room Compose config and build",
            "dependency-gated cold start",
            "aggregate MemOS/Qdrant/Neo4j readiness",
            "MemOS-created Qdrant collection",
            "no published host ports",
            "internal-only runtime network",
            "named-volume persistence across restart",
            "Qdrant stop detection and recovery",
        ],
    }
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name")
    parser.add_argument("--embedding-dimension", type=int, default=16)
    parser.add_argument("--build-timeout", type=float, default=1800.0)
    parser.add_argument("--health-timeout", type=float, default=180.0)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.embedding_dimension <= 0:
        print("verification failed: embedding dimension must be positive", file=sys.stderr)
        return 2
    try:
        report = verify_lifecycle(args)
    except (VerificationError, subprocess.TimeoutExpired) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

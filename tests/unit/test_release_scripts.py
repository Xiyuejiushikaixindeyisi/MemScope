from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = ROOT / "scripts" / "run_release.sh"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_release.sh"
STOP_SCRIPT = ROOT / "scripts" / "stop_release.sh"
DOCKER_HELPER = ROOT / "scripts" / "lib" / "rootful_docker.sh"
COMMIT = "a" * 40
IMAGE_IDS = {
    "memscope/memory-api:b10-release": f"sha256:{'1' * 64}",
    "memscope/memos:2.0.32-b10-release": f"sha256:{'2' * 64}",
    "neo4j:5.26.6-community": f"sha256:{'3' * 64}",
    "qdrant/qdrant:v1.15.3": f"sha256:{'4' * 64}",
}


def test_release_compose_is_four_service_load_only_topology() -> None:
    compose = (ROOT / "compose.release.yaml").read_text(encoding="utf-8")
    service_block = compose.split("\nservices:\n", maxsplit=1)[1].split(
        "\nnetworks:\n", maxsplit=1
    )[0]
    service_names = [
        line.removeprefix("  ").removesuffix(":")
        for line in service_block.splitlines()
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")
    ]
    assert service_names == ["memory-api", "neo4j", "qdrant", "memos"]
    assert "\n    build:" not in compose
    assert compose.count("pull_policy: never") == 4
    assert "memscope/memory-api:b10-release" in compose
    assert "memscope/memos:2.0.32-b10-release" in compose

    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "compose.env" in dockerignore
    assert "deploy/*.env" in dockerignore


def test_organizer_entrypoints_need_no_public_download_path() -> None:
    entrypoints = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (RUN_SCRIPT, VERIFY_SCRIPT, STOP_SCRIPT, DOCKER_HELPER)
    )
    for forbidden_command in (
        "docker pull ",
        "docker build ",
        "docker compose build",
        "pip install",
        "uv sync",
        "curl ",
        "wget ",
    ):
        assert forbidden_command not in entrypoints
    assert 'load --input "${IMAGE_BUNDLE}"' in entrypoints
    assert "--no-build --pull never" in entrypoints
    assert "rootful Docker daemon is required" in entrypoints
    assert "must stay under the ordinary operator HOME" in entrypoints

    quickstart = (ROOT / "ORGANIZER_QUICKSTART.md").read_text(encoding="utf-8")
    assert "不依赖公网、镜像仓库、PyPI、源码站点" in quickstart
    assert "唯一需要的网络" in quickstart
    assert "model_api_unreachable" in quickstart


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _write_env(path: Path, *, allow_http: bool = True) -> None:
    path.write_text(
        "\n".join(
            (
                "NEO4J_PASSWORD=strong-password",
                "MEMSCOPE_MODEL_PROFILE=gateway",
                f"MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP={'true' if allow_http else 'false'}",
                "MEMRADER_MODEL=reader-model",
                "MEMRADER_API_BASE=http://models.invalid/v1",
                "MEMRADER_API_KEY=reader-secret",
                "MOS_EMBEDDER_MODEL=embedding-model",
                "MOS_EMBEDDER_API_BASE=http://models.invalid/v1",
                "MOS_EMBEDDER_API_KEY=embedding-secret",
                "EMBEDDING_DIMENSION=1024",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _write_lock(path: Path, *, mismatch: bool = False) -> None:
    lines = ["# memscope.release-lock.v1"]
    records = (
        (
            "memory-api",
            "memscope/memory-api:b10-release",
            IMAGE_IDS["memscope/memory-api:b10-release"],
            COMMIT,
        ),
        (
            "memos",
            "memscope/memos:2.0.32-b10-release",
            IMAGE_IDS["memscope/memos:2.0.32-b10-release"],
            COMMIT,
        ),
        ("neo4j", "neo4j:5.26.6-community", IMAGE_IDS["neo4j:5.26.6-community"], "-"),
        ("qdrant", "qdrant/qdrant:v1.15.3", IMAGE_IDS["qdrant/qdrant:v1.15.3"], "-"),
    )
    for role, reference, image_id, revision in records:
        if mismatch and role == "qdrant":
            image_id = f"sha256:{'9' * 64}"
        lines.append("\t".join((role, reference, image_id, revision)))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fake_docker(directory: Path, log: Path, *, image_platform: str = "linux/amd64") -> None:
    cases = "\n".join(
        f'    "{reference}") printf "%s\\n" "{image_id}" ;;'
        for reference, image_id in IMAGE_IDS.items()
    )
    _write_executable(
        directory / "docker",
        f"""#!/usr/bin/env bash
set -eu
printf 'docker %s\\n' "$*" >> {log!s}
if [[ "$*" == "compose version --short" ]]; then printf '2.40.0\\n'; exit 0; fi
if [[ "$*" == "info --format {{{{json .SecurityOptions}}}}" ]]; then
  printf '%s\\n' "${{FAKE_DOCKER_SECURITY_OPTIONS:-[]}}"
  exit 0
fi
if [[ "$*" == *"image inspect --format {{{{.Id}}}} "* ]]; then
  case "${{@: -1}}" in
{cases}
  esac
  exit 0
fi
if [[ "$*" == *"org.opencontainers.image.revision"* ]]; then printf '%s\\n' "{COMMIT}"; exit 0; fi
if [[ "$*" == *"image inspect --format {{{{.Os}}}}/{{{{.Architecture}}}} "* ]]; then
  printf '%s\\n' "{image_platform}"
  exit 0
fi
if [[ "$*" == *" ps --quiet "* ]]; then printf 'container-id\\n'; exit 0; fi
if [[ "$*" == "inspect --format {{{{.State.Running}}}} container-id" ]]; then
  printf 'true\\n'
  exit 0
fi
if [[ "$*" == *"State.Health.Status"* ]]; then printf 'healthy\\n'; exit 0; fi
if [[ "$*" == *" port memory-api 8080" ]]; then printf '0.0.0.0:18080\\n'; exit 0; fi
exit 0
""",
    )
    _write_executable(directory / "sudo", "#!/usr/bin/env bash\\nexit 1\\n")


def _run(
    tmp_path: Path,
    script: Path,
    *arguments: str,
    image_platform: str = "linux/amd64",
    docker_security_options: str = "[]",
) -> tuple[subprocess.CompletedProcess[str], str]:
    solution = tmp_path / "solution"
    (solution / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (solution / "code" / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "compose.release.yaml", solution / "compose.release.yaml")
    shutil.copy2(script, solution / "scripts" / script.name)
    shutil.copy2(DOCKER_HELPER, solution / "scripts" / "lib" / DOCKER_HELPER.name)
    shutil.copy2(
        ROOT / "scripts" / "verify_b06_candidate.py",
        solution / "code" / "scripts" / "verify_b06_candidate.py",
    )
    copied_script = solution / "scripts" / script.name
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    log = tmp_path / "commands.log"
    _fake_docker(fake_bin, log, image_platform=image_platform)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["HOME"] = str(tmp_path)
    environment["FAKE_DOCKER_SECURITY_OPTIONS"] = docker_security_options
    result = subprocess.run(
        [str(copied_script), *arguments],
        cwd=solution,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


def test_run_release_rejects_rootless_daemon(tmp_path: Path) -> None:
    env_file = tmp_path / "organizer.env"
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    _write_env(env_file)
    _write_lock(lock_file)

    result, commands = _run(
        tmp_path,
        RUN_SCRIPT,
        "--skip-load",
        "--lock-file",
        str(lock_file),
        "--env-file",
        str(env_file),
        docker_security_options='["name=rootless"]',
    )

    assert result.returncode != 0
    assert "a rootful Docker daemon is required" in result.stderr
    assert " up --detach" not in commands


def test_run_release_rejects_host_path_outside_operator_home(tmp_path: Path) -> None:
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    _write_lock(lock_file)

    result, commands = _run(
        tmp_path,
        RUN_SCRIPT,
        "--skip-load",
        "--lock-file",
        str(lock_file),
        "--env-file",
        "/etc/hosts",
    )

    assert result.returncode != 0
    assert "must stay under the ordinary operator HOME" in result.stderr
    assert commands == ""


def test_run_release_loads_and_starts_without_build_or_registry_pull(tmp_path: Path) -> None:
    env_file = tmp_path / "organizer.env"
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    bundle = tmp_path / "images.tar"
    sums = tmp_path / "SHA256SUMS"
    _write_env(env_file)
    _write_lock(lock_file)
    bundle.write_bytes(b"image bundle")
    sums.write_text(f"{hashlib.sha256(bundle.read_bytes()).hexdigest()}  {bundle.name}\n")

    result, commands = _run(
        tmp_path,
        RUN_SCRIPT,
        "--image-bundle",
        str(bundle),
        "--sha256-file",
        str(sums),
        "--lock-file",
        str(lock_file),
        "--env-file",
        str(env_file),
    )

    assert result.returncode == 0, result.stderr
    assert "docker load --input" in commands
    assert "image inspect --format {{.Os}}/{{.Architecture}}" in commands
    assert " up --detach --no-build --pull never --wait" in commands
    assert " compose build" not in commands
    assert " docker pull" not in commands
    assert "MemScope release started" in result.stdout


def test_run_release_rejects_image_identity_mismatch_before_start(tmp_path: Path) -> None:
    env_file = tmp_path / "organizer.env"
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    bundle = tmp_path / "images.tar"
    _write_env(env_file)
    _write_lock(lock_file, mismatch=True)
    bundle.write_bytes(b"image bundle")

    result, commands = _run(
        tmp_path,
        RUN_SCRIPT,
        "--image-bundle",
        str(bundle),
        "--lock-file",
        str(lock_file),
        "--env-file",
        str(env_file),
    )

    assert result.returncode != 0
    assert "loaded image ID does not match" in result.stderr
    assert " up --detach" not in commands


def test_run_release_rejects_non_amd64_image_before_start(tmp_path: Path) -> None:
    env_file = tmp_path / "organizer.env"
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    _write_env(env_file)
    _write_lock(lock_file)

    result, commands = _run(
        tmp_path,
        RUN_SCRIPT,
        "--skip-load",
        "--lock-file",
        str(lock_file),
        "--env-file",
        str(env_file),
        image_platform="linux/arm64",
    )

    assert result.returncode != 0
    assert "platform is not linux/amd64" in result.stderr
    assert " up --detach" not in commands


def test_run_release_requires_explicit_opt_in_for_http_models(tmp_path: Path) -> None:
    env_file = tmp_path / "organizer.env"
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    _write_env(env_file, allow_http=False)
    _write_lock(lock_file)

    result, _ = _run(
        tmp_path,
        RUN_SCRIPT,
        "--skip-load",
        "--lock-file",
        str(lock_file),
        "--env-file",
        str(env_file),
    )

    assert result.returncode != 0
    assert "HTTP model endpoints require" in result.stderr


@pytest.mark.parametrize("mode", [0o640, 0o644])
def test_run_release_rejects_visible_private_env(tmp_path: Path, mode: int) -> None:
    env_file = tmp_path / "organizer.env"
    lock_file = tmp_path / "RELEASE_LOCK.tsv"
    _write_env(env_file)
    env_file.chmod(mode)
    _write_lock(lock_file)

    result, _ = _run(
        tmp_path,
        RUN_SCRIPT,
        "--skip-load",
        "--lock-file",
        str(lock_file),
        "--env-file",
        str(env_file),
    )
    assert result.returncode != 0
    assert "mode 0600 or stricter" in result.stderr


def test_verify_and_stop_use_container_runtime_and_preserve_volumes(tmp_path: Path) -> None:
    env_file = tmp_path / "organizer.env"
    _write_env(env_file)

    verified, verify_commands = _run(tmp_path, VERIFY_SCRIPT, "--env-file", str(env_file))
    assert verified.returncode == 0, verified.stderr
    assert " exec -T neo4j" in verify_commands
    assert " exec -T memos python -c" in verify_commands
    assert " exec -T memory-api python -" in verify_commands
    assert "Release verification passed" in verified.stdout

    stopped, stop_commands = _run(tmp_path, STOP_SCRIPT, "--env-file", str(env_file))
    assert stopped.returncode == 0, stopped.stderr
    assert " down --remove-orphans --timeout 30" in stop_commands
    assert "down -v" not in stop_commands
    assert "named volumes were preserved" in stopped.stdout

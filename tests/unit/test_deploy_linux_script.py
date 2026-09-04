from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/deploy_linux.sh"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _write_env(path: Path, *, placeholder: bool = False) -> None:
    reader_model = "replace-with-model" if placeholder else "reader-model"
    path.write_text(
        "\n".join(
            (
                "NEO4J_PASSWORD=strong-password",
                "MEMSCOPE_MODEL_PROFILE=gateway",
                f"MEMRADER_MODEL={reader_model}",
                "MEMRADER_API_BASE=https://models.invalid/v1",
                "MEMRADER_API_KEY=reader-secret",
                "MOS_EMBEDDER_MODEL=embedding-model",
                "MOS_EMBEDDER_API_BASE=https://models.invalid/v1",
                "MOS_EMBEDDER_API_KEY=embedding-secret",
                "EMBEDDING_DIMENSION=1024",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _write_internal_http_env(path: Path, *, allow: bool) -> None:
    _write_env(path)
    source = path.read_text(encoding="utf-8").replace("https://models.invalid", "http://models")
    if allow:
        source += "MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true\n"
    path.write_text(source, encoding="utf-8")


def _fake_commands(directory: Path, log: Path) -> None:
    _write_executable(
        directory / "uv",
        f"""#!/usr/bin/env bash
set -eu
printf 'uv %s\\n' "$*" >> {log!s}
if [[ "${{1:-}}" == "--version" ]]; then
    printf 'uv 0.12.9 (x86_64-unknown-linux-gnu)\\n'
fi
exit 0
""",
    )
    _write_executable(
        directory / "docker",
        f"""#!/usr/bin/env bash
set -eu
printf 'docker %s\\n' "$*" >> {log!s}
if [[ "${{FAKE_DOCKER_COMPOSE_UNAVAILABLE:-0}}" == "1" && "$*" == "compose version" ]]; then
    exit 1
fi
if [[ "$*" == "compose version --short" ]]; then
    printf '%s\\n' "${{FAKE_COMPOSE_VERSION:-2.40.0}}"
fi
if [[ "$*" == *" port memory-api 8080" ]]; then
    printf '0.0.0.0:18080\\n'
fi
exit 0
""",
    )
    _write_executable(
        directory / "docker-compose",
        f"""#!/usr/bin/env bash
set -eu
printf 'docker-compose %s\\n' "$*" >> {log!s}
if [[ "$*" == "version --short" ]]; then
    printf '%s\\n' "${{FAKE_COMPOSE_VERSION:-2.40.0}}"
fi
if [[ "$*" == *" port memory-api 8080" ]]; then
    printf '0.0.0.0:18080\\n'
fi
exit 0
""",
    )


def _run_script(
    tmp_path: Path,
    *arguments: str,
    environment_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "commands.log"
    _fake_commands(fake_bin, log)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment.update(environment_overrides or {})
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_deploy_runs_locked_sync_build_start_and_health(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_env(env_file)

    result = _run_script(tmp_path, "--env-file", str(env_file), "--project", "test-project")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert "uv sync --frozen" in commands
    assert " config --quiet" in commands
    assert " build memory-api memos" in commands
    assert " up --detach --pull missing --wait --wait-timeout 300" in commands
    assert " port memory-api 8080" in commands
    assert " ps" in commands
    assert "MemScope deployment completed successfully" in result.stdout


def test_check_only_does_not_sync_build_or_start(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_env(env_file)

    result = _run_script(tmp_path, "--env-file", str(env_file), "--check-only")

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert " config --quiet" in commands
    assert "uv sync --frozen" not in commands
    assert " build " not in commands
    assert " up " not in commands


def test_accepts_explicitly_allowed_internal_http_model_endpoints(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_internal_http_env(env_file, allow=True)

    result = _run_script(tmp_path, "--env-file", str(env_file), "--check-only")

    assert result.returncode == 0, result.stderr


def test_rejects_internal_http_without_explicit_opt_in(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_internal_http_env(env_file, allow=False)

    result = _run_script(tmp_path, "--env-file", str(env_file), "--check-only")

    assert result.returncode != 0
    assert "HTTP model endpoints require MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true" in result.stderr


def test_falls_back_to_standalone_docker_compose(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_env(env_file)

    result = _run_script(
        tmp_path,
        "--env-file",
        str(env_file),
        "--check-only",
        environment_overrides={"FAKE_DOCKER_COMPOSE_UNAVAILABLE": "1"},
    )

    assert result.returncode == 0, result.stderr
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert "docker-compose --project-directory" in commands
    assert "docker-compose version" in commands


def test_rejects_legacy_compose_v1(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_env(env_file)

    result = _run_script(
        tmp_path,
        "--env-file",
        str(env_file),
        "--check-only",
        environment_overrides={"FAKE_COMPOSE_VERSION": "1.29.2"},
    )

    assert result.returncode != 0
    assert "Docker Compose v2 or newer is required" in result.stderr


def test_missing_env_is_created_from_template_and_opened_in_editor(tmp_path: Path) -> None:
    valid_env = tmp_path / "valid.env"
    _write_env(valid_env)
    editor = tmp_path / "fake-editor"
    _write_executable(
        editor,
        """#!/usr/bin/env bash
set -eu
cp "${VALID_ENV}" "$1"
chmod 0600 "$1"
""",
    )
    destination = tmp_path / "private" / "memscope.env"

    result = _run_script(
        tmp_path,
        "--env-file",
        str(destination),
        "--check-only",
        environment_overrides={"EDITOR": str(editor), "VALID_ENV": str(valid_env)},
    )

    assert result.returncode == 0, result.stderr
    assert destination.is_file()
    assert destination.stat().st_mode & 0o777 == 0o600
    assert "Created" in result.stdout
    assert "Preflight checks passed" in result.stdout


def test_default_env_is_created_in_config_directory(tmp_path: Path) -> None:
    valid_env = tmp_path / "valid.env"
    _write_env(valid_env)
    editor = tmp_path / "fake-editor"
    _write_executable(
        editor,
        """#!/usr/bin/env bash
set -eu
cp "${VALID_ENV}" "$1"
chmod 0600 "$1"
""",
    )
    config_dir = tmp_path / "config"

    result = _run_script(
        tmp_path,
        "--check-only",
        environment_overrides={
            "EDITOR": str(editor),
            "VALID_ENV": str(valid_env),
            "MEMSCOPE_CONFIG_DIR": str(config_dir),
        },
    )

    assert result.returncode == 0, result.stderr
    destination = config_dir / "compose.env"
    assert destination.is_file()
    assert destination.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("mode", [0o640, 0o644])
def test_rejects_env_files_visible_to_other_users(tmp_path: Path, mode: int) -> None:
    env_file = tmp_path / "memscope.env"
    _write_env(env_file)
    env_file.chmod(mode)

    result = _run_script(tmp_path, "--env-file", str(env_file), "--check-only")

    assert result.returncode != 0
    assert "must not be accessible by group/others" in result.stderr


def test_rejects_placeholder_configuration(tmp_path: Path) -> None:
    env_file = tmp_path / "memscope.env"
    _write_env(env_file, placeholder=True)

    result = _run_script(tmp_path, "--env-file", str(env_file), "--check-only")

    assert result.returncode != 0
    assert "still contains a placeholder: MEMRADER_MODEL" in result.stderr

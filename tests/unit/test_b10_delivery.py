"""Deterministic tests for the active B10 ZIP/image delivery builder."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest


def _load_builder() -> Any:
    path = Path(__file__).parents[2] / "scripts" / "build_candidate_delivery.py"
    spec = importlib.util.spec_from_file_location("memscope_b10_delivery", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load B10 delivery builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()
_COMMIT = "a" * 40


def _write(root: Path, relative: str, payload: bytes = b"fixture\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _write_memos_archive(root: Path, payload: bytes = b"safe upstream fixture\n") -> None:
    archive_relative = "third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz"
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as package:
        info = tarfile.TarInfo("MemoryOS-v2.0.32-185ebdb/src/memos/safe.py")
        info.size = len(payload)
        info.mtime = 0
        package.addfile(info, io.BytesIO(payload))
    archive_payload = stream.getvalue()
    _write(root, archive_relative, archive_payload)
    allowlist = {
        "archive": Path(archive_relative).name,
        "archive_sha256": hashlib.sha256(archive_payload).hexdigest(),
        "reviewed_matches": [],
    }
    _write(
        root,
        "third_party/memos/SECRET_SCAN_ALLOWLIST.json",
        (json.dumps(allowlist) + "\n").encode(),
    )


def _source_tree(root: Path) -> Path:
    for relative in builder._DIRECT_FILES:
        _write(root, relative)
    for relative in builder._CODE_ROOT_FILES:
        _write(root, relative)
    for relative in builder._CODE_DIRECTORIES:
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        if not any(path.is_file() for path in directory.rglob("*")):
            _write(root, f"{relative}/fixture.txt")
    _write(root, "scripts/run_release.sh", b"#!/bin/sh\nexit 0\n").chmod(0o755)
    _write(root, "scripts/verify_release.sh", b"#!/bin/sh\nexit 0\n").chmod(0o755)
    _write(root, "scripts/stop_release.sh", b"#!/bin/sh\nexit 0\n").chmod(0o755)
    _write(root, "scripts/lib/rootful_docker.sh", b"#!/bin/sh\nexit 0\n").chmod(0o755)
    _write_memos_archive(root)
    _write(root, ".env", b"API_KEY=this-file-must-not-be-selected\n")
    _write(root, "deploy/private.env", b"API_KEY=this-file-must-not-be-selected\n")
    _write(root, "src/__pycache__/ignored.pyc")
    return root


def _images() -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "reference": reference,
            "image_id": f"sha256:{str(index) * 64}",
            "source_revision": _COMMIT if custom else None,
            "platform": "linux/amd64",
            "repo_digests": [builder._UPSTREAM_REPO_DIGEST[role]]
            if role in builder._UPSTREAM_REPO_DIGEST
            else [],
        }
        for index, (role, reference, custom) in enumerate(builder._IMAGE_ROLES, start=1)
    ]


def test_delivery_builder_selects_rootful_sudo_without_rootless_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    executables = {
        "docker": "/usr/bin/docker",
        "env": "/usr/bin/env",
        "sudo": "/usr/bin/sudo",
    }

    monkeypatch.setattr(builder.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(builder.shutil, "which", executables.get)

    def fake_run(command: list[str], **_: Any) -> str:
        commands.append(command)
        return '["name=rootless"]' if command[0] == "/usr/bin/docker" else "[]"

    monkeypatch.setattr(builder, "_run", fake_run)

    assert builder._docker_command() == [
        "/usr/bin/env",
        "-u",
        "DOCKER_HOST",
        "-u",
        "DOCKER_CONTEXT",
        "/usr/bin/sudo",
        "-n",
        "--",
        "/usr/bin/docker",
    ]
    assert len(commands) == 2


def test_delivery_builder_rejects_running_whole_process_as_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builder.os, "geteuid", lambda: 0)

    with pytest.raises(builder.DeliveryError, match="ordinary operator"):
        builder._docker_command()


def test_solution_zip_is_deterministic_complete_and_verifiable(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    builder.write_solution_archive(first, root=source, candidate_commit=_COMMIT, images=_images())
    builder.write_solution_archive(second, root=source, candidate_commit=_COMMIT, images=_images())

    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )
    result = builder.verify_solution_archive(first)
    assert result["status"] == "passed"
    assert result["candidate_commit"] == _COMMIT
    with zipfile.ZipFile(first) as package:
        names = set(package.namelist())
        lock = package.read("solution/RELEASE_LOCK.tsv").decode()
    assert "solution/ORGANIZER_AGENT_PROMPT.md" in names
    assert "solution/scripts/run_release.sh" in names
    assert "solution/scripts/lib/rootful_docker.sh" in names
    assert "solution/code/src/fixture.txt" in names
    assert "solution/code/third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz" in names
    assert "memory-api\tmemscope/memory-api:b10-release" in lock
    assert not any(name.endswith(("/.env", "private.env")) for name in names)
    assert not any("__pycache__" in name for name in names)


def test_expanded_vendor_scan_rejects_unreviewed_secret_pattern(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    _write_memos_archive(source, b"api_key=" + b"x" * 32 + b"\n")

    entries = builder.collect_entries(source)
    with pytest.raises(builder.DeliveryError, match="unreviewed assigned_secret"):
        builder._scan_entries(entries)


def test_source_collection_rejects_links_and_in_tree_output(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    (source / "src/link.py").symlink_to(source / "src/fixture.txt")
    with pytest.raises(builder.DeliveryError, match="symbolic links"):
        builder.collect_entries(source)
    with pytest.raises(builder.DeliveryError, match="outside the source tree"):
        builder._safe_output_directory(source, source / "artifacts")


def test_delivery_verifier_rejects_tampered_checksum(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    archive = delivery / f"solution-{_COMMIT[:12]}.zip"
    image_bundle = delivery / f"memscope-images-{_COMMIT[:12]}-linux-amd64.tar"
    builder.write_solution_archive(archive, root=source, candidate_commit=_COMMIT, images=_images())
    image_bundle.write_bytes(b"docker archive fixture")
    artifacts = [
        {
            "filename": archive.name,
            "kind": "solution_zip",
            "sha256": builder._sha256_file(archive),
            "size": archive.stat().st_size,
        },
        {
            "filename": image_bundle.name,
            "kind": "docker_image_bundle",
            "sha256": builder._sha256_file(image_bundle),
            "size": image_bundle.stat().st_size,
        },
    ]
    manifest = {
        "schema": builder.DELIVERY_SCHEMA,
        "candidate_commit": _COMMIT,
        "target_platform": "linux/amd64",
        "service_count": 4,
        "runtime_policy": {
            "build": False,
            "pull": False,
            "host_python": False,
            "rootful_docker": True,
            "operator_home_only": True,
        },
        "claims": {"official_score": False, "organizer_runtime_pass": False},
        "artifacts": artifacts,
        "images": _images(),
    }
    manifest_path = delivery / "delivery-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    sums = delivery / "SHA256SUMS"
    sums.write_text(
        "".join(
            f"{builder._sha256_file(path)}  {path.name}\n"
            for path in (archive, image_bundle, manifest_path)
        ),
        encoding="utf-8",
    )

    assert builder.verify_delivery(delivery)["status"] == "passed"
    sums.write_text(sums.read_text(encoding="utf-8").replace("a", "b", 1), encoding="utf-8")
    with pytest.raises(builder.DeliveryError, match="SHA256SUMS"):
        builder.verify_delivery(delivery)

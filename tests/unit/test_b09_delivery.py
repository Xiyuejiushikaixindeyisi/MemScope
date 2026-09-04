"""Deterministic tests for the B09 delivery artifact builder."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest


def _load_builder() -> Any:
    path = Path(__file__).parents[2] / "scripts" / "build_b09_delivery.py"
    spec = importlib.util.spec_from_file_location("memscope_b09_delivery", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load B09 delivery builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()
_COMMIT = "2498c904e97ab36d85a8596898996243460dae6f"


def _write(root: Path, relative: str, content: bytes = b"fixture\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _source_tree(root: Path) -> Path:
    for relative in builder._COMMON_ROOT_FILES + builder._HANDOFF_EXTRA_ROOT_FILES:
        _write(root, relative)
    for relative in (
        builder._REQUIRED_FILES + builder._HANDOFF_REQUIRED_FILES + builder._SUBMISSION_EXTRA_FILES
    ):
        _write(root, relative)
    for relative in builder._COMMON_DIRECTORIES + builder._HANDOFF_EXTRA_DIRECTORIES:
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        if not any(path.is_file() for path in directory.rglob("*")):
            _write(root, f"{relative}/fixture.txt")
    (root / "docker/memory-api/entrypoint.sh").chmod(0o755)
    (root / "docker/memos/entrypoint.sh").chmod(0o755)
    _write(root, "src/memscope/__pycache__/ignored.pyc")
    _write(root, "artifacts/ignored.zip")
    _write(root, ".env", f"API_KEY={'x' * 30}\n".encode())
    return root


def test_submission_build_is_deterministic_and_sidecar_verifies(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    first = builder.build_archive(
        root=source,
        output_directory=tmp_path / "first",
        mode="submission",
        candidate_commit=_COMMIT,
    )
    second = builder.build_archive(
        root=source,
        output_directory=tmp_path / "second",
        mode="submission",
        candidate_commit=_COMMIT,
    )

    assert first["archive_sha256"] == second["archive_sha256"]
    verified = builder.verify_archive(Path(first["archive"]), Path(first["sidecar"]))
    assert verified["status"] == "passed"
    assert verified["candidate_commit"] == _COMMIT

    with zipfile.ZipFile(first["archive"]) as package:
        names = set(package.namelist())
    assert "solution/INSTRUCTION.md" in names
    assert "solution/SDD.md" in names
    assert "solution/code/src/memscope/main.py" in names
    assert "solution/LICENSES/MemOS-Apache-2.0.txt" in names
    assert not any("tests/" in name for name in names)
    assert not any("评测集" in name for name in names)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


def test_handoff_contains_audit_material_but_no_forbidden_files(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    result = builder.build_archive(
        root=source,
        output_directory=tmp_path / "output",
        mode="handoff",
        candidate_commit=_COMMIT,
    )

    with zipfile.ZipFile(result["archive"]) as package:
        names = set(package.namelist())
        manifest = json.loads(package.read("memscope-b09-handoff/DELIVERY_MANIFEST.json"))
    assert "memscope-b09-handoff/docs/batches/B08/SYSTEM_VERIFICATION.md" in names
    assert "memscope-b09-handoff/scripts/verify_b08_system.py" in names
    assert any("评测集" in name for name in names)
    assert manifest["claims"] == {"live_system_pass": False, "official_score": False}
    assert manifest["pending_external_evidence"] == [
        "b08_live_exercise",
        "b08_restart_persistence",
        "b08_resource_observations",
        "real_model_baseline_and_tuning",
    ]
    assert not any("/.git/" in name or name.endswith("/.env") for name in names)


def test_builder_rejects_secret_symlink_and_in_tree_output(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "source")
    (source / "README.md").write_text(f"API_KEY={'a' * 30}\n", encoding="utf-8")
    with pytest.raises(builder.DeliveryError, match="potential secret"):
        builder.build_archive(
            root=source,
            output_directory=tmp_path / "secret-output",
            mode="submission",
            candidate_commit=_COMMIT,
        )

    (source / "README.md").write_text("safe fixture\n", encoding="utf-8")
    (source / "src/link.py").symlink_to(source / "src/memscope/main.py")
    with pytest.raises(builder.DeliveryError, match="symbolic links"):
        builder.collect_entries(source, "submission")
    (source / "src/link.py").unlink()

    with pytest.raises(builder.DeliveryError, match="outside the source tree"):
        builder.build_archive(
            root=source,
            output_directory=source / "artifacts",
            mode="submission",
            candidate_commit=_COMMIT,
        )


def test_verifier_rejects_path_traversal_and_wrong_sidecar(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as package:
        package.writestr("../escape.txt", "bad")
    with pytest.raises(builder.DeliveryError, match="unsafe path"):
        builder.verify_archive(unsafe)

    source = _source_tree(tmp_path / "source")
    result = builder.build_archive(
        root=source,
        output_directory=tmp_path / "output",
        mode="submission",
        candidate_commit=_COMMIT,
    )
    sidecar = Path(result["sidecar"])
    sidecar.write_text(f"{'0' * 64}  {Path(result['archive']).name}\n", encoding="utf-8")
    with pytest.raises(builder.DeliveryError, match="sidecar does not match"):
        builder.verify_archive(Path(result["archive"]), sidecar)

#!/usr/bin/env python3
"""Build and verify deterministic B09 handoff and submission archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

SCHEMA = "memscope.b09.delivery-manifest.v1"
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_ZIP_TIMESTAMP: Final = (2026, 9, 4, 0, 0, 0)
_CHUNK_SIZE = 1024 * 1024

_COMMON_ROOT_FILES = (
    ".dockerignore",
    ".env.example",
    ".python-version",
    "INSTRUCTION.md",
    "README.md",
    "SDD.md",
    "THIRD_PARTY_NOTICES.md",
    "compose.yaml",
    "pyproject.toml",
    "uv.lock",
)
_HANDOFF_EXTRA_ROOT_FILES = (
    ".gitignore",
    "MEMOS_BASELINE_IMPLEMENTATION_PLAN.md",
    "技术难题-Agent-Memory-任务书-1.0.md",
    "技术难题-Agent-Memory-调测指南-1.0.md",
)
_COMMON_DIRECTORIES = ("deploy", "docker", "src", "third_party/memos")
_HANDOFF_EXTRA_DIRECTORIES = (
    "docs",
    "scripts",
    "tests",
    "技术难题-Agent-Memory-评测集（开源）-1.0",
)
_REQUIRED_FILES = (
    "INSTRUCTION.md",
    "README.md",
    "SDD.md",
    "THIRD_PARTY_NOTICES.md",
    "compose.yaml",
    "pyproject.toml",
    "uv.lock",
    "deploy/compose.env.example",
    "docker/memory-api/Dockerfile",
    "docker/memory-api/entrypoint.sh",
    "docker/memory-api/requirements.txt",
    "docker/memos/Dockerfile",
    "docker/memos/PATCHSET_LOCK.json",
    "docker/memos/apply_patchset.py",
    "docker/memos/constraints.txt",
    "docker/memos/entrypoint.sh",
    "src/memscope/main.py",
    "third_party/memos/LICENSE",
    "third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz",
    "third_party/memos/SHA256SUMS",
    "third_party/memos/SOURCE_LOCK.json",
)
_HANDOFF_REQUIRED_FILES = (
    "docs/batches/B08/HANDOFF.md",
    "docs/batches/B08/SYSTEM_VERIFICATION.md",
    "docs/batches/B09/DELIVERY.md",
    "docs/collaboration/TRANSFER_MANIFEST_TEMPLATE.md",
    "docs/collaboration/TUNING_REPORT_TEMPLATE.md",
    "scripts/build_b09_delivery.py",
    "scripts/verify_b08_system.py",
    "tests/unit/test_b09_delivery.py",
)
_SUBMISSION_EXTRA_FILES = (
    "docs/batches/B06/NATIVE_DEPLOYMENT.md",
    "docs/batches/B06/ORGANIZER_DEPLOYMENT.md",
    "docs/batches/B08/SYSTEM_VERIFICATION.md",
    "docs/interfaces/contest-http-v1.md",
    "scripts/verify_b06_candidate.py",
    "scripts/verify_b08_system.py",
)
_SKIPPED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "data",
    "htmlcov",
    "logs",
}
_SECRET_PATTERNS = (
    ("private_key", re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("openai_style_key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "assigned_secret",
        re.compile(
            rb"(?i)\b(?:api[_-]?key|iam[_-]?token|access[_-]?token|secret[_-]?key)"
            rb"\s*[:=]\s*['\"]?(?!replace-|example|change-me|empty|none|null|<|\$\{)"
            rb"[A-Za-z0-9_./+=-]{24,}"
        ),
    ),
)


class DeliveryError(RuntimeError):
    """Raised when a delivery artifact cannot be trusted."""


@dataclass(frozen=True)
class SourceEntry:
    """One validated source file and its archive destination."""

    source: Path
    relative: PurePosixPath
    archive_name: PurePosixPath


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_commit(value: str) -> str:
    normalized = value.strip().lower()
    if _COMMIT_RE.fullmatch(normalized) is None:
        raise DeliveryError("candidate commit must be exactly 40 hexadecimal characters")
    return normalized


def _validate_relative_name(name: str) -> PurePosixPath:
    if "\\" in name:
        raise DeliveryError("archive paths must use forward slashes")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DeliveryError("archive contains an unsafe path")
    return path


def _is_forbidden_source(relative: PurePosixPath) -> bool:
    if any(part in _SKIPPED_PARTS for part in relative.parts):
        return True
    name = relative.name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if name.endswith((".key", ".pem", ".pyc")):
        return True
    return name in {".coverage", "coverage.json"}


def _validate_regular_file(root: Path, path: Path) -> PurePosixPath:
    try:
        relative_path = path.relative_to(root)
    except ValueError as error:
        raise DeliveryError("selected file escapes source root") from error
    relative = PurePosixPath(relative_path.as_posix())
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DeliveryError(f"symbolic links are forbidden: {relative.as_posix()}")
    if not path.is_file():
        raise DeliveryError(f"selected path is not a regular file: {relative.as_posix()}")
    if _is_forbidden_source(relative):
        raise DeliveryError(f"forbidden source path selected: {relative.as_posix()}")
    return relative


def _scan_payload(name: str, payload: bytes) -> None:
    for classification, pattern in _SECRET_PATTERNS:
        if pattern.search(payload) is not None:
            raise DeliveryError(f"potential secret ({classification}) in {name}")


def _iter_directory(root: Path, relative_directory: str) -> list[Path]:
    directory = root / relative_directory
    if directory.is_symlink() or not directory.is_dir():
        raise DeliveryError(f"required directory is missing or unsafe: {relative_directory}")
    selected: list[Path] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _is_forbidden_source(relative):
            continue
        if path.is_symlink():
            raise DeliveryError(f"symbolic links are forbidden: {relative.as_posix()}")
        if path.is_file():
            selected.append(path)
        elif not path.is_dir():
            raise DeliveryError(f"non-regular source entry is forbidden: {relative.as_posix()}")
    if not selected:
        raise DeliveryError(f"required directory is empty: {relative_directory}")
    return selected


def _selected_paths(root: Path, mode: str) -> list[Path]:
    root_files = list(_COMMON_ROOT_FILES)
    directories = list(_COMMON_DIRECTORIES)
    required = list(_REQUIRED_FILES)
    if mode == "handoff":
        root_files.extend(_HANDOFF_EXTRA_ROOT_FILES)
        directories.extend(_HANDOFF_EXTRA_DIRECTORIES)
        required.extend(_HANDOFF_REQUIRED_FILES)
    else:
        required.extend(_SUBMISSION_EXTRA_FILES)

    selected: set[Path] = set()
    for relative in root_files:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise DeliveryError(f"required file is missing or unsafe: {relative}")
        selected.add(path)
    for relative in directories:
        selected.update(_iter_directory(root, relative))
    if mode == "submission":
        selected.update(root / relative for relative in _SUBMISSION_EXTRA_FILES)
    for relative in required:
        if root / relative not in selected:
            raise DeliveryError(f"required delivery file is absent: {relative}")
    return sorted(selected, key=lambda item: item.relative_to(root).as_posix())


def collect_entries(root: Path, mode: str) -> list[SourceEntry]:
    """Collect a stable, explicit allowlist for one artifact mode."""

    if root.is_symlink():
        raise DeliveryError("source root must not be a symbolic link")
    source_root = root.resolve()
    if not source_root.is_dir():
        raise DeliveryError("source root must be a real directory")
    if mode not in {"handoff", "submission"}:
        raise DeliveryError("artifact mode must be handoff or submission")

    prefix = PurePosixPath("memscope-b09-handoff" if mode == "handoff" else "solution/code")
    entries: list[SourceEntry] = []
    for source in _selected_paths(source_root, mode):
        relative = _validate_regular_file(source_root, source)
        archive_name = prefix / relative
        if mode == "submission" and relative.as_posix() in {
            "INSTRUCTION.md",
            "SDD.md",
            "THIRD_PARTY_NOTICES.md",
        }:
            archive_name = PurePosixPath("solution") / relative
        entries.append(SourceEntry(source, relative, archive_name))

    if mode == "submission":
        license_source = source_root / "third_party/memos/LICENSE"
        entries.append(
            SourceEntry(
                license_source,
                PurePosixPath("third_party/memos/LICENSE"),
                PurePosixPath("solution/LICENSES/MemOS-Apache-2.0.txt"),
            )
        )
    names = [entry.archive_name.as_posix() for entry in entries]
    if len(names) != len(set(names)):
        raise DeliveryError("delivery mapping contains duplicate archive paths")
    return sorted(entries, key=lambda entry: entry.archive_name.as_posix())


def _git_identity(root: Path, candidate_commit: str) -> None:
    git_marker = root / ".git"
    if not git_marker.exists():
        return
    git = shutil.which("git")
    if git is None:
        raise DeliveryError("Git executable is required to verify source identity")
    try:
        head = subprocess.run(  # noqa: S603 - executable is resolved and arguments are fixed.
            [git, "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        status_output = subprocess.run(  # noqa: S603 - executable is resolved and arguments fixed.
            [git, "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise DeliveryError("could not verify Git source identity") from error
    if head != candidate_commit:
        raise DeliveryError("candidate commit does not match source HEAD")
    if status_output:
        raise DeliveryError("source Git worktree is not clean")


def _manifest_payload(*, mode: str, candidate_commit: str, records: list[dict[str, Any]]) -> bytes:
    document = {
        "schema": SCHEMA,
        "artifact_type": mode,
        "candidate_commit": candidate_commit,
        "deterministic_timestamp": "2026-09-04T00:00:00+08:00",
        "claims": {
            "live_system_pass": False,
            "official_score": False,
        },
        "pending_external_evidence": [
            "b08_live_exercise",
            "b08_restart_persistence",
            "b08_resource_observations",
            "real_model_baseline_and_tuning",
        ],
        "entries": records,
    }
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _zip_info(name: str, mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def _write_archive(
    archive: Path,
    *,
    mode: str,
    candidate_commit: str,
    entries: list[SourceEntry],
) -> None:
    records: list[dict[str, Any]] = []
    payloads: list[tuple[SourceEntry, bytes, int]] = []
    for entry in entries:
        payload = entry.source.read_bytes()
        _scan_payload(entry.relative.as_posix(), payload)
        file_mode = 0o755 if entry.source.stat().st_mode & 0o111 else 0o644
        payloads.append((entry, payload, file_mode))
        records.append(
            {
                "path": entry.archive_name.as_posix(),
                "sha256": _sha256_bytes(payload),
                "size": len(payload),
                "source": entry.relative.as_posix(),
            }
        )

    manifest_name = (
        "memscope-b09-handoff/DELIVERY_MANIFEST.json"
        if mode == "handoff"
        else "solution/DELIVERY_MANIFEST.json"
    )
    manifest = _manifest_payload(
        mode=mode,
        candidate_commit=candidate_commit,
        records=records,
    )
    with zipfile.ZipFile(archive, "w", allowZip64=True) as package:
        for entry, payload, file_mode in payloads:
            package.writestr(
                _zip_info(entry.archive_name.as_posix(), file_mode),
                payload,
                compresslevel=9,
            )
        package.writestr(_zip_info(manifest_name), manifest, compresslevel=9)


def _safe_output_directory(root: Path, output_directory: Path) -> Path:
    source_root = root.resolve()
    if output_directory.is_symlink():
        raise DeliveryError("output directory must not be a symbolic link")
    output = output_directory.resolve()
    try:
        output.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise DeliveryError("output directory must be outside the source tree")
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir():
        raise DeliveryError("output directory must be a real directory")
    return output


def build_archive(
    *, root: Path, output_directory: Path, mode: str, candidate_commit: str
) -> dict[str, Any]:
    """Build one deterministic archive and SHA-256 sidecar without overwriting files."""

    if root.is_symlink():
        raise DeliveryError("source root must not be a symbolic link")
    source_root = root.resolve()
    commit = _validate_commit(candidate_commit)
    _git_identity(source_root, commit)
    output = _safe_output_directory(source_root, output_directory)
    short_commit = commit[:12]
    filename = f"memscope-b09-{mode}-{short_commit}.zip"
    archive = output / filename
    sidecar = output / f"{filename}.sha256"
    if archive.exists() or sidecar.exists():
        raise DeliveryError("refusing to overwrite an existing delivery artifact")

    entries = collect_entries(source_root, mode)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".b09-", suffix=".zip", dir=output)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _write_archive(
            temporary,
            mode=mode,
            candidate_commit=commit,
            entries=entries,
        )
        verify_archive(temporary)
        os.link(temporary, archive)
        temporary.unlink()
        digest = _sha256_file(archive)
        with sidecar.open("x", encoding="utf-8") as stream:
            stream.write(f"{digest}  {filename}\n")
        sidecar.chmod(0o644)
    except BaseException:
        temporary.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        raise
    return {
        "status": "passed",
        "artifact_type": mode,
        "candidate_commit": commit,
        "archive": str(archive),
        "archive_sha256": digest,
        "archive_size": archive.stat().st_size,
        "sidecar": str(sidecar),
        "entry_count": len(entries),
    }


def _manifest_from_package(package: zipfile.ZipFile) -> tuple[str, dict[str, Any]]:
    candidates = [
        "memscope-b09-handoff/DELIVERY_MANIFEST.json",
        "solution/DELIVERY_MANIFEST.json",
    ]
    present = [name for name in candidates if name in package.namelist()]
    if len(present) != 1:
        raise DeliveryError("archive must contain exactly one delivery manifest")
    name = present[0]
    try:
        document = json.loads(package.read(name))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise DeliveryError("delivery manifest is invalid") from error
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise DeliveryError("delivery manifest schema is invalid")
    return name, document


def verify_archive(archive: Path, sidecar: Path | None = None) -> dict[str, Any]:
    """Verify archive path safety, identity, exact manifest and member hashes."""

    if archive.is_symlink():
        raise DeliveryError("archive must not be a symbolic link")
    path = archive.resolve()
    if not path.is_file():
        raise DeliveryError("archive must be a regular file")
    archive_digest = _sha256_file(path)
    if sidecar is not None:
        line = sidecar.read_text(encoding="utf-8").strip()
        expected_line = f"{archive_digest}  {path.name}"
        if line != expected_line:
            raise DeliveryError("archive SHA-256 sidecar does not match")

    try:
        with zipfile.ZipFile(path, "r") as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise DeliveryError("archive contains duplicate paths")
            for info in infos:
                relative = _validate_relative_name(info.filename)
                file_type = (info.external_attr >> 16) & 0o170000
                if file_type == stat.S_IFLNK or info.is_dir():
                    raise DeliveryError("archive contains a link or directory entry")
                if _is_forbidden_source(relative):
                    raise DeliveryError("archive contains a forbidden path")

            manifest_name, manifest = _manifest_from_package(package)
            mode = manifest.get("artifact_type")
            if mode not in {"handoff", "submission"}:
                raise DeliveryError("delivery artifact type is invalid")
            commit = _validate_commit(str(manifest.get("candidate_commit", "")))
            records = manifest.get("entries")
            if not isinstance(records, list) or not records:
                raise DeliveryError("delivery manifest entries are invalid")
            expected_names = {manifest_name}
            for record in records:
                if not isinstance(record, dict):
                    raise DeliveryError("delivery manifest entry is invalid")
                member_name = str(record.get("path", ""))
                _validate_relative_name(member_name)
                if member_name in expected_names:
                    raise DeliveryError("delivery manifest contains duplicate paths")
                expected_names.add(member_name)
                payload = package.read(member_name)
                if record.get("size") != len(payload):
                    raise DeliveryError("delivery member size does not match manifest")
                if record.get("sha256") != _sha256_bytes(payload):
                    raise DeliveryError("delivery member hash does not match manifest")
                _scan_payload(member_name, payload)
            if expected_names != set(names):
                raise DeliveryError("archive contents do not exactly match manifest")
    except zipfile.BadZipFile as error:
        raise DeliveryError("delivery archive is not a valid ZIP") from error
    return {
        "status": "passed",
        "artifact_type": mode,
        "candidate_commit": commit,
        "archive": str(path),
        "archive_sha256": archive_digest,
        "archive_size": path.stat().st_size,
        "entry_count": len(records),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a deterministic delivery archive")
    build.add_argument("--source-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--candidate-commit", required=True)
    build.add_argument("--mode", choices=("handoff", "submission"), required=True)
    verify = subparsers.add_parser("verify", help="verify an existing delivery archive")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--sha256-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command == "build":
            result = build_archive(
                root=arguments.source_root,
                output_directory=arguments.output_dir,
                mode=arguments.mode,
                candidate_commit=arguments.candidate_commit,
            )
        else:
            result = verify_archive(arguments.archive, arguments.sha256_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (DeliveryError, OSError) as error:
        print(
            json.dumps(
                {"status": "failed", "classification": "delivery_invalid", "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

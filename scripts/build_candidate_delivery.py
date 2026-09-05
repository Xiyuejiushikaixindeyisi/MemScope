#!/usr/bin/env python3
"""Build and verify the B10 source ZIP plus four-image offline delivery set."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urlsplit

DELIVERY_SCHEMA = "memscope.b10.delivery-manifest.v1"
SOURCE_SCHEMA = "memscope.b10.source-manifest.v1"
LOCK_SCHEMA = "memscope.release-lock.v1"
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_IMAGE_ID_RE = re.compile(r"sha256:[0-9a-f]{64}")
_ZIP_TIMESTAMP: Final = (2026, 9, 5, 0, 0, 0)
_CHUNK_SIZE = 1024 * 1024

MEMORY_API_IMAGE = "memscope/memory-api:b10-release"
MEMOS_IMAGE = "memscope/memos:2.0.32-b10-release"
NEO4J_IMAGE = "neo4j:5.26.6-community"
QDRANT_IMAGE = "qdrant/qdrant:v1.15.3"
NEO4J_PIN = (
    "neo4j:5.26.6-community@sha256:eef89955a0ff6ce578ec5fb264333818bb2f56e169bcb8dda5bcadad1fc48893"
)
QDRANT_PIN = (
    "qdrant/qdrant:v1.15.3@sha256:31407c0e8e32eb771b71718f1a4772e2ad47a07557917b21ac96792f40eb8007"
)
_UPSTREAM_REPO_DIGEST = {
    "neo4j": "neo4j@sha256:eef89955a0ff6ce578ec5fb264333818bb2f56e169bcb8dda5bcadad1fc48893",
    "qdrant": (
        "qdrant/qdrant@sha256:31407c0e8e32eb771b71718f1a4772e2ad47a07557917b21ac96792f40eb8007"
    ),
}

_IMAGE_ROLES = (
    ("memory-api", MEMORY_API_IMAGE, True),
    ("memos", MEMOS_IMAGE, True),
    ("neo4j", NEO4J_IMAGE, False),
    ("qdrant", QDRANT_IMAGE, False),
)
_DIRECT_FILES = {
    "INSTRUCTION.md": "solution/INSTRUCTION.md",
    "ORGANIZER_QUICKSTART.md": "solution/ORGANIZER_QUICKSTART.md",
    "ORGANIZER_AGENT_PROMPT.md": "solution/ORGANIZER_AGENT_PROMPT.md",
    "SDD.md": "solution/SDD.md",
    "THIRD_PARTY_NOTICES.md": "solution/THIRD_PARTY_NOTICES.md",
    "LICENSE_STATUS.md": "solution/LICENSE_STATUS.md",
    "compose.release.yaml": "solution/compose.release.yaml",
    "deploy/organizer.env.example": "solution/deploy/organizer.env.example",
    "scripts/run_release.sh": "solution/scripts/run_release.sh",
    "scripts/verify_release.sh": "solution/scripts/verify_release.sh",
    "scripts/stop_release.sh": "solution/scripts/stop_release.sh",
    "scripts/lib/rootful_docker.sh": "solution/scripts/lib/rootful_docker.sh",
    "third_party/memos/LICENSE": "solution/LICENSES/MemOS-Apache-2.0.txt",
}
_CODE_ROOT_FILES = (
    ".dockerignore",
    ".python-version",
    "README.md",
    "compose.yaml",
    "compose.release.yaml",
    "pyproject.toml",
    "uv.lock",
)
_CODE_DIRECTORIES = ("deploy", "docker", "scripts", "src", "third_party/memos")
_SKIPPED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "data",
    "dist",
    "htmlcov",
    "logs",
}
_SECRET_PATTERNS = (
    ("private_key", re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("openai_style_key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("github_token", re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("bearer_token", re.compile(rb"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]{20,}")),
    (
        "assigned_secret",
        re.compile(
            rb"(?i)\b(?:api[_-]?key|iam[_-]?token|access[_-]?token|secret[_-]?key)"
            rb"\s*[:=]\s*(?!replace-|example|change-me|empty|none|null|<|\$\{)"
            rb"[A-Za-z0-9_./+=-]{24,}"
        ),
    ),
)


class DeliveryError(RuntimeError):
    """A final delivery input or artifact failed closed validation."""


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """One regular source file and its exact ZIP member path."""

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
    candidate = value.strip().lower()
    if _COMMIT_RE.fullmatch(candidate) is None:
        raise DeliveryError("candidate commit must be exactly 40 lowercase hexadecimal characters")
    return candidate


def _validate_member_name(name: str) -> PurePosixPath:
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
    if name.endswith(".env") and not name.endswith(".env.example"):
        return True
    return name in {".coverage", "coverage.json"}


def _validate_source_file(root: Path, path: Path) -> PurePosixPath:
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
    if not path.is_file() or _is_forbidden_source(relative):
        raise DeliveryError(f"selected source path is unsafe: {relative.as_posix()}")
    return relative


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


def collect_entries(root: Path) -> list[SourceEntry]:
    """Collect the explicit final solution allowlist."""

    if root.is_symlink():
        raise DeliveryError("source root must not be a symbolic link")
    source_root = root.resolve()
    if not source_root.is_dir():
        raise DeliveryError("source root must be a real directory")

    entries: list[SourceEntry] = []
    for source_name, archive_name in _DIRECT_FILES.items():
        source = source_root / source_name
        relative = _validate_source_file(source_root, source)
        entries.append(SourceEntry(source, relative, _validate_member_name(archive_name)))

    selected: set[Path] = set()
    for root_file in _CODE_ROOT_FILES:
        selected.add(source_root / root_file)
    for directory_name in _CODE_DIRECTORIES:
        selected.update(_iter_directory(source_root, directory_name))
    for source in selected:
        relative = _validate_source_file(source_root, source)
        entries.append(SourceEntry(source, relative, PurePosixPath("solution/code") / relative))

    names = [entry.archive_name.as_posix() for entry in entries]
    if len(names) != len(set(names)):
        raise DeliveryError("solution allowlist contains duplicate archive paths")
    return sorted(entries, key=lambda entry: entry.archive_name.as_posix())


def _load_archive_allowlist(payload: bytes) -> tuple[str, set[tuple[str, str]]]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeliveryError("MemOS secret-scan allowlist is invalid JSON") from error
    if not isinstance(document, dict):
        raise DeliveryError("MemOS secret-scan allowlist must be an object")
    archive_hash = document.get("archive_sha256")
    records = document.get("reviewed_matches")
    if not isinstance(archive_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", archive_hash):
        raise DeliveryError("MemOS secret-scan allowlist has an invalid archive hash")
    if not isinstance(records, list):
        raise DeliveryError("MemOS secret-scan allowlist has invalid match records")
    matches: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            raise DeliveryError("MemOS secret-scan allowlist record is invalid")
        classification = record.get("classification")
        path = record.get("path")
        if not isinstance(classification, str) or not isinstance(path, str):
            raise DeliveryError("MemOS secret-scan allowlist record is incomplete")
        _validate_member_name(path)
        matches.add((classification, path))
    if len(matches) != len(records):
        raise DeliveryError("MemOS secret-scan allowlist contains duplicates")
    return archive_hash, matches


def _payload_matches(payload: bytes) -> set[str]:
    return {
        classification for classification, pattern in _SECRET_PATTERNS if pattern.search(payload)
    }


def _scan_memos_archive(archive_payload: bytes, allowlist_payload: bytes) -> None:
    expected_hash, allowed_matches = _load_archive_allowlist(allowlist_payload)
    if _sha256_bytes(archive_payload) != expected_hash:
        raise DeliveryError("MemOS archive hash does not match its secret-scan review")
    observed: set[tuple[str, str]] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_payload), mode="r:gz") as package:
            for member in package.getmembers():
                _validate_member_name(member.name.rstrip("/"))
                if member.issym() or member.islnk() or member.isdev():
                    raise DeliveryError("MemOS archive contains a link or device entry")
                if member.isfile():
                    stream = package.extractfile(member)
                    if stream is None:
                        raise DeliveryError("MemOS archive member could not be read")
                    payload = stream.read()
                    for classification in _payload_matches(payload):
                        observed.add((classification, member.name))
                elif not member.isdir():
                    raise DeliveryError("MemOS archive contains a non-regular entry")
    except (tarfile.TarError, OSError) as error:
        raise DeliveryError("MemOS source archive is invalid") from error
    unexpected = observed - allowed_matches
    missing = allowed_matches - observed
    if unexpected:
        classification, path = sorted(unexpected)[0]
        raise DeliveryError(f"unreviewed {classification} pattern in locked MemOS path: {path}")
    if missing:
        raise DeliveryError("MemOS secret-scan allowlist no longer matches the locked archive")


def _scan_entries(entries: list[SourceEntry]) -> dict[str, bytes]:
    payloads = {entry.relative.as_posix(): entry.source.read_bytes() for entry in entries}
    archive_name = "third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz"
    allowlist_name = "third_party/memos/SECRET_SCAN_ALLOWLIST.json"
    for relative, payload in payloads.items():
        if relative == archive_name:
            continue
        matches = _payload_matches(payload)
        if matches:
            raise DeliveryError(f"potential secret ({sorted(matches)[0]}) in {relative}")
    try:
        _scan_memos_archive(payloads[archive_name], payloads[allowlist_name])
    except KeyError as error:
        raise DeliveryError("locked MemOS archive or secret-scan allowlist is missing") from error
    return payloads


def _release_lock(images: list[dict[str, Any]]) -> bytes:
    lines = [f"# {LOCK_SCHEMA}"]
    if not all(isinstance(record, dict) for record in images):
        raise DeliveryError("image records must be objects")
    by_role: dict[str, dict[str, Any]] = {}
    for record in images:
        role = record.get("role")
        if not isinstance(role, str):
            raise DeliveryError("image record has an invalid or missing role")
        by_role[role] = record
    if len(by_role) != len(images):
        raise DeliveryError("image records contain duplicate roles")
    for role, reference, custom in _IMAGE_ROLES:
        matched_record = by_role.get(role)
        if matched_record is None or matched_record.get("reference") != reference:
            raise DeliveryError("image records do not match the fixed four-image topology")
        image_id = matched_record.get("image_id")
        if not isinstance(image_id, str) or _IMAGE_ID_RE.fullmatch(image_id) is None:
            raise DeliveryError("image record contains an invalid image ID")
        revision = matched_record.get("source_revision") if custom else "-"
        if custom and (not isinstance(revision, str) or _COMMIT_RE.fullmatch(revision) is None):
            raise DeliveryError("custom image record contains an invalid source revision")
        lines.append(f"{role}\t{reference}\t{image_id}\t{revision}")
    return ("\n".join(lines) + "\n").encode()


def _zip_info(name: str, mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def write_solution_archive(
    archive: Path,
    *,
    root: Path,
    candidate_commit: str,
    images: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write a deterministic source ZIP. The caller owns output lifecycle."""

    commit = _validate_commit(candidate_commit)
    entries = collect_entries(root)
    payloads = _scan_entries(entries)
    records: list[dict[str, Any]] = []
    archive_payloads: list[tuple[str, bytes, int]] = []
    for entry in entries:
        payload = payloads[entry.relative.as_posix()]
        mode = 0o755 if entry.source.stat().st_mode & 0o111 else 0o644
        name = entry.archive_name.as_posix()
        archive_payloads.append((name, payload, mode))
        records.append(
            {
                "path": name,
                "sha256": _sha256_bytes(payload),
                "size": len(payload),
                "source": entry.relative.as_posix(),
            }
        )

    lock_payload = _release_lock(images)
    lock_name = "solution/RELEASE_LOCK.tsv"
    archive_payloads.append((lock_name, lock_payload, 0o644))
    records.append(
        {
            "path": lock_name,
            "sha256": _sha256_bytes(lock_payload),
            "size": len(lock_payload),
            "source": "generated:image-inspection",
        }
    )
    manifest = {
        "schema": SOURCE_SCHEMA,
        "candidate_commit": commit,
        "claims": {"official_score": False, "organizer_runtime_pass": False},
        "entries": sorted(records, key=lambda record: record["path"]),
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    with zipfile.ZipFile(archive, "w", allowZip64=True) as package:
        for name, payload, mode in sorted(archive_payloads):
            package.writestr(_zip_info(name, mode), payload, compresslevel=9)
        package.writestr(
            _zip_info("solution/SOURCE_MANIFEST.json"), manifest_payload, compresslevel=9
        )
    return {"entry_count": len(records), "candidate_commit": commit}


def _run(command: list[str], *, cwd: Path, timeout: float | None = None) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - executable and fixed argument vectors are controlled.
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeliveryError(
            f"command failed without exposing captured output: {command[0]}"
        ) from error
    return result.stdout


def _git_identity(root: Path, candidate_commit: str) -> None:
    git = shutil.which("git")
    if git is None or not (root / ".git").exists():
        raise DeliveryError("final build requires a Git checkout and Git executable")
    head = _run([git, "-C", str(root), "rev-parse", "HEAD"], cwd=root, timeout=10).strip()
    status = _run(
        [git, "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        timeout=10,
    )
    if head != candidate_commit:
        raise DeliveryError("candidate commit does not match source HEAD")
    if status:
        raise DeliveryError("final build requires a clean Git worktree")


def _validate_package_index(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise DeliveryError("package index must be one credential-free HTTPS URL")
    return value


def _docker_command() -> list[str]:
    if os.geteuid() == 0:
        raise DeliveryError(
            "run the delivery builder as the ordinary operator; "
            "only Docker commands may be elevated"
        )
    docker = shutil.which("docker")
    if docker is None:
        raise DeliveryError("Docker executable is required for final delivery")

    candidates = [[docker]]
    sudo = shutil.which("sudo")
    env = shutil.which("env")
    if sudo is not None and env is not None:
        candidates.append(
            [env, "-u", "DOCKER_HOST", "-u", "DOCKER_CONTEXT", sudo, "-n", "--", docker]
        )
    for candidate in candidates:
        try:
            security_options = _run(
                [*candidate, "info", "--format", "{{json .SecurityOptions}}"],
                cwd=Path.cwd(),
                timeout=15,
            )
        except DeliveryError:
            continue
        if security_options.strip() and "rootless" not in security_options.lower():
            return candidate
    raise DeliveryError(
        "a rootful Docker daemon is required; run 'sudo -v', ensure the system Docker "
        "service is active, and retry as the ordinary user"
    )


def _build_custom_images(root: Path, commit: str, package_index: str) -> None:
    docker = _docker_command()
    common = [
        *docker,
        "build",
        "--build-arg",
        f"SOURCE_REVISION={commit}",
        "--build-arg",
        f"PIP_INDEX_URL={package_index}",
    ]
    _run(
        [*common, "--file", "docker/memory-api/Dockerfile", "--tag", MEMORY_API_IMAGE, "."],
        cwd=root,
        timeout=1800,
    )
    _run(
        [*common, "--file", "docker/memos/Dockerfile", "--tag", MEMOS_IMAGE, "."],
        cwd=root,
        timeout=1800,
    )


def _prepare_upstream_images(root: Path, *, pull: bool) -> None:
    docker = _docker_command()
    for pinned, tag in ((NEO4J_PIN, NEO4J_IMAGE), (QDRANT_PIN, QDRANT_IMAGE)):
        if pull:
            _run([*docker, "pull", pinned], cwd=root, timeout=900)
            _run([*docker, "tag", pinned, tag], cwd=root, timeout=30)
        else:
            _run([*docker, "image", "inspect", tag], cwd=root, timeout=30)


def _inspect_images(root: Path, commit: str) -> list[dict[str, Any]]:
    docker = _docker_command()
    records: list[dict[str, Any]] = []
    for role, reference, custom in _IMAGE_ROLES:
        raw = _run([*docker, "image", "inspect", reference], cwd=root, timeout=30)
        try:
            values = json.loads(raw)
            document = values[0]
        except (json.JSONDecodeError, IndexError, KeyError, TypeError) as error:
            raise DeliveryError(f"Docker returned invalid image metadata for {role}") from error
        image_id = document.get("Id")
        architecture = document.get("Architecture")
        operating_system = document.get("Os")
        repo_digests = document.get("RepoDigests") or []
        labels = (document.get("Config") or {}).get("Labels") or {}
        if not isinstance(image_id, str) or _IMAGE_ID_RE.fullmatch(image_id) is None:
            raise DeliveryError(f"Docker image ID is invalid for {role}")
        if architecture != "amd64" or operating_system != "linux":
            raise DeliveryError(f"image platform is not linux/amd64 for {role}")
        revision = labels.get("org.opencontainers.image.revision") if custom else None
        if custom and revision != commit:
            raise DeliveryError(f"custom image source revision does not match for {role}")
        if not isinstance(repo_digests, list) or not all(
            isinstance(item, str) for item in repo_digests
        ):
            raise DeliveryError(f"Docker RepoDigests are invalid for {role}")
        expected_digest = _UPSTREAM_REPO_DIGEST.get(role)
        if expected_digest is not None and expected_digest not in repo_digests:
            raise DeliveryError(
                f"upstream image digest does not match the pinned source for {role}"
            )
        records.append(
            {
                "role": role,
                "reference": reference,
                "image_id": image_id,
                "source_revision": revision,
                "platform": "linux/amd64",
                "repo_digests": sorted(repo_digests),
            }
        )
    return records


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


def build_delivery(
    *,
    root: Path,
    output_directory: Path,
    candidate_commit: str,
    build_images: bool,
    pull_upstream: bool,
    package_index: str,
) -> dict[str, Any]:
    """Build the four final artifacts without overwriting any existing path."""

    source_root = root.resolve()
    commit = _validate_commit(candidate_commit)
    _git_identity(source_root, commit)
    output = _safe_output_directory(source_root, output_directory)
    short = commit[:12]
    archive = output / f"solution-{short}.zip"
    image_bundle = output / f"memscope-images-{short}-linux-amd64.tar"
    manifest_path = output / "delivery-manifest.json"
    sums_path = output / "SHA256SUMS"
    final_paths = (archive, image_bundle, manifest_path, sums_path)
    if any(path.exists() for path in final_paths):
        raise DeliveryError("refusing to overwrite an existing delivery artifact")

    index = _validate_package_index(package_index)
    if build_images:
        _build_custom_images(source_root, commit, index)
    _prepare_upstream_images(source_root, pull=pull_upstream)
    images = _inspect_images(source_root, commit)

    temporary_paths: list[Path] = []
    try:
        image_fd, image_name = tempfile.mkstemp(prefix=".images-", suffix=".tar", dir=output)
        os.close(image_fd)
        image_temp = Path(image_name)
        temporary_paths.append(image_temp)
        docker = _docker_command()
        _run(
            [*docker, "save", "--output", str(image_temp), *[item[1] for item in _IMAGE_ROLES]],
            cwd=source_root,
            timeout=1800,
        )

        zip_fd, zip_name = tempfile.mkstemp(prefix=".solution-", suffix=".zip", dir=output)
        os.close(zip_fd)
        zip_temp = Path(zip_name)
        temporary_paths.append(zip_temp)
        source_result = write_solution_archive(
            zip_temp,
            root=source_root,
            candidate_commit=commit,
            images=images,
        )
        verify_solution_archive(zip_temp)

        artifacts = [
            {
                "filename": archive.name,
                "kind": "solution_zip",
                "sha256": _sha256_file(zip_temp),
                "size": zip_temp.stat().st_size,
            },
            {
                "filename": image_bundle.name,
                "kind": "docker_image_bundle",
                "sha256": _sha256_file(image_temp),
                "size": image_temp.stat().st_size,
            },
        ]
        manifest = {
            "schema": DELIVERY_SCHEMA,
            "candidate_commit": commit,
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
            "images": images,
        }
        manifest_payload = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        manifest_fd, manifest_name = tempfile.mkstemp(
            prefix=".manifest-", suffix=".json", dir=output
        )
        os.close(manifest_fd)
        manifest_temp = Path(manifest_name)
        temporary_paths.append(manifest_temp)
        manifest_temp.write_bytes(manifest_payload)

        sums_payload = "".join(
            f"{digest}  {name}\n"
            for digest, name in (
                (_sha256_file(zip_temp), archive.name),
                (_sha256_file(image_temp), image_bundle.name),
                (_sha256_file(manifest_temp), manifest_path.name),
            )
        ).encode()
        sums_fd, sums_name = tempfile.mkstemp(prefix=".sums-", dir=output)
        os.close(sums_fd)
        sums_temp = Path(sums_name)
        temporary_paths.append(sums_temp)
        sums_temp.write_bytes(sums_payload)

        os.link(zip_temp, archive)
        os.link(image_temp, image_bundle)
        os.link(manifest_temp, manifest_path)
        os.link(sums_temp, sums_path)
        for path in final_paths:
            path.chmod(0o644)
        verify_delivery(output)
    except BaseException:
        for path in final_paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)

    return {
        "status": "passed",
        "candidate_commit": commit,
        "solution_zip": archive.name,
        "image_bundle": image_bundle.name,
        "manifest": manifest_path.name,
        "sha256sums": sums_path.name,
        "source_entry_count": source_result["entry_count"],
    }


def _validate_release_lock(payload: bytes, images: list[dict[str, Any]] | None = None) -> None:
    try:
        lines = payload.decode().splitlines()
    except UnicodeDecodeError as error:
        raise DeliveryError("RELEASE_LOCK.tsv is not UTF-8") from error
    if not lines or lines[0] != f"# {LOCK_SCHEMA}":
        raise DeliveryError("RELEASE_LOCK.tsv schema is invalid")
    records: list[tuple[str, str, str, str]] = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) != 4:
            raise DeliveryError("RELEASE_LOCK.tsv record is invalid")
        records.append(tuple(fields))  # type: ignore[arg-type]
    if len(records) != 4:
        raise DeliveryError("RELEASE_LOCK.tsv must contain four image records")
    for record, expected in zip(records, _IMAGE_ROLES, strict=True):
        role, reference, image_id, revision = record
        if (role, reference) != expected[:2] or _IMAGE_ID_RE.fullmatch(image_id) is None:
            raise DeliveryError("RELEASE_LOCK.tsv image identity is invalid")
        if expected[2] and _COMMIT_RE.fullmatch(revision) is None:
            raise DeliveryError("RELEASE_LOCK.tsv source revision is invalid")
        if not expected[2] and revision != "-":
            raise DeliveryError("upstream RELEASE_LOCK.tsv revision must be '-' ")
    if images is not None and payload != _release_lock(images):
        raise DeliveryError("RELEASE_LOCK.tsv does not match delivery manifest images")


def verify_solution_archive(archive: Path) -> dict[str, Any]:
    """Verify solution path safety, embedded manifest, hashes and expanded vendor scan."""

    if archive.is_symlink() or not archive.is_file():
        raise DeliveryError("solution ZIP must be a regular non-link file")
    try:
        with zipfile.ZipFile(archive, "r") as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise DeliveryError("solution ZIP contains duplicate paths")
            for info in infos:
                _validate_member_name(info.filename)
                file_type = (info.external_attr >> 16) & 0o170000
                if info.is_dir() or file_type == stat.S_IFLNK:
                    raise DeliveryError("solution ZIP contains a directory or link entry")
            manifest_name = "solution/SOURCE_MANIFEST.json"
            try:
                manifest = json.loads(package.read(manifest_name))
            except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
                raise DeliveryError("solution source manifest is invalid") from error
            if not isinstance(manifest, dict) or manifest.get("schema") != SOURCE_SCHEMA:
                raise DeliveryError("solution source manifest schema is invalid")
            commit = _validate_commit(str(manifest.get("candidate_commit", "")))
            records = manifest.get("entries")
            if not isinstance(records, list) or not records:
                raise DeliveryError("solution source manifest entries are invalid")
            expected_names = {manifest_name}
            payloads: dict[str, bytes] = {}
            for record in records:
                if not isinstance(record, dict):
                    raise DeliveryError("solution source manifest record is invalid")
                name = str(record.get("path", ""))
                _validate_member_name(name)
                if name in expected_names:
                    raise DeliveryError("solution source manifest contains duplicate paths")
                expected_names.add(name)
                try:
                    payload = package.read(name)
                except KeyError as error:
                    raise DeliveryError(
                        "solution source manifest references a missing member"
                    ) from error
                if record.get("size") != len(payload) or record.get("sha256") != _sha256_bytes(
                    payload
                ):
                    raise DeliveryError("solution member does not match source manifest")
                payloads[name] = payload
            if expected_names != set(names):
                raise DeliveryError("solution ZIP contents do not exactly match source manifest")

            archive_name = "solution/code/third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz"
            allowlist_name = "solution/code/third_party/memos/SECRET_SCAN_ALLOWLIST.json"
            for name, payload in payloads.items():
                if name == archive_name:
                    continue
                matches = _payload_matches(payload)
                if matches:
                    raise DeliveryError(f"potential secret ({sorted(matches)[0]}) in {name}")
            _scan_memos_archive(payloads[archive_name], payloads[allowlist_name])
            _validate_release_lock(payloads["solution/RELEASE_LOCK.tsv"])
    except zipfile.BadZipFile as error:
        raise DeliveryError("solution ZIP is invalid") from error
    return {
        "status": "passed",
        "candidate_commit": commit,
        "archive_sha256": _sha256_file(archive),
        "entry_count": len(records),
    }


def verify_delivery(directory: Path) -> dict[str, Any]:
    """Verify one final four-file delivery directory without loading its Docker images."""

    root = directory.resolve()
    manifest_path = root / "delivery-manifest.json"
    sums_path = root / "SHA256SUMS"
    if any(path.is_symlink() or not path.is_file() for path in (manifest_path, sums_path)):
        raise DeliveryError("delivery manifest or SHA256SUMS is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise DeliveryError("delivery manifest is invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != DELIVERY_SCHEMA:
        raise DeliveryError("delivery manifest schema is invalid")
    commit = _validate_commit(str(manifest.get("candidate_commit", "")))
    if manifest.get("target_platform") != "linux/amd64" or manifest.get("service_count") != 4:
        raise DeliveryError("delivery platform or service count is invalid")
    images = manifest.get("images")
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(images, list)
        or len(images) != 4
        or not isinstance(artifacts, list)
        or len(artifacts) != 2
    ):
        raise DeliveryError("delivery image or artifact records are invalid")
    if manifest.get("runtime_policy") != {
        "build": False,
        "pull": False,
        "host_python": False,
        "rootful_docker": True,
        "operator_home_only": True,
    }:
        raise DeliveryError("delivery runtime policy is invalid")
    if manifest.get("claims") != {"official_score": False, "organizer_runtime_pass": False}:
        raise DeliveryError("delivery claims are invalid")
    _release_lock(images)
    by_role = {record["role"]: record for record in images}
    for role, _, custom in _IMAGE_ROLES:
        record = by_role[role]
        if record.get("platform") != "linux/amd64":
            raise DeliveryError("delivery image platform is invalid")
        if custom and record.get("source_revision") != commit:
            raise DeliveryError("delivery custom image revision does not match candidate")
        repo_digests = record.get("repo_digests")
        if not isinstance(repo_digests, list) or not all(
            isinstance(item, str) for item in repo_digests
        ):
            raise DeliveryError("delivery image RepoDigests are invalid")
        expected_digest = _UPSTREAM_REPO_DIGEST.get(role)
        if expected_digest is not None and expected_digest not in repo_digests:
            raise DeliveryError("delivery upstream image digest is not pinned")

    expected_sums: dict[str, str] = {}
    for record in artifacts:
        if not isinstance(record, dict):
            raise DeliveryError("delivery artifact record is invalid")
        filename = str(record.get("filename", ""))
        relative = _validate_member_name(filename)
        if len(relative.parts) != 1:
            raise DeliveryError("delivery artifact filename must not contain directories")
        path = root / filename
        if path.is_symlink() or not path.is_file():
            raise DeliveryError("delivery artifact is missing or unsafe")
        digest = _sha256_file(path)
        if record.get("sha256") != digest or record.get("size") != path.stat().st_size:
            raise DeliveryError("delivery artifact does not match manifest")
        expected_sums[filename] = digest
    expected_sums[manifest_path.name] = _sha256_file(manifest_path)

    lines = sums_path.read_text(encoding="utf-8").splitlines()
    observed_sums: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if match is None or match.group(2) in observed_sums:
            raise DeliveryError("SHA256SUMS format is invalid")
        observed_sums[match.group(2)] = match.group(1)
    if observed_sums != expected_sums:
        raise DeliveryError("SHA256SUMS does not exactly match the delivery manifest")

    solution_records = [record for record in artifacts if record.get("kind") == "solution_zip"]
    bundle_records = [record for record in artifacts if record.get("kind") == "docker_image_bundle"]
    if len(solution_records) != 1 or len(bundle_records) != 1:
        raise DeliveryError("delivery must contain one solution ZIP and one image bundle")
    expected_solution_name = f"solution-{commit[:12]}.zip"
    expected_bundle_name = f"memscope-images-{commit[:12]}-linux-amd64.tar"
    if (
        solution_records[0].get("filename") != expected_solution_name
        or bundle_records[0].get("filename") != expected_bundle_name
    ):
        raise DeliveryError("delivery artifact names do not match the candidate commit")
    solution_result = verify_solution_archive(root / solution_records[0]["filename"])
    if solution_result["candidate_commit"] != commit:
        raise DeliveryError("solution ZIP candidate does not match delivery manifest")
    with zipfile.ZipFile(root / solution_records[0]["filename"]) as package:
        _validate_release_lock(package.read("solution/RELEASE_LOCK.tsv"), images)
    return {
        "status": "passed",
        "candidate_commit": commit,
        "solution_zip": solution_records[0]["filename"],
        "image_bundle": bundle_records[0]["filename"],
        "image_count": len(images),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build the final ZIP/image/manifest/checksum set")
    build.add_argument("--source-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--candidate-commit", required=True)
    image_mode = build.add_mutually_exclusive_group(required=True)
    image_mode.add_argument("--build-images", action="store_true")
    image_mode.add_argument("--reuse-images", action="store_true")
    build.add_argument("--pull-upstream", action="store_true")
    build.add_argument("--package-index", default="https://pypi.org/simple")
    verify = subparsers.add_parser("verify", help="verify an existing final delivery directory")
    verify.add_argument("--delivery-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command == "build":
            result = build_delivery(
                root=arguments.source_root,
                output_directory=arguments.output_dir,
                candidate_commit=arguments.candidate_commit,
                build_images=arguments.build_images,
                pull_upstream=arguments.pull_upstream,
                package_index=arguments.package_index,
            )
        else:
            result = verify_delivery(arguments.delivery_dir)
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

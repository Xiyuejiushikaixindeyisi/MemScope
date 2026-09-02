from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "third_party" / "memos"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_memos_archive_matches_lock_and_contains_complete_source_tree() -> None:
    lock = json.loads((VENDOR / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    source = lock["source"]
    archive = VENDOR / source["archive"]

    assert source["tag"] == "v2.0.32"
    assert source["commit"] == "185ebdb925911b55c13b7efe666b74e2e292e484"
    assert _sha256(archive) == source["archive_sha256"]
    assert _sha256(VENDOR / source["license_file"]) == source["license_sha256"]

    prefix = source["archive_prefix"]
    with tarfile.open(archive, "r:gz") as package:
        names = set(package.getnames())
    assert f"{prefix}src/memos/api/server_api.py" in names
    assert f"{prefix}src/memos/api/config.py" in names
    assert f"{prefix}docker/requirements.txt" in names
    assert f"{prefix}pyproject.toml" in names
    assert not any("/.git/" in name or name.endswith("/.git") for name in names)


def test_checksum_file_uses_only_the_locked_archive() -> None:
    lock = json.loads((VENDOR / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    checksum_lines = (VENDOR / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert checksum_lines == [f"{lock['source']['archive_sha256']}  {lock['source']['archive']}"]


def test_compose_has_only_approved_services_and_four_named_volumes() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    service_block = compose.split("\nnetworks:\n", maxsplit=1)[0]
    service_names = re.findall(r"^  ([a-z][a-z0-9_-]*):$", service_block, re.MULTILINE)
    assert service_names == ["neo4j", "qdrant", "memos"]
    assert "ports:" not in service_block
    assert "internal: true" in compose
    for volume in ("memos_data", "neo4j_data", "neo4j_logs", "qdrant_data"):
        assert f"  {volume}:" in compose


def test_container_image_digests_match_source_lock() -> None:
    lock = json.loads((VENDOR / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "docker" / "memos" / "Dockerfile").read_text(encoding="utf-8")

    for name in ("neo4j", "qdrant"):
        image = lock["container_images"][name]
        assert f"{image['reference']}@{image['index_digest']}" in compose
    python = lock["container_images"]["python"]
    assert f"{python['reference']}@{python['index_digest']}" in dockerfile
    assert "pip install --no-cache-dir --upgrade pip" not in dockerfile


def test_compose_requires_secret_and_disables_model_calls_for_b04() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "${NEO4J_PASSWORD:?" in compose
    assert "neo4j/12345678" not in compose
    assert "MOS_EMBEDDER_BACKEND: universal_api" in compose
    assert "MOS_RERANKER_BACKEND: cosine_local" in compose
    assert "http://127.0.0.1:9/v1" in compose
    assert 'ENABLE_INTERNET: "false"' in compose
    assert 'API_SCHEDULER_ON: "false"' in compose


def test_compose_readiness_covers_all_three_services() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("healthcheck:") == 3
    assert "cypher-shell" in compose
    assert "/dev/tcp/127.0.0.1/6333" in compose
    assert "http://127.0.0.1:8000/health" in compose
    assert compose.count("condition: service_healthy") == 2


def test_runtime_verifier_is_scoped_to_disposable_b04_projects() -> None:
    verifier = (ROOT / "scripts" / "verify_b04_runtime.py").read_text(encoding="utf-8")
    assert "memscope_b04_gate_" in verifier
    assert '"down", "--volumes", "--remove-orphans"' in verifier
    assert "docker system prune" not in verifier
    assert "docker volume prune" not in verifier

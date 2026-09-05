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


def test_compose_has_only_approved_services_and_five_named_volumes() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    service_block = compose.split("\nservices:\n", maxsplit=1)[1].split(
        "\nnetworks:\n", maxsplit=1
    )[0]
    service_names = re.findall(r"^  ([a-z][a-z0-9_-]*):$", service_block, re.MULTILINE)
    assert service_names == ["memory-api", "neo4j", "qdrant", "memos"]
    memory_api, private_services = service_block.split("\n  neo4j:\n", maxsplit=1)
    assert "ports:" in memory_api
    assert "ports:" not in private_services
    assert "internal: true" in compose
    for volume in ("memscope_data", "memos_data", "neo4j_data", "neo4j_logs", "qdrant_data"):
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


def test_memos_build_is_multistage_and_uses_configurable_internal_pypi() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "docker" / "memos" / "Dockerfile").read_text(encoding="utf-8")

    assert "B04_PIP_INDEX_URL:-https://cmc.centralrepo.rnd.huawei.com" in compose
    assert "B04_PIP_EXTRA_INDEX_URL:-https://cmc.centralrepo.rnd.huawei.com" in compose
    assert "B04_PIP_TRUSTED_HOST:-cmc.centralrepo.rnd.huawei.com" in compose
    assert "ARG PIP_INDEX_URL=https://cmc.centralrepo.rnd.huawei.com" in dockerfile
    assert "ARG PIP_EXTRA_INDEX_URL=" in dockerfile
    assert "ARG PIP_TRUSTED_HOST=cmc.centralrepo.rnd.huawei.com" in dockerfile
    assert "pip config set global.index-url" in dockerfile
    assert "pip config set global.extra-index-url" in dockerfile
    assert "pip config set global.trusted-host" in dockerfile
    assert dockerfile.count("FROM ${PYTHON_IMAGE}") == 2
    assert "AS builder" in dockerfile
    assert "AS runtime" in dockerfile
    assert "COPY --from=builder" in dockerfile
    assert "apt-get" not in dockerfile
    assert "build-essential" not in dockerfile
    assert "ARG SOURCE_DATE_EPOCH=1787929140" in dockerfile
    assert '--date="@${SOURCE_DATE_EPOCH}"' in dockerfile
    assert "--constraint /opt/vendor/constraints.txt" in dockerfile


def test_memos_transitive_constraints_are_exact() -> None:
    constraints = (ROOT / "docker" / "memos" / "constraints.txt").read_text(encoding="utf-8")
    requirements = [line for line in constraints.splitlines() if line and not line.startswith("#")]

    assert len(requirements) == 12
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[^\s]+", line) for line in requirements)


def test_compose_requires_secrets_and_explicit_b05_model_configuration() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    neo4j_service = compose.split("  neo4j:\n", maxsplit=1)[1].split("\n  qdrant:\n", maxsplit=1)[0]
    assert "${NEO4J_PASSWORD:?" in compose
    assert "neo4j/12345678" not in compose
    assert "      NEO4J_PASSWORD:" not in neo4j_service
    assert "$${NEO4J_AUTH#neo4j/}" in neo4j_service
    assert 'MEMSCOPE_MODEL_PROFILE: "${MEMSCOPE_MODEL_PROFILE:?' in compose
    assert (
        'MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP: "${MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP:-false}"'
        in compose
    )
    assert "MOS_EMBEDDER_BACKEND: universal_api" in compose
    assert "MOS_RERANKER_BACKEND: cosine_local" in compose
    assert "MEM_READER_TOKENIZER: word" in compose
    assert 'HF_HUB_OFFLINE: "1"' in compose
    assert 'TRANSFORMERS_OFFLINE: "1"' in compose
    assert 'MOS_EMBEDDER_API_BASE: "${MOS_EMBEDDER_API_BASE:?' in compose
    assert 'MEMRADER_API_BASE: "${MEMRADER_API_BASE:?' in compose
    assert 'EMBEDDING_DIMENSION: "${EMBEDDING_DIMENSION:?' in compose
    assert 'ENABLE_INTERNET: "false"' in compose
    assert 'API_SCHEDULER_ON: "false"' in compose
    assert 'MOS_ENABLE_REORGANIZE: "false"' in compose

    entrypoint = (ROOT / "docker" / "memos" / "entrypoint.sh").read_text(encoding="utf-8")
    assert ': "${MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP:=false}"' in entrypoint
    assert 'http://*) test "${MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP}" = "true"' in entrypoint


def test_memos_build_applies_locked_b04_and_b05_patchset() -> None:
    dockerfile = (ROOT / "docker" / "memos" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY docker/memos/apply_patchset.py" in dockerfile
    assert "COPY docker/memos/PATCHSET_LOCK.json" in dockerfile
    assert "python /opt/vendor/apply_patchset.py --source /opt/memos" in dockerfile
    assert "grep -F -c" not in dockerfile


def test_memos_patchset_guards_disabled_scheduler_shutdown() -> None:
    patcher = (ROOT / "docker" / "memos" / "apply_patchset.py").read_text(encoding="utf-8")

    assert 'getattr(self, "_io_loop_thread", None)' in patcher


def test_compose_readiness_covers_all_four_services() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("healthcheck:") == 4
    assert "cypher-shell" in compose
    assert "/dev/tcp/127.0.0.1/6333" in compose
    assert "http://127.0.0.1:8000/health" in compose
    assert compose.count("condition: service_healthy") == 3


def test_compose_has_resource_shutdown_and_log_controls() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    qdrant_service = compose.split("  qdrant:\n", maxsplit=1)[1].split("\n  memos:\n", maxsplit=1)[
        0
    ]
    memos_service = compose.split("\n  memos:\n", maxsplit=1)[1].split("\nnetworks:\n", maxsplit=1)[
        0
    ]
    memory_api_service = compose.split("  memory-api:\n", maxsplit=1)[1].split(
        "\n  neo4j:\n", maxsplit=1
    )[0]

    assert compose.count("stop_grace_period: 30s") == 4
    assert compose.count("pids_limit: 512") == 3
    assert "pids_limit: 256" in memory_api_service
    assert compose.count("logging: *default-logging") == 4
    assert 'max-size: "10m"' in compose
    assert 'max-file: "3"' in compose
    for service in ("MEMOS", "NEO4J", "QDRANT"):
        assert f"B04_{service}_MEMORY_LIMIT" in compose
        assert f"B04_{service}_CPU_LIMIT" in compose
    assert "init: true" in qdrant_service
    assert "init: true" in memory_api_service
    assert "init: true" not in memos_service


def test_runtime_verifier_is_scoped_to_disposable_b04_projects() -> None:
    verifier = (ROOT / "scripts" / "verify_b04_runtime.py").read_text(encoding="utf-8")
    assert "memscope_b04_gate_" in verifier
    assert 'f"B04-{secrets.token_urlsafe(24)}"' in verifier
    assert "NEO4J_AUTH#neo4j/" in verifier
    assert '"$NEO4J_PASSWORD"' not in verifier
    assert '["kill", "-KILL", pid_before]' in verifier
    assert '"stop", "--timeout", "30", "memos"' in verifier
    assert '"down", "--volumes", "--remove-orphans"' in verifier
    assert "docker system prune" not in verifier
    assert "docker volume prune" not in verifier

# B04 Gate 2 Handoff

> Status: Accepted/Frozen
>
> Gate 1 approved: 2026-09-02
>
> Gate 2 approved: 2026-09-03 by explicit user message “Gate 2 通过”
>
> Initial implementation commit: `9667c69`
>
> Final runtime-hardening commit: `432182a`

## 1. Delivered capability

B04 provides one Compose command surface containing exactly three single-purpose services: pinned
MemOS `v2.0.32`, Neo4j Community and Qdrant. It includes the complete fixed MemOS source archive,
license/checksum/image locks, a non-root multistage MemOS image, dependency-gated health, internal
networking, named volumes, restart policy, shutdown grace, CPU/memory/PID ceilings and bounded logs.

The B04 topology intentionally cannot perform semantic Add/Search. Model clients point to explicit
loopback no-call addresses, network tokenizer/model downloads are disabled, and no host ports are
published. MemOS health here proves infrastructure initialization only.

## 2. Accepted runtime evidence

The clean-room verifier passed on:

| Item | Recorded value |
|---|---|
| Platform | Linux/amd64, WSL2 kernel `6.18.33.2-microsoft-standard-WSL2` |
| Docker Engine | Community 29.7.2, API 1.55, rootless |
| Docker Compose | 5.4.0 |
| MemOS resolved image | `sha256:d073319403213693a8fff8351d20ab55eb3049b6f7c3b9d3a4940afa74f60b41` |
| Neo4j resolved image | `sha256:eef89955a0ff6ce578ec5fb264333818bb2f56e169bcb8dda5bcadad1fc48893` |
| Qdrant resolved image | `sha256:31407c0e8e32eb771b71718f1a4772e2ad47a07557917b21ac96792f40eb8007` |
| Bootstrap vector dimension | 16; lifecycle probe only, not a model decision |
| Cached clean-room build | 1.107 seconds |
| Cold start to all healthy | 31.547 seconds |
| Compose restart recovery | 39.252 seconds |

Passed lifecycle assertions:

- clean-room Compose config and image build;
- dependency-gated cold start and aggregate MemOS/Neo4j/Qdrant readiness;
- MemOS-created Qdrant collection with the configured bootstrap dimension;
- no published host ports and internal-only runtime network;
- MemOS local, Neo4j data/log and Qdrant named-volume markers survive restart;
- Qdrant stop is detected and recovers;
- all services have configured CPU/memory/PID ceilings and bounded JSON log rotation;
- MemOS process SIGKILL triggers automatic container recovery;
- MemOS graceful stop exits with code 0 and restarts healthy;
- generated Neo4j credentials do not appear in aggregated logs.

Authoritative command:

```bash
python scripts/verify_b04_runtime.py --report /tmp/b04-runtime-final-report.json
```

The verifier only creates and removes a randomly named `memscope_b04_gate_*` project and its test
volumes. It never performs global Docker prune or touches an existing project.

## 3. Static, reproducibility and image evidence

| Check | Result |
|---|---|
| B04 manifest tests | 12 passed |
| Full pytest regression | 330 passed in 8.16 seconds; 98.25% combined branch-aware coverage |
| Ruff format/lint | passed, 60 files checked at implementation freeze |
| Mypy | passed, 60 source files checked at implementation freeze |
| Hadolint 2.15.1 | zero findings |
| Source archive | SHA-256 `9a804fd874932f0a4fd86f75fa4edb48fdd41807417f236bacda49b8664cdf3c` |
| Image size | about 985 MB via Docker image list; accepted project limit is 1 GB |
| Dive 0.13.1 | about 693 MB unpacked; 99.45% layer efficiency |
| Secret scan | no embedded secrets found |

Two no-cache builds produced identical RootFS layer arrays and equal sizes. Their final image IDs
were `sha256:7c2809...` and `sha256:5ab12c...` because OCI config/history metadata differed. The
user approved functional reproducibility because the runtime filesystem, entry command and behavior
match; bit-for-bit image identity is not a B04 requirement.

## 4. Guarded fixed-source compatibility patches

The original vendored archive and checksum remain unchanged. During image build, the extracted copy
receives two explicit patches:

1. exactly three upstream hardcoded `gpt2` tokenizer defaults become
   `MEM_READER_TOKENIZER`, with B04 default `word`, so infrastructure startup never downloads a
   tokenizer; B05/B06 must choose an exact Qwen/GLM/local tokenizer based on the real algorithm;
2. disabled scheduler shutdown checks `_io_loop_thread` with `getattr`, because that thread is not
   created when the scheduler is disabled.

The Dockerfile asserts the exact original text/count before changing it, so an upstream source drift
fails closed instead of applying a blind patch.

## 5. Approved exceptions and open risk

- **Trivy debt:** an equivalent pinned B04 candidate scan recorded OS 23 HIGH/5 CRITICAL and Python
  38 HIGH/2 CRITICAL findings. The user explicitly waived these for B04; reports must not state
  “HIGH/CRITICAL = 0”. Upgrading FastMCP/Starlette/Transformers to suggested major versions without
  a separate compatibility batch could break FastAPI or MemOS.
- **Rootless evidence boundary:** resource ceilings are present in container configuration, but WSL
  rootless Docker cannot authoritatively prove host cgroup enforcement or boot/daemon auto-start.
  The final Linux deployment machine must retest both.
- **Build-network risk:** runtime does not access GitHub/Hugging Face, and MemOS source is vendored.
  A cold build still needs the pinned base images and Python wheels from reachable registry/PyPI or
  internal mirrors. B09 must freeze an internal registry/wheelhouse strategy if the final builder
  cannot reach them.
- **Persistence boundary:** named volumes cover restart/recreation on one Docker host, not cross-host
  backup/migration. Competition correctness currently needs only one Add→Search deployment lifecycle.
- **Vector dimension:** 16 is disposable B04 bootstrap data. A real Embedding dimension change
  requires recreating test collections/volumes or an explicit migration.

Post-acceptance release recheck on 2026-09-03 confirmed that this build-network risk is active. One
`--pull` build failed closed when the package path for `fastapi==0.115.14` advertised SHA-256
`04a412...`, while the downloaded bytes hashed to `95e96a...`. A separate download inside the same
pinned Python image then produced the valid 95,514-byte wheel at SHA-256 `6c0c8b...`, matching this
repository's `uv.lock`; a second complete build exceeded the 1,800-second dependency-download
timeout without reaching runtime startup. No source or hash check was relaxed. The previously
accepted image `d0733194...` remains available and its lifecycle evidence remains valid, but a
future clean build must use a stable reachable package mirror or audited wheelhouse.

## 6. Downstream contract

Downstream work may depend on the fixed three-service topology, image/source locks, service DNS,
health ordering and lifecycle verifier. It must not depend on bootstrap vectors, the offline `word`
tokenizer, loopback model placeholders, internal container implementation, or B04 MemOS health as
contest readiness.

B04 acceptance does not authorize B05. B05 must start in a new Session at Gate 0 and design the
write algorithm, model boundaries and tuning variables before any core implementation.

# B04 runtime infrastructure implementation plan

> Status: Gate 1 implementation complete; Docker Gate 2 execution pending
> Batch: B04
> Approved: 2026-09-02 by explicit user message “B04 Gate 1 审批通过”
> Base commit: `3ed5477d` (`main`)
> Branch: `batch/b04-runtime-infra`
> Boundary: B04 infrastructure only; B05 is not authorized

## Goal

Create the smallest reproducible runtime for fixed MemOS `v2.0.32`: one Compose entry containing
MemOS, Neo4j Community and Qdrant, with deterministic source/image locks, dependency-gated health,
internal networking, named volumes and an executable clean-room lifecycle verifier.

## Approved decisions

- Three services, not a supervised multi-process container: `memos`, `neo4j`, `qdrant`.
- No `memory-api`, Mock Model API, embedding service, reranker service or Ollama in B04.
- Complete MemOS source is included as a deterministic archive, not fetched by Git during build.
- B04 model URLs are explicit local no-call placeholders. No Add/Search/model capability is claimed.
- Compose publishes no ports. The backend network is internal at runtime.
- Four named volumes preserve MemOS local state, Neo4j data/logs and Qdrant data through restart.
- Local Gate 2 verifies restart persistence on one Docker host. Competition correctness still only
  depends on Add→Search within one deployment lifecycle; cross-host persistence is out of scope.
- The evaluator builds source from the ZIP. Build-time package access or cache is allowed by this
  B04 design; runtime downloads are forbidden.
- No production secret has a default. The verifier generates an isolated ephemeral Neo4j password.
- B00–B03 application code, interfaces, migrations and dependencies remain frozen.

## Deliverables

- `compose.yaml`, `.dockerignore`, `docker/memos/{Dockerfile,entrypoint.sh}`;
- `deploy/compose.env.example`;
- complete archive, `SOURCE_LOCK.json`, `SHA256SUMS`, upstream license and notices;
- `scripts/verify_b04_runtime.py` and static unit coverage;
- ADR 0005, fixed-source map and B04 Plan/Context/Handoff;
- narrow updates to repository navigation and current organizer facts.

## Gate 2 commands and evidence

Static repository gate:

```bash
uv lock --check --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Lifecycle gate on a clean Linux host with Docker Engine and Compose v2:

```bash
python scripts/verify_b04_runtime.py --report /tmp/b04-runtime-report.json
```

The verifier copies only build inputs to a fresh temporary directory, validates Compose, builds
the MemOS image, starts all services, waits for health, probes all backends, verifies the MemOS
collection, checks network/ports, verifies three-store restart persistence, injects a Qdrant stop,
checks failure detection and recovery, and removes only its randomly named project and volumes.

Gate 2 must record Docker/Compose versions, OS/architecture, image manifests, build/cold-start/
restart durations and every failure. Missing Docker is an environment blocker, not a pass.

## Rollback and safety

- All implementation stays on `batch/b04-runtime-infra` until Gate 2 approval.
- The verifier accepts only project names prefixed `memscope_b04_gate_`.
- Cleanup is `docker compose down --volumes --remove-orphans` scoped to that project; global prune,
  broad deletion and existing user volumes are forbidden.
- `.vendor-src/MemOS` remains untouched and is excluded from build/submission inputs.
- If fixed MemOS cannot initialize with its own requirements or the locked topology, stop and
  report the exact incompatibility; do not patch upstream or enter B05 without a new review.

## Exit criteria

B04 can enter Gate 2 review only when all static gates and the complete clean-room Docker lifecycle
run pass. Gate 1 approval authorizes implementation; it does not pre-approve Gate 2 or B05.

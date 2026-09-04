# MemScope

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. B01 provides the contest HTTP contract, B02 the transactional Raw Store, and B03 a
provider-independent Memory Gateway plus deterministic no-key substitutes. B04 adds the pinned
MemOS/Neo4j/Qdrant runtime infrastructure. B00–B09 are accepted/frozen; B05 delivers synchronous
Real Add and B06 delivers Real Search plus complete readiness. B05/B06 real-model and Docker
host-port/cgroup validation is transferred to a capable tuning machine under the accepted handoff
conditions. B07 freezes the tests-and-documents reliability closure without changing production
code. B08's deterministic system-verification candidate at `44ce4a7` is accepted/frozen under the
tuning-machine live-evidence transfer exception; this is not a live-system pass claim. B09 Gate 1
is approved and reproducible-delivery candidate `fe246c0` is Accepted/Frozen at Gate 2. Final
handoff ZIP/hash generation is explicitly prohibited pending additional development and version
consolidation. Docker is an optional delivery accelerator, not a prerequisite for tuning.

## Development environment

- CPython 3.11.16
- uv 0.12.9
- No model API key or external service is required for the current scaffold

Install the locked development environment:

```bash
uv sync --frozen
```

On a Linux x86_64 laboratory host with Docker Engine and Compose v2, the complete production-profile
stack can be validated, built and started with one command:

```bash
./scripts/deploy_linux.sh --env-file /secure/path/memscope.env
```

The script verifies the locked MemOS archive, runs `uv sync --frozen`, validates Compose without
printing resolved secrets, builds both local images, starts the four-service stack and waits for the
public Health contract. If the selected env file does not exist, the script creates it from
`deploy/compose.env.example` with mode `0600` and opens `${VISUAL:-$EDITOR}` (or a standard terminal
editor) so the operator can replace the placeholders. Existing env files are never overwritten. It
never creates credentials or removes persistent volumes. Use `--check-only` to stop after the
configuration preflight or `--build-only` to stop after the image build.

Create a local environment file only when overrides are needed:

```bash
cp .env.example .env
```

`.env` is ignored and must never be committed.

## Quality gates

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Coverage is branch-aware, covers only `src/memscope`, and must remain at least 95% overall.
The Gate 2 handoff reports statement and branch coverage separately.

## Contest adapter

Start the ASGI adapter with one worker:

```bash
uv run uvicorn memscope.main:app --host 0.0.0.0 --port 8080 --workers 1
```

The adapter registers:

- `GET /health`
- `POST /add`
- `POST /search`

The default composition still does not install a complete `ContestOperations` implementation. It
therefore returns 503 from all three valid contest calls instead of claiming false readiness,
persistence, or retrieval. B03 tests assemble Raw Store + Fake Gateway only through explicit app
factory injection; the Fake is never a default or submission candidate.

Health is always unauthenticated. Add and Search authentication defaults to `none`. To enable one
shared key through any one of Bearer, Token, or X-Api-Key:

```text
CONTEST_AUTH_MODE=shared_key
CONTEST_API_KEY=<secret supplied outside source control>
```

Never commit the key or place it in logs or command examples.

## Raw Store component

The B02 SQLite component can be opened explicitly by later orchestration or component tests:

```python
from memscope.raw_store import SqliteRawStore

store = await SqliteRawStore.open(
    settings.database_path,
    busy_timeout_ms=settings.sqlite_busy_timeout_ms,
)
```

Defaults are `DATABASE_PATH=data/memory.db` and `SQLITE_BUSY_TIMEOUT_MS=5000`. The local `data/`
directory and SQLite WAL/SHM artifacts are ignored. Every operation uses a private short-lived
connection with WAL, FULL synchronous mode and foreign keys. `prepare_add` is durable and
idempotent locally, but B02 does not call MemOS or expose a successful HTTP Add path.

The stable internal contract and consistency limits are documented in
`docs/interfaces/raw-store-v1.md`.

## B03 no-key substitutes

`FakeMemoryGateway` provides a non-durable deterministic implementation of the internal
`MemoryGateway` contract. `MemoryOperations` composes it with a `RawStore` for tests. This path
proves synchronous visibility, replay, recovery and isolation; its token-overlap ranking is not a
quality result.

The independent Mock Model API can be started for protocol tests:

```bash
uv run uvicorn memscope.mock_model_api.main:app --host 127.0.0.1 --port 18080 --workers 1
```

It exposes health plus a small non-streaming Chat/Embedding subset, requires no key, and must not be
enabled in an organizer profile. See `docs/interfaces/memory-gateway-v1.md` and
`docs/interfaces/mock-model-api-v1.md` for exact contracts and non-compatibility boundaries.

## B04–B06 runtime

B04 uses one Compose entry with three internal services: fixed MemOS `v2.0.32`, Neo4j Community
and Qdrant. It exposes no host port and deliberately has no usable model endpoint, so it is an
infrastructure lifecycle target rather than a contest service. The complete upstream source archive,
license, SHA-256 and OCI image locks are included under `third_party/memos/`.

On a clean Linux Docker Compose v2 host, rerun the accepted build/start/restart/fault gate with:

```bash
python scripts/verify_b04_runtime.py --report /tmp/b04-runtime-report.json
```

The verifier uses a random isolated project and removes only that project's test volumes. B04 Gate 2
passed on 2026-09-03; evidence and accepted exceptions are in `docs/batches/B04/HANDOFF.md`. See also
`docs/batches/B04/PLAN.md` and `docs/adr/0005-b04-compose-runtime-topology.md`. Do not interpret MemOS
`/health` as Add/Search/model readiness.

B05 adds the public `memory-api`, real MemOS Add wiring and a deterministic no-key runtime fixture.
The images build successfully, but full host-port and cgroup proof is environment-dependent. Use
`docs/batches/B06/ORGANIZER_DEPLOYMENT.md` to select and gate the Compose or native path; complete
native commands are in `docs/batches/B06/NATIVE_DEPLOYMENT.md`. Do not postpone model/evaluation
tuning to repair an optional container runtime.

B06 adds real Product Search, strict active/provenance filtering, stable exact deduplication,
55-second end-to-end Search budgeting and complete public readiness. The fixed Search baseline is
`fast + cosine_local`; it does not select answers or default-enable MMR/BM25/full-text/external
reranking. Development-machine tests do not substitute for a Huawei-model Add/Search smoke.

## Development and tuning workflow

During the active 48-hour delivery window, use the mandatory fast iteration path:

```text
Python unit/contract tests
  -> native memory-api or source bind mount
  -> reuse running Neo4j/Qdrant/MemOS
  -> freeze code
  -> one final image build
```

See `docs/collaboration/48H_DELIVERY_GUARDRAILS.md` and the linked B05 Add tuning design before
starting Docker or model experiments.

Development/Git work and Huawei-network tuning run on separate machines. The development machine
owns accepted B05/B06, B07 deterministic closure, SDD and a checksummed tuning handoff. The tuning machine
owns real gateway probes, Docker revalidation, baseline/full evaluation, controlled tuning and the
final submission ZIP. It must return source/config differences and evidence so the final candidate
remains auditable.

Start with `docs/README.md`, `docs/acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md` and
`docs/collaboration/TWO_MACHINE_WORKFLOW.md`. B05 Gate 0 R1 is recorded in
`docs/batches/B05/GATE0.md`; its approved Gate 1 implementation plan is
`docs/batches/B05/PLAN.md`, and the native deployment fallback is
`docs/batches/B05/NATIVE_DEPLOYMENT.md`. B06 Gate 0 R1 is recorded in
`docs/batches/B06/GATE0.md`; its approved Gate 1 plan is `docs/batches/B06/PLAN.md`, the unified
organizer deployment gate is `docs/batches/B06/ORGANIZER_DEPLOYMENT.md`, and the complete native
path is `docs/batches/B06/NATIVE_DEPLOYMENT.md`.

## Current boundaries

B06 implements Real Add + Search + complete readiness and was accepted/frozen at Gate 2 on
2026-09-04. It does not claim a final model, semantic score, reliable natural-language
update/forget publication, outbox workers,
production retries/fallback or final-answer generation. See
`docs/interfaces/contest-http-v1.md`,
`docs/interfaces/raw-store-v1.md`, `docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, and the active Batch
documents for the current contracts and scope.

B07 Gate 2 was accepted/frozen on 2026-09-04 at `e30fa91`. Its scope is limited to composed restart,
reconciliation, fail-closed and no-automatic-retry evidence in deterministic tests plus correction of
the historical B07–B09 sequencing text. B08 Gate 1 is approved and adds only a public verifier,
deterministic system tests and a runbook. B08 Gate 2 was accepted/frozen on 2026-09-04 under the
tuning-machine live-evidence transfer exception; real exercise/restart/resource evidence remains a
transferred item and is not claimed as passed. B09 has entered Gate 1 planning, with no B09
product change authorized. Its delivery candidate `fe246c0` adds organizer instructions,
lock/license audit, deterministic handoff/submission packaging and two-machine SHA-256 closure.
B09 Gate 2 is Accepted/Frozen, but the user explicitly prohibited the final handoff ZIP and
out-of-band SHA-256 pending additional development/version consolidation. No final artifact or tag
exists, and the preview hashes are not final delivery identities.

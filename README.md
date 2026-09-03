# MemScope

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. B01 provides the contest HTTP contract, B02 the transactional Raw Store, and B03 a
provider-independent Memory Gateway plus deterministic no-key substitutes. B04 adds the pinned
MemOS/Neo4j/Qdrant runtime infrastructure and is accepted/frozen. Real MemOS Add/Search integration
remains deferred; B05 and B06 have not started.

## Development environment

- CPython 3.11.16
- uv 0.12.9
- No model API key or external service is required for the current scaffold

Install the locked development environment:

```bash
uv sync --frozen
```

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

## B04 infrastructure runtime

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

## Development and tuning workflow

Development/Git work and Huawei-network tuning run on separate machines. The development machine
owns B05/B06 Gate 0–2, deterministic tests, SDD and a checksummed tuning handoff. The tuning machine
owns real gateway probes, Docker revalidation, baseline/full evaluation, controlled tuning and the
final submission ZIP. It must return source/config differences and evidence so the final candidate
remains auditable.

Start with `docs/README.md`, `docs/acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md` and
`docs/collaboration/TWO_MACHINE_WORKFLOW.md`. B05 and B06 must each begin in a new Session with a
user-approved Gate 0 algorithm review; B04 acceptance does not authorize either implementation.

## Current boundaries

B04 adds only the pinned infrastructure topology. It does not implement the Real Gateway, public
contest composition, model access, Add/Search, semantic retrieval, quality results, outbox workers,
production retries/fallback or final-answer generation. See `docs/interfaces/contest-http-v1.md`,
`docs/interfaces/raw-store-v1.md`, `docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, and the active Batch
documents for the current contracts and scope.

# MemScope

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. B01 provides the contest HTTP contract, B02 the transactional Raw Store, and B03 a
provider-independent Memory Gateway, application orchestration, deterministic in-process Fake and
independent no-key Mock Model API. Real MemOS integration remains deferred.

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

## Current boundaries

B03 adds a complete explicit Fake test path and isolated model HTTP Mock. It does not implement real
MemOS, Qdrant, Neo4j, semantic retrieval, model quality, lifecycle behavior, outbox workers,
production retries/fallback or final-answer generation. See `docs/interfaces/contest-http-v1.md`,
`docs/interfaces/raw-store-v1.md`, `docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, and the active Batch
documents for the current contracts and scope.

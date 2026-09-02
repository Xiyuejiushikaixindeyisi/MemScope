# MemScope

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. B01 provides the contest HTTP contract and a framework-independent application port.
B02 adds the internal transactional Raw Store, stable identity and migration foundation. Memory
Gateway and application orchestration remain deferred to later batches.

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

The default composition does not install a complete `ContestOperations` implementation. It
therefore returns 503 from all three valid contest calls instead of claiming false readiness,
persistence, or retrieval. B02's Raw Store is an internal component; B03 and later batches assemble
the complete path through the app factory.

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

## Current boundaries

B02 provides SQLite persistence, local idempotency, ordered raw messages, user/Cube mapping and a
pending/completed outbox record. It does not implement MemOS, Qdrant, Neo4j, model calls, retrieval,
outbox workers, retries, fallback or final-answer generation. See `docs/interfaces/contest-http-v1.md`,
`docs/interfaces/raw-store-v1.md`, `docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, and the active Batch
documents for the current contracts and scope.

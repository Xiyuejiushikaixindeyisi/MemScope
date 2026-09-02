# MemScope

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. B01 provides the contest HTTP contract and a framework-independent application port.
Raw storage and memory backends are intentionally deferred to later batches.

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

The default B01 composition has no Raw Store or memory implementation. It therefore returns 503
from all three valid contest calls instead of claiming false readiness, persistence, or retrieval.
Later batches inject a `ContestOperations` implementation through the app factory.

Health is always unauthenticated. Add and Search authentication defaults to `none`. To enable one
shared key through any one of Bearer, Token, or X-Api-Key:

```text
CONTEST_AUTH_MODE=shared_key
CONTEST_API_KEY=<secret supplied outside source control>
```

Never commit the key or place it in logs or command examples.

## Current boundaries

B01 performs no database, MemOS, Qdrant, Neo4j, model, or external network calls. It does not
implement persistent idempotency, user isolation, retries, fallback, or final-answer generation.
See `docs/interfaces/contest-http-v1.md`, `docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, and
`docs/batches/B01/PLAN.md` for the current contract and approved scope.

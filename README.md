# MemScope

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. The current B00 batch provides only the engineering foundation; contest
`/health`, `/add`, and `/search` endpoints are intentionally deferred to B01.

## Development environment

- CPython 3.11.16
- uv 0.12.9
- No model API key or external service is required for B00

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

## Minimal application

Start the B00 ASGI shell with one worker:

```bash
uv run uvicorn memscope.main:app --host 0.0.0.0 --port 8080 --workers 1
```

`/openapi.json` proves the ASGI shell is running. The contest endpoints remain absent until
B01, so `/health`, `/add`, and `/search` return 404 in B00.

## Current boundaries

B00 performs no database, MemOS, Qdrant, Neo4j, model, or external network calls. See
`docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, and `docs/batches/B00/PLAN.md` for the current
architecture and approved scope.

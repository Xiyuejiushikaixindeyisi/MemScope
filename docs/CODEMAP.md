# MemScope Codemap

## Current modules

| Path | Responsibility | May depend on |
|---|---|---|
| `src/memscope/settings.py` | Typed environment configuration and sanitized load failures | Pydantic Settings, internal errors |
| `src/memscope/errors.py` | Transport-independent structured errors | Python standard library |
| `src/memscope/logging_config.py` | Idempotent JSON/console application logging | Python standard library, Settings |
| `src/memscope/app.py` | Dependency-injectable FastAPI app factory | Settings, logging, FastAPI |
| `src/memscope/main.py` | Default ASGI composition root | App factory |
| `src/memscope/operations.py` | Framework-independent contest commands, evidence and application port | Python standard library, internal errors |
| `src/memscope/api/models.py` | Strict external Health/Add/Search/error JSON models | Pydantic |
| `src/memscope/api/auth.py` | Optional shared-key parsing for Bearer, Token and X-Api-Key | Settings, internal errors, Starlette headers |
| `src/memscope/api/errors.py` | Sanitized HTTP error mapping and bounded request logging | FastAPI/Starlette, internal errors/logging |
| `src/memscope/api/routes.py` | HTTP-to-application mapping, exact response shaping and top-k safety truncation | API models/auth, ContestOperations, FastAPI |
| `tests/unit/` | Settings, error, logging and app behavior | Public B00 module surfaces |
| `tests/contract/` | End-to-end ASGI contract, auth, failure and cancellation behavior | App factory plus tests-only operation recorder |
| `tests/smoke/` | In-process ASGI and real Uvicorn startup/readiness checks | Installed project and locked test dependencies |

## Dependency direction

```text
main → app ─┬→ api.routes → api.models
            │             → api.auth → settings → errors
            │             → operations → errors
            ├→ api.errors → errors / logging_config
            ├→ settings → errors
            └→ logging_config → settings
```

Settings, errors and operations remain framework-independent. API modules may depend on FastAPI or
Pydantic, but future Raw Store, orchestration and Gateway implementations must not. Runtime defaults
to `UnavailableContestOperations`; successful substitutes remain test-only until their owning Batch.

## Deferred ownership

- B02: Raw Store, SQLite schema/migrations, idempotency and user/cube identity mapping.
- B03: Fake MemOS Gateway and Mock Model API substitutes sharing approved application contracts.
- B04+: infrastructure and real MemOS integration.

This file records navigation and dependency direction, not implementation copies.

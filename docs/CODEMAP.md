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
| `src/memscope/raw_store/models.py` | Frozen Raw Store dispositions, response, Cube and persisted Add/message values | Python standard library |
| `src/memscope/raw_store/identity.py` | Canonical Add v1 hashing and stable logical Cube/message IDs | AddCommand, Python standard library |
| `src/memscope/raw_store/protocol.py` | Async persistence port for future orchestration | AddCommand, Raw Store models |
| `src/memscope/raw_store/migrations.py` | Forward-only SQLite Schema and checksum ledger | Python sqlite3 |
| `src/memscope/raw_store/sqlite.py` | Short-connection SQLite transactions, replay classification and recovery reads | Raw Store modules, AddCommand, sqlite3/asyncio |
| `tests/unit/` | Settings, errors, logging, HTTP models, identity and persistence value behavior | Public module surfaces |
| `tests/component/` | SQLite migration, persistence, restart, concurrency, cancellation and fault behavior | Public RawStore interface and temporary databases |
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

future orchestration → raw_store.protocol
                            ↑
                    raw_store.sqlite
                      ├→ migrations
                      ├→ identity → operations.AddCommand
                      └→ models / errors
```

Settings, errors and operations remain framework-independent. API modules may depend on FastAPI or
Pydantic. Raw Store models/protocol/migrations are framework-independent, and SQLite is confined to
one implementation. Runtime still defaults to `UnavailableContestOperations`; B02 deliberately does
not connect component readiness to HTTP readiness.

## Deferred ownership

- B03: Fake MemOS Gateway and Mock Model API substitutes sharing approved application contracts.
- B04+: infrastructure and real MemOS integration.

This file records navigation and dependency direction, not implementation copies.

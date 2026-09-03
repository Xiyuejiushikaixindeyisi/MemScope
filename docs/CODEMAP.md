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
| `src/memscope/memory_gateway/models.py` | Strict provider-independent Add/Search/evidence provenance values | Python standard library |
| `src/memscope/memory_gateway/protocol.py` | Replaceable async memory-provider port | Gateway models |
| `src/memscope/memory_gateway/fake.py` | Non-durable deterministic Gateway contract Fake and typed fault injection | Gateway contract, asyncio |
| `src/memscope/application/memory_operations.py` | NEW/PENDING/COMPLETED orchestration, conflict translation and Search isolation | Contest operations, RawStore and MemoryGateway ports |
| `src/memscope/mock_model_api/` | Independent deterministic Chat/Embedding HTTP subset | FastAPI/Pydantic and standard library |
| `compose.yaml` | B04 MemOS/Neo4j/Qdrant topology, health ordering, internal network and named volumes | Docker Compose v2 |
| `docker/memos/` | Builds/runs the fixed upstream MemOS source archive | pinned Python image, bundled source |
| `third_party/memos/` | Complete MemOS archive, source/image lock, checksum and upstream license | fixed upstream commit |
| `scripts/verify_b04_runtime.py` | Disposable clean-room build, readiness, restart persistence and fault-recovery evidence | Docker Engine/Compose v2 |
| `docs/acceptance/` | Verified contest requirements, project gates and explicitly pending facts | Formal task/API materials and user approvals |
| `docs/collaboration/` | Two-machine workflow, human/AI rules and transfer/tuning templates | Current project context and Git identities |
| `tests/unit/` | Settings, errors, logging, HTTP models, identity and persistence value behavior | Public module surfaces |
| `tests/component/` | SQLite migration, persistence, restart, concurrency, cancellation and fault behavior | Public RawStore interface and temporary databases |
| `tests/contract/` | Contest HTTP, reusable Gateway, explicit Fake path and Mock Model contracts | Public ports and app factories |
| `tests/smoke/` | Default/Fake ASGI paths and real default/Mock Uvicorn processes | Installed project and locked test dependencies |

## Dependency direction

```text
main → app ─┬→ api.routes → api.models
            │             → api.auth → settings → errors
            │             → operations → errors
            ├→ api.errors → errors / logging_config
            ├→ settings → errors
            └→ logging_config → settings

api.routes → ContestOperations ← application.MemoryOperations
                                      ├→ raw_store.protocol ← raw_store.sqlite
                                      │                         ├→ migrations
                                      │                         ├→ identity
                                      │                         └→ models / errors
                                      └→ memory_gateway.protocol ← memory_gateway.fake

mock_model_api.main → mock_model_api.app → mock_model_api.models / deterministic
```

Settings, errors, operations, Gateway and Raw Store contracts remain framework-independent. API and
Mock Model modules may depend on FastAPI/Pydantic. SQLite and Fake details are confined to their
implementations. Runtime still defaults to `UnavailableContestOperations`; only tests explicitly
inject the B03 Fake path. B04 Compose is an independent infrastructure target and does not import
or replace the `src/memscope` composition root.

## Batch ownership

- B00–B04: accepted and frozen. B04 runtime lifecycle evidence is recorded in
  `docs/batches/B04/HANDOFF.md`.
- B05: Real Gateway, public adapter composition, Cube lifecycle and synchronous Add. Not started;
  must begin in a new Session at Gate 0.
- B06: Search conversion, isolation, evidence length/ranking and failure policy. Not started; must
  begin in a separate new Session at Gate 0.
- Real Huawei API probes, semantic baseline and tuning belong to the tuning machine and do not
  become Git facts until their reports and source/config differences are returned.

This file records navigation and dependency direction, not implementation copies.

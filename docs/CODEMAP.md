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
| `src/memscope/memory_gateway/memos.py` | Strict async MemOS Product Add adapter, tenant/digest readback and deadline/error translation | Gateway contract, HTTPX, receipt store |
| `src/memscope/memory_gateway/receipt_store.py` | Durable provider-delivery idempotency receipts | SQLite/asyncio |
| `src/memscope/application/memory_operations.py` | Deadline-bounded NEW/PENDING/COMPLETED Add orchestration and Search isolation | Contest operations, RawStore, MemoryGateway and user lanes |
| `src/memscope/application/user_lanes.py` | FIFO same-user serialization with cross-user concurrency and cancellation cleanup | asyncio |
| `src/memscope/runtime.py` | Lifespan-owned `memos_add` resource composition and reverse cleanup | Settings, Raw Store, Real Gateway |
| `src/memscope/mock_model_api/` | Independent deterministic Chat/Embedding HTTP subset | FastAPI/Pydantic and standard library |
| `compose.yaml` | B05 public memory-api plus MemOS/Neo4j/Qdrant topology, health ordering, networks and volumes | Docker Compose v2 |
| `docker/memory-api/` | Builds/runs the non-root public Adapter process | locked MemScope runtime dependencies |
| `docker/memos/` | Builds/runs fixed MemOS with hash-guarded B04/B05 compatibility patches | pinned Python image, bundled source |
| `third_party/memos/` | Complete MemOS archive, source/image lock, checksum and upstream license | fixed upstream commit |
| `scripts/verify_b04_runtime.py` | Disposable clean-room build, readiness, restart persistence and fault-recovery evidence | Docker Engine/Compose v2 |
| `scripts/verify_b05_runtime.py` | Optional clean-room no-key Add/replay/isolation/deadline/runtime evidence | Docker Engine/Compose v2 |
| `docs/batches/B05/NATIVE_DEPLOYMENT.md` | First-class host-process deployment fallback when Docker is unavailable | Python 3.11, Neo4j, Qdrant |
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
                                      └→ memory_gateway.protocol ←┬─ memory_gateway.fake
                                                                 └─ memory_gateway.memos
                                                                       └→ receipt_store

mock_model_api.main → mock_model_api.app → mock_model_api.models / deterministic
app lifespan → runtime → raw_store.sqlite + memory_gateway.memos
```

Settings, errors, operations, Gateway and Raw Store contracts remain framework-independent. API and
Mock Model modules may depend on FastAPI/Pydantic. Runtime defaults to
`UnavailableContestOperations`; only the explicit `memos_add` profile opens SQLite and the Real
Gateway during ASGI lifespan. The B03 Fake remains test-only.

## Batch ownership

- B00–B04: accepted and frozen. B04 runtime lifecycle evidence is recorded in
  `docs/batches/B04/HANDOFF.md`.
- B05: Real Gateway, public adapter composition, Cube lifecycle and synchronous Add. Gate 0 R1 is
  confirmed, Gate 1 is approved and implementation is in final verification. Docker runtime
  hardening is optional and must not displace model/evaluation tuning.
- B06: Search conversion, isolation, evidence length/ranking and failure policy. Not started; must
  begin in a separate new Session at Gate 0.
- Real Huawei API probes, semantic baseline and tuning belong to the tuning machine and do not
  become Git facts until their reports and source/config differences are returned.

This file records navigation and dependency direction, not implementation copies.

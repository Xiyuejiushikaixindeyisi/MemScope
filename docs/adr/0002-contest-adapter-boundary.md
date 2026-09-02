# ADR 0002: Separate the Contest HTTP Adapter from Memory Operations

- Status: Accepted for B01
- Date: 2026-09-02
- Decision owner: B01 Gate 1

## Context

The competition fixes an evaluator-facing Health/Add/Search JSON contract, while persistence,
idempotency, Raw Store and MemOS integrations arrive in separate later batches. Coupling FastAPI or
Pydantic models directly to those implementations would make protocol changes propagate through the
system and make Fake and real paths diverge.

B01 also has no persistence-capable runtime implementation. Returning successful placeholder data
would violate synchronous Add and readiness semantics.

## Decision

Use a thin FastAPI Adapter and one asynchronous `ContestOperations` application port:

- external Pydantic models validate and serialize only the competition contract;
- explicit mapping produces frozen standard-library dataclasses;
- future application orchestration implements the port without importing FastAPI/Pydantic;
- the production default is an unavailable implementation that returns false readiness and raises a
  safe 503 error for Add/Search;
- successful recorders and fault injectors remain in tests;
- the later `MemoryGateway` is a lower-level integration boundary and is not conflated with this
  application port.

## Consequences

- B01 can fully test HTTP success and failure behavior without claiming durable memory exists.
- B02/B03 can evolve storage and Gateway implementations behind a stable evaluator contract.
- One explicit mapping layer adds small code and test cost.
- The public process returns 503 until a later Batch installs complete operations; this is deliberate
  and must be documented in Smoke and handoff material.

## Revisit conditions

Revisit if the organizer changes the HTTP contract or synchronous semantics, or if later application
orchestration proves that the port methods cannot represent required atomicity or readiness.

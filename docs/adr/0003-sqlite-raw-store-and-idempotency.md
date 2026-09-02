# ADR 0003: Use a Transactional SQLite Raw Store with Versioned Identity

- Status: Accepted for B02
- Date: 2026-09-02
- Decision owner: B02 Gate 1

## Context

The contest Add contract requires synchronous durability, stable request identity, exact message
order and user isolation before a memory backend is available. Future MemOS writes cannot share an
atomic transaction with local state, and organizer hardware/concurrency limits are still unknown.
The project also needs deterministic no-key tests and a replaceable foundation for finals work.

Long-lived SQLite connections are awkward with `asyncio.to_thread`: a connection is thread-affine
by default, and cancellation can release an async caller while its worker thread continues. Adding
`check_same_thread=False` plus an event-loop lock would still make cancellation and close behavior
easy to misread. An ORM, Alembic or aiosqlite would add dependencies without removing the external
consistency boundary.

## Decision

Use the standard-library `sqlite3` driver behind an asynchronous `RawStore` protocol:

- every blocking operation owns one short-lived connection created and closed in its worker thread;
- WAL, FULL synchronous mode, foreign keys and bounded busy timeout are mandatory;
- `BEGIN IMMEDIATE` plus database constraints decide concurrent writes across instances/processes;
- Add preparation atomically writes request, messages, stable user/Cube mapping and pending outbox;
- Add completion atomically stores the canonical response and completes the outbox;
- canonical Add v1 and version-prefixed SHA-256 identities are documented and golden-tested;
- forward-only embedded migrations use immutable checksums and fail closed;
- pending external work supports future at-least-once recovery without claiming distributed
  exactly-once.

The runtime default is not wired to this component in B02. Health/Add/Search remain 503 until a
later Batch provides a complete Add and Search path.

## Consequences

- File-backed persistence, restart recovery and concurrency behavior are testable without keys or
  external services.
- Per-operation connection setup and `synchronous=FULL` add measurable write latency; correctness is
  preferred until organizer hardware and timeouts permit evidence-based tuning.
- Cancelled callers may observe no response even though their private transaction completes; retry
  convergence depends on the stable request ID.
- The durable outbox is data only in B02. Worker leases, retry policy and external readback remain
  B07 responsibilities.
- Logical Cube IDs remain stable if MemOS later requires a separate provider identifier.

## Rejected alternatives

- In-memory storage cannot prove restart, process or persistent idempotency behavior.
- One shared connection requires fragile cross-thread/cancellation coordination.
- A process-local mutex cannot protect multiple instances or future workers.
- ORM/Alembic/aiosqlite dependencies are disproportionate for the current five-table schema.
- Writing MemOS first loses a durable recovery record; claiming a distributed transaction would be
  incorrect.

## Revisit conditions

Revisit after measured organizer hardware/concurrency data, a demonstrated SQLite bottleneck, a
provider Cube constraint, or a finals requirement that changes storage scale or topology. Any
durability reduction requires separate review and crash/performance evidence.

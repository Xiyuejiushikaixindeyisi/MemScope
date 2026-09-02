# Raw Store Interface v1

> Owner: B02
> Authority: approved B02 Gate 1 plan
> Scope: internal persistence contract; not an evaluator-facing API

## Purpose and boundary

Raw Store v1 durably records normalized Add inputs before a future Gateway call. It owns raw
messages, persistent idempotency, logical user/Cube identity and the durable outbox boundary. It
does not implement memory extraction, current-effective-memory semantics, retrieval, lifecycle
interpretation or final-answer generation.

The asynchronous `RawStore` protocol exposes:

- `is_ready()` to probe an already-open current schema without migrating it;
- `prepare_add(command)` to atomically persist a new request or classify an exact replay;
- `complete_add(request_id, payload_sha256, response)` to atomically retain the successful response
  and mark its outbox complete;
- `load_add(user_id, request_id)` for user-isolated recovery reads;
- `close()` to reject new operations while allowing work already running in a worker thread to
  finish its private transaction.

`SqliteRawStore.open(...)` is the only operation that creates parent directories, creates a
database or applies migrations. B02 does not install this store into `ContestOperations`; the
default HTTP application therefore remains deliberately unavailable.

## Identity and canonical payload

The canonical payload contains schema `memscope.add.v1`, all three exact external IDs and every
message's exact role, content and nullable timestamp in array order. JSON serialization uses UTF-8,
sorted keys, compact separators and unescaped Unicode. It does not normalize Unicode, whitespace or
IDs. Its lowercase SHA-256 is stored with `payload_schema_version=1`.

Logical identities are:

```text
cube_id    = "cube_v1_" + sha256(UTF-8 user_id).hexdigest()
message_id = "msg_v1_"  + sha256(canonical_json([request_id, request_position])).hexdigest()
```

These hashes provide deterministic identity, not anonymization. Provider-specific Cube identifiers
may be added later without changing the v1 logical ID.

## Add state machine

```text
request absent
  └─ prepare_add ─→ pending request + raw messages + reserved Cube + pending outbox
                         │
                         ├─ same payload replay ─→ PENDING, no writes
                         ├─ different payload ───→ request.conflict, no writes
                         └─ complete_add ─────────→ completed request/response + completed outbox
                                                        │
                                                        └─ same payload replay ─→ COMPLETED response
```

`NEW` means the local transaction was inserted. `PENDING` is never a successful Add replay because
there is no stored successful response yet. `COMPLETED` always includes a validated exact response.
The future orchestration layer owns pending wait/recovery behavior and HTTP 409 mapping.

## Ordering and isolation

- `request_position` starts at zero for every Add chunk and preserves input order.
- `session_position` is allocated continuously for the exact `(user_id, session_id)` under
  `BEGIN IMMEDIATE`; concurrent chunks are ordered by acquisition of the SQLite write transaction.
- `load_add` requires both user and request ID and returns no record for a mismatched user.
- Composite foreign keys bind messages to their request/user/session and outbox records to their
  request/Cube. User and logical Cube IDs are both unique.

The contract does not infer order from the textual shape of `request_id` and Search must not filter
by session.

## SQLite and migration guarantees

The v1 implementation uses one short-lived connection per blocking operation. Each connection
enables foreign keys, configures the bounded busy timeout and `synchronous=FULL`, and verifies WAL
and the current migration ledger. No connection crosses worker threads.

Schema migration is forward-only. An exclusive transaction creates/verifies the ledger, checks
contiguous versions and immutable migration checksums, applies outstanding statement tuples, and
updates both the ledger and `PRAGMA user_version`. A checksum mismatch, gap, future version, failed
DDL or integrity failure fails closed without exposing SQL or database paths.

SQLite transactions provide exactly-once insertion for local request/messages/Cube/outbox state.
SQLite and future MemOS calls do not form a distributed transaction. A process crash after an
external write but before `complete_add` deliberately leaves a pending outbox for later
at-least-once recovery using provenance and downstream idempotency.

## Errors and cancellation

| Error | Retryable | Meaning |
|---|---:|---|
| `request.conflict` | no | Existing request ID has another canonical payload |
| `storage.unavailable` | yes | Lock, closed store, filesystem or transient SQLite failure |
| `storage.invariant_failed` | no | Persisted state violates the v1 model |
| `storage.migration_failed` | no | Schema version, checksum or migration is unsafe |

Errors and logs never contain SQL, full database paths, payload digests, business IDs, messages,
timestamps, response JSON or SQLite exception text.

Cancelling the awaiting coroutine does not stop work already running in `asyncio.to_thread`. That
worker owns a private connection and must finish commit/rollback and close it. A retry with the same
request ID converges through persistent idempotency.

## Evolution rules

Changing canonicalization, ID algorithms, Schema v1 interpretation, Add dispositions or transaction
boundaries requires a new architecture review. Schema evolution must use a new forward migration.
FTS/Raw Search, outbox leases/retries, provider Cube state and lifecycle fields belong to later
batches and must not be retrofitted into v1 semantics silently.

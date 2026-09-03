# Memory Gateway Interface v1

> Owner: B03 contract; B05 Real Add implementation
> Scope: internal provider boundary; not an evaluator-facing API

## Purpose

`MemoryGateway` separates MemScope application orchestration from the memory provider. It accepts
already-validated, provenance-bearing messages and returns evidence; it does not own the contest
HTTP contract, local durability, final-answer generation, lifecycle policy, retries or fallback.
The B03 implementation is an in-process Fake. B05 adds a real MemOS adapter while keeping MemOS and
HTTP DTOs behind this interface.

The async port exposes `is_ready()`, idempotent synchronous `add(GatewayAdd)`, isolated
`search(GatewaySearch)`, and idempotent `close()`.

## Add contract

`GatewayAdd` carries request ID, canonical payload SHA-256, exact user/session/logical-Cube IDs and
the stable session start position, plus ordered `GatewayMessage` values. Message positions must be
contiguous from zero and message IDs must be unique. A successful return means the write is
committed and immediately readable from the provider boundary.

Replaying an identical request is a no-op. Reusing a request identity for another payload fails
closed with `gateway.request_conflict`. The Gateway owns any provider-side ensure/create needed for
the supplied user/Cube pair; v1 deliberately has no public `create_cube` operation.

The B05 `MemosMemoryGateway` sends one synchronous `fine` Product Add to exactly one logical Cube.
It attaches payload/session/source provenance, then reads back through tenant + Cube + payload
digest filters. A non-empty Add succeeds only when all returned IDs, content, type, result indices,
count and vector synchronization match. A valid empty extraction succeeds without inventing raw
memory. A durable local receipt makes completed replays no-ops and lets a pending request reconcile
a provider write that completed before the Raw Store response was committed.

## Search contract

Search receives exact query, user, logical Cube, `top_k` and optional answer options. It returns at
most `top_k` ranked evidence items with exact content and mandatory user/Cube provenance. It does
not select an option, generate an answer, filter by session or consult gold data.

The application recomputes the expected logical Cube and drops evidence with foreign provenance.
Ranking algorithm and score calibration are implementation-specific. Consequently, the shared
contract tests isolation, ordering, visibility and bounds—not semantic retrieval quality.

## Safe errors

| Code | Retryable | Meaning |
|---|---:|---|
| `gateway.rate_limited` | yes | Provider rejected capacity |
| `gateway.unavailable` | yes | Closed, disconnected or transient provider failure |
| `gateway.timeout` | yes | Caller-defined upstream deadline expired |
| `gateway.protocol_invalid` | no | Provider wire/business response is invalid |
| `gateway.request_conflict` | no | Stable request/message identity was reused inconsistently |

Errors do not carry URLs, provider bodies, IDs, content, queries or underlying exception text.
The Fake itself adds no timeout, retry, fallback, circuit breaker or background recovery policy.
The B05 application supplies the one-shot remaining Add budget to the real adapter; it performs no
automatic HTTP retry.

## Fake behavior and limits

`FakeMemoryGateway` is asyncio-safe, process-local and non-durable. Its named
`fake-token-overlap-v1` search uses Unicode casefolded `\w+` tokens, scores query-token coverage,
then sorts by descending score and ingestion order. It accepts options without selecting one.
Optional fault injection raises typed Gateway errors by operation.

The Fake proves orchestration, idempotency, isolation and failure wiring only. It is not a MemOS
emulator, baseline candidate, persistence proof, lifecycle implementation or LoCoMo/MemOps quality
signal. A completed Raw request plus a newly-created empty Fake is intentionally not recoverable.

## Evolution

Provider IDs, receipts and implementation-specific transport DTOs remain behind the port. Any change to
immediate visibility, provenance, idempotency, synchronous success or user/Cube isolation requires
architecture review and a contract version decision.

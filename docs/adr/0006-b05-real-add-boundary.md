# ADR 0006: B05 synchronous Real Add boundary

- Status: Accepted/Frozen after B05 Gate 2
- Date: 2026-09-03
- Decision owner: user-approved B05 Gate 0 R1, Gate 1 and Docker-priority amendment

## Context

B05 must turn the B03 provider-independent contract into a real MemOS `v2.0.32` Add path while
preserving the contest's 120-second maximum. Accuracy is more important than performance after the
timeout requirement is met. The extraction model, prompt and later Search policy require real
evaluation on the tuning machine; infrastructure work must leave time for that evidence.

The pinned MemOS source has several behaviors that are unsafe for this baseline: technical reader
failure can become raw-text memory, concurrent windows can reorder, graph write failure can be
swallowed, vector failure can accompany HTTP 200, scheduler work can be submitted despite disabled
startup flags, and INFO logs can contain requests/prompts/responses. Product Add also lacks a
documented request-id idempotency contract.

## Decision

B05 uses one synchronous Add unit per public request:

1. Raw Store durably prepares the exact request and stable session position.
2. A process-local FIFO lane serializes work for the same user; different users can run concurrently.
3. The Real Gateway sends one `async_mode=sync`, `mode=fine` Product Add to the user's deterministic
   logical Cube.
4. Provider memories carry source, payload, user, session, Cube, index and count provenance.
5. Non-empty results are read back through exact tenant + Cube + payload-digest filtering and must
   match Product Add IDs/content/type with successful vector synchronization.
6. A durable Gateway receipt records provider completion before Raw Store completion. Pending
   replays reconcile by provenance and completed replays perform no provider write.
7. A valid empty extraction is success. Model, parse, schema, graph, vector, readback or deadline
   failure is explicit; no raw fallback, backup LLM, automatic retry or silent partial success is
   allowed.

The application owns a 115-second Add deadline, warns at 105 seconds and reserves five seconds from
the provider budget. A guarded build-time patchset changes only the fixed MemOS archive copy and
validates pre/post hashes. The original archive remains unchanged.

Search and public readiness remain unavailable until B06. The chosen extractor model, prompt
variants, clustering, semantic lifecycle policy and quality claims remain tuning work.

## Deployment priority

Compose remains a supported, reproducible delivery artifact and both images must build. It is a
bonus rather than the center of the solution. Full Docker lifecycle evidence is run when a capable
daemon is readily available; host-specific rootless port publication or cgroup limitations are
reported and do not block model/evaluation tuning. `docs/batches/B05/NATIVE_DEPLOYMENT.md` is the
first-class fallback for organizer or tuning hosts where Docker cannot be deployed promptly.

This priority does not weaken application correctness, timeout, isolation, replay, provenance or
failure semantics. It changes only how much time is spent proving optional container behavior.

## Consequences

- Success has a stronger meaning than upstream HTTP 200 and can cost one filtered readback.
- A crash between provider write and receipt completion is reconciled from provider provenance;
  ambiguous partial state fails closed and remains pending for inspection.
- Same-user order is guaranteed only in the shipped one-worker process. Multi-worker/multi-replica
  deployment requires distributed lane ownership and is out of scope.
- The receipt database is operational idempotency state, not a memory source of truth.
- Prompt/model selection remains externally configurable so the tuning machine can compare models
  without changing the public or provider contracts.
- Native deployment must recreate the same versions, environment, patchset and one-worker rule; it
  is not permission to bypass validation.

## Revisit conditions

Revisit before enabling multiple API workers, automatic retries, asynchronous Add, semantic
Update/Forget, a different MemOS version, a second extractor/reviewer, or a provider API that offers
an authoritative atomic idempotency key and committed-status endpoint.

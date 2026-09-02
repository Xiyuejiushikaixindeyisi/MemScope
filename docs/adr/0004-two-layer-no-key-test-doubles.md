# ADR 0004: Separate Memory Gateway Fake from Model HTTP Mock

- Status: Accepted for B03
- Date: 2026-09-02
- Decision owner: B03 Gate 1

## Context

No organizer Chat, Embedding or Rerank endpoint/key is available, while MemScope still needs to
verify Adapter-to-storage orchestration and future MemOS model-client behavior. A single broad mock
would make failures ambiguous and could accidentally be treated as a quality or compatibility
claim.

## Decision

Use two independent substitutes:

- `FakeMemoryGateway` implements the provider-independent in-process memory contract for Add,
  Search, idempotency, user/Cube isolation and typed failures;
- the Mock Model ASGI app implements a deliberately small deterministic Chat/Embedding HTTP subset
  for protocol and failure-classification tests.

`MemoryOperations` composes the accepted RawStore and MemoryGateway ports. NEW and PENDING requests
call the idempotent Gateway and complete Raw state only after success; COMPLETED replay performs no
external call. Raw conflicts become application `request.conflict` and HTTP 409. The default
composition remains unavailable and neither substitute is enabled automatically.

## Consequences

- Application wiring defects and model-wire defects can be localized independently without keys.
- A Gateway failure leaves durable pending state; same-ID retry can converge through downstream
  idempotency, but B03 has no proactive worker.
- The Fake ranking and Mock responses cannot support proxy scores, semantic claims or a baseline
  release.
- B05 can replace the Gateway and refine the Mock after targeted inspection of pinned MemOS without
  changing Adapter or RawStore boundaries.

## Rejected alternatives

- One end-to-end MemOS mock couples internal orchestration to an unverified upstream protocol.
- Installing the Fake in the default app risks false readiness and accidental submission.
- Calling live third-party models would make no-key tests nondeterministic and does not validate the
  organizer environment.
- Prebuilding retries, fallback, Rerank or lifecycle semantics would freeze unknown competition
  policy prematurely.

## Revisit conditions

Revisit when targeted B05 source mapping shows incompatible model-client fields, organizer APIs
arrive, or finals requirements change provider, lifecycle or deployment boundaries. Do not broaden
the Mock merely to claim generic compatibility.


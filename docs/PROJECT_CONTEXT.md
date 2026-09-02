# MemScope Project Context

> Current through B03 implementation on `batch/b03-no-key-doubles`; Gate 2 verification is recorded
> in the active B03 handoff.

## Objective

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. The contestant service accepts conversation history through Add and returns ranked
memory evidence through Search. The organizer owns final answer generation and judging.

## Current boundaries

- The repository's `official/` data is a local rules reconstruction and proxy regression set, not
  an organizer byte-verified package.
- No organizer Chat, Embedding, or Rerank API or key is currently available.
- No organizer hardware, timeout, concurrency, failure-policy, Compose, network, build, or finals
  delivery clarification is currently available.
- Missing organizer information does not block the no-key scaffold. It does block the affected
  baseline, deployment, or finals freeze described in the main implementation plan.
- MemOS is fixed to tag `v2.0.32`, commit
  `185ebdb925911b55c13b7efe666b74e2e292e484`.

## Delivery stages

1. B00～B09 build and freeze `memos-scaffold-v0` without organizer credentials.
2. Real API capability probes and representative/full proxy evaluation freeze `baseline-v0`.
3. Controlled single-variable experiments improve the baseline.
4. Finals requirements trigger a new scope and architecture review when published.

## Long-lived engineering constraints

- Keep component responsibilities and dependency direction explicit.
- Use small, stable interfaces at real change boundaries; do not prebuild unused abstractions.
- Keep configuration typed, centralized, validated and safely summarized.
- Treat isolation, idempotency, recovery, observability and failure semantics as first-class work.
- Maintain deterministic no-key tests and separate mock wiring evidence from semantic quality.
- Optimize accuracy, robustness, latency, resources, explainability and reproducibility together.
- Never hardcode reconstructed questions, gold answers, question IDs or proxy-Judge behavior.

## Batch Status

B00, B01 and B02 are `Accepted/Frozen`. B03 Gate 1 is approved and its implementation provides a
framework-independent `MemoryGateway`, deterministic in-process Fake, independent Mock Model API
and `MemoryOperations` composition. The Fake path proves wiring/recovery/isolation without claiming
semantic quality or real MemOS compatibility.

B02 provides a framework-independent
`RawStore` port, SQLite Schema/migrations, canonical persistent idempotency, ordered raw messages,
stable logical user/Cube identity and a durable pending/completed outbox record.

The default runtime deliberately remains 503: B03 does not install its Fake composition in
`memscope.main`. Real MemOS/model compatibility, durable proactive recovery, lifecycle semantics,
production failure policy and infrastructure remain later-batch work.

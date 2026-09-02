# MemScope Project Context

> Current through B00 implementation commit
> `ff2484b7732671c3c96f35ad3dd25b4da108618c`; see the B00 Gate 2 handoff for verification data.

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

## Current Batch

B00 provides only the engineering foundation: locked Python tooling, Settings, logging, internal
errors, a route-free ASGI shell, quality gates and project context documents. B01 owns the contest
HTTP contract. No later Batch starts without its own Gate 1 approval.

# MemScope Project Context

> Current through approved B04 Gate 1 on `batch/b04-runtime-infra`; B00–B03 remain accepted and
> frozen. B04 runtime Gate 2 evidence is not complete.

## Objective

MemScope is an independently deployable long-term memory service for the Agent Memory
competition. The contestant service accepts conversation history through Add and returns ranked
memory evidence through Search. The organizer owns final answer generation and judging.

## Current boundaries

- The repository's `official/` data is a local rules reconstruction and proxy regression set, not
  an organizer byte-verified package.
- Submission is a source `solution.zip`; the organizer builds it. It includes `INSTRUCTION.md`,
  `SDD.md`, complete `code/` with dependency declarations, and optional Dockerfile/Compose.
- No hosted database is provided. Add→Search is guaranteed only within one deployment lifecycle;
  data may remain in container-local/configurable storage. Cross-restart persistence is not a
  competition dependency, though B04 tests same-host named-volume restart for operational safety.
- The Huawei AI Gateway base URLs and Bearer authentication are known and its Chat, Embeddings,
  Responses and rerank paths are OpenAI-compatible. Exact subscribed model IDs still come from
  `/v1/models`; formal embedding access, model ID, vector dimension and limits remain pending.
- Model-dependent tools/JSON/extra fields are passed through and reasoning output has platform
  support, but the exact Qwen/GLM capability combinations still require probes.
- The organizer does not provide a separate hosted database. Embedding/rerank may be self-hosted,
  but permission, package size and license limits for bundled weights are still pending.
- Add has a 1–120 second budget and Search a 1–60 second budget. Rate limits include concurrency
  and requests-per-minute 429 cases, so later batch execution needs throttling and backoff.
- The contract fixes formal `top_k=100`; no separate K bonus formula exists. Evaluation accuracy
  and response time take priority over speculative K tuning.
- Health is unauthenticated and any 2xx indicates readiness. The final public port/entry command is
  not published; MemScope will keep the port configurable and use 8000 as its current default.
- Hardware, memory, disk, architecture and image-size restrictions are currently unspecified.
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

B00, B01, B02 and B03 are `Accepted/Frozen`. B04 Gate 1 is approved and its three-service
MemOS/Neo4j/Qdrant Compose implementation is in progress; it is not accepted until clean-room
Docker build, cold start, restart persistence and fault recovery are executed. The current host
has no Docker CLI/daemon, so static evidence cannot be promoted to runtime evidence.

B03 provides a
framework-independent `MemoryGateway`, deterministic in-process Fake, independent Mock Model API
and `MemoryOperations` composition. The Fake path proves wiring/recovery/isolation without claiming
semantic quality or real MemOS compatibility.

B02 provides a framework-independent
`RawStore` port, SQLite Schema/migrations, canonical persistent idempotency, ordered raw messages,
stable logical user/Cube identity and a durable pending/completed outbox record.

The default MemScope runtime deliberately remains 503: B04 does not alter `src/memscope` or install
its infrastructure behind the contest Adapter. Real MemOS/model compatibility, Add/Search,
durable proactive recovery and production failure policy remain later-batch work.

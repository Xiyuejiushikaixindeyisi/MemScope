# MemScope Project Context

> Current through B05 Gate 1 implementation verification on 2026-09-03. B00–B04 are
> `Accepted/Frozen`. B05 Gate 0 R1 and Gate 1 are approved; Gate 2 has not been requested. B06 has
> not started and must begin in a new Session at Gate 0.

## Objective

MemScope is an independently deployable long-term memory service for the Agent Memory competition.
The contestant service accepts conversation history through Add and returns ranked memory evidence
through Search. The organizer owns final answer generation and judging.

## Current accepted capabilities

- B01 freezes the contest HTTP contract and strict response shapes.
- B02 freezes the SQLite Raw Store, persistent idempotency, ordered raw messages and stable logical
  user/Cube identity.
- B03 freezes a provider-independent `MemoryGateway`, deterministic in-process Fake, independent
  Mock Model API and `MemoryOperations` composition for no-key tests.
- B04 freezes a single Compose entry with pinned MemOS `v2.0.32`, Neo4j and Qdrant, internal
  networking, named volumes, dependency-gated health, resource ceilings, bounded logs and lifecycle
  recovery checks.
- B05 Gate 0 R1 freezes the Real Add design. The approved Gate 1 implementation adds the real MemOS
  Add Gateway, durable receipts, same-user lanes, deadline propagation, guarded fixed-source
  patches, public runtime composition and deterministic verification fixtures.

The default `core` profile remains unavailable/503. The explicit `memos_add` profile serves Real Add
but deliberately leaves public Health/Search unavailable until B06. Semantic quality and real model
capability are not yet verified.

## B04 accepted evidence

The clean-room lifecycle verifier passed on Linux/amd64 under WSL2 rootless Docker Engine 29.7.2
and Compose 5.4.0:

- MemOS image: `sha256:d073319403213693a8fff8351d20ab55eb3049b6f7c3b9d3a4940afa74f60b41`;
- cold start: 31.547 seconds; Compose restart recovery: 39.252 seconds;
- aggregate MemOS/Neo4j/Qdrant readiness and MemOS-created Qdrant collection;
- no host ports, internal-only network and named-volume persistence;
- Qdrant stop detection/recovery, MemOS SIGKILL self-recovery and graceful exit code 0;
- configured CPU/memory/PID ceilings and bounded JSON log rotation.

User-approved B04 exceptions:

- MemOS image is about 985 MB and accepted against the project B04 limit of 1 GB.
- Two no-cache builds had identical RootFS layers but different final OCI config/history metadata;
  functional reproducibility is accepted because runtime content and behavior match.
- Trivy found no embedded secrets, but pinned OS/Python dependencies retain known HIGH/CRITICAL
  findings. This is a documented B04 security-debt waiver, not a claim of zero vulnerabilities.
- WSL rootless evidence cannot authoritatively prove host cgroup enforcement or boot/daemon
  auto-start; the final Linux deployment machine must retest those items.

See `docs/batches/B04/HANDOFF.md` for the authoritative B04 handoff.

## Organizer and environment boundaries

- Submission is a source `solution.zip`; the organizer builds it. It includes `INSTRUCTION.md`,
  `SDD.md`, complete `code/` with dependency declarations, and optional Dockerfile/Compose.
- No hosted database is provided. Add→Search is guaranteed only within one deployment lifecycle;
  data may remain in container-local/configurable storage. B04's named-volume restart is an
  operational quality check, not a competition dependency.
- Health is unauthenticated and any 2xx indicates readiness. Public port/entry command is not
  published; MemScope keeps the port configurable and currently defaults to 8000.
- Add has a 1–120 second total budget and Search a 1–60 second total budget.
- Formal `top_k=100`; no separate K bonus formula exists. Accuracy and response time take priority.
- The Huawei AI Gateway base URLs and Bearer authentication are known. Chat, Embeddings, Responses
  and rerank paths are advertised as compatible, but exact model capabilities must be probed.
- Current expected models include `GLM-V5.2-DX`, `Qwen-V3.6-27B-bf16`, `bge-m3` and
  `bge-reranker-v2-m3`; exact subscribed IDs and the actual Embedding dimension/limits remain
  runtime facts, not assumptions.
- Model-dependent tools/JSON/pass-through/reasoning fields require per-model probes.
- Batch execution must handle concurrency and requests-per-minute 429 responses with throttling and
  bounded exponential backoff.
- Permission, package size and license limits for bundled open-source model weights remain pending.
- The checked formal Markdown does not specify a `solution.zip` size limit; the reported 5 GB limit
  remains unverified and must not be treated as a hard rule.

## Two-machine workflow

The development machine owns Git, design, deterministic tests, B05/B06 Gate 0–2, initial SDD and
the B09 tuning handoff. It cannot reach Huawei AI Gateway and must not claim real API or quality
evidence.

The tuning machine owns Huawei gateway capability probes, baseline/full evaluation, controlled
tuning and the final submission ZIP. Docker revalidation and resource measurements are useful
delivery evidence but must not consume time needed for accuracy tuning; the native deployment guide
is the supported fallback when Docker is unavailable or unproductive.

Every transfer is identified by Git commit and SHA-256. The tuning machine returns the final ZIP,
source/config diff, sanitized model configuration, reports and Docker evidence for audit. Full rules
and templates are under `docs/collaboration/`.

## Delivery stages

1. B00～B09 build and freeze `memos-scaffold-v0` without organizer credentials.
2. B05 and B06 each start in a separate Session with user-approved Gate 0 algorithm design.
3. B06 produces the initial `SDD.md`; B09 freezes the reproducible tuning handoff ZIP.
4. The Huawei-network tuning machine performs capability probes, baseline evaluation and tuning.
5. Only a candidate with an identified source/configuration and returned audit evidence is treated
   as the reproducible final submission candidate.

## Long-lived engineering constraints

- Keep component responsibilities and dependency direction explicit.
- Use small, stable interfaces at real change boundaries; do not prebuild unused abstractions.
- Keep configuration typed, centralized, validated and safely summarized.
- Treat isolation, idempotency, recovery, observability and failure semantics as first-class work.
- Maintain deterministic no-key tests and separate Mock wiring evidence from semantic quality.
- Optimize accuracy, robustness, latency, resources, explainability and reproducibility together.
- Never hardcode reconstructed questions, gold answers, question IDs or proxy-Judge behavior.
- Never store keys/tokens in source, Markdown, images, transfer ZIPs, reports or logs.

## Next authorized state

B05 Gate 1 implementation and verification are authorized under `docs/batches/B05/PLAN.md`.
Complete deterministic regression evidence and the B05 handoff before requesting Gate 2. Docker
host-port/cgroup evidence is a non-blocking bonus when the target runtime supports it; model and
evaluation tuning take priority. B06 remains unopened and requires its own new-Session Gate 0.

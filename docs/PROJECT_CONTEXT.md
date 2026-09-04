# MemScope Project Context

> Current through the B09 reproducible-delivery candidate on 2026-09-04. B00–B08 are
> `Accepted/Frozen`; B08 uses a named tuning-machine live-evidence transfer exception.
> B05/B06 real-model and Docker host-port/cgroup validation is transferred to a capable tuning
> machine under explicit handoff conditions. The accepted B06 implementation commit is
> `1507317b048fc06d25f020ded751f35fae2aeb6f`.

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

The default `core` profile remains unavailable/503. The explicit `memos_add` profile now provides
the accepted B06 Real Add + Search and complete readiness baseline: single-Cube Product Search,
strict active/provenance filtering, stable exact deduplication and a 55-second Search deadline.
Semantic quality and real model capability are transferred verification items, not claims made by
the development machine.

The accepted B07 closure adds deterministic cross-layer evidence for completed-receipt Raw recovery,
lost-response provenance reconciliation, partial-provenance fail-closed behavior and one provider
attempt per external replay. It changes no production module or runtime contract and is frozen at
candidate commit `e30fa91`.

The B08 deterministic candidate adds a standard-library three-phase public verifier plus ASGI system
tests for concurrency, isolation, restart and typed failures. It changes no runtime implementation.
It is recorded at candidate commit `44ce4a7` and is Accepted/Frozen under the tuning-machine
live-evidence transfer exception. This acceptance does not claim a live-system pass; real
exercise/restart/resource evidence remains due from the tuning machine.

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

### Active 48-hour execution memory

The user declared roughly 48 hours remaining before code submission. Until submission, all agents
must read `docs/collaboration/48H_DELIVERY_GUARDRAILS.md` and use this development path:

```text
Python unit/contract tests
  -> native memory-api or source bind mount
  -> reuse running Neo4j/Qdrant/MemOS
  -> freeze code
  -> one final image build
```

Docker gets a 10-minute capability preflight and a 30-minute per-stage stop limit. Model, prompt,
URL, key and threshold experiments do not rebuild images. Docker failure cannot stop a native
baseline or tuning run. The Add tuning authority is
`docs/batches/B05/ADD_DESIGN_AND_TUNING.md`.

## Delivery stages

1. B00～B06 are accepted/frozen and provide the Real Add + Search candidate.
2. B07 proves the frozen recovery boundary with composed deterministic tests and adds no production
   reliability mechanism.
3. After separate approval, B08 owns end-to-end, concurrency, restart, resource and segmented
   performance verification without redesigning the architecture.
4. After B08 acceptance, B09 freezes documentation, locks, licenses, clean-build/two-machine
   evidence and the reproducible delivery candidate.
5. The Huawei-network tuning machine performs real capability probes, baseline/full evaluation and
   controlled tuning; only returned, checksummed evidence becomes a repository fact.
6. Only a candidate with an identified source/configuration and returned audit evidence is treated
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

B05–B08 are frozen under their respective `HANDOFF.md` files. B07 Gate 2 was explicitly accepted on
2026-09-04 at candidate commit `e30fa91`. B08 Gate 1 is approved and its deterministic public
verifier/system-test candidate is complete without production changes. The user explicitly
accepted/froze B08 Gate 2 on 2026-09-04 under the named tuning-machine live-evidence transfer
exception. The missing `exercise`, restart-persistence and resource evidence remains a transferred
obligation, not a passed claim. The user also entered B09 Gate 1; B09 implementation requires
no product behavior change. The user then explicitly approved its plan for organizer instructions,
lock/license audit, deterministic delivery packaging and two-machine identity closure; Gate 2
remains a separate explicit decision. The implementation candidate is `fe246c0`; deterministic
archive and quality evidence is recorded in `docs/batches/B09/HANDOFF.md`.

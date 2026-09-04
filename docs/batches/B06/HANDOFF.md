# B06 Gate 1 implementation handoff

> Status: Gate 2 Accepted/Frozen by explicit user approval on 2026-09-04
>
> Gate 0 R1 and Gate 1 approved by explicit user messages
>
> Base commit: `3e735b3e0aa49c8b66436123fa245c9bc974dee7`
>
> Branch: `batch/b06-real-search`
>
> Candidate commit: pending

## 1. Delivered candidate

B06 connects the frozen public Search contract to pinned MemOS v2.0.32 Product Search. The
application recomputes the logical Cube, applies one 55-second end-to-end deadline and passes the
remaining budget to the Real Gateway. The Gateway sends one conservative, single-Cube Search,
strictly validates the Product response, filters inactive/foreign/uncommitted candidates, performs
stable exact deduplication and returns at most public `top_k` evidence in upstream order.

The candidate does not generate an answer or send public options to MemOS. It does not filter by
session, retry, consult Raw as a Search fallback, default-enable MMR/BM25/full-text, or introduce an
external reranker/service/worker. The baseline keeps fixed `cosine_local` reranking.

Public readiness now requires Raw Store, provider receipt store, current MemOS health, and a Search
capability probe that succeeded during startup. The probe is bounded, uses a dedicated nonexistent
Cube and makes no write; each public Health request does not repeat the embedding-backed probe.

## 2. Search trust and visibility rules

An upstream item is public only when all of the following hold:

1. its Product bucket matches the unique expected logical Cube;
2. metadata user and `memscope_cube_id` match the request;
3. status is exactly `activated`;
4. type is Working, LongTerm or User memory;
5. the B05 payload digest, result index/count and vector-success provenance are valid;
6. ID/content are nonblank and score is missing or finite.

Timezone-aware `created_at` is preserved; missing, invalid or naive time is omitted. Exact duplicate
IDs/content and trimmed content are removed stably. One ID with conflicting content is a protocol
failure. `resolving`, archived, deleted, unknown, preference/tool/skill, foreign and incomplete-
provenance candidates cannot appear in public evidence.

## 3. Deadline and failure behavior

- Search warning: 50 seconds; application hard deadline: 55 seconds; public limit: below 60 seconds.
- HTTP connect/read/write/pool consumes the caller's remaining budget.
- Gateway checks the deadline again after synchronous response parsing/filtering; application checks
  again after evidence conversion, preventing late success without an `await` boundary.
- Cancellation propagates. Timeout, rate limit, 4xx/5xx, disconnect, oversized/non-JSON response and
  invalid business envelope remain explicit sanitized failures.
- A fixed-source patch removes `_search_text()`'s catch-all exception-to-empty behavior. Only a real
  zero-hit Search can return an empty success.

## 4. Fixed-source patch evidence

`docker/memos/apply_patchset.py` remains anchored to the exact archive preimages and
`PATCHSET_LOCK.json` postimages. B06 adds/extends guarded transforms for:

- `multi_mem_cube/single_cube.py`: Search exceptions propagate; raw user/fine hint logging removed;
- `retrieve/searcher.py`: raw query, COT, internet items, request metadata and exception detail are
  replaced by bounded counts/stages;
- `retrieve/task_goal_parser.py`: prompt/query/LLM response logging removed;
- `retrieve/retrieve_utils.py`: malformed raw LLM response text is no longer logged.

`apply_patchset.py --verify-only` passes against `.vendor-src/MemOS`, and transformed targets compile.
Archive/source commit and upstream code are unchanged.

## 5. Deterministic verification

Environment:

- CPython `3.11.16` from persistent uv-managed storage;
- uv `0.12.9`;
- `uv sync --frozen --offline` checked 30 locked packages;
- `pyproject.toml` and `uv.lock` were not changed by environment recovery.

Quality evidence:

| Check | Result |
|---|---|
| Full pytest | 542 passed in 13.62 seconds |
| Statements | 2,232 / 2,296; 97.21% |
| Branches | 579 / 610; 94.92% |
| Combined coverage | 96.73%; required minimum 95% |
| Ruff format/check | passed |
| Mypy `src tests scripts` | passed; 75 source files |
| Fixed patch pre/post lock | passed |
| Candidate verifier compile/help/scheme rejection | passed |
| Compose interpolated config | passed with the checked-in example; no daemon required |

Tests cover exact Product payload, absence of session/options, runtime Search settings, strict
envelope/bucket/item parsing, status/type/provenance/score/time filtering, stable dedup/order/top_k,
HTTP/business/transport failures, remaining budgets, late-success rejection, cancellation, Search
probe success/failure/recovery, complete public readiness, fixed-source log/error guards and explicit
disablement of deferred Search paths. Conflicting content for one ID fails closed even when the first
same-ID candidate is otherwise untrusted.

The first sandboxed full run appeared to hang because this execution sandbox blocks Python 3.11
`asyncio.to_thread()` completion wakeups. A minimal `asyncio.to_thread(lambda: 42)` reproduced the
issue only inside the sandbox and completed immediately outside it. SQLite component/full tests were
therefore run outside that restriction while still using only local temp files and MockTransport.

## 6. Deployment deliverables

- Docker/Compose wiring: `compose.yaml` and `deploy/compose.env.example` include all typed Search
  settings; memory-api healthcheck now checks exact public Health success rather than a socket.
- Unified organizer gate: `docs/batches/B06/ORGANIZER_DEPLOYMENT.md` separates Docker Compose and
  native startup, enforces candidate-specific storage, exact Embedding dimension, Qdrant collection
  and Neo4j index inspection, real Add/Search smoke, fail-closed admission and non-destructive rollback.
- Formal non-Docker path: `docs/batches/B06/NATIVE_DEPLOYMENT.md` independently covers fixed source,
  two Python environments, Neo4j/Qdrant, model configuration, one-worker startup, Health, Add replay,
  cross-session Search, cross-user isolation, deadlines, logs, faults and rollback.
- Public candidate smoke: `scripts/verify_b06_candidate.py` performs unique-user Health, Add, replay,
  second-session Add, Search, cross-user Search and latency checks without printing memory content.
- System description: root `SDD.md` explains Extract, Store, Recall, Update/Forget, short/long memory,
  anti-noise, models and limitations.

## 7. Not verified on this development machine

No MemOS, Neo4j or Qdrant service was listening on its standard local port. Gate 2 confirmed Compose
v5.4.0 can parse the interpolated manifest, but no Docker daemon is running at the local system
socket; no image was built and no container was started. Therefore this handoff does **not** claim:

- a real Huawei Chat/Embedding model ID, capability, dimension or quota;
- a real Add producing `activated` memory followed by a non-empty Search hit;
- semantic quality, LoCoMo/MemOps score, P50/P95/P99/max latency or final threshold;
- Docker host-port/cgroup/lifecycle behavior for this candidate.

The tuning machine must first run the unchanged `fast + cosine_local` baseline and
`scripts/verify_b06_candidate.py --require-hit`. If a normal Add is committed only as `resolving`,
stop and request a formal B05 boundary revision. Do not make Search expose that state.

## 8. Known limitations and risks

1. B05 does not guarantee natural-language Update/Forget requests publish reliable fact keys,
   dominance relations or tombstones. B06 filters committed states but cannot invent them.
2. Exact deduplication reduces duplicate evidence but is not semantic contradiction detection or
   diversity optimization.
3. Search response size is bounded by the Gateway response-byte limit and top_k, but no per-item
   token truncation is introduced because the public Answer input budget is not frozen.
4. Same-user Add ordering remains process-local; multiple memory-api workers/replicas are forbidden.
5. Graph/vector/receipt/Raw commits are not one distributed transaction; B05 provenance
   reconciliation remains the accepted recovery boundary.
6. Real Search latency can increase with `top_k=100`; any candidate reaching 60 seconds is rejected,
   and MMR/external rerank cannot be enabled without measured headroom and review.
7. Deferred BM25/full-text upstream paths retain raw query/query-term logs. Docker and native R1
   explicitly set `FAST_GRAPH/BM25_CALL/VEC_COT_CALL/FULLTEXT_CALL=false`; enabling one requires a
   separate sanitized fixed-source patch and canary before evaluation.

## 9. Gate 2 acceptance state

The user explicitly accepted B06 Gate 2 on 2026-09-04. Gate 0 R1, the Gate 1 implementation and the
development-machine evidence are now `Accepted/Frozen`. Real-model Add/Search semantics, latency,
quality and optional Docker P4 evidence are transferred to the tuning machine under sections 7–8;
they were not falsely claimed as development-machine evidence.

The accepted files remain an uncommitted working tree (`Candidate commit: pending`) at this point.
Acceptance freezes their semantics but does not authorize an automatic commit, push or B07 branch.
Those Git transitions require a separate explicit user instruction. No later Batch begins
automatically.

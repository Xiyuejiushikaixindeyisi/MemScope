# MemScope System Design Description

> Version: B09 reproducible-delivery candidate, 2026-09-04.
>
> This document describes the implemented baseline, not an official score or a final model choice.
> B00–B08 are Accepted/Frozen. B08 uses the tuning-machine live-evidence transfer exception;
> real-model, live-system and semantic-quality evidence remains a tuning-machine responsibility.

## 1. Purpose and evaluation role

MemScope is a standalone long-term-memory service for the Agent Memory competition. It implements
the organizer-facing `GET /health`, `POST /add`, and `POST /search` contract. The service stores
conversation evidence and returns ranked memory evidence; it does not generate the final answer,
select a supplied option, or run the organizer's Answer/Judge stages.

The formal API is [contest-http-v1](docs/interfaces/contest-http-v1.md). Search is isolated by
`user_id` mapped to one deterministic logical Cube, not by `session_id`; a user's Search can recall
that user's memories across sessions.

## 2. Architecture

```text
Evaluator
  -> memory-api / FastAPI Adapter
     -> MemoryOperations
        -> Raw Store (SQLite WAL, canonical Add input and receipt)
        -> MemoryGateway
           -> Gateway receipt SQLite
           -> pinned MemOS v2.0.32 Product API
              -> Neo4j Community graph
              -> Qdrant vectors
              -> OpenAI-compatible Chat and Embedding endpoints
```

The public DTOs, application commands, provider-independent Gateway DTOs and MemOS wire DTOs are
separate trust boundaries. Runtime composition is lifespan-owned and closes dependencies in reverse
order. `APP_PROFILE=memos_add` is retained for compatibility but, after B06, represents the complete
Real Add + Search candidate.

## 3. What is remembered: Extract

Add accepts ordered `user`/`assistant` messages with an optional millisecond timestamp. The Raw
Store durably records the exact request before provider delivery. The Real Gateway sends the ordered
messages to one synchronous MemOS Product Add in `fine` mode. Fixed MemOS `SimpleMemReader` uses the
configured Chat model to extract structured textual memories.

The guarded compatibility patch preserves outer-window order and source provenance, rejects
technical parse/schema/model failures, and permits a genuinely valid empty extraction. It never
turns failed extraction into a successful raw-text memory. The extraction model, endpoint and prompt
variant are deployment/tuning inputs; the repository does not claim one Huawei model as final.

## 4. How memory is stored: Store

The Raw Store assigns stable identities from canonical request content and maintains stable session
positions across chunks. Replaying the same request and payload is idempotent; reusing a request ID
for different content fails with a conflict.

Each extracted provider memory carries:

- exact `user_id`, `session_id`, and deterministic logical Cube;
- canonical payload SHA-256;
- result index and total result count;
- memory type/status and vector synchronization state.

Non-empty Add succeeds only after tenant/Cube/payload-filtered graph readback proves the complete
result set, exact ID/content/type correspondence and `vector_sync=success`. The Gateway then commits
a content-free local receipt and the Raw Store commits the public Add response. An interrupted
pending Add reconciles this provenance before considering another provider write; there is no
automatic retry loop.

Neo4j stores graph/text metadata and Qdrant stores vectors. Both use persistent local service data.
The two SQLite ledgers use WAL and `synchronous=FULL` and must remain separate local files.

## 5. How memory is recalled: Recall

The application recomputes the user's logical Cube and gives the Gateway the remaining portion of
one 55-second monotonic Search deadline. The Gateway issues exactly one
`POST /product/search` with:

- the original query and user;
- exactly one `readable_cube_ids` value;
- no session filter and no public answer options;
- baseline `fast`, `relativity=0.0`, exact-text dedup and local cosine rerank;
- preference/tool/skill, internet and neighbor recall disabled.

The pinned stack's normal candidate generation can combine graph and vector recall. BM25/full-text,
MMR/sim expansion, external rerankers and LLM-heavy Search modes are not baseline defaults. Runtime
mode, relativity, dedup and local rerank switches are typed so the tuning machine can perform
single-variable experiments without rebuilding.

MemOS results are untrusted candidates. A public evidence item must come from the expected Cube and
repeat the exact user/Cube in metadata, be `activated`, use `WorkingMemory`, `LongTermMemory` or
`UserMemory`, and carry valid B05 payload/result/vector provenance. Missing or non-finite scores are
omitted/rejected as appropriate; time is returned only when timezone-aware.

Results retain provider order. Exact duplicate IDs/content and exact duplicate trimmed content are
removed stably; one ID with conflicting content fails the whole request. The Gateway, application
and Adapter each enforce the requested `top_k` upper bound. The implementation does not overfetch
low-quality evidence to fill 100 slots and does not claim that similarity alone proves semantic
non-conflict.

## 6. Short- and long-term boundary

MemOS may classify textual output as Working, LongTerm or User memory; all three are eligible for
Search after the same isolation, committed-provenance and status checks. Session identity remains
stored as source provenance but is intentionally not a Search ACL, enabling LoCoMo-style cross-
session recall.

Raw input is the durable audit/source layer, not a Search fallback. Preference, tool, skill, outer
and raw-file categories are excluded from the B06 public baseline even if the pinned provider can
represent them.

## 7. Update and Forget

The intended semantics are logical state transition rather than unconditional physical deletion:
new valid versions become `activated`; superseded or forgotten memories should become non-visible
through an archived/deleted/tombstone state while protected Raw/provenance remains auditable.

The implemented Search enforces the visibility half of that rule: only `activated` is returned;
`resolving`, `archived`, `deleted` and unknown states are excluded. It never calls an LLM at query
time to infer a forgotten fact and never writes state during Search.

Important limitation: the B05 Add baseline has scheduler/reorganizer disabled and does not yet
guarantee that natural-language update/forget requests publish reliable fact keys, dominance links
or tombstones. B06 therefore cannot promise end-to-end Update/Forget correctness when the provider
never committed the required state transition. If a normal Add completes with only `resolving`
memories, the correct action is to stop and formally revise the B05 boundary—not expose the
intermediate state.

## 8. Anti-noise and conflicting evidence

The baseline resists noise through exact user/Cube ACLs, committed source provenance, active-status
filtering, approved memory types, finite-score checks, provider relevance ordering, stable exact
deduplication and bounded `top_k`. Fewer than `top_k` results is valid.

These controls remove foreign, stale-status, malformed and duplicate evidence. They cannot infer
which of two semantically conflicting `activated` statements is current without a committed fact
key/version/tombstone. MMR may later improve diversity but is not conflict resolution. Any tuning
candidate with cross-user leakage, deterministic forgotten-value leakage, technical-error-to-empty
success or Search at/above 60 seconds is rejected.

## 9. Models and reranking

The service uses an OpenAI-compatible Chat model for extraction and an OpenAI-compatible Embedding
model for graph/vector indexing and Search. The baseline reranker is MemOS `cosine_local`, which
uses embeddings already available in the fixed stack and adds no external reranker service.

Real model IDs, context/tool behavior, Embedding dimension, quotas, relevance distribution and
accuracy are machine-specific tuning facts. Dimension must be probed before creating/reusing the
Qdrant collection. Model/URL/Key/threshold changes are environment changes and do not require an
image rebuild.

## 10. Availability, deadlines and failure policy

Add is serialized per user in one process, uses a 115-second hard deadline and has no automatic
retry. Search does not enter the Add lane, uses a 50-second warning and 55-second hard deadline, and
passes one decreasing budget through HTTP, parsing, filtering and output conversion. Late results,
timeouts and cancellation never become empty success.

Provider 429, 408/504, other 4xx/5xx, disconnects, oversized/non-JSON responses and invalid Product
business envelopes map to sanitized typed errors. A fixed-source patch removes MemOS's catch-all
Search exception-to-empty behavior. R1 baseline logs contain only allowlisted metadata such as stage,
duration, counts, bounded configuration and error code; query/options/content, prompts, complete
provider responses and credentials are forbidden.

Public Health is 2xx only when Raw and Gateway receipt stores are ready, MemOS is currently healthy,
and this process completed a bounded no-write Product Search capability probe during startup. Health
does not rerun the embedding probe on each request. Release still requires one real Add + Search
smoke.

## 11. Deployment and verification

The primary time-bounded iteration path is Python tests → native memory-api/source-mounted MemOS →
reuse Neo4j/Qdrant/MemOS → code freeze → one final image build. Docker is optional and cannot block
core scoring work. The common Docker/native organizer admission gate is
[B06 ORGANIZER_DEPLOYMENT](docs/batches/B06/ORGANIZER_DEPLOYMENT.md); complete native commands are in
[B06 NATIVE_DEPLOYMENT](docs/batches/B06/NATIVE_DEPLOYMENT.md).

The fixed source/archive/patch map is
[MEMOS_V2_0_32_MAP](docs/integrations/MEMOS_V2_0_32_MAP.md); the internal contracts are
[memory-gateway-v1](docs/interfaces/memory-gateway-v1.md) and
[raw-store-v1](docs/interfaces/raw-store-v1.md). Deterministic tests verify public schemas,
idempotency, isolation, error propagation, deadlines, status/provenance filtering, readiness and
fixed patch hashes. Real model quality, P95/max latency and official scores must be returned from the
Huawei tuning machine before the final candidate can claim them.

B07 adds composed recovery/reconciliation evidence without changing production behavior. B08 adds
a three-phase public HTTP verifier for exercise, restart persistence and sanitized resource
observations. Its deterministic candidate is accepted, but those live phases have not been executed
on this development machine and are not claimed as passed.

## 12. Known limitations

1. Same-user Add FIFO is process-local; multiple memory-api workers/replicas are forbidden.
2. Raw/receipt SQLite commits and graph/vector writes are not one distributed atomic transaction;
   provenance-based pending reconciliation narrows but cannot eliminate every ambiguous partial
   failure.
3. End-to-end natural-language Update/Forget publication is not guaranteed by the current disabled-
   organizer Add baseline.
4. Search exact dedup does not solve semantic contradiction or optimize evidence diversity.
5. No real Huawei model capability, accuracy, latency distribution or official evaluation result is
   asserted by this development-machine document.
6. Docker host-port/cgroup proof remains a tuning-machine/P4 task; the native path is fully supported.
7. Deferred BM25/full-text paths are explicitly disabled in R1 and require an additional log-
   sanitization patch/canary before they may be enabled.

## 13. Reproducible delivery

B09 adds a deterministic standard-library artifact builder with separate `handoff` and `submission`
allowlists. Both modes reject links and unsafe paths, exclude Git/cache/runtime/secret material,
normalize ZIP metadata, embed file-level SHA-256 records and emit an external full-archive hash.

The handoff artifact carries tests, public evaluation assets, verification runbooks and two-machine
templates for the tuning machine. The formal submission artifact contains `INSTRUCTION.md`, this
SDD, third-party notices/licenses and the complete runtime/build source under `solution/code/`; it
does not carry the public evaluation dataset or internal Batch history.

Package reproducibility does not certify a real model, official score or live-system behavior. The
tuning machine must validate the received handoff hash, complete the B08 phases, run the real
baseline/tuning sequence, freeze its final non-secret configuration, and return the final ZIP plus
source/config differences and evidence.

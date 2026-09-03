# B05 Real Add implementation plan

> Status: Accepted/Frozen after explicit Gate 2 approval on 2026-09-03; Docker host-port/cgroup
> validation transferred to a capable tuning-machine daemon.
>
> Batch: B05
>
> Gate 0: R1 confirmed by the user on 2026-09-03
>
> Base Git identity: `main` at `0c2a35d62add20472658e316f0ca332159c598f9`, equal to
> `origin/main`, plus the current uncommitted B05 Gate 0/design documentation.
>
> Implementation branch: `batch/b05-real-add`
>
> Boundary: Real synchronous Add only. B06 Search, semantic tuning and final service readiness are
> not authorized by this plan.

> Implementation priority amendment approved by the user on 2026-09-03: Docker is a bonus delivery
> path and must not consume time needed for model/evaluation tuning. The Docker baseline must remain
> buildable and auditable, while `NATIVE_DEPLOYMENT.md` is the first-class fallback. Host-specific
> port publication and cgroup proof are non-blocking when the available rootless daemon cannot
> provide them.

## 1. Goal

Deliver the smallest production-shaped B05 baseline that connects the frozen Contest Adapter and
Raw Store to the pinned MemOS v2.0.32 Product API and performs one synchronous, ordered,
provenance-bearing `simple_struct + fine` Add.

A successful public Add must mean that:

1. its canonical raw request is durable;
2. MemOS returned a structurally valid result;
3. every non-empty extracted memory is present in the intended logical Cube and reports successful
   vector synchronization;
4. the provider delivery receipt is durable;
5. the Raw Store response is `COMPLETED` and can be replayed exactly.

B05 does not claim semantic model quality or a submission-ready service. `/health` remains 503 and
`/search` remains explicitly unavailable until B06 completes the Real Search path.

## 2. Authority and invariants

This plan implements [Gate 0 R1](GATE0.md) and uses
[ADD_DESIGN_AND_TUNING.md](ADD_DESIGN_AND_TUNING.md) as the tuning-machine input. Existing B00–B04
public behavior remains frozen unless an additive internal evolution is listed in this plan.

The non-negotiable invariants are:

- no public request or response schema changes;
- exact `request_id`, `user_id` and `session_id` echo on successful Add;
- strong `user_id -> logical Cube` isolation;
- original role, content, nullable timestamp and request order remain durable in Raw Store;
- one Add request/chunk is one independent synchronous unit;
- no final-chunk inference, first-Search consolidation or background semantic mutation;
- `async_mode="sync"`, `mode="fine"`, one primary extractor LLM and one Embedding model;
- a valid empty extraction is success; model/parse/schema/persistence failure is not;
- no raw-text success fallback, backup LLM, extra reviewer, automatic retry or destructive organizer;
- a single end-to-end Add deadline is strictly below 120 seconds;
- no credentials, full prompts, full model responses or conversation bodies in logs;
- the pinned MemOS archive and its recorded SHA-256 remain unchanged.

## 3. In scope

1. A production `memos_add` application profile and lifespan-owned resource composition.
2. An async HTTP `MemosMemoryGateway` for MemOS `/health`, `/product/add` and tenant-scoped,
   digest-filtered `/product/get_memory` readback.
3. A small persistent Gateway receipt store used only for downstream Add idempotency.
4. Same-user ordered Add lanes in the shipped single-worker process; different users remain
   concurrent.
5. Add-wide deadline propagation from Adapter/application to MemOS and its nested LLM call.
6. Stable cross-chunk session positions exposed from Raw Store to the Gateway payload.
7. Strict provider request/response DTO validation and sanitized error translation.
8. Guarded build-time compatibility patches for the exact pinned MemOS source.
9. A non-root `memory-api` container, public Adapter port and model-egress network.
10. A deterministic no-key model profile and B05 clean-room runtime verifier.
11. Additive documentation, configuration examples, tests and handoff evidence.

## 4. Explicitly out of scope

- B06 Search result conversion, ranking, reranking, evidence packing or public readiness;
- final GLM/Qwen winner or actual Huawei model IDs;
- prompt P1/P2, extra LLM, backup model or automatic model routing;
- cross-session/full-session carry-over;
- semantic clustering, fuzzy deduplication, LLM fusion or raw-message reordering;
- query-time Markdown dossiers or GraphMemix-style complementary recall;
- a full committed-generation/current-version store;
- irreversible semantic delete/merge and asynchronous organizer authority;
- automatic retries, circuit breakers, outbox workers, leases or dead-letter handling;
- multi-process same-user coordination;
- final SDD, final submission ZIP or claims about 1000-question accuracy.

These remain tuning/B06/B07/B09 work and cannot be introduced while implementing this plan without
returning to review.

## 5. Fixed-source findings that shape the implementation

| Finding | Consequence in B05 |
|---|---|
| `/product/add` defaults to async and ignores `mode` in async | Always send `async_mode="sync"`, `mode="fine"` |
| `writable_cube_ids` is the current field; `mem_cube_id` is deprecated | Send exactly one stable logical Cube in `writable_cube_ids` |
| Product Add accepts the Cube view directly and does not require REST `/create_cube` | Do not call the user/cube registration endpoints; prove the stable ID with integration tests |
| failed LLM generation/JSON parse is converted to raw `UserMemory` | Guarded patch makes technical failures propagate and keeps valid empty distinct |
| outer windows are collected with `as_completed` | Tag futures with their original index and reassemble in that order |
| one mutable `info` dict is passed to concurrent readers and `custom_tags` is popped | Copy per-task metadata and forward kwargs explicitly |
| chat is split first by 10 messages/2 overlap and again by 1024 tokens/200 overlap | Preserve stable source IDs and deduplicate only byte-identical facts sharing source identity |
| batch graph-write failures are logged and swallowed | Guarded patch must propagate the batch failure |
| vector-write failure can still lead to an HTTP 200 with `vector_sync="failed"` | Gateway readback rejects anything other than successful vector synchronization |
| `/product/get_memory_by_ids` applies the startup-default graph `user_name` and returns empty for dynamic logical Cube views | Keep tenant filtering strict; use `/product/get_memory` constrained by user, Cube and payload digest, then match all returned Add IDs and markers |
| scheduler start flags do not prevent sync `ADD_TASK_LABEL` immediate dispatch | When the scheduler is disabled, the Add path must skip scheduler submission entirely |
| MemOS logs full Add requests, LLM prompts and model responses at INFO | Guarded patch replaces them with bounded counts/model/status/timing only |
| the sync OpenAI client has no Add-wide deadline | Pass a bounded per-call timeout derived from the request deadline and check the deadline before write |
| Product Add has no documented `request_id` idempotency contract | Add provider provenance markers, readback reconciliation and a local durable Gateway receipt |

All conclusions above refer to the fixed archive commit
`185ebdb925911b55c13b7efe666b74e2e292e484`; they are not assumptions about another MemOS version.

## 6. Target architecture

```text
Contest client
    |
    v
memory-api /add
    |
    v
MemoryOperations
    |-- per-user ordered lane
    |-- RawStore.prepare_add -> NEW/PENDING/COMPLETED
    |-- one monotonic deadline
    |
    v
MemosMemoryGateway
    |-- GatewayReceiptStore
    |-- POST /product/get_memory   (reconcile/readback only)
    |-- POST /product/add          (sync + fine)
    |-- POST /product/get_memory   (post-write returned-ID/result-set verification)
    |
    v
MemOS -> extractor LLM / Embedding -> Neo4j Community + Qdrant
```

The `memory-api` container is the only public service. MemOS, Neo4j, Qdrant and the optional B05
mock-model service remain unexposed on the host.

## 7. Public request execution

### 7.1 NEW or PENDING

```text
enter public Add and start deadline
  -> acquire exact user lane within remaining budget
  -> RawStore.prepare_add
  -> obtain payload SHA, logical Cube and persisted session_start_position
  -> build GatewayAdd from the exact command + persisted positions
  -> MemosMemoryGateway.add(timeout_seconds=remaining)
       -> receipt completed? validate hash and return without provider call
       -> receipt pending/new? reconcile provider marker
       -> if no complete provider result, POST sync/fine Add
       -> validate response, returned IDs and provider readback
       -> atomically mark Gateway receipt completed
  -> RawStore.complete_add
  -> return exact public HTTP 200 body
```

### 7.2 COMPLETED

The application validates the stored response and returns it without acquiring a provider lane or
calling MemOS. A different payload for the same request ID remains HTTP 409.

### 7.3 Failure

Any provider, parse, readback, vector, deadline or local persistence failure prevents a new success
response. Raw remains `PENDING` unless its already-running SQLite transaction completed safely.
No layer retries automatically. A later evaluator retry with the same request ID follows the same
idempotent path.

## 8. Internal interface evolution

### 8.1 Raw Store preparation result

`PreparedAdd` gains required `session_start_position: int`. It is the minimum persisted
`session_position` for the request and is returned identically for NEW and exact PENDING/COMPLETED
replays. The existing SQLite schema already stores these positions, so B05 does not add a Raw Store
migration for this field.

`SqliteRawStore` verifies that:

- the request has exactly the expected number of messages;
- request positions are contiguous;
- session positions equal `session_start_position + request_position`;
- replay returns the same start position.

### 8.2 Gateway Add value and protocol

`GatewayAdd` gains required `session_start_position: int`. `GatewayMessage` retains its existing
stable message ID and request position. Per-message session order is derived without duplication as
`session_start_position + request_position`.

The Add method becomes:

```python
async def add(self, request: GatewayAdd, *, timeout_seconds: float) -> None: ...
```

`timeout_seconds` must be finite and positive. It is a remaining budget, not a provider default and
is never serialized verbatim to logs. Fake and Real implementations must honor cancellation. This
is an additive B05 review of the internal v1 interface; it does not change the contest API.

Real Gateway `search()` raises the existing sanitized `GatewayUnavailableError` in B05.
`is_ready()` returns `False` because both Add and Search are not yet available together. This keeps
public Health honest even though Add itself is testable.

### 8.3 Application deadline and lanes

`MemoryOperations` receives validated `add_deadline_seconds`, `add_warn_seconds` and an injectable
monotonic clock. It uses one total `asyncio.timeout` around lane acquisition, Raw prepare, Gateway
Add and Raw complete. Expiry is translated to a new sanitized `add.timeout` error with
`retryable=true`; `CancelledError` is never caught or translated.

A small ref-counted keyed-lane utility serializes the whole Add critical section for one exact
logical Cube/user. Entries are removed after the final waiter exits. The shipped container runs one
Uvicorn worker; configuration/instructions reject claims of cross-process ordering.

## 9. MemOS request mapping

The Real Gateway sends only the current request/chunk:

```json
{
  "user_id": "<exact external user_id>",
  "session_id": "<exact external session_id>",
  "writable_cube_ids": ["<stable logical cube_id>"],
  "async_mode": "sync",
  "mode": "fine",
  "messages": [
    {
      "role": "user|assistant|system",
      "content": "<exact content>",
      "chat_time": "<UTC ISO-8601 milliseconds when timestamp exists>",
      "message_id": "<stable Raw/Gateway message ID>"
    }
  ],
  "info": {
    "memscope_add_schema": "v1",
    "memscope_payload_sha256": "<canonical payload digest>",
    "memscope_session_start_position": 0,
    "memscope_source_count": 1,
    "memscope_deadline_unix_ms": 0
  }
}
```

The example values are shapes, not production data. Missing timestamps are omitted. A timestamp
representable by Python `datetime` is rendered as deterministic UTC ISO-8601 milliseconds; an
out-of-range signed integer is rendered as `unix_ms:<exact integer>`. The exact integer always
remains in Raw Store. The guarded reader patch preserves `message_id` in every source record.

The Gateway does not send `chat_history`, MemOS `task_id`, `mem_cube_id`, `operation`, `custom_tags`,
feedback flags, options, questions or gold. Omitting `task_id` avoids exposing the external request
identifier to the scheduler path, which is disabled in this baseline.

## 10. Strict provider response contract

For every internal MemOS call, the Gateway requires:

- HTTP status and JSON content type compatible with the expected endpoint;
- a response body no larger than the configured byte limit;
- a JSON object with integer `code == 200`, nonblank string `message` and correctly typed `data`;
- Product Add `data` is a list of objects containing UUID `memory_id`, nonblank `memory`, supported
  `memory_type` and the exact requested Cube, or an empty list;
- no duplicate returned memory IDs;
- readback for every returned ID has the expected user/Cube, payload digest, result index/count,
  activated/resolving state allowed by baseline, and `vector_sync == "success"`;
- marker reconciliation finds exactly indices `0..result_count-1`, all with the same digest/count.

Unknown extra provider fields are ignored, but missing/wrong required fields fail closed. Provider
bodies and extracted memory text are never copied into exception messages or normal logs.

## 11. Downstream idempotency and receipt state

### 11.1 Receipt store

`GatewayReceiptStore` is a private SQLite component owned by the Real Gateway. It uses its own file
and forward-only checksum ledger; it never opens the Raw Store database directly.

One row per request contains only:

- request ID;
- payload SHA-256;
- `pending|completed`;
- expected result count and canonical JSON list of provider memory IDs after completion;
- created/updated timestamps.

It stores no message content, model response text, URL or credential.

### 11.2 Replay rules

| State | Action |
|---|---|
| absent | insert pending, then reconcile/provider Add |
| same ID + different hash | `gateway.request_conflict`; no provider call |
| completed + same hash | validate stored receipt and return; no provider call |
| pending + no provider marker | call Product Add once |
| pending + complete coherent marker set | persist completed receipt and return; no duplicate Add |
| pending + partial/incoherent marker set | fail closed as provider protocol/invariant error; do not delete or retry |

For a valid empty extraction, the completed zero-count receipt is written before Gateway success is
returned. If the process dies after an empty provider result but before that receipt, re-extraction
is allowed because the first attempt created no visible memory. For non-empty results, provider
markers enable reconciliation after a lost response or process restart.

This closes the normal “provider succeeded, Raw complete failed” replay gap. A detected partial
provider write remains an explicit B05 recovery limitation rather than being silently duplicated or
destructively repaired; B07 may later add a bounded repair policy.

## 12. Guarded MemOS compatibility patchset

The original archive, source lock and `.vendor-src/MemOS` remain untouched. The MemOS Docker build
extracts the archive and invokes one deterministic patch applicator. The applicator verifies the
expected preimage SHA-256 and exact anchor count for every changed file, applies transformations,
then verifies recorded postimage hashes. Any drift fails the image build.

The patchset includes the two accepted B04 compatibility changes and these B05-only changes:

1. `simple_struct.py`
   - raise on LLM call, empty response, JSON or memory-item schema failure;
   - accept a legal `{ "memory list": [] }`;
   - copy per-window metadata, forward required kwargs and preserve source `message_id`;
   - reassemble outer results by original index;
   - exact-only overlap dedup with stable provenance;
   - expose configurable 1024-token chat windows without changing the default;
   - check the request deadline before every model call and before returning extracted results.
2. `single_cube.py`
   - attach payload digest, stable result index/count and source/session positions before persistence;
   - check deadline immediately before database write;
   - skip all scheduler submission when the scheduler is disabled;
   - redact content, prompts and user/Cube/session/request/memory identifiers from Add-path ordinary
     and timing logs; retain only bounded counts, stages, durations and status classes.
3. `tree_text_memory/organize/manager.py`
   - propagate any batch graph write failure instead of logging and returning successful IDs.
4. `llms/openai.py` and `configs/llm.py`
   - accept a bounded per-call timeout derived from the Add deadline;
   - remove prompt/request/response bodies and underlying exception strings from logs;
   - keep backup client disabled in baseline.
5. `api/handlers/add_handler.py`
   - remove full Add request logging and emit counts/mode only.
6. `api/config.py`
   - wire validated chat-window, prompt-example and LLM timeout environment values;
   - retain one primary extractor and local cosine reranker defaults used by B05.

No prompt wording, memory scoring, semantic relation rule, database schema or Search ranking is
changed by this patchset. If any requirement cannot be achieved with the listed files, stop and
return to Gate 1 review rather than widening the patch silently.

## 13. Baseline state interpretation

B05 stores non-destructive memory events with exact source IDs, request/session order, timestamp,
payload marker and provider status. Scheduler and graph reorganization are disabled; B05 never
archives, merges or deletes an earlier semantic fact.

For this Batch, “critical state publication” means the ordered new/correction/forget evidence is
durably and immediately visible together with the metadata B06 needs to suppress stale state.
B05 does not claim that unchanged upstream P0 extraction can always classify an ambiguous update or
forget. B06 owns query-time active/history filtering; prompt/state classifiers remain controlled
tuning candidates.

This is the minimal non-destructive mapping of Gate 0 R1. Gate 1 approval explicitly approves this
boundary; requiring Add-time semantic tombstones for all Update/Forget cases would expand B05 into
a new state algorithm and requires a separate Gate 0 revision.

## 14. Timeout, retry and cancellation

Initial baseline values:

| Budget | Value | Rule |
|---|---:|---|
| formal Add limit | 120 s | external hard limit |
| application Add deadline | 115 s | covers lane + Raw + Gateway + Raw complete |
| warning threshold | 105 s | observation only; does not cancel |
| MemOS/provider deadline reserve | 5 s | nested deadline must expire before application deadline |
| MemOS connect timeout | 3 s | bounded by remaining total budget |
| Embedding call timeout | 5 s | existing call-level bound; still checked against total deadline |
| automatic retries | 0 | all layers |

All numbers except the formal limit are typed configuration. Validation requires
`0 < warning < application < 120` and `0 < reserve < application`. The tuning machine may adjust
them below 120 based on P99/max evidence without changing public semantics.

An application timeout returns the existing sanitized error envelope with code `add.timeout` and
HTTP 500. Provider 429, transport/5xx, caller timeout, invalid provider response and request conflict
map respectively to the existing Gateway error families. No `Retry-After`, provider body, URL,
identifier or exception string is reflected externally.

Client disconnect/cancellation propagates. A SQLite worker already running in `to_thread` may finish
its private transaction, as documented by Raw Store; the next identical request converges through
Raw and Gateway receipts.

## 15. Configuration contract

### 15.1 Memory API settings

| Setting | Baseline | Validation / secrecy |
|---|---|---|
| `APP_PROFILE` | `core`; Compose sets `memos_add` | enum; `core` remains unavailable |
| `MEMOS_BASE_URL` | required for `memos_add` | HTTP(S), no query/userinfo/fragment; safe summary stores scheme only |
| `DATABASE_PATH` | `/var/lib/memscope/raw.db` in Compose | file path |
| `MEMOS_GATEWAY_RECEIPT_PATH` | `/var/lib/memscope/gateway-receipts.db` | file path, must differ from Raw DB |
| `ADD_DEADLINE_SECONDS` | `115` | finite, positive, `<120` |
| `ADD_WARN_SECONDS` | `105` | finite, positive, `< deadline` |
| `MEMOS_DEADLINE_RESERVE_SECONDS` | `5` | finite, positive, `< deadline` |
| `MEMOS_CONNECT_TIMEOUT_SECONDS` | `3` | finite, positive, bounded by deadline |
| `MEMOS_RESPONSE_MAX_BYTES` | `1048576` | bounded positive integer |

`safe_summary()` reports only booleans, numeric limits, profile and URL scheme/receipt-path kind.
It never reports complete URLs, paths, IDs or secrets.

### 15.2 MemOS/model settings

Production Compose has no functional model defaults. It requires the tuning/deployment environment
to supply exact values for:

- `MEMRADER_MODEL`, `MEMRADER_API_BASE`, `MEMRADER_API_KEY`;
- `MOS_EMBEDDER_MODEL`, `MOS_EMBEDDER_API_BASE`, `MOS_EMBEDDER_API_KEY`;
- `EMBEDDING_DIMENSION`.

Baseline freezes:

- `MEM_READER_BACKEND=simple_struct`;
- `MEMRADER_ENABLE_BACKUP=false`;
- `MEM_READER_CHAT_WINDOW_MAX_TOKENS=1024`;
- `MEM_READER_REMOVE_PROMPT_EXAMPLE=false`;
- `SIMPLE_STRUCT_ADD_FILTER=false`;
- `MEM_READER_SAVE_RAWFILENODE=false` for chat-only contest Add;
- `MOS_EMBEDDER_BACKUP_CLIENT=false`;
- `MOS_RERANKER_BACKEND=cosine_local`;
- `ENABLE_ACTIVATION_MEMORY=false`, `ENABLE_PREFERENCE_MEMORY=false`;
- `MOS_ENABLE_SCHEDULER=false`, `API_SCHEDULER_ON=false`;
- `MOS_ENABLE_REORGANIZE=false`, `ENABLE_INTERNET=false`, `ENABLE_CHAT_API=false`.

The simple-struct chat counter remains the packaged local `cl100k_base` tiktoken counter. The B04
`word` value remains only the unused document chunker startup fallback and is not used for chat
window accounting. Prompt P0 is identified by MemOS commit plus the post-patch SHA-256 of
`mem_reader_prompts.py`; B05 does not add an arbitrary prompt-file loader.

A startup validator supports explicit `gateway|mock` model profiles. `gateway` requires HTTPS and
non-placeholder credentials. `mock` is allowed only by the verifier/Compose test override and may
use internal HTTP plus `EMPTY`; no automatic fallback from gateway to mock exists.

## 16. Runtime and Compose changes

1. Add one non-root `memory-api` image with exact runtime requirements exported from `uv.lock` and
   source mounted/copied read-only except `/var/lib/memscope`.
2. Publish only `${MEMSCOPE_PUBLIC_PORT:-8080}:8080` from `memory-api`.
3. Attach application and databases to the private backend network.
4. Attach only MemOS to a separate non-internal model-egress network so it can reach the configured
   Huawei gateway; `ENABLE_INTERNET=false` still disables MemOS web retrieval.
5. Keep MemOS, Neo4j, Qdrant and mock-model without host ports.
6. Add a named `memscope_data` volume for Raw and Gateway receipt SQLite files.
7. Preserve B04 database volumes, resource ceilings, restart policies and bounded JSON logs.
8. Replace B04 bootstrap model/dimension defaults with required B05 variables. The no-key verifier
   supplies an isolated override using a deterministic `mock-model` service and dimension 16.
9. Use one Uvicorn worker. The memory-api container healthcheck is process/socket liveness only;
   it does not turn the deliberately 503 public `/health` into a readiness claim.
10. Continue to disallow runtime model/tokenizer downloads. Build-time wheels still require an
    audited reachable mirror/cache as documented by B04.

## 17. Error mapping

| Condition | Internal result | Public behavior |
|---|---|---|
| same request, different payload | request/Gateway conflict | 409, non-retryable |
| end-to-end deadline | `add.timeout` | 500, retryable |
| MemOS/model 429 | `gateway.rate_limited` | 500, retryable |
| connection, 5xx or closed client | `gateway.unavailable` | 500, retryable |
| MemOS 408/504 or Gateway call budget exhausted | `gateway.timeout` | 500, retryable |
| MemOS 400/401/403/404/422 | `gateway.protocol_invalid` | 500, non-retryable |
| invalid JSON/schema/body size/readback/vector marker | `gateway.protocol_invalid` | 500, non-retryable |
| partial/incoherent provider marker set | `gateway.protocol_invalid` | 500, non-retryable; Raw stays pending |
| Raw Store failure | existing storage error | existing sanitized 500 |
| cancellation | propagated | no fabricated success/fallback |

No 202 response, task polling, partial-success response or empty-success fallback is introduced.

## 18. Observability and privacy

Memory-api emits bounded structured records for:

- total Add outcome/duration and 105-second warning;
- lane wait, Raw prepare, receipt prepare/reconcile, Product Add, readback, receipt complete and Raw
  complete durations;
- message/window/result counts, valid-empty count and exact-overlap duplicate count;
- model/Embedding call counts and token usage only when supplied as numeric metadata;
- response category, timeout, cancellation, 429/5xx and vector/readback status;
- a stable non-secret configuration fingerprint.

Identifiers, payload digests, Cube IDs, provider URLs, message text, prompt text, extracted memories,
model responses and exception strings are excluded. MemOS patch logs use the same rule. Gate 2 scans
aggregate logs with unique canary content and test credentials and must find neither.

## 19. Exact implementation file boundary

### Existing files allowed to change

- `pyproject.toml`, `uv.lock`, `.env.example`, `.dockerignore`, `README.md`;
- `compose.yaml`, `deploy/compose.env.example`;
- `docker/memos/Dockerfile`, `docker/memos/entrypoint.sh`;
- `src/memscope/settings.py`, `src/memscope/app.py`, `src/memscope/main.py`;
- `src/memscope/operations.py`;
- `src/memscope/application/memory_operations.py`;
- `src/memscope/raw_store/models.py`, `src/memscope/raw_store/sqlite.py`;
- `src/memscope/memory_gateway/{__init__.py,protocol.py,models.py,errors.py,fake.py}`;
- `src/memscope/mock_model_api/{app.py,main.py}` only for additive deterministic B05 fixtures;
- corresponding existing tests affected by the internal signature/config additions;
- `docs/interfaces/raw-store-v1.md`, `docs/interfaces/memory-gateway-v1.md`;
- `docs/integrations/MEMOS_V2_0_32_MAP.md`;
- `docs/{README.md,PROJECT_CONTEXT.md,CODEMAP.md}` and this B05 directory.

### New files allowed

- `src/memscope/application/user_lanes.py`;
- `src/memscope/memory_gateway/memos.py`;
- `src/memscope/memory_gateway/memos_models.py`;
- `src/memscope/memory_gateway/receipt_store.py`;
- `src/memscope/runtime.py`;
- `src/memscope/mock_model_api/memos_main.py`;
- `docker/memory-api/{Dockerfile,requirements.txt,entrypoint.sh}`;
- `docker/memos/apply_patchset.py`, `docker/memos/PATCHSET_LOCK.json`;
- `scripts/verify_b05_runtime.py`;
- `tests/unit/test_b05_memos_patchset.py`;
- focused unit/component/contract/integration tests under the existing test directories;
- `docs/adr/0006-b05-real-add-boundary.md`;
- `docs/batches/B05/{CONTEXT.md,HANDOFF.md,NATIVE_DEPLOYMENT.md}` during
  implementation/handoff.

### Forbidden without renewed review

- `.vendor-src/MemOS/**` and the pinned archive contents/checksum;
- contest HTTP request/response shapes or endpoint paths;
- B00–B04 migrations/ADRs/HANDOFF decisions beyond the additive interface notes listed above;
- public Search algorithm or a 2xx readiness claim;
- new database/model/reranker services;
- prompt semantics, gold-derived rules or evaluation-data-specific code;
- any file outside this manifest except purely mechanical generated test/cache output.

If implementation requires another production file, stop and amend Gate 1 before editing it.

## 20. Dependency decision

Move existing locked `httpx==0.28.1` from dev-only to runtime dependencies for the async MemOS
client. No other Python package is added. Update `uv.lock` only as required by the dependency-group
metadata and verify offline lock consistency.

The MemOS version, its Python requirements and all database image digests remain pinned. No
dependency upgrade is used to address the already accepted B04 vulnerability debt.

## 21. Test matrix

### 21.1 Settings and composition

- `core` remains unavailable with no I/O or credentials;
- `memos_add` requires all local settings and rejects equal Raw/receipt paths;
- numeric deadline relationships and URL forms fail fast;
- safe summaries and validation errors contain no raw values;
- lifespan opens/closes Raw, receipt and HTTP resources once and in reverse order;
- startup failure never installs partially ready operations;
- `/health` and `/search` remain 503 while `/add` can execute.

### 21.2 Raw/Gateway values and ordered lanes

- NEW/PENDING/COMPLETED expose the same session start position;
- request and session positions remain contiguous across concurrent chunks;
- same user completes in persisted order even when the first provider call is delayed;
- different users can overlap;
- cancelled waiters do not leak locks or reorder later work;
- invalid/non-finite timeouts are rejected.

### 21.3 Receipt store and Real Gateway

- first Add, exact completed replay and conflicting replay;
- provider success followed by Raw complete failure, then exact retry with zero duplicate provider
  calls/writes;
- restart reloads completed receipt;
- pending receipt reconciles a complete provider marker set;
- partial, duplicate, foreign or incoherent markers fail closed;
- valid zero-memory response completes and replays without provider I/O;
- request mapping preserves order, message IDs, timestamps and exact single Cube;
- no `chat_history`, legacy Cube field, options or gold-adjacent data is sent;
- HTTP 429/4xx/5xx, invalid content type/JSON/schema, duplicate IDs, oversized body, slow response,
  connect failure and cancellation map exactly;
- post-write filtered readback requires the exact returned IDs plus matching
  tenant/Cube/digest/content/type/index/count and vector success;
- close is idempotent and post-close calls fail safely.

### 21.4 Guarded MemOS patch behavior

- the exact archive preimages and postimages match `PATCHSET_LOCK.json`;
- applying twice or to drifted text fails;
- patched files compile in the MemOS image;
- valid empty memory list succeeds with zero memories;
- empty/non-JSON/wrong-schema LLM output produces a non-200 Product Add and no raw fallback node;
- slow outer windows still return/write in source order;
- concurrent windows receive independent metadata;
- `message_id`, time and positions survive both window layers;
- byte-identical/source-overlapping duplicates collapse, while similar or different-time facts do not;
- graph or vector write failure cannot result in Gateway success;
- disabled scheduler receives no Add task;
- request deadline expiry before write creates no memory;
- full prompt/request/response canaries do not appear in logs.

### 21.5 Public application and fault recovery

- exact 200 body after complete Add and exact replay;
- conflict remains 409;
- provider/model failure leaves Raw pending;
- cancellation/timeout never produces a success response;
- completed Raw replay does not call Gateway;
- two users with identical text write only to their own Cube;
- restart preserves Raw, receipts and provider memories;
- Qdrant unavailable or `vector_sync=failed` prevents success;
- stopping the scheduler has no effect on already successful Add state.

### 21.6 Clean-room Compose gate

The B05 verifier uses only a randomly named `memscope_b05_gate_*` project and disposable volumes. It
must prove:

- Compose config, clean build and non-root processes;
- only memory-api publishes one configured port;
- mock model is internal and enabled only by the verifier override;
- cold start and dependency recovery;
- public Health/Search are intentionally 503 in B05;
- non-empty synchronous Add, direct internal readback and exact replay without duplicate memories;
- valid-empty Add;
- invalid extractor output and model timeout fail with Raw pending and no raw-memory fallback;
- two-user isolation;
- memory-api/MemOS restart persistence;
- deadline remains below 120 seconds in mock tests;
- resource ceilings, bounded logs and secret/content canary scan;
- cleanup is restricted to the generated project and never invokes a global prune.

## 22. Quality commands and Gate 2 evidence

Static gate:

```bash
uv lock --check --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Runtime gate:

```bash
python scripts/verify_b05_runtime.py --report /tmp/b05-runtime-report.json
```

Gate 2 must report:

- exact branch/commit and dirty state;
- full test counts, statement/branch coverage and static-tool results;
- archive, patchset, prompt and built image SHA-256 identities;
- Compose/Docker/OS/architecture versions;
- build, cold-start, Add P50/P95/P99/max for deterministic mock workloads;
- every contract/fault/restart/isolation assertion;
- image sizes, published ports, resource ceilings and log scan;
- untested Huawei/model facts and all remaining limitations.

Mock latency and extraction output are engineering evidence only and must not be described as real
semantic performance.

## 23. Risks and stop conditions

| Risk | Mitigation / stop rule |
|---|---|
| Huawei IDs, fields or dimensions differ | keep required runtime config; probe on tuning machine; never guess |
| MemOS patch anchor/source hash differs | fail build and return to review; never fuzzy-patch |
| Product Add cannot use stable logical Cube directly | stop; do not silently introduce REST registration or change logical IDs |
| provider response cannot support strict readback | stop and amend the idempotency/visibility design |
| partial provider write detected | fail closed and preserve evidence; no destructive repair in B05 |
| model call continues beyond public timeout | nested deadline must prevent pre-write continuation; failing test blocks Gate 2 |
| same-user lane harms timeout under real concurrency | tuning machine measures; any Add at 120 seconds rejects the candidate |
| B05 state evidence is insufficient for B06 Update/Forget | return to B06/Gate 0 or a B05 amendment; do not hide it in prompt tuning |
| build mirror repeats B04 hash/download instability | use audited mirror/wheel cache or stop; never relax hashes |
| sensitive upstream log remains | canary scan blocks Gate 2 |
| full Search/readiness becomes necessary to test Add | use bounded internal readback only; do not implement B06 implicitly |

## 24. Rollback

- Work begins only after approval on `batch/b05-real-add`.
- The pinned archive is never changed; removing the B05 patch applicator restores the exact B04
  MemOS source behavior.
- `APP_PROFILE=core` remains the no-I/O unavailable fallback.
- `memos_add` feature/tuning switches default to the frozen baseline and can be disabled without a
  data migration.
- Gateway receipts contain no unique source of memory truth; Raw Store and provider provenance
  remain sufficient for audit.
- A failed Gate 2 candidate is not merged and cannot alter B00–B04 accepted commits.

## 25. Definition of Done

B05 may request Gate 2 only when all of the following are true:

1. every file change is within section 19;
2. static quality commands pass with at least 95% branch-aware `src/memscope` coverage;
3. fixed MemOS archive/source hashes and guarded post-patch hashes pass;
4. Real Gateway maps only the approved Product API calls and passes strict payload/response tests;
5. valid empty succeeds and every technical extraction failure fails explicitly;
6. outer/inner windows are deterministic, provenance-bearing and free of proven exact duplicates;
7. same-user ordering, different-user isolation and durable receipt replay pass;
8. Add success requires graph and vector readback and no scheduler-dependent mutation;
9. total deadline, cancellation and zero-auto-retry behavior pass fault injection;
10. no public Search success or Health 2xx is introduced;
11. Compose configuration and both images build; the deterministic Add/replay/isolation/fault gate
    is provided for a capable Docker host, while host-specific port/cgroup evidence is optional and
    any limitation is reported honestly;
12. no secrets or content canaries appear in source, image, logs or report;
13. docs, ADR, config example, source map, Context and Handoff match the code;
14. Huawei/model/semantic results are explicitly marked unverified;
15. the implementation commit and complete Gate 2 evidence are presented to the user.

## 26. Approval boundary

The user explicitly approved B05 Gate 1. That approval authorizes this plan and the recorded Docker
priority amendment only; any other material deviation returns to Gate 1 review. It does not
authorize B06 or semantic tuning changes on the development machine.

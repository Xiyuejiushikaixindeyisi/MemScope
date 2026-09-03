# MemOS v2.0.32 B04/B05 source map

## Fixed source

| Item | Value |
|---|---|
| Upstream | `https://github.com/MemTensor/MemOS.git` |
| Tag | `v2.0.32` |
| Commit | `185ebdb925911b55c13b7efe666b74e2e292e484` |
| Bundled archive | `third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz` |
| Archive SHA-256 | `9a804fd874932f0a4fd86f75fa4edb48fdd41807417f236bacda49b8664cdf3c` |
| License | Apache-2.0; copied at `third_party/memos/LICENSE` |

`SOURCE_LOCK.json` is the machine-readable authority. The archive contains the complete Git tree
at the fixed commit, without `.git` metadata. `.vendor-src/MemOS` is only a local inspection
checkout and is never a build input.

## B04 runtime entry and initialization

| Concern | Fixed upstream symbol | B04 use |
|---|---|---|
| ASGI application | `src/memos/api/server_api.py:app` | Uvicorn module entry, one worker |
| Shallow HTTP health | `server_api.py:health_check` | Container liveness only |
| Component startup | `src/memos/api/routers/server_router.py` → `handlers.init_server()` | Runs at module import |
| Component graph | `src/memos/api/handlers/component_init.py:init_server` | Creates graph, LLM, embedder, reader, reranker and scheduler objects |
| Environment mapping | `src/memos/api/config.py:APIConfig` | B04 sets topology/model bootstrap values explicitly |
| Neo4j Community config | `APIConfig.get_neo4j_community_config` | `bolt://neo4j:7687`, database `neo4j` |
| Nested Qdrant config | `get_neo4j_community_config()["vec_config"]` | `qdrant:6333`, collection `neo4j_vec_db` |
| Embedding config | `APIConfig.get_embedder_config` | `universal_api`, loopback no-call bootstrap |
| Reranker config | `APIConfig.get_reranker_config` | `cosine_local`, no rerank service |
| Default cube | `APIConfig.get_default_cube_config` | Enabled for concrete tree-memory config |
| Static download mount | `server_api.py` reads `FILE_LOCAL_PATH` during import | Entrypoint creates writable directory before Uvicorn |
| Local state root | `src/memos/settings.py:MEMOS_DIR` | `MEMOS_BASE_PATH=/var/lib/memos` named volume |
| Python dependency lock | `docker/requirements.txt` | Upstream exact requirements plus B04 exact transitive constraints |
| Tokenizer bootstrap | three `tokenizer_or_token_counter: gpt2` defaults in `api/config.py` | Text-guarded build patch to configurable `MEM_READER_TOKENIZER`; B04 uses offline `word` |
| Disabled scheduler shutdown | `_io_loop_thread` access in `rabbitmq_service.py` | Text-guarded `getattr` patch when scheduler never created the thread |

## B04 configuration boundary

B04 deliberately does not prove an Add/Search call. Constructing OpenAI-shaped clients does not
call their endpoints during expected initialization; all configured model URLs point to
`127.0.0.1:9` so an accidental call fails locally and visibly. `ENABLE_INTERNET=false` and the
internal Compose network prevent implicit runtime downloads.

`EMBEDDING_DIMENSION=16` is a bootstrap schema value only. It matches the B03 deterministic Mock
dimension for a cheap infrastructure check but does not select the B05 embedding model. B05 must
replace model ID, endpoint, credential and dimension as one reviewed configuration change.

## B05 Real Add mapping

| Concern | Fixed upstream symbol/path | B05 use |
|---|---|---|
| Synchronous Product Add | `POST /product/add` | `async_mode=sync`, `mode=fine`, exactly one `writable_cube_ids` value |
| Tenant-scoped readback | `POST /product/get_memory` | filters exact user, Cube and `memscope_payload_sha256`; avoids startup-default tenant behavior in `get_memory_by_ids` |
| Technical extraction failure | `SimpleMemReader` parse/fallback path | guarded patch propagates model/parse/schema failure; valid empty remains valid |
| Outer-window order | `MemReader` concurrent task collection | guarded index/reassembly preserves source order |
| Per-task metadata | reader `info` forwarding | guarded copy prevents shared mutation and retains provenance |
| Graph write failure | batch graph add path | guarded patch propagates instead of logging and swallowing |
| Vector status | returned/read memory `vector_sync` | public Add rejects any non-success value |
| Scheduler dispatch | sync Add task submission | disabled scheduler means no immediate background task |
| Nested LLM timeout | OpenAI-compatible reader client | bounded remaining request deadline is forwarded |
| Sensitive logs | Product Add and reader log calls | counts/model/status/timing only; no request, prompt or model response bodies |

The build extracts the unchanged archive and executes `docker/memos/apply_patchset.py`. The
applicator validates exact preimage and postimage SHA-256 values from `PATCHSET_LOCK.json`; source
drift, partial application and a second application all fail closed.

Model ID, endpoint, credential, embedding dimension and prompt variants are deployment/tuning
inputs. The deterministic Mock profile is verification-only and is rejected by the production
profile boundary.

## Health interpretation

MemOS `/health` only reports that the ASGI process responds. The B04 verifier therefore also:

1. calls Qdrant `/readyz` from the MemOS container;
2. runs authenticated `RETURN 1` through `cypher-shell`;
3. verifies the MemOS-created `neo4j_vec_db` collection and configured dimension;
4. checks no host port is published and the backend network is internal;
5. writes markers in all three persistent stores, restarts Compose and reads them back;
6. stops Qdrant, expects aggregate readiness to fail, restarts it and expects recovery;
7. checks CPU/memory/PID ceilings and bounded log rotation;
8. kills the MemOS process and verifies automatic recovery;
9. verifies graceful MemOS shutdown exits with code 0 and returns healthy after start.

This aggregate result is Gate 2 evidence; it is not exposed as the contest `/health` endpoint in
B04.

## Accepted evidence and remaining risks

The complete Gate 2 lifecycle passed on Linux/amd64 with rootless Docker Engine 29.7.2 and Compose
5.4.0. Exact timings and resolved image identities are frozen in `docs/batches/B04/HANDOFF.md`.

- Build success still depends on pinned base images and Python wheels being available from a
  reachable registry/package source or mirror. Runtime is offline.
- The selected images are multi-platform indexes, but only Linux/amd64 was executed locally; other
  target architectures require their own lifecycle run.
- WSL rootless Docker cannot authoritatively prove cgroup enforcement or host boot/daemon recovery;
  the final Linux deployment machine must retest them.
- The B04 `word` tokenizer and dimension 16 are bootstrap-only and must not leak into B05/B06 model
  or ranking decisions.

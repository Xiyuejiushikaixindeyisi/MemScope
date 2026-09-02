# MemOS v2.0.32 B04 source map

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
| Python dependency lock | `docker/requirements.txt` | Installed exactly as shipped upstream |

## B04 configuration boundary

B04 deliberately does not prove an Add/Search call. Constructing OpenAI-shaped clients does not
call their endpoints during expected initialization; all configured model URLs point to
`127.0.0.1:9` so an accidental call fails locally and visibly. `ENABLE_INTERNET=false` and the
internal Compose network prevent implicit runtime downloads.

`EMBEDDING_DIMENSION=16` is a bootstrap schema value only. It matches the B03 deterministic Mock
dimension for a cheap infrastructure check but does not select the B05 embedding model. B05 must
replace model ID, endpoint, credential and dimension as one reviewed configuration change.

## Health interpretation

MemOS `/health` only reports that the ASGI process responds. The B04 verifier therefore also:

1. calls Qdrant `/readyz` from the MemOS container;
2. runs authenticated `RETURN 1` through `cypher-shell`;
3. verifies the MemOS-created `neo4j_vec_db` collection and configured dimension;
4. checks no host port is published and the backend network is internal;
5. writes markers in all three persistent stores, restarts Compose and reads them back;
6. stops Qdrant, expects aggregate readiness to fail, restarts it and expects recovery.

This aggregate result is Gate 2 evidence; it is not exposed as the contest `/health` endpoint in
B04.

## Known implementation risks for Gate 2

- The current execution host has no Docker CLI or daemon, so image build/runtime behavior is not
  yet observed here.
- The upstream dependency list is large and includes build-time native dependencies. It is pinned,
  but build success still depends on artifact availability unless wheels/packages are mirrored.
- Qdrant's in-container health command and MemOS/Qdrant client compatibility must be confirmed by
  the real Compose run; static review cannot substitute for it.
- The selected exact images are multi-platform indexes, but Gate 2 must record the actual target
  architecture and resolved platform manifests.

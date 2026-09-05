# MemScope project context

> Current through B10 Gate 1 implementation on 2026-09-05. Gate 2, tuning, final artifacts, merge,
> tag and release remain pending.

## 1. Version facts

- Historical B00–B09 baseline: `main@4ed49dd06dbb38b3faa46de3c77e446ffcc07b96`.
- Current B10 implementation start: `ca470eb475d3d3af15fef6bed5ebc5547d8c4bab`, including three
  post-B09 deployment commits that were not a separately accepted Batch.
- Active candidate branch: `batch/b10-baseline-closure`.
- B00–B09 historical approvals are not rewritten by B10.
- B08 was accepted under an explicit live-evidence transfer exception. Real exercise,
  restart-persistence and resource observations were not claimed as passed.
- No final ZIP, image bundle, tag or release exists at Gate 1.

## 2. Implemented product baseline

MemScope exposes `GET /health`, `POST /add` and `POST /search` from one `memory-api` worker. Real Add
and Search use fixed MemOS `v2.0.32`, Neo4j `5.26.6-community` and Qdrant `1.15.3`. Raw/Add identity
and provider receipts are persisted in separate SQLite WAL files; graph/vector state is in Neo4j and
Qdrant. One user maps to one deterministic Cube, allowing cross-session recall while enforcing
cross-user isolation.

Add is synchronous, serialized per user, hard-deadlined at 115 seconds and not automatically retried.
Search has a 55-second hard deadline, strict active/type/provenance filters and exact dedup. The
baseline uses `fast + cosine_local`; BM25, full-text, VEC-CoT and external reranking are disabled.
Public output is memory evidence, not an answer or Judge decision.

Known semantic limitations remain explicit: Update/Forget is natural-language only and is not fully
guaranteed with scheduler/reorganizer disabled; graph/vector/SQLite writes are not one distributed
transaction; exact dedup does not solve semantic contradiction; an empty valid extraction has a
narrow crash/re-call ambiguity. B10 does not silently redesign these behaviors.

## 3. Current two-machine workflow

The development machine owns Git, Python dependency installation, source deployment, tests,
reachable OpenAI-compatible API probes, baseline evaluation, tuning, final image construction and
final delivery generation. The organizer review machine only verifies artifacts, loads images,
injects private runtime configuration, starts four services with Compose and runs Smoke/official
evaluation. It does not build/pull images or install Python/uv/pip.

The organizer facts supplied by the user are:

- Chat: `http://aigateway.huawei.com/v1`, model `GLM-V5_1-DX`;
- Embedding: the same base, model `bge-m3`, dimension 1024;
- HTTP is allowed inside the Huawei organizer network;
- a rerank endpoint/model exists, but exact wire compatibility has not been independently verified.

The baseline therefore keeps `cosine_local` reranking. The current MemOS Chat/Embedding clients use
OpenAI-compatible Bearer API-key auth. A different IAM header syntax requires an explicit protocol
decision; example alternatives are never hardcoded as credentials.

## 4. Deployment facts

`compose.yaml` is development-only and may build the two project images using exactly one explicit
HTTPS Python package index. `.dockerignore` excludes private root/deploy env files and artifact
formats from the build context.

`compose.release.yaml` is organizer-only. It defines four containers and five named volumes, has no
`build:` key and sets `pull_policy: never`. Only memory-api publishes a host port, default 8080.
MemOS stays internal on port 8000. Default memory ceilings total 8.5 GiB, so 10 GiB host RAM is
recommended.

The final image TAR is one offline transport bundle containing four images, not a single runtime
container. `run_release.sh` validates SHA-256, private env permissions, image IDs and custom OCI
revision labels before using `--no-build --pull never`. `verify_release.sh` checks four health
states, Neo4j, Qdrant and real Add/Search from Python already inside the memory-api image.

## 5. Delivery identity and security

After tuning and separate user approval, `build_candidate_delivery.py` creates outside the repository:

```text
solution-<12-char-commit>.zip
memscope-images-<12-char-commit>-linux-amd64.tar
delivery-manifest.json
SHA256SUMS
```

Final generation requires clean Git HEAD equal to the literal candidate commit. The manifest binds
artifact hashes, Linux/amd64, four image IDs and custom revision labels. The ZIP uses an explicit
allowlist, normalized metadata, path/link checks and member hashes. The fixed MemOS archive is
expanded and secret-scanned; upstream fixture matches are accepted only through a hash- and
path/classification-bound review.

No public license has been selected for original MemScope source. `LICENSE_STATUS.md` records this
without inventing a grant. MemOS remains Apache-2.0 and its license/provenance are included.

Raw conversation data remains plaintext inside candidate volumes; the organizer must treat volumes
as sensitive and retain/delete them under its evaluation policy. Logs and reports must not contain
credentials, request bodies, memory contents, vectors, gold answers or complete provider responses.

## 6. Gate state and next authority

B10 Gate 1 was approved and implementation is in progress. Gate 2 must review the diff, deterministic
tests, Compose semantics, source preview reproducibility and residual risks before freezing the
development/tuning start. Gate 2 does not authorize final artifact generation.

After Gate 2, the development machine obtains its reachable API configuration, deploys, runs a real
baseline, performs controlled tuning and freezes a candidate. A separate user approval is required
before the final ZIP/image set is built. Returned organizer evidence must identify the same commit,
hashes and image IDs. Only another explicit user approval permits merge to `main`, tag or release.

See `docs/batches/B10/PLAN.md`, `docs/collaboration/TWO_MACHINE_WORKFLOW.md`,
`ORGANIZER_QUICKSTART.md` and `ORGANIZER_AGENT_PROMPT.md` for the active procedure.

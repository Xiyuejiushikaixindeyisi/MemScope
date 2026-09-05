# B10 Gate 1 handoff and Gate 2 model API integration

> Status: Gate 1 implemented; Gate 2 model API patch implemented; formal baseline not started
>
> Gate 1 approved by explicit user message on 2026-09-05
>
> Historical baseline: `4ed49dd06dbb38b3faa46de3c77e446ffcc07b96`
>
> Implementation start: `ca470eb475d3d3af15fef6bed5ebc5547d8c4bab`
>
> Branch: `batch/b10-baseline-closure`
>
> Final ZIP/image generation: held until development-machine tuning and separate user approval

## 1. Implemented outcome

B10 now has separate development and organizer runtime paths. The development machine owns dependency
installation, deployment, reachable-API evaluation, tuning and final image/artifact construction. The
organizer review machine only verifies the delivered set, loads prebuilt images, injects a private runtime
configuration, starts four services with Compose, runs the supplied smoke and hands the endpoint to the
official evaluator.

Both machines require a rootful Docker daemon. Scripts are launched by the ordinary operator and elevate
Docker commands only when necessary. On the organizer machine the delivery set, extraction, private env,
script work, evaluation data/output and report all stay under that operator's `$HOME`; `/root`, `/secure`
and other system-level work directories are unsupported.

The organizer path is public-Internet-independent: it performs no registry, package-index, source-host or
dependency download. Its sole runtime network dependency is the configured organizer-intranet Chat/Embedding
API, and its official evaluator is assumed to be locally supplied. A completely disconnected host can load
and start the containers but cannot complete real Add/Search without an available compatible model endpoint.

The release topology is four containers: `memory-api`, MemOS, Neo4j and Qdrant. The single offline image
TAR is only a transport bundle. `compose.release.yaml` has no `build:` key, applies `pull_policy: never` to
all four services and publishes only `memory-api`.

## 2. Delivery and operator surface

- `scripts/build_candidate_delivery.py` builds the post-tuning four-file set only from a clean, exact Git
  HEAD: source ZIP, Linux/amd64 four-image TAR, JSON manifest and `SHA256SUMS`.
- The builder rejects unsafe links/paths, in-tree output, overwrite, credential-bearing package-index URLs,
  secret patterns and changes to the hash-bound MemOS fixture review. It records four image IDs, upstream
  digests and the two custom OCI source-revision labels.
- `scripts/run_release.sh` requires Linux x86_64, Docker/Compose v2 and a mode-0600 private env; it verifies
  delivery hashes, runs `docker load`, checks image IDs/platform/revisions and starts with
  `--no-build --pull never --wait`. It rejects rootless Docker and organizer host paths outside `$HOME`.
- `scripts/verify_release.sh` uses Python already inside the delivered container, not host Python, for a
  sanitized real Health/Add/replay/Search/cross-user smoke.
- `scripts/stop_release.sh` stops containers without deleting named volumes.
- `ORGANIZER_QUICKSTART.md` and `ORGANIZER_AGENT_PROMPT.md` give the human and blank-context agent paths
  for loading, private configuration, one-command startup, smoke, official evaluation and safe failure.

The organizer template records the confirmed non-secret profile: Chat `GLM-V5_1-DX`, Embedding `bge-m3`
dimension 1024, trusted Huawei-intranet base `http://aigateway.huawei.com/v1`, and explicit insecure-HTTP
opt-in. External `/v1/reranker` remains disabled; the baseline uses local cosine reranking.

## 3. Local deterministic evidence

| Check | Result |
|---|---|
| Full pytest with branch-aware coverage | 603 passed in 14.85 s; 96.73%, threshold 95% |
| Restricted-sandbox unit/contract subset | 455 passed in 3.37 s |
| B08 local-socket verifier outside the restricted socket sandbox | 4 passed in 1.08 s |
| B10 delivery/release/deploy/rootful-path tests | 28 passed in 1.39 s |
| Ruff format/check | passed |
| Mypy, production/tests/B10 builder/public proxy evaluator | passed |
| Bash syntax for release scripts | passed |
| Release Compose with non-secret test values | parsed; exactly four services |
| Fixed MemOS archive SHA-256 and patch preimages | passed |
| Actual source allowlist and expanded MemOS secret scan | 85 selected entries; passed |

The full test run needed the local-only sandbox exception because existing tests bind `127.0.0.1` and use
SQLite worker threads. The same B08 file produced two `socket()` permission errors inside the restricted
sandbox and passed 4/4 when only that restriction was removed; this is classified as an environment
restriction, not a product failure.

## 4. Evidence not claimed

An exploratory rootless daemon was able to build the two project images and complete an internal-container
Add/Search smoke, but it could not publish the host port or enforce the configured cgroup limits. The user
has now made rootful Docker mandatory on both machines, so that exploratory run is diagnostic only and is
not accepted as deployment or baseline evidence. Therefore B10 does not yet claim:

- an authoritative rootful build, save, load or host-published start for the exact current commit;
- container Health, host-port, resource or restart-persistence evidence for that exact set;
- any call to the inaccessible organizer Huawei API;
- a semantic baseline, tuning gain, official score or organizer-runtime pass.

No final ZIP, image TAR, manifest, checksum, release, tag, push or merge was produced.

## 5. Residual decisions and risks

- Original MemScope source has no selected public license. `LICENSE_STATUS.md` makes this explicit; the
  owner must choose terms before redistribution beyond the authorized competition workflow.
- Python packages are exactly locked, and the final image IDs bind the runtime, but B10 does not yet provide
  artifact hashes for every package fetched during image construction. The final development build must use
  one approved credential-free HTTPS index and retain its image/build evidence.
- The current client supports OpenAI-compatible Bearer API-key auth. A different Huawei IAM-token header
  syntax needs an exact organizer-provided contract before it can be enabled.
- Natural-language Update/Forget publication, cross-store atomicity, semantic contradiction handling and
  the empty-extraction crash window remain disclosed product risks; Gate 1 did not silently change them.
- Runtime/evaluation data remains plaintext in local volumes and private output directories; retention and
  deletion are operator-owned policies.

## 6. Gate 2 entry

Gate 2 should independently review the diff from `ca470eb`, rerun static/full tests, inspect the exact
four-service/no-build/no-pull topology, and create two deterministic source-ZIP previews in `/tmp` from the
clean committed candidate. The previews must verify and match byte-for-byte, while remaining explicitly
non-final.

Gate 2 may accept the pre-tuning boundary only. It must not mark external live evidence complete, start
tuning, create final artifacts, merge to `main` or publish anything without the subsequent explicit user
decisions defined in `PLAN.md`.

## 7. Gate 2 model API integration

On 2026-09-05 the user approved the minimal development integration profile: Zhipu general API
`glm-5.1` with thinking disabled, ordinary SiliconFlow `BAAI/bge-m3` without the `dimensions` request
field while retaining a strict 1024-dimension storage contract, and local cosine reranking by default.

The locked MemOS build patch now provides explicit GLM request controls, separates the embedding request
shape from its response/storage dimension, and makes the existing HTTP BGE reranker authenticated,
bounded, sanitized and fail-closed. Both Compose files expose the optional wiring but retain
`cosine_local` defaults. `deploy/development-api.env.example` captures the approved development profile;
the organizer template keeps provider-specific fields empty and retains the Huawei gateway profile.

`scripts/preflight_model_apis.py` performs model-visibility checks by default. Its inference mode is
explicit and bounded; its independent reranker option does not require changing the baseline Compose
backend. See `docs/batches/B10/MODEL_API_GATE2.md` for the secure operating procedure.

Gate 2 model-API patch evidence: 599 tests passed with 96.73% coverage; Ruff format/check and strict
Mypy passed; the locked MemOS patch verified and compiled; both Compose files passed quiet interpolation;
the real development credentials passed sanitized `/models` checks for Zhipu and SiliconFlow; and the
83-entry delivery source allowlist passed its expanded secret scan. No additional inference request was
made after the approved protocol probes. The development host still exposes no usable Docker daemon, so
this step does not claim a rebuilt image or container-level service smoke.

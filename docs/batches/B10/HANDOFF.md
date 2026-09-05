# B10 Gate 1 implementation handoff

> Status: Gate 1 implemented; Gate 2 review pending explicit user instruction
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
  `--no-build --pull never --wait`.
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
| Full pytest with branch-aware coverage | 583 passed in 15.36 s; 96.73%, threshold 95% |
| Restricted-sandbox unit/contract subset | 455 passed in 3.37 s |
| B08 local-socket verifier outside the restricted socket sandbox | 4 passed in 1.08 s |
| B10 delivery/release-script tests after platform hardening | 12 passed in 0.39 s |
| Ruff format/check | passed |
| Mypy, production/tests/B10 builder/public proxy evaluator | passed |
| Bash syntax for release scripts | passed |
| Release Compose with non-secret test values | parsed; exactly four services |
| Fixed MemOS archive SHA-256 and patch preimages | passed |
| Actual source allowlist and expanded MemOS secret scan | 81 selected entries; passed |

The full test run needed the local-only sandbox exception because existing tests bind `127.0.0.1` and use
SQLite worker threads. The same B08 file produced two `socket()` permission errors inside the restricted
sandbox and passed 4/4 when only that restriction was removed; this is classified as an environment
restriction, not a product failure.

## 4. Evidence not claimed

The available development environment has no running Docker daemon. Both the default socket and the
rootless `/run/user/1000/docker.sock` path were checked; the latter does not exist outside the sandbox.
Therefore Gate 1 does not claim:

- a real build, save, load or start of the B10 four-image set;
- container Health, host-port, resource or restart-persistence evidence for that exact set;
- a call to either the development API or the inaccessible organizer Huawei API;
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

# B10 Gate 1 approved implementation plan

> Approved by the user on 2026-09-05, including the revised organizer wording.

## 1. Outcome

B10 creates a trustworthy pre-tuning candidate on `batch/b10-baseline-closure`. It preserves B00–B09
history, reconciles the post-B09 deployment commits, and replaces the old “tuning machine builds the
source ZIP” assumption with this current boundary:

```text
development machine
  deploys/tests/evaluates/tunes -> freezes source/config -> builds ZIP + four-image bundle
organizer review machine
  verifies hashes -> docker load -> injects runtime config -> Compose starts four services -> evaluates
```

“Four-image offline bundle” describes transport. It does not change the runtime into one container.
Offline organizer operation means no public Internet, registry, package-index or source-host access;
the configured organizer intranet model API is the sole runtime network dependency, and the official
evaluator is assumed to be locally available.

## 2. Authorized implementation

1. Establish this independent candidate branch from current `main`; do not rewrite historical Batch
   commits or merge back to `main` without separate user approval.
2. Add `compose.release.yaml` with exactly four services, no `build:` key and `pull_policy: never`.
3. Add a secret-free organizer env template using the user-confirmed Huawei model/API facts. Keep
   the external reranker disabled pending a separately tested adapter.
4. Add host-Python-free organizer scripts to load/identity-check images, start with
   `--no-build --pull never`, verify infrastructure plus a real Add/Search smoke, and stop without
   deleting volumes.
5. Add `ORGANIZER_QUICKSTART.md` and a blank-context `ORGANIZER_AGENT_PROMPT.md` that cover loading,
   private configuration, one-command Compose startup, official evaluation handoff and safe failure.
6. Add a candidate builder that creates, only after tuning and explicit approval:
   `solution-<candidate>.zip`, `memscope-images-<candidate>-linux-amd64.tar`,
   `delivery-manifest.json` and `SHA256SUMS`.
7. Bind the two custom images to the literal Git commit through OCI revision labels; bind all four
   runtime references to inspected image IDs in both the JSON manifest and `RELEASE_LOCK.tsv`.
8. Harden source selection and secret checks: exclude private Compose env/artifacts from Docker
   context, use an explicit allowlist, reject links/path traversal, and expand-scan the locked MemOS
   archive against a hash- and path-bound fixture review.
9. Remove silent multi-index/trusted-host Python package fallback. Development builds use one
   explicit credential-free HTTPS index; exact pins remain in existing lock/requirements files.
10. Update active project, collaboration, design and transfer documents. Historical B00–B09 files
    remain historical and are not rewritten.

## 3. Explicit non-goals and holds

- No public API/schema or memory algorithm change.
- No single-container redesign and no new runtime service.
- No enabling the external reranker without a verified request/response contract.
- No claim that organizer HTTP endpoints are independently reachable from the development machine.
- No real credential in any tracked file, image build argument, command example or report.
- No final artifact, tag, release, push or merge to `main` during Gate 1/Gate 2.
- No claim of official score, organizer-runtime pass or closed B08 live evidence without returned
  evidence tied to the exact commit and image set.

## 4. Gate 2 verification criteria

- Clean candidate identity and a reviewable diff from `ca470eb` and historical `4ed49dd`.
- Release Compose validates with a placeholder-free temporary env, defines exactly four services,
  contains no build key and never pulls.
- Shell syntax and deterministic unit tests cover load/start/no-build/no-pull, image mismatch,
  env permission/HTTP gates, smoke, safe stop and delivery tamper/path/secret rejection.
- Ruff format/check, mypy and applicable pytest suites pass; sandbox-only limitations are separated
  from product failures.
- Two source ZIP previews produced in `/tmp` are byte-identical and verify successfully. They are
  explicitly named previews and are not final artifacts or final checksums.
- The final delivery procedure is demonstrably executable on a clean organizer host with no project
  Python/uv/pip, no public Internet/download access and only organizer model-network access.
- The organizer agent prompt is executable from blank context, never requests secret output, invokes
  the official evaluator rather than inventing scoring, and preserves volumes on failure.

Gate 2 freezes only the later development/tuning start. Final ZIP/image creation remains a separate
post-tuning user decision.

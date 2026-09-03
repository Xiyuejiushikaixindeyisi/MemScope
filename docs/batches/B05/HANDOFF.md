# B05 Gate 1 implementation handoff

> Status: implementation verified; Gate 2 approval pending
>
> Gate 0 R1 and Gate 1 approved: 2026-09-03
>
> Base commit: `0c2a35d62add20472658e316f0ca332159c598f9`
>
> Branch: `batch/b05-real-add`

## 1. Delivered Real Add baseline

B05 connects the frozen contest Adapter and Raw Store to pinned MemOS `v2.0.32`. The explicit
`memos_add` profile opens lifespan-owned Raw/receipt SQLite stores and a strict async Product API
Gateway. Public Add is synchronous, deadline-bounded and serialized per user while different users
remain concurrent.

Success requires durable raw input, valid extraction output, exact tenant/Cube/payload provenance,
matching provider result IDs/content/type, complete result indices/count, successful vector sync,
a durable provider receipt and final Raw completion. Valid empty extraction succeeds; technical
failure never becomes raw-text memory. Public Health/Search intentionally remain 503 until B06.

## 2. Deterministic verification

| Check | Result |
|---|---|
| Full pytest | 469 passed in 7.99 seconds |
| Statements | 2,078/2,139; 97.15% |
| Branches | 527/556; 94.78% |
| Combined coverage | 96.66%; required minimum 95% |
| Ruff format/lint | passed; 74 files checked |
| Mypy | passed; 72 source/test/script files checked |
| Fixed archive | SHA-256 `9a804fd874932f0a4fd86f75fa4edb48fdd41807417f236bacda49b8664cdf3c` |
| Guarded patch preimage | passed against `.vendor-src/MemOS` |
| Compose config | `docker compose ... config --quiet` passed |

The tests cover Raw stable session positions, receipt persistence/conflict/restart/cancellation,
strict provider DTOs, committed readback, no automatic retry, timeouts, lanes, runtime construction,
lifespan cleanup, valid-empty and invalid-schema model fixtures.

## 3. Docker evidence and priority boundary

Both B05 images were built successfully using the explicit Huawei Cloud PyPI mirror. A disposable
five-service no-key topology reached healthy state and manually demonstrated:

- Add 200, pending reconciliation and completed replay without a second provider node;
- distinct user-to-Cube isolation;
- valid-empty Add 200 with zero memory nodes;
- invalid extraction schema returning explicit 500 while Raw remains pending;
- aggregate logs containing neither the content canary nor test password;
- public Health 503 as designed.

The fixed-source integration run also found that upstream `/product/get_memory_by_ids` applies a
startup-default tenant and returns empty for dynamic logical Cubes. The final Gateway therefore uses
`/product/get_memory` with exact user, Cube and payload-digest filters and validates the whole result
set. This is a correctness fix, not a Search implementation.

The local rootless daemon does not expose configured host ports and reports `MemoryLimit=false`,
`PidsLimit=false` and no cgroup driver. The clean-room verifier correctly treats those missing
runtime guarantees as failure on this host. Docker metadata resolution also consumed about 50
seconds per pinned Docker Hub image even with all layers cached; a final incremental rebuild was
stopped after roughly 98 seconds in accordance with the user's instruction not to displace tuning
work. The already-built integration images are evidence for the implemented baseline, not a claim
that the final uncommitted tree image was reproduced bit-for-bit.

Docker is an optional bonus path. `NATIVE_DEPLOYMENT.md` provides the supported organizer fallback
and must be preferred over prolonged container debugging when tuning time is at risk.

## 4. Failure and recovery semantics

- Same request and same payload: completed response replays exactly; pending state reconciles from
  exact provider provenance.
- Same request and another payload: fails closed as conflict.
- 429, timeout, provider 5xx and transport failure: sanitized retryable Gateway errors, with no
  automatic retry inside B05.
- Malformed/oversized/non-JSON/business-invalid response: sanitized non-retryable protocol error.
- Crash after provider write: Raw remains pending; receipt/readback reconciliation prevents a blind
  duplicate on retry when the provider commit is complete and attributable.
- Ambiguous or partial readback: no Raw completion and no destructive repair.

## 5. Open risks

1. Huawei Chat/Embedding model IDs, tool/JSON behavior, dimensions, quotas and semantic accuracy are
   unverified on the development machine.
2. The fixed MemOS patchset is deliberately narrow and tied to one source archive; upgrading MemOS
   requires a fresh source review and lock.
3. Same-user FIFO lanes are process-local. More than one memory-api worker or replica can violate
   order and is forbidden until distributed coordination exists.
4. SQLite Raw and receipt commits plus provider graph/vector writes are not one atomic transaction.
   Provenance reconciliation narrows this window but ambiguous partial provider state still needs
   manual inspection.
5. Provider committed readback adds latency. It is required for baseline correctness unless a later
   provider API proves an equivalent atomic committed receipt.
6. Docker host-port/cgroup/lifecycle proof remains pending on a capable final host, but is not a
   blocker for model/evaluation tuning or the native deployment path.
7. Public service readiness remains false until B06 implements and verifies Search.

## 6. Tuning-machine priorities

Start from the unchanged B05 baseline and record latency, failures, extraction precision/recall and
evaluation score. First compare candidate extractor models with the frozen P0 prompt; only then run
P1/P2 prompt ablations on a fixed validation slice. Keep one primary extractor, no backup/reviewer,
no auto retry and the 115-second hard budget until evidence justifies a reviewed change. See
`ADD_DESIGN_AND_TUNING.md` for the experiment order and stop conditions.

## 7. Deployment entry points

- Docker/Compose: repository `compose.yaml` and `deploy/compose.env.example`.
- Non-Docker organizer fallback: `docs/batches/B05/NATIVE_DEPLOYMENT.md`.
- Optional clean-room Docker evidence: `scripts/verify_b05_runtime.py`; run only on a daemon that
  supports host port publication and cgroup limits.

This handoff does not claim Gate 2 acceptance, a production model choice, a quality score, Search,
public readiness or final submission readiness.

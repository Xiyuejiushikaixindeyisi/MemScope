# B05 Gate 1 implementation handoff

> Status: Gate 2 review; approval pending
>
> Gate 0 R1 and Gate 1 approved: 2026-09-03
>
> Base commit: `0c2a35d62add20472658e316f0ca332159c598f9`
>
> Branch: `batch/b05-real-add`
>
> Candidate commit: `e7abf5f8140f61cda5d3cee8b17ef8dbd3b0d062`

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

## 8. Schedule retrospective and Docker stop rules

The roughly four-hour elapsed time cannot be reconstructed minute-by-minute because this batch did
not record a phase timer. The evidence nevertheless identifies three material causes: repeated
Docker registry/package resolution, diagnosis of a fixed-source tenant/readback incompatibility,
and production-grade failure/replay/deadline verification around a small public API change. The
commit contains about 1,271 added production-source lines, 1,347 test lines, 2,339 documentation
lines and 1,476 deployment/lock/verifier lines; public endpoint count is not a useful proxy for the
integration surface.

Two delays were avoidable. First, B04 had already recorded unstable official-PyPI downloads, so B05
should have selected the explicit Huawei mirror before the first build. Second, the rootless daemon
should have been preflighted for published ports and cgroups before attempting full lifecycle
evidence. Once those capabilities were absent, work should have switched immediately to the native
path instead of continuing Docker diagnosis.

Future batches use this stop policy:

1. Spend at most 10 minutes on daemon/Compose/rootless/port/cgroup and registry/package probes.
2. Use an explicit audited PyPI mirror on the first slow/failing probe; do not confuse a Python
   package mirror with a Docker Hub registry mirror.
3. Freeze application changes before the one candidate image build. Reuse BuildKit cache and add a
   local/registry cache exporter only when the target environment can consume it.
4. Cap batch-local Docker investigation at 30 minutes. On expiry, record the exact limitation and
   switch to native deployment or a known-capable Docker host.
5. Never let Docker packaging delay model capability probes, baseline evaluation or accuracy tuning.

For repeated multi-machine builds, the preferred infrastructure optimization is a trusted Docker
Hub pull-through cache configured at the daemon plus a persistent BuildKit local/registry cache.
That is host provisioning work, not a semantic B05 source change.

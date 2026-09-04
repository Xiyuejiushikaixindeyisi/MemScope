# B08 Gate 1 approved implementation plan

> Status: Approved by explicit user message on 2026-09-04
>
> Base commit: `d281aa03b5b90f9e9903033fd9f1fc822011a490`
>
> Branch: `batch/b08-system-verification`

## 1. Purpose

B08 adds system-verification evidence, not product behavior. It supplies a standard-library public
HTTP verifier, deterministic tests for that verifier, and a public ASGI system test spanning the
Adapter, real SQLite stores, real MemOS Gateway and application orchestration.

## 2. Frozen boundary

Health/Add/Search schemas, 115/55-second internal deadlines, user-to-Cube isolation, cross-session
Search, synchronous Add, receipt/provenance recovery, activated-only evidence and single-worker
deployment remain unchanged. The verifier never retries a failed public request automatically.

No file below `src/`, migration, dependency/lock, Compose/Docker or MemOS patch file may change.
Finding such a need is a stop condition.

## 3. Files

New:

- `docs/batches/B08/CONTEXT.md`
- `docs/batches/B08/PLAN.md`
- `docs/batches/B08/SYSTEM_VERIFICATION.md`
- `docs/batches/B08/HANDOFF.md`
- `scripts/verify_b08_system.py`
- `tests/unit/test_b08_system_verifier.py`
- `tests/system/test_b08_public_system.py`

After evidence, status/navigation-only edits are allowed in `README.md`, `docs/README.md`,
`docs/PROJECT_CONTEXT.md` and `docs/CODEMAP.md`.

## 4. Public verifier

`scripts/verify_b08_system.py` uses only Python's standard library and targets an already-running
memory-api. It accepts `exercise`, `prepare-restart` and `verify-restart` phases.

- `exercise` verifies exact Health, Add/replay, cross-session Search, cross-user isolation,
  conflict/validation failures, bounded low concurrency and stage latency distributions.
- `prepare-restart` writes a synthetic uniquely-namespaced Add and a mode-0600 state file outside
  the repository. It does not restart services.
- `verify-restart` consumes that state after an operator-controlled restart and verifies Health,
  exact replay, Search visibility and isolation.

Default concurrency is 2 and is capped at 8. Default timing samples are 5 and are capped at 30.
Reports contain counts, timings, classifications and hashes/opaque run identity, never API keys,
memory/query content, full provider responses or raw user identifiers.

## 5. Failure and timing semantics

Failures are classified as validation, conflict, rate-limited, timeout, provider unavailable,
protocol invalid, readiness unavailable, isolation breach, duplicate/recovery invariant or
unclassified. Unexpected status/body, cross-user evidence, Add duration at least 120 seconds,
Search duration at least 60 seconds and any unclassified failure fail the run.

P50/P95/P99/max are nearest-rank observations for Health, initial Add, replay, Search, isolation,
concurrent batches and restart readiness. These small samples are smoke evidence, not a semantic or
performance baseline.

## 6. Deterministic tests

- Unit tests drive the verifier against a local fixture server and cover CLI validation, report
  redaction, classification, percentile math, concurrency bounds and restart-state integrity.
- System tests use public ASGI calls with real Raw/receipt/Gateway components and MockTransport to
  cover full-path readiness, Add/Search/replay, concurrency/isolation, restart and fail-closed error
  envelopes.
- All persistent test files use pytest `tmp_path`; no external network, service or key is used.

## 7. Live execution and resources

At least one viable deployed path must run `exercise`, `prepare-restart`, an operator restart and
`verify-restart` before ordinary Gate 2 acceptance. Native/source execution is preferred when Docker
preflight fails. Docker gets a ten-minute preflight and no new image build because B08 changes no
runtime source.

The operator records candidate identity, versions, one-worker proof, CPU/RSS/disk observations,
Neo4j index and Qdrant collection state. Existing deadlines and configured ceilings are hard gates;
unpublished resource thresholds are observations only.

## 8. Verification commands

```bash
uv run pytest tests/unit/test_b08_system_verifier.py tests/system/test_b08_public_system.py
uv run pytest tests/component/test_b07_reliability_boundary.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests scripts
uv run pytest
```

Combined branch-aware coverage remains at least 95%; Gate 2 reports statement and branch coverage
separately.

## 9. Completion and rollback

B08 completes only when deterministic gates pass and a sanitized live report demonstrates the
public exercise/restart path, or the user explicitly approves a named external-evidence transfer
exception. Otherwise the candidate is documented but Gate 2 remains not ready. B09 never begins
automatically.

Rollback is a normal revert of B08 scripts/tests/docs. The verifier does not delete provider data,
volumes or services; its synthetic uniquely-namespaced records remain auditable test data.

# B07 Gate 1 approved implementation plan

> Status: Approved by explicit user message on 2026-09-04
>
> Base commit: `ee4a8720ec400642fa5925350c0c441b2cabfbb6`
>
> Branch: `batch/b07-reliability-closure`

## 1. Purpose

B07 closes the deterministic reliability evidence gap between the already accepted B05 Raw/Add
implementation and Gateway receipt/reconciliation implementation. It proves recovery by composing
the real SQLite Raw Store, real SQLite receipt ledger, real MemOS Gateway and `MemoryOperations`
against `httpx.MockTransport` across reconstructed component instances.

This is a tests-and-documents-only Batch. It does not add a reliability mechanism.

## 2. Frozen interfaces and invariants

- Public Health/Add/Search schemas and internal ports do not change.
- Add remains synchronous, uses the same user lane and 115-second application deadline, and has no
  automatic retry or raw-text success fallback.
- A completed receipt short-circuits provider I/O; a pending receipt reconciles only a complete,
  exact tenant/Cube/session/payload result set.
- Partial, duplicate-index, conflicting or foreign provenance fails closed without repair.
- Search exposes only `activated`, supported-type, vector-synchronized, attributable evidence and
  retains its 55-second total deadline.
- Single-worker deployment remains mandatory.

## 3. File boundary

New files:

- `docs/batches/B07/CONTEXT.md`
- `docs/batches/B07/PLAN.md`
- `tests/component/test_b07_reliability_boundary.py`
- `docs/batches/B07/HANDOFF.md`

Status/navigation-only edits may be made to `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md`,
`docs/PROJECT_CONTEXT.md`, `docs/CODEMAP.md`, `docs/README.md` and `README.md`.

No file below `src/`, no migration, lock, dependency, Compose, Docker or fixed MemOS patch file may
change. Discovering a need for such a change is a stop condition, not implicit authorization.

## 4. Deterministic scenarios

1. Provider Add and receipt completion succeed, then Raw completion fails. After both stores and
   Gateway are reconstructed, exact external replay must complete Raw without any provider request.
2. Provider commits the result but the Add response is lost, leaving Raw and receipt pending. After
   reconstruction, exact provenance readback must complete receipt and Raw without another Add.
3. A pending attempt encounters a partial or inconsistent provenance result set. It must raise a
   protocol error, retain pending state and issue no Add, repair or destructive request.
4. A technical provider failure, including 429, receives one provider attempt in that public call.
   Only a new external replay may initiate another attempt.
5. At least one successfully recovered memory is returned through the real Gateway Search path only
   when B06 ownership, state, type and provenance filters accept it.

All state is written below pytest `tmp_path`; all HTTP is local in-process MockTransport. Tests use
call counts and persisted state snapshots rather than real sleeps or network timing.

## 5. Verification

Run in shortest-feedback order:

```bash
uv run pytest tests/component/test_b07_reliability_boundary.py
uv run pytest tests/component/test_gateway_receipt_store.py \
  tests/component/test_sqlite_raw_store.py tests/unit/test_memos_memory_gateway.py \
  tests/unit/test_memory_operations.py tests/unit/test_b05_memos_patchset.py \
  tests/unit/test_b06_memos_patchset.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests scripts
uv run pytest
```

The existing branch-aware combined coverage gate remains at least 95%. Gate 2 reports statement and
branch coverage separately. B07 does not run Docker, external services, a model API, native live
integration or performance tests; B08 owns system verification.

## 6. Documentation reconciliation

The master plan receives a dated closure override explaining that its older B07 outbox/retry/
fallback/D04-B row is historical intent superseded by B05/B06 R1. The active sequence is B07
deterministic reliability evidence, B08 system verification and B09 reproducibility/delivery
closure. Development-machine evidence is never presented as a real-model baseline.

## 7. Rollback and review

B07 creates no runtime data or production migration. Rollback uses a normal revert of B07 test and
documentation changes; shared history is not rewritten. Any public/internal contract change,
production fix, retry/fallback/worker, dependency, MemOS patch, multi-worker support or Update/Forget
scope expansion requires a revised plan and explicit user approval.

## 8. Definition of done

- All five recovery/search assertions are proven by deterministic composed tests.
- Provider call counts demonstrate no implicit retry or duplicate write.
- Production source, schema, dependencies and runtime configuration have zero diff.
- Targeted checks, Ruff, mypy and full pytest with at least 95% combined branch-aware coverage pass.
- Closure sequencing and the historical B07 row are reconciled in authoritative documentation.
- `HANDOFF.md` records exact evidence, remaining limitations and B08 inputs.
- Gate 2 remains pending until the user explicitly accepts it; commit/push are not automatic.

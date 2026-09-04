# B09 Gate 1 approved implementation plan

> Status: Approved by explicit user message on 2026-09-04
>
> Base commit: `2498c904e97ab36d85a8596898996243460dae6f`
>
> Branch: `batch/b09-delivery-closure`

## 1. Purpose

B09 closes reproducible source delivery. It supplies the organizer entry document, aligns the SDD,
audits locks/licenses, and builds deterministic handoff and formal-submission archives from explicit
allowlists. It does not change the memory product or claim external evidence.

## 2. Frozen boundary

Public schemas, Raw/receipt persistence, Gateway semantics, 115/55-second internal deadlines,
user/Cube isolation, activated/provenance Search filtering, synchronous Add, no automatic retry or
Raw fallback and single-worker deployment remain unchanged.

No file below `src/`, migration, dependency version/lock, Compose/Docker runtime, MemOS archive or
patchset may change. Finding such a need is a stop condition.

## 3. Files

New:

- `INSTRUCTION.md`
- `docs/batches/B09/CONTEXT.md`
- `docs/batches/B09/PLAN.md`
- `docs/batches/B09/DELIVERY.md`
- `docs/batches/B09/HANDOFF.md`
- `scripts/build_b09_delivery.py`
- `tests/unit/test_b09_delivery.py`

Status and factual alignment edits are allowed in `README.md`, `SDD.md`, `THIRD_PARTY_NOTICES.md`,
`docs/README.md`, `docs/PROJECT_CONTEXT.md` and `docs/CODEMAP.md`. `.gitignore` or `.dockerignore`
may change only if a generated-artifact leak is proven.

## 4. Artifact model

The standard-library builder has two modes:

- `handoff` carries auditable source, tests, locks, public evaluation assets, deployment/runbooks,
  B08 verification and tuning/return templates for the capable tuning machine.
- `submission` produces the minimal `solution/` hierarchy with `INSTRUCTION.md`, `SDD.md`, notices,
  the MemOS license and runtime/build source under `solution/code/`. It excludes tests, internal
  Batch history and the public evaluation dataset.

Both modes use explicit root/directory allowlists, reject links and unsafe paths, omit Git/cache/
runtime/secret material, scan selected text for likely credentials, normalize ZIP timestamps and
permissions, embed a file-level SHA-256 manifest and emit a non-circular ZIP SHA-256 sidecar. If a
Git checkout is present, the builder requires the supplied 40-character commit to equal clean HEAD.
It refuses to write inside the source tree or overwrite an existing artifact.

## 5. Documentation and license policy

`INSTRUCTION.md` is the non-interactive organizer entry for Compose and native deployment,
configuration, authentication, endpoints, readiness, verification, stopping and failure policy.
`SDD.md` is aligned through B08/B09 without introducing real-model or score claims.

`THIRD_PARTY_NOTICES.md`, source locks, archive checksums, patch hashes and OCI digests remain the
auditable licensing/version chain. B09 includes the upstream MemOS license in the submission but
does not invent a license for original MemScope source.

## 6. Deterministic verification

Unit tests cover stable rebuild hashes, formal and handoff contents, manifest/sidecar verification,
forbidden-file exclusion, credential detection, symlink rejection, in-tree output rejection and
unsafe archive paths. Preview archives are built twice in separate temporary directories and must
have identical hashes, then be verified without extracting untrusted paths.

Existing MemOS source/patch/image lock tests remain authoritative. Compose receives static
`config --quiet` validation only; B09 does not start/build Docker or access a real model API.

## 7. Quality gates

```bash
uv run pytest tests/unit/test_b09_delivery.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests scripts
uv run pytest
```

Combined branch-aware coverage remains at least 95%; Gate 2 reports statement and branch coverage
separately. The source/patch checks and two-build artifact identity are reported independently.

## 8. Completion and freeze

The B09 Gate 2 candidate includes the implementation commit, clean working tree, complete quality
evidence, preview artifact hashes, limitations and rollback. Preview archives live outside the
repository and are not committed.

No final tag, release or named handoff ZIP is created until explicit B09 Gate 2 acceptance.

**Post-approval override, 2026-09-04:** the user accepted B09 Gate 2 but explicitly prohibited the
planned final handoff ZIP and out-of-band SHA-256 because additional development and version
consolidation are required. Therefore acceptance freezes the B09 implementation only; it does not
authorize the artifact, sidecar or tag. A new explicit instruction is required after the additional
work is scoped and approved.

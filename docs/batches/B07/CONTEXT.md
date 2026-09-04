# B07 context manifest

```yaml
batch: B07
status: gate_2_candidate_pending_user_acceptance
date: 2026-09-04
gate_1_approval: user_explicit
base_commit: ee4a8720ec400642fa5925350c0c441b2cabfbb6
branch: batch/b07-reliability-closure
candidate_commit: uncommitted
depends_on:
  hard:
    - b00_b01_b02_b03_b04_b05_b06_accepted_frozen
    - b05_real_add_commit_e7abf5f8140f61cda5d3cee8b17ef8dbd3b0d062
    - b06_real_search_commit_1507317b048fc06d25f020ded751f35fae2aeb6f
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484
    - exact_user_to_logical_cube_isolation
    - synchronous_add_with_no_automatic_retry
    - activated_committed_search_evidence_only
scope:
  - composed_raw_receipt_gateway_recovery_evidence
  - deterministic_restart_and_fault_injection_tests
  - b07_b09_closure_sequence_document_reconciliation
forbidden_without_reapproval:
  - production_source_or_public_contract_change
  - schema_migration_or_dependency_change
  - outbox_worker_or_background_service
  - automatic_retry_or_raw_search_fallback
  - multi_worker_or_multi_replica_support
  - memos_patch_or_version_change
  - update_forget_semantic_claims
  - docker_or_live_provider_execution
deterministic_evidence:
  focused_b07: 4_passed
  b05_b06_reliability_regression: 141_passed
  full_pytest: 546_passed
  combined_coverage: 96.73_percent
  statement_coverage: 97.21_percent
  branch_coverage: 94.92_percent
  ruff: passed
  mypy: passed
```

## P0 implementation context

- `docs/batches/B05/CONTEXT.md`, `docs/batches/B05/HANDOFF.md` and
  `docs/adr/0006-b05-real-add-boundary.md` define the frozen synchronous Add, durable receipt and
  provenance reconciliation boundary.
- `docs/batches/B06/CONTEXT.md`, `docs/batches/B06/HANDOFF.md` and
  `docs/batches/B06/SEARCH_DESIGN_AND_TUNING.md` define the frozen Search visibility, filtering and
  deadline boundary.
- `src/memscope/application/memory_operations.py`, `src/memscope/raw_store/sqlite.py`,
  `src/memscope/memory_gateway/memos.py` and `src/memscope/memory_gateway/receipt_store.py` are the
  composed path under test. B07 does not modify them.
- Existing Raw, receipt and Gateway unit/component tests remain authoritative for each individual
  layer. B07 adds only the missing cross-layer restart evidence.

Vendor-wide source, the 1000-item evaluation corpus and unrelated modules are outside the working
set. Real model identity, Embedding dimension, semantic score and latency distribution remain
tuning-machine evidence and are not development-machine completion criteria.

## Frozen recovery boundary

Raw, Gateway receipt, graph and vector state are not one distributed transaction. An exact replay
may finish a pending Raw request by short-circuiting a completed receipt, or may finish a pending
receipt after a complete and tenant-consistent provenance readback. Partial, conflicting or foreign
provenance fails closed. One public Add attempt never performs an automatic provider retry.

## Stop condition

If deterministic composition shows that any accepted invariant requires production code, schema,
configuration, dependency or fixed-source patch changes, implementation stops and requests a formal
Gate 1 amendment or B05/B06 revision. B07 must not silently repair a frozen semantic boundary.

No such gap was found by the B07 candidate. Gate 2 acceptance remains a user decision and does not
implicitly authorize B08, a commit or a push.

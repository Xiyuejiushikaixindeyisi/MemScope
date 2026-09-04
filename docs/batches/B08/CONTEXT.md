# B08 context manifest

```yaml
batch: B08
status: deterministic_candidate_complete_gate_2_not_ready_live_evidence_missing
date: 2026-09-04
gate_1_approval: user_explicit
base_commit: d281aa03b5b90f9e9903033fd9f1fc822011a490
branch: batch/b08-system-verification
depends_on:
  hard:
    - b00_b01_b02_b03_b04_b05_b06_b07_accepted_frozen
    - b07_candidate_commit_e30fa91d332e2945f27185b5a5f3248cc5ebe680
    - b07_freeze_commit_d281aa03b5b90f9e9903033fd9f1fc822011a490
    - add_below_120_seconds
    - search_below_60_seconds
    - exact_user_cube_isolation
    - single_memory_api_worker
scope:
  - public_system_verifier
  - deterministic_public_full_path_tests
  - concurrency_restart_resource_latency_evidence_protocol
forbidden_without_reapproval:
  - production_source_or_contract_change
  - schema_migration_dependency_or_memos_patch
  - automatic_retry_fallback_or_background_worker
  - multi_worker_or_multi_replica_support
  - new_search_update_forget_or_conflict_algorithm
  - unapproved_docker_build_or_live_provider_access
deterministic_evidence:
  verifier_unit_tests: 4_passed
  b08_b07_focused_tests: 10_passed
  full_pytest: 552_passed
  combined_coverage: 96.73_percent
  statement_coverage: 97.21_percent
  branch_coverage: 94.92_percent
  ruff: passed
  mypy: passed
pending_live_evidence:
  - exercise_report
  - prepare_restart_report
  - operator_restart_record
  - verify_restart_report
  - sanitized_resource_and_storage_observations
```

## P0 context

- `docs/batches/B07/HANDOFF.md` freezes the composed recovery boundary and is the immediate hard
  dependency.
- `docs/batches/B06/ORGANIZER_DEPLOYMENT.md` and `docs/batches/B06/NATIVE_DEPLOYMENT.md` define the
  current Docker/native admission gates and storage checks.
- `scripts/verify_b06_candidate.py`, `scripts/verify_b05_runtime.py` and
  `scripts/verify_b04_runtime.py` are historical verification inputs. B08 does not rewrite their
  accepted evidence or automatically run their destructive/container paths.
- `docs/collaboration/48H_DELIVERY_GUARDRAILS.md` makes native/source execution primary and Docker a
  time-boxed optional path.

## Machine boundary

This development machine can run deterministic Python verification but has no accepted live
MemOS/Neo4j/Qdrant/model topology. B08 can build and test the audit tool here, but a Gate 2 claim of
live system success requires a sanitized report returned from a viable native or Docker deployment.
MockTransport and local fixture evidence cannot be presented as a real-model baseline.

The deterministic candidate is complete. A read-only listener check on 2026-09-04 found no
memory-api, MemOS, Neo4j or Qdrant listeners on their candidate ports, so no live execution was
attempted and ordinary Gate 2 remains not ready.

## Stop condition

Any observed need to alter production code, contracts, databases, dependencies, fixed-source
patches, retries/fallback, worker topology or memory algorithms stops B08 and requires an amended
plan or a formal revision of the owning frozen Batch.

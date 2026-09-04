# B09 context manifest

```yaml
batch: B09
status: gate_2_review_open_not_accepted_not_frozen
date: 2026-09-04
gate_1_entry: user_explicit
gate_1_approval: user_explicit
gate_2_review_entry: user_explicit
accepted: false
frozen: false
base_commit: 2498c904e97ab36d85a8596898996243460dae6f
branch: batch/b09-delivery-closure
candidate_commit: fe246c0ba59a39a108850f6e35126114c0a20716
depends_on:
  hard:
    - b00_through_b08_accepted_frozen
    - b08_deterministic_candidate_44ce4a7be3e052fa839692bb3dc2c4c8b149ecb4
    - b08_freeze_commit_2498c904e97ab36d85a8596898996243460dae6f
  transferred:
    - b08_live_exercise
    - b08_restart_persistence
    - b08_resource_observations
    - real_model_baseline_and_tuning
scope:
  - organizer_instruction_and_sdd_alignment
  - dependency_source_image_and_license_audit
  - deterministic_allowlisted_handoff_and_submission_packaging
  - two_machine_sha256_manifest_and_return_protocol
  - clean_extract_and_static_delivery_verification
forbidden_without_reapproval:
  - production_source_contract_or_schema_change
  - dependency_model_or_embedding_dimension_change
  - memos_patch_or_search_add_algorithm_change
  - retry_fallback_background_worker_or_multi_worker_change
  - fabricated_live_evidence_or_official_score
  - final_tag_or_release_before_gate_2_acceptance
deterministic_evidence:
  b09_unit_tests: 4_passed
  full_pytest: 556_passed
  combined_coverage: 96.73_percent
  statement_coverage: 97.21_percent
  branch_coverage: 94.92_percent
  ruff: passed
  mypy: passed
  handoff_reproducible_sha256: 1ec051876a3098476adfb49422b46cffe37984d5f248cbb6aee8ba367fb6b6f7
  submission_reproducible_sha256: af647cd751b6378f1d9aa2417b874107d5a8eddef3e20a7bdf8a7b58e0473960
```

## P0 context

B09 inherits B00–B08 without reopening their implementation. B08 is Accepted/Frozen under the named
tuning-machine live-evidence transfer exception: the public verifier and deterministic system tests
are accepted, while real `exercise`, restart-persistence and resource evidence remains pending.
B09 must carry that limitation into every manifest and guide; it cannot relabel pending evidence as
passed.

The formal submission requires `INSTRUCTION.md`, `SDD.md`, complete source and a usable build/start
path. The repository already has exact Python dependency locks, a fixed MemOS archive and checksum,
a guarded patch lock, OCI digests, third-party notices and two-machine templates. At Gate 1 entry it
lacks the root organizer instruction and an allowlisted reproducible artifact builder.

## Licensing boundary

B09 audits redistributed third-party material and carries the MemOS Apache-2.0 license. The
repository owner has not selected a license for original MemScope source. B09 therefore does not
invent or grant a root project license; such a legal decision requires separate user authorization.

## Stop condition

Any discovered need to change production behavior, dependencies, fixed MemOS source/patches,
Compose topology or public contracts stops B09 and requires a revised plan or formal revision of the
owning frozen Batch. A tuning-machine P0 failure reopens B08 rather than being hidden in packaging.

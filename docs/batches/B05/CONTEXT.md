# B05 context manifest

```yaml
batch: B05
status: gate_1_implementation_verified_gate_2_pending
date: 2026-09-03
gate_0_revision: R1
gate_0_approval: user_explicit
gate_1_approval: user_explicit
base_commit: 0c2a35d62add20472658e316f0ca332159c598f9
branch: batch/b05-real-add
depends_on:
  hard:
    - b00_b01_b02_b03_b04_accepted_frozen
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484
    - add_total_timeout_below_120_seconds
    - one_worker_for_same_user_ordering
    - exact_user_to_logical_cube_isolation
    - synchronous_committed_add_or_explicit_failure
  runtime:
    - python_3_11
    - neo4j_community_5_26_6
    - qdrant_1_15_3
    - openai_compatible_chat_and_embedding_endpoints
  pending_external:
    - exact_huawei_model_ids_and_capabilities
    - embedding_dimension_and_rate_limits
    - semantic_baseline_and_evaluation_score
    - organizer_host_and_entrypoint_constraints
priority:
  first: correctness_and_evaluation_accuracy_within_timeout
  second: robust_extensible_baseline
  optional_bonus: docker_service_packaging_and_host_specific_runtime_evidence
deployment_paths:
  docker: compose.yaml
  native_fallback: docs/batches/B05/NATIVE_DEPLOYMENT.md
required_reading:
  - docs/batches/B05/GATE0.md
  - docs/batches/B05/PLAN.md
  - docs/batches/B05/ADD_DESIGN_AND_TUNING.md
  - docs/adr/0006-b05-real-add-boundary.md
  - docs/interfaces/raw-store-v1.md
  - docs/interfaces/memory-gateway-v1.md
  - docs/integrations/MEMOS_V2_0_32_MAP.md
delivered:
  - real_memos_product_add_gateway
  - durable_gateway_receipts_and_pending_reconciliation
  - tenant_cube_digest_committed_readback
  - same_user_fifo_lanes_and_cross_user_concurrency
  - stable_cross_chunk_session_positions
  - 115_second_total_deadline_and_nested_timeout
  - guarded_memos_patchset
  - explicit_memos_add_runtime_profile
  - deterministic_no_key_fault_fixtures
  - docker_and_native_deployment_paths
deferred_to_tuning:
  - extractor_model_selection
  - prompt_p1_p2_ablation
  - real_embedding_model_and_dimension
  - accuracy_latency_failure_rate_measurement
deferred_to_b06:
  - public_search
  - result_ranking_and_evidence_packing
  - public_health_readiness
forbidden_without_review:
  - multi_worker_or_multi_replica_add
  - automatic_provider_retry
  - async_add_or_background_semantic_mutation
  - raw_text_success_fallback
  - backup_or_reviewer_llm
  - destructive_merge_delete_or_global_cleanup
  - public_search_success
```

## Current machine boundary

The available rootless Docker daemon can build and run the topology but does not reliably publish
the configured host port and reports no cgroup memory/PID enforcement. This is host evidence, not an
application failure. The B05 runtime verifier intentionally fails those assertions on such a host.
Per the user-approved priority, do not spend tuning time repairing that optional environment; use a
capable Docker host when convenient or follow `NATIVE_DEPLOYMENT.md`.

## Next work

Finish the B05 Gate 2 review/approval without claiming Huawei or semantic-quality evidence. Then
start B06 only in a new Session with its own Gate 0. The tuning machine should begin with capability
probes and an unchanged-baseline evaluation before changing the extractor model or prompt.

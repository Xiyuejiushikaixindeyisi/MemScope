# B06 context manifest

```yaml
batch: B06
status: accepted_frozen
date: 2026-09-04
gate_0_revision: R1
gate_0_approval: user_explicit
gate_1_approval: user_explicit
gate_2: accepted_by_user_2026_09_04
base_commit: 3e735b3e0aa49c8b66436123fa245c9bc974dee7
candidate_commit: 1507317b048fc06d25f020ded751f35fae2aeb6f
branch: batch/b06-real-search
depends_on:
  hard:
    - b00_b01_b02_b03_b04_b05_accepted_frozen
    - b05_real_add_commit_e7abf5f8140f61cda5d3cee8b17ef8dbd3b0d062
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484
    - exact_user_to_logical_cube_isolation
    - search_total_timeout_below_60_seconds
    - activated_and_committed_provenance_only
  runtime:
    - python_3_11_16
    - uv_0_12_9
    - neo4j_community_5_26_6
    - qdrant_1_15_3
    - openai_compatible_chat_and_embedding_endpoints
  pending_external:
    - exact_huawei_model_ids_and_capabilities
    - embedding_dimension_and_existing_collection_compatibility
    - real_add_search_health_smoke
    - activated_state_after_normal_add
    - semantic_accuracy_and_latency_distribution
    - capable_docker_host_validation
priority:
  first: correctness_and_evaluation_accuracy_within_timeout
  second: robust_extensible_baseline
  optional_bonus: docker_packaging
deployment_paths:
  organizer_gate: docs/batches/B06/ORGANIZER_DEPLOYMENT.md
  docker: compose.yaml
  native_fallback: docs/batches/B06/NATIVE_DEPLOYMENT.md
required_reading:
  - docs/batches/B06/GATE0.md
  - docs/batches/B06/PLAN.md
  - docs/batches/B06/SEARCH_DESIGN_AND_TUNING.md
  - docs/batches/B06/ORGANIZER_DEPLOYMENT.md
  - docs/batches/B06/HANDOFF.md
  - SDD.md
  - docs/interfaces/contest-http-v1.md
  - docs/interfaces/memory-gateway-v1.md
  - docs/integrations/MEMOS_V2_0_32_MAP.md
delivered_candidate:
  - real_memos_product_search_gateway
  - conservative_fast_cosine_local_search_payload
  - activated_type_provenance_source_filtering
  - stable_exact_id_content_dedup_and_top_k
  - 50_second_warning_and_55_second_total_deadline
  - search_error_propagation_fixed_source_patch
  - search_log_sanitization_fixed_source_patch
  - raw_receipt_current_health_and_startup_search_probe_readiness
  - typed_runtime_search_configuration
  - organizer_docker_native_storage_initialization_gate
  - organizer_native_add_search_health_deployment_guide
  - initial_system_design_description
  - deterministic_public_candidate_verifier
deterministic_evidence:
  pytest: 542_passed
  combined_coverage: 96.73_percent
  statement_coverage: 97.21_percent
  branch_coverage: 94.92_percent
  ruff: passed
  mypy: passed
  fixed_patch_lock: passed
deferred_to_tuning:
  - production_model_selection
  - real_embedding_dimension
  - relativity_mode_dedup_rerank_single_variable_ablation
  - locomo_memops_accuracy
  - p50_p95_p99_max_latency
forbidden_without_review:
  - public_schema_change_or_final_answer_generation
  - session_id_search_isolation
  - raw_search_or_raw_text_success_fallback
  - automatic_retry_or_multi_worker
  - external_reranker_or_default_mmr_bm25_fulltext
  - query_time_llm_conflict_or_forget_mutation
  - exposing_resolving_archived_deleted_or_unknown_status
  - silent_b05_add_semantic_change
```

## Current machine boundary

The development machine has a persistent CPython 3.11.16 + uv 0.12.9 environment and completes all
deterministic checks. It has no MemOS/Neo4j/Qdrant listeners on the standard service ports, and its
known rootless Docker daemon cannot reliably prove host-port publication or cgroup enforcement.
Gate 1 therefore did not start/build Docker and does not claim a real-model Search hit.

The absence of real model IDs, Embedding dimension, score distribution or official evaluation data
does not invalidate the design/implementation candidate. Those are explicit tuning-machine tasks.
However, a normal Add that completes only as `resolving`, a Search technical exception that still
becomes empty HTTP 200, or any cross-user evidence would block acceptance and require review.

## Next authorized state

The user accepted B06 Gate 2 on 2026-09-04. Its contract, design and implementation semantics are
therefore frozen at implementation commit `1507317b048fc06d25f020ded751f35fae2aeb6f`; the real
Huawei-host smoke and Docker P4 checks are transferred under the explicit conditions in
`HANDOFF.md`. Do not build Docker or create a B07 branch automatically. A later Session must first
complete the read-only B07–B09 closure context review and wait for explicit authorization.

# B04 context manifest

```yaml
batch: B04
status: gate_1_implementation_complete_gate_2_runtime_pending
approved_at: 2026-09-02
gate_1_approval: user_explicit
base_commit: 3ed5477
branch: batch/b04-runtime-infra
depends_on:
  hard:
    - b00_b01_b02_b03_accepted_frozen
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484
    - source_zip_built_by_organizer
    - docker_compose_optional_delivery_allowed
    - no_hosted_database
    - add_search_same_deployment_lifecycle
  soft:
    - organizer_build_network_or_dependency_cache
    - final_linux_architecture
    - model_weight_packaging_and_license_limits
    - organizer_embedding_model_permission_id_dimension_and_rate_limit
  deferred_to_b05:
    - memory_api_public_entry
    - real_memos_gateway
    - embedding_and_llm_model_egress
    - add_path_and_cube_lifecycle
  deferred_to_b06:
    - search_path_and_quality_policy
    - optional_external_reranker
required_reading:
  - docs/batches/B04/PLAN.md
  - docs/adr/0005-b04-compose-runtime-topology.md
  - docs/integrations/MEMOS_V2_0_32_MAP.md
  - docs/batches/B03/HANDOFF.md
  - MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
  - compose.yaml
allowed_changes:
  - compose.yaml
  - .dockerignore
  - .gitignore
  - .env.example
  - README.md
  - docker/memos/**
  - deploy/**
  - third_party/memos/**
  - THIRD_PARTY_NOTICES.md
  - scripts/verify_b04_runtime.py
  - tests/unit/test_b04_runtime_manifest.py
  - tests/integration/test_b04_runtime.py
  - docs/adr/0005-b04-compose-runtime-topology.md
  - docs/integrations/MEMOS_V2_0_32_MAP.md
  - docs/batches/B04/**
  - docs/PROJECT_CONTEXT.md
  - docs/CODEMAP.md
  - MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
forbidden_changes:
  - src/memscope/**
  - tests_for_b00_b03_except_new_b04_test
  - pyproject.toml
  - uv.lock
  - docs/interfaces/**
  - docs/adr/0001_to_0004
  - docs/batches/B00_to_B03
  - .vendor-src/MemOS/**
non_goals:
  - contest_http_success
  - add_or_search
  - semantic_quality
  - model_api_compatibility
  - one_image_one_container
  - cross_host_persistence_or_backup
  - offline_image_build
  - b05_or_b06_implementation
gate_2_required:
  - complete_static_quality_suite
  - clean_room_compose_config_and_build
  - three_service_healthy_cold_start
  - aggregate_database_readiness
  - memos_qdrant_collection_dimension
  - no_published_ports_and_internal_runtime_network
  - named_volume_restart_persistence
  - qdrant_fault_detection_and_recovery
  - measured_build_cold_start_restart
```

## Current external facts

- Submission is `solution.zip` with `INSTRUCTION.md`, `SDD.md`, complete `code/`, dependency
  declarations and optional Dockerfile/Compose. The organizer builds and runs it.
- Health is unauthenticated and returns any 2xx when ready. Public port/entry command is not yet
  published; the future adapter defaults to configurable 8000.
- Add timeout is 1–120 seconds and Search timeout is 1–60 seconds.
- Formal `top_k` is fixed at 100 in the provided contract; there is no separate K bonus formula.
  Accuracy on the evaluation set and response time are the primary optimization concerns.
- No hosted database exists. Local container storage is sufficient within a deployment lifecycle;
  a mount path may become configurable when the organizer publishes one.
- Huawei AI Gateway provides OpenAI-compatible Chat/Embeddings/Responses and rerank paths, but the
  exact subscribed model IDs must be discovered with `/v1/models`. Formal embedding access, ID,
  dimension and rate limits remain pending.
- The platform uses Bearer API Key or IAM token, model-dependent pass-through fields and standard
  HTTP status classes. Batch evaluation requires rate limiting and exponential-backoff design in a
  later batch.
- Hardware, image size and target platform limits are currently unspecified.
- Permission and size/license rules for bundling an open-source embedding model remain pending.

## Implementation-time environment fact

The current MemScope host is Linux x86_64 but has no Docker, Podman, nerdctl, buildah or Compose
binary. Static implementation and tests may complete here; none can be treated as the required
Gate 2 runtime evidence.

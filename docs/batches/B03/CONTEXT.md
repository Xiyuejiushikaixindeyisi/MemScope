# B03 Context Manifest

```yaml
batch: B03
status: Approved/In Progress
approved_at: 2026-09-02
gate_1_approval: user_explicit
base_commit: a7822047640cac26a46e25663be9b60542f7d47b
planned_branch: batch/b03-no-key-doubles
depends_on:
  hard:
    - user_explicit_gate_1_approval
    - b00_b01_b02_accepted_frozen
    - contest_http_v1_and_contest_operations_unchanged_except_additive_conflict_error
    - raw_store_v1_schema_identity_and_transactions_unchanged
    - python_3_11_16_uv_0_12_9_sqlite_3_53_1_and_existing_lockfile
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484_unchanged
  soft:
    - organizer_model_api_and_keys
    - organizer_hardware_timeout_concurrency_failure_policy
    - organizer_compose_network_build_constraints
    - fixed_memos_model_client_protocol_and_extraction_schema
    - fixed_memos_rerank_requirement
    - finals_delivery_requirements
  experimental: []
required_reading:
  P0:
    - path: docs/batches/B03/PLAN.md
      range: complete_file
      reason: proposed B03 scope, Gateway/Mock contracts, orchestration, tests and approval points
      authority: current_batch_gate_1
    - path: docs/batches/B03/CONTEXT.md
      range: complete_file
      reason: authoritative context and allowed-change manifest
      authority: current_batch_gate_1
    - path: docs/batches/B02/HANDOFF.md
      range: complete_file
      reason: frozen Raw Store public surface, pending recovery and default 503 boundary
      authority: accepted_upstream_batch
    - path: docs/interfaces/raw-store-v1.md
      range: complete_file
      reason: canonical identity, local/external consistency and evolution rules
      authority: accepted_internal_interface
    - path: docs/batches/B01/HANDOFF.md
      range: complete_file
      reason: frozen ContestOperations, HTTP readiness and application error boundary
      authority: accepted_upstream_batch
    - path: docs/interfaces/contest-http-v1.md
      range: complete_file
      reason: exact Add/Search evidence and default-unavailable evaluator contract
      authority: accepted_external_interface
    - path: MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
      range: sections_2_5_6_7_2_to_7_5_8_4_9_to_12_16_to_19
      reason: architecture, two no-key doubles, Add/Search, profiles, quality and Batch scope
      authority: current_project_plan
    - path: src/memscope/operations.py
      range: complete_file
      reason: frozen application commands/evidence/port and additive conflict location
      authority: accepted_b01_code
    - path: src/memscope/app.py
      range: complete_file
      reason: explicit operation injection and unchanged default composition
      authority: accepted_b01_code
    - path: src/memscope/api/errors.py
      range: complete_file
      reason: safe application error to HTTP status mapping
      authority: accepted_b01_code
    - path: src/memscope/api/routes.py
      range: complete_file
      reason: Add OpenAPI 409 addition and response invariants
      authority: accepted_b01_code
    - path: src/memscope/raw_store/protocol.py
      range: complete_file
      reason: operations composition boundary
      authority: accepted_b02_code
    - path: src/memscope/raw_store/models.py
      range: complete_file
      reason: NEW/PENDING/COMPLETED and stored response invariants
      authority: accepted_b02_code
    - path: src/memscope/raw_store/identity.py
      range: complete_file
      reason: stable logical cube/message IDs used for Gateway provenance
      authority: accepted_b02_code
    - path: pyproject.toml
      range: complete_file
      reason: existing FastAPI/Pydantic/HTTPX and no dependency-change constraint
      authority: repository_configuration
  P1:
    - path: docs/CODEMAP.md
      range: complete_file
      reason: current ownership and dependency direction
      authority: current_project_navigation
    - path: src/memscope/logging_config.py
      range: complete_file
      reason: extend fixed safe log allowlist
      authority: accepted_b00_b02_code
    - path: tests/contract/test_contest_api.py
      range: conflict_error_and_default_regression_relevant_sections
      reason: preserve HTTP error envelope and default behavior
      authority: accepted_b01_tests
    - path: tests/smoke/test_minimal_app.py
      range: complete_file
      reason: default main process must remain unavailable and cleanly stoppable
      authority: accepted_b01_tests
    - path: tests/component/test_sqlite_raw_store.py
      range: replay_failure_concurrency_and_cancel_relevant_tests
      reason: reuse public behavior without depending on private SQLite state
      authority: accepted_b02_tests
    - path: README.md
      range: current_boundaries_and_local_run_sections
      reason: document explicit Fake/Mock usage without changing defaults
      authority: repository_documentation
    - path: .gitignore
      range: complete_file
      reason: confirm no Mock/runtime artifacts are committed
      authority: repository_configuration
  P2:
    - path: .vendor-src/MemOS
      range: none_in_B03_unless_exact_mock_protocol_is_pulled_forward_and_regated
      reason: B03 deliberately does not claim real MemOS compatibility
      authority: fixed_upstream_source
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/api_contract.md
      range: only_if_contest_http_409_or_evidence_shape_is_challenged
      reason: B01 interface remains primary accepted contract
      authority: current_contest_contract_reconstruction
do_not_load:
  - docs/achieve/**
  - 技术难题-Agent-Memory-评测集（开源）-1.0/official/questions.jsonl
  - 技术难题-Agent-Memory-评测集（开源）-1.0/official/samples/**
  - complete_formal_samples
  - complete_MemOS_source_tree
  - historical_chat_records
  - proxy_evaluation_questions_or_gold
  - unrelated_MemOS_plugins_frontend_and_memory_types
allowed_changes:
  - README.md
  - src/memscope/operations.py
  - src/memscope/api/errors.py
  - src/memscope/api/routes.py
  - src/memscope/logging_config.py
  - src/memscope/application/**
  - src/memscope/memory_gateway/**
  - src/memscope/mock_model_api/**
  - tests/unit/test_operations.py
  - tests/unit/test_api_errors.py
  - tests/unit/test_logging_config.py
  - tests/unit/test_gateway_models.py
  - tests/unit/test_fake_memory_gateway.py
  - tests/unit/test_memory_operations.py
  - tests/unit/test_mock_model_deterministic.py
  - tests/contract/test_contest_api.py
  - tests/contract/memory_gateway_contract.py
  - tests/contract/test_fake_gateway_contract.py
  - tests/contract/test_memory_operations_http.py
  - tests/contract/test_mock_model_api.py
  - tests/smoke/test_fake_memory_path.py
  - tests/smoke/test_mock_model_process.py
  - docs/PROJECT_CONTEXT.md
  - docs/CODEMAP.md
  - docs/interfaces/contest-http-v1.md
  - docs/interfaces/memory-gateway-v1.md
  - docs/interfaces/mock-model-api-v1.md
  - docs/adr/0004-two-layer-no-key-test-doubles.md
  - docs/batches/B03/PLAN.md
  - docs/batches/B03/CONTEXT.md
  - docs/batches/B03/HANDOFF.md
required_tests:
  - uv_lock_check_offline_and_unchanged
  - ruff_format_check
  - ruff_lint
  - mypy_strict
  - pytest_unit_contract_component_smoke_and_regression
  - total_coverage_at_least_95_percent
  - b03_statement_coverage_at_least_95_percent
  - b03_branch_coverage_at_least_90_percent
  - gateway_models_strict_invariants
  - reusable_gateway_contract_suite
  - fake_add_exact_idempotency_and_conflict
  - fake_search_determinism_top_k_and_no_session_filter
  - fake_cross_user_and_cube_isolation
  - memory_operations_new_pending_completed_and_conflict
  - memory_operations_gateway_and_complete_failure_recovery
  - concurrent_duplicate_add_and_cancel_convergence
  - malicious_gateway_provenance_filter
  - explicit_fake_http_health_add_search_and_409
  - mock_chat_and_embedding_subset_contract
  - mock_embedding_cross_process_golden_and_dimension
  - mock_429_500_timeout_invalid_json_dimension_and_bad_header
  - mock_uvicorn_start_health_request_and_clean_shutdown
  - default_main_503_and_no_database_regression
  - b02_raw_schema_identity_migration_and_restart_regression
  - fake_and_mock_local_segmented_latency_report
open_decisions:
  - approve_gateway_fake_operations_and_independent_mock_api_scope
  - approve_explicit_fake_success_path_but_default_main_503
  - approve_memory_gateway_v1_models_methods_errors_and_dependencies
  - approve_gateway_add_owns_internal_cube_ensure_without_create_cube_method
  - approve_pending_gateway_replay_and_completed_no_gateway_call
  - approve_application_request_conflict_and_http_409_mapping
  - approve_logical_cube_derivation_and_gateway_provenance_filter
  - approve_nonpersistent_async_safe_exact_idempotent_fake
  - approve_fake_token_overlap_v1_as_wiring_only
  - approve_typed_fake_faults_and_mock_http_malformed_json_separation
  - approve_openai_shaped_mock_health_chat_embedding_subset
  - approve_mock_default_chat_content_dimension_and_factory_injection
  - approve_internal_allowlist_failure_header_and_no_rerank_stream_tools_tokens
  - approve_no_timeout_retry_fallback_or_background_recovery
  - approve_no_new_env_dependency_profile_app_main_rawstore_or_compose_changes
  - approve_allowed_change_scope_shared_contract_and_quality_matrix
  - approve_branch_creation_and_implementation_only_after_gate_1
```

## 使用规则

- B03 实施前必须重新核验 `base_commit`、工作区、B00～B02 状态和 MemOS 固定版本；
- Gate 1 批准后才创建 `batch/b03-no-key-doubles`，Draft 状态不得编写 Gateway/Mock/编排代码；
- P0 完整读取项为 15 个；P1/P2 只能按标注范围定向读取；
- 当前 `official/` 仅是本地规则重建与代理回归集，不是主办方字节级正式包；
- Fake 只能证明 MemScope contract/wiring；Mock 只能证明其 HTTP subset，二者都不能产生 baseline 分数；
- 所有 SQLite 测试只写临时目录；Mock 测试只绑定临时 localhost port；
- 若 P0、hard dependency、Gateway/Mock contract、409/重放/隔离语义、依赖或允许范围变化，本 Manifest 失效；
- P2 只有在具体约束被拉入 B03 时读取，并必须先判断是否触发重新 Gate 1；
- B03 不读取正式题目、gold、样本内容或完整 MemOS 源码，不执行代理评分，不进入 B04。

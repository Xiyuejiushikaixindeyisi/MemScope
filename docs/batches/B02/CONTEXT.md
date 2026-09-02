# B02 Context Manifest

```yaml
batch: B02
status: Accepted/Frozen
approved_at: 2026-09-02
gate_1_approval: user_explicit
implementation_commit: fede40d03bd4f7a21c87499a498b15a9a8581412
accepted_at: 2026-09-02
accepted_head: ae479f18f153d6c0159cabf28e0be4714f368233
gate_2_approval: user_explicit
base_commit: 2f846a06e9c6f6b399a4753ad32bd3b565fd5fff
planned_branch: batch/b02-raw-identity
depends_on:
  hard:
    - user_explicit_gate_1_approval
    - b00_accepted_frozen
    - b01_accepted_frozen
    - b01_contest_operations_and_http_contract_unchanged
    - python_3_11_16_uv_0_12_9_and_sqlite_3_53_1
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484_unchanged
  soft:
    - organizer_model_api_and_keys
    - organizer_hardware_timeout_concurrency_failure_policy
    - organizer_compose_network_build_constraints
    - memos_provider_cube_id_constraints
    - finals_delivery_requirements
  experimental: []
required_reading:
  P0:
    - path: docs/batches/B02/PLAN.md
      range: complete_file
      reason: proposed B02 scope, Schema, interfaces, transactions, tests and approval points
      authority: current_batch_gate_1
    - path: docs/batches/B02/CONTEXT.md
      range: complete_file
      reason: authoritative context and allowed-change manifest
      authority: current_batch_gate_1
    - path: docs/batches/B01/HANDOFF.md
      range: complete_file
      reason: frozen upstream application port, HTTP invariants and limitations
      authority: accepted_upstream_batch
    - path: docs/interfaces/contest-http-v1.md
      range: complete_file
      reason: exact Add identity, sync and default unavailable boundary
      authority: accepted_external_interface
    - path: MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
      range: sections_2_7_2_8_9_11_12_16_18_19
      reason: Raw D04-A, user/cube, consistency, health, configuration and quality gates
      authority: current_project_plan
    - path: src/memscope/operations.py
      range: complete_file
      reason: frozen AddCommand input and future application integration boundary
      authority: accepted_b01_code
    - path: src/memscope/settings.py
      range: complete_file
      reason: centralized configuration and safe summary to extend
      authority: accepted_b01_code
    - path: src/memscope/logging_config.py
      range: complete_file
      reason: fixed allowlist logging boundary to extend without content leakage
      authority: accepted_b00_b01_code
    - path: pyproject.toml
      range: complete_file
      reason: Python, dependency and test constraints; dependency changes forbidden
      authority: repository_configuration
    - path: tests/contract/test_contest_api.py
      range: complete_file
      reason: preserve B01 contract and default unavailable regression behavior
      authority: accepted_b01_tests
  P1:
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/api_contract.md
      range: add_and_identity_sections
      reason: request_id uniqueness, exact IDs, message order and synchronous Add rules
      authority: current_contest_contract_reconstruction
    - path: 技术难题-Agent-Memory-任务书-1.0.md
      range: sections_1_2_3_5
      reason: persistence, sync visibility, isolation and compliance requirements
      authority: contest_task
    - path: 技术难题-Agent-Memory-调测指南-1.0.md
      range: contract_smoke_and_common_failures
      reason: repeated chunks, restart and cross-user failure expectations
      authority: contest_debugging_guide
    - path: docs/adr/0002-contest-adapter-boundary.md
      range: complete_file
      reason: preserve HTTP-to-application dependency direction
      authority: accepted_architecture_decision
    - path: docs/CODEMAP.md
      range: complete_file
      reason: current module ownership and dependency direction
      authority: current_project_navigation
    - path: .gitignore
      range: complete_file
      reason: confirm DB/WAL/SHM runtime artifacts remain excluded
      authority: repository_configuration
    - path: .env.example
      range: complete_file
      reason: synchronize safe database configuration examples
      authority: repository_configuration
  P2:
    - path: .vendor-src/MemOS
      range: targeted_cube_id_validation_only_if_B05_constraint_is_pulled_forward
      reason: B02 logical IDs do not normally require upstream source
      authority: fixed_upstream_source
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/official/manifest.json
      range: metadata_only_if_scale_assumption_is_challenged
      reason: estimate local row counts without loading questions or samples
      authority: local_proxy_metadata_not_official_byte_verified
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
  - .env.example
  - README.md
  - src/memscope/settings.py
  - src/memscope/logging_config.py
  - src/memscope/raw_store/**
  - tests/support.py
  - tests/unit/test_settings.py
  - tests/unit/test_logging_config.py
  - tests/unit/test_raw_identity.py
  - tests/unit/test_raw_models.py
  - tests/component/test_raw_store_migrations.py
  - tests/component/test_sqlite_raw_store.py
  - docs/PROJECT_CONTEXT.md
  - docs/CODEMAP.md
  - docs/interfaces/raw-store-v1.md
  - docs/adr/0003-sqlite-raw-store-and-idempotency.md
  - docs/batches/B02/PLAN.md
  - docs/batches/B02/CONTEXT.md
  - docs/batches/B02/HANDOFF.md
required_tests:
  - uv_lock_check_offline_and_unchanged
  - ruff_format_check
  - ruff_lint
  - mypy_strict
  - pytest_unit_component_contract_and_smoke
  - total_coverage_at_least_95_percent
  - b02_statement_coverage_at_least_95_percent
  - b02_branch_coverage_at_least_90_percent
  - canonical_payload_and_identity_golden_vectors
  - migration_new_reopen_concurrent_future_checksum_and_rollback
  - sqlite_wal_full_foreign_keys_busy_timeout_and_schema_version
  - prepare_add_atomic_request_messages_cube_and_outbox
  - same_payload_pending_and_completed_replay_without_side_effects
  - different_payload_conflict_preserves_original_state
  - complete_add_atomic_and_idempotent_state_transition
  - multi_chunk_session_order_and_cross_user_isolation
  - restart_recovers_all_persisted_state
  - concurrent_request_and_cube_uniqueness
  - transaction_failure_rolls_back_without_orphans
  - locked_closed_and_corrupt_store_safe_errors
  - b01_http_contract_and_default_503_regression
  - minimal_uvicorn_start_and_clean_shutdown
  - raw_store_local_latency_and_size_report
open_decisions:
  - approve_raw_store_only_scope_and_default_http_503
  - approve_stdlib_sqlite_async_to_thread_with_per_operation_connections_without_new_dependency
  - approve_canonical_add_v1_and_full_sha256
  - approve_new_pending_completed_and_typed_conflict_idempotency_semantics
  - approve_http_409_mapping_deferred_until_operations_integration
  - approve_versioned_logical_cube_and_message_ids
  - approve_session_position_by_transaction_commit_order
  - approve_schema_v1_tables_composite_consistency_constraints_indexes_and_statuses
  - approve_prepare_complete_transactions_and_consistency_boundary
  - approve_durable_outbox_without_worker_lease_or_retry
  - approve_embedded_forward_only_checksum_migrations
  - approve_database_path_busy_timeout_wal_full_and_foreign_keys
  - approve_to_thread_cancellation_semantics
  - approve_no_fts_gateway_http_success_or_official_samples
  - approve_no_dependency_lockfile_or_b01_frozen_code_changes
  - approve_allowed_change_scope_and_test_matrix
  - approve_branch_creation_and_implementation_only_after_gate_1
```

## 使用规则

- B02 实施前必须重新核验 `base_commit`、工作区、B00/B01 状态和 MemOS 固定版本；
- Gate 1 批准后才创建 `batch/b02-raw-identity`，Draft 状态不得编写 Raw Store 代码；
- P0 完整读取项为 10 个；P1/P2 只能按标注范围定向读取；
- 当前 `official/` 仅是本地规则重建与代理回归集，不是主办方字节级正式包；
- 所有测试数据库只能写系统临时目录；不得读取、迁移或删除用户真实数据库；
- 若 P0、hard dependency、RawStore 公共接口、Schema/算法/事务、依赖或允许范围变化，本 Manifest 失效；
- P2 只有在具体约束被拉入 B02 时读取，并必须先判断是否触发重新 Gate 1；
- B02 不读取正式题目、gold、样本内容或完整 MemOS 源码，不执行代理评分，不进入 B03。

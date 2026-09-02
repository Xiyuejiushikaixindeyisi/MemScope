# B01 Context Manifest

```yaml
batch: B01
status: Code Review
approved_at: 2026-09-02
gate_1_approval: user_explicit
implementation_commit: 160a46cbbd62dcc9d1aa34bf80f36459541b9d1c
base_commit: 714e5581104cd84a41cbb05d46a12e89ae10cdda
planned_branch: batch/b01-api-contract
depends_on:
  hard:
    - user_explicit_gate_1_approval
    - b00_accepted_frozen
    - b00_public_interfaces_unchanged
    - python_3_11_16_and_uv_0_12_9_toolchain
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484_unchanged
  soft:
    - organizer_model_api_and_keys
    - organizer_hardware_timeout_concurrency_failure_policy
    - organizer_compose_network_build_constraints
    - finals_delivery_requirements
  experimental: []
required_reading:
  P0:
    - path: docs/batches/B01/PLAN.md
      range: complete_file
      reason: proposed B01 scope, interfaces, semantics, tests and approval points
      authority: current_batch_gate_1
    - path: docs/batches/B01/CONTEXT.md
      range: complete_file
      reason: authoritative context and allowed-change manifest
      authority: current_batch_gate_1
    - path: docs/batches/B00/HANDOFF.md
      range: complete_file
      reason: frozen upstream public interfaces, invariants and limitations
      authority: accepted_upstream_batch
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/api_contract.md
      range: complete_file
      reason: Add, Search, Health, authentication and success-shape contract
      authority: current_contest_contract_reconstruction
    - path: MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
      range: sections_2_4_11_12_16_18_19
      reason: adapter boundary, readiness, configuration, testing and collaboration gates
      authority: current_project_plan
    - path: src/memscope/app.py
      range: complete_file
      reason: frozen application factory to extend compatibly
      authority: accepted_b00_code
    - path: src/memscope/settings.py
      range: complete_file
      reason: frozen centralized Settings and safe-summary behavior
      authority: accepted_b00_code
    - path: src/memscope/errors.py
      range: complete_file
      reason: frozen transport-independent base error contract
      authority: accepted_b00_code
    - path: src/memscope/logging_config.py
      range: complete_file
      reason: fixed log allowlist and redaction boundary to extend
      authority: accepted_b00_code
    - path: tests
      range: existing_B00_unit_and_smoke_files_only
      reason: preserve frozen behavior and intentionally replace the contest-route 404 assertion
      authority: accepted_b00_tests
  P1:
    - path: 技术难题-Agent-Memory-任务书-1.0.md
      range: sections_1_2_3_5_7
      reason: sync Add, evidence-only Search, evaluation flow and compliance boundaries
      authority: contest_task
    - path: 技术难题-Agent-Memory-调测指南-1.0.md
      range: unified_interface_and_contract_smoke_sections
      reason: evaluator-facing Smoke behavior and common protocol failures
      authority: contest_debugging_guide
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/schema/sample.schema.json
      range: complete_file
      reason: role, content, timestamp and options source-shape compatibility
      authority: local_reconstructed_sample_schema
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/scripts/smoke_curl.sh
      range: complete_file
      reason: exact public Smoke request construction
      authority: local_reconstructed_smoke_client
    - path: pyproject.toml
      range: complete_file
      reason: existing dependency and quality-tool constraints; no dependency change allowed
      authority: repository_configuration
    - path: .env.example
      range: complete_file
      reason: keep Settings documentation synchronized without secrets
      authority: repository_configuration
    - path: docs/CODEMAP.md
      range: complete_file
      reason: preserve dependency direction and B01 ownership
      authority: current_project_navigation
  P2:
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/official/manifest.json
      range: metadata_only
      reason: only if a contract choice is challenged by reconstructed pack metadata
      authority: local_proxy_metadata_not_official_byte_verified
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/scripts/smoke_curl.ps1
      range: complete_file_only_if_cross_platform_request_difference_appears
      reason: compare Windows Smoke construction when needed
      authority: local_reconstructed_smoke_client
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
  - src/memscope/app.py
  - src/memscope/settings.py
  - src/memscope/logging_config.py
  - src/memscope/operations.py
  - src/memscope/api/**
  - tests/conftest.py
  - tests/support.py
  - tests/smoke/test_minimal_app.py
  - tests/unit/test_app.py
  - tests/unit/test_settings.py
  - tests/unit/test_logging_config.py
  - tests/unit/test_api_auth.py
  - tests/unit/test_api_errors.py
  - tests/unit/test_api_models.py
  - tests/unit/test_operations.py
  - tests/contract/test_contest_api.py
  - docs/PROJECT_CONTEXT.md
  - docs/CODEMAP.md
  - docs/interfaces/contest-http-v1.md
  - docs/adr/0002-contest-adapter-boundary.md
  - docs/batches/B01/PLAN.md
  - docs/batches/B01/CONTEXT.md
  - docs/batches/B01/HANDOFF.md
required_tests:
  - uv_lock_check_offline_and_unchanged
  - ruff_format_check
  - ruff_lint
  - mypy_strict
  - pytest_unit_contract_and_smoke
  - total_coverage_at_least_95_percent
  - b01_statement_coverage_at_least_95_percent
  - b01_branch_coverage_at_least_90_percent
  - add_exact_echo_and_waits_for_completion
  - search_envelope_order_empty_and_top_k_bound
  - health_ready_200_and_unavailable_503
  - strict_validation_and_safe_error_mapping
  - auth_none_bearer_token_x_api_key_and_rejection_paths
  - key_body_query_and_content_absent_from_logs_and_errors
  - default_runtime_has_no_false_success
  - minimal_uvicorn_start_and_clean_shutdown
  - adapter_local_latency_report
open_decisions:
  - approve_b01_scope_and_contest_operations_boundary
  - approve_default_unavailable_without_runtime_fake
  - approve_strict_types_preserve_strings_and_ignore_extra_input_fields
  - approve_nonempty_messages_top_k_1_to_100_and_open_role_values
  - approve_search_preserve_order_and_safety_truncate_only
  - approve_none_or_shared_key_auth_with_three_mutually_exclusive_carriers
  - approve_safe_http_error_envelope_and_status_mapping
  - approve_no_timeout_retry_degradation_idempotency_or_recovery_in_b01
  - approve_http_log_allowlist_without_business_identifiers_or_content
  - approve_no_dependency_or_lockfile_changes
  - approve_allowed_change_scope_and_test_matrix
  - approve_branch_creation_and_implementation_only_after_gate_1
```

## 使用规则

- B01 实施前必须重新核验 `base_commit`、工作区、B00 状态及 MemOS 固定版本；
- Gate 1 批准后才创建 `batch/b01-api-contract`，不得在当前 Draft 状态编写业务代码；
- P0 完整读取项为 10 个，实施不得把 P1/P2 擅自升级为全仓读取；
- 当前 `official/` 仅是本地规则重建与代理回归集，不是主办方字节级正式包；
- 测试替身只允许存在于 `tests/`，不得作为 `memscope.main:app` 的成功默认实现；
- 若 P0、hard dependency、公共 HTTP/内部接口、依赖或允许修改范围变化，本 Manifest 失效并重新评审；
- P2 只在具体问题出现时定向读取，并在 Gate 2 HANDOFF 记录原因；
- B01 不读取正式问题、gold 或样本内容，不执行代理评分，不进入 B02。

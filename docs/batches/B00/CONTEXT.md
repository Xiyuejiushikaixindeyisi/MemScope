# B00 Context Manifest

```yaml
batch: B00
status: Code Review
base_commit: 4a57925aaee6559fe9c48d174357861c8a8a10d4
working_tree_context:
  - path: MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
    state: committed
    commit: 099e659447680eac973bc8efc20e05ece9f4078d
    reason: user-requested finals extensibility constraints and organizer-confirmation checklist
depends_on:
  hard:
    - user_explicit_gate_1_approval
    - python_3_11_toolchain_before_implementation_tests
    - memos_v2_0_32_commit_185ebdb925911b55c13b7efe666b74e2e292e484_unchanged
  soft:
    - organizer_model_api_and_keys
    - organizer_hardware_timeout_concurrency_failure_policy
    - organizer_compose_network_build_constraints
    - finals_delivery_requirements
  experimental: []
required_reading:
  P0:
    - path: docs/batches/B00/PLAN.md
      range: complete_file
      reason: approved B00 scope, interfaces, tests and completion criteria
      authority: current_batch_gate_1
    - path: docs/batches/B00/CONTEXT.md
      range: complete_file
      reason: authoritative context and allowed-change manifest
      authority: current_batch_gate_1
    - path: MEMOS_BASELINE_IMPLEMENTATION_PLAN.md
      range: sections_1_3_4_12_16_18_19
      reason: project constraints, toolchain, configuration, quality gates and context workflow
      authority: current_project_plan
    - path: .gitignore
      range: complete_file
      reason: preserve secret, runtime-data, cache and upstream-source exclusions
      authority: repository_configuration
    - path: .vendor-src/MemOS/pyproject.toml
      range: complete_file
      reason: Python compatibility and dependency alignment for fixed MemOS version
      authority: fixed_upstream_source
    - path: .vendor-src/MemOS/LICENSE
      range: complete_file
      reason: redistribution and attribution obligations
      authority: fixed_upstream_license
    - path: .vendor-src/MemOS/README.md
      range: quick_start_self_host_docker_uvicorn_sections_only
      reason: later deployment boundary and single-worker upstream entry point
      authority: fixed_upstream_documentation
  P1:
    - path: 技术难题-Agent-Memory-任务书-1.0.md
      range: technical_requirements_and_delivery_sections
      reason: ensure foundation remains deployable and submission-compatible
      authority: contest_task
    - path: 技术难题-Agent-Memory-评测集（开源）-1.0/api_contract.md
      range: endpoint_names_and_health_only
      reason: prevent B00 from accidentally claiming B01 contract ownership
      authority: contest_contract
  P2:
    - path: .vendor-src/MemOS/poetry.lock
      range: selected_direct_package_blocks_only
      reason: verify proposed version alignment if dependency resolution disagrees
      authority: fixed_upstream_lock
    - path: .vendor-src/MemOS/docker/docker-compose.yml
      range: only_if_B00_assumption_about_process_boundary_is_challenged
      reason: B04 concern; not needed for normal B00 implementation
      authority: fixed_upstream_configuration
do_not_load:
  - docs/achieve/**
  - 技术难题-Agent-Memory-评测集（开源）-1.0/official/questions.jsonl
  - 技术难题-Agent-Memory-评测集（开源）-1.0/official/samples/**
  - complete_formal_samples
  - complete_MemOS_source_tree
  - historical_chat_records
  - unrelated_MemOS_plugins_frontend_and_memory_types
allowed_changes:
  - .gitignore
  - .python-version
  - .env.example
  - README.md
  - pyproject.toml
  - uv.lock
  - src/memscope/**
  - tests/**
  - docs/PROJECT_CONTEXT.md
  - docs/CODEMAP.md
  - docs/adr/0001-python-toolchain-and-layout.md
  - docs/batches/B00/PLAN.md
  - docs/batches/B00/CONTEXT.md
  - docs/batches/B00/HANDOFF.md
required_tests:
  - uv_sync_frozen_on_python_3_11
  - ruff_format_check
  - ruff_lint
  - mypy_strict
  - pytest_unit_and_smoke
  - statement_coverage_at_least_95_percent
  - branch_coverage_at_least_90_percent
  - invalid_configuration_fails_before_ready
  - structured_logging_is_idempotent_and_redacted
  - minimal_uvicorn_start_and_clean_shutdown
  - contest_routes_remain_unimplemented
open_decisions:
  - approve_python_3_11_src_layout_and_uv_uv_build_0_12_9
  - approve_proposed_direct_dependency_versions
  - approve_stdlib_json_logging
  - approve_minimal_settings_surface
  - approve_no_health_route_until_B01
  - approve_coverage_and_type_check_gates
  - approve_B00_file_change_scope
  - approve_branch_creation_and_dependency_setup_only_after_gate_1
```

## 使用规则

- B00 实施开始前必须重新核验 `base_commit`、工作区和 MemOS 固定版本；
- 当前 `base_commit` 之后的工作区文档修改属于本轮用户明确要求，不代表 B00 已获编码批准；
- Gate 1 批准后，先创建 `batch/b00-engineering-foundation`，再准备工具链和代码；
- 若 P0、hard dependency、公共接口、依赖版本或允许修改范围变化，本 Manifest 失效并重新评审；
- P2 只在出现明确问题时定向读取，并在 HANDOFF 记录新增上下文；
- B00 不读取正式题目或样本内容，不以代理数据驱动工程基础设计。

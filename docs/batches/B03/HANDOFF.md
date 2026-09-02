# B03 Gate 2 Handoff

> 状态：Accepted/Frozen，2026-09-02 用户已完成 Gate 2 验收
> Gate 1 文档提交：`f964c34`
> 实现提交：`2590adc`
> 测试提交：`1465938`
> 分支：`batch/b03-no-key-doubles`
> 日期：2026-09-02

## 1. 交付能力

B03 已交付两个互相独立的无 Key 替身层：

- framework-independent async `MemoryGateway` v1、严格 frozen DTO 和安全 typed errors；
- 非持久、asyncio-safe、exact-idempotent 的 `FakeMemoryGateway`；
- `MemoryOperations` 对 B02 RawStore 的 NEW/PENDING/COMPLETED 编排；
- Raw conflict → application `RequestConflictError` → HTTP 409；
- Search logical Cube 推导、user/Cube provenance 二次隔离和 evidence 映射；
- 独立可启动的 OpenAI-shaped Chat/Embedding Mock Model ASGI API；
- 跨进程稳定的 `mock-sha256-vector-v1` embedding；
- Gateway typed faults 及 Mock 429/500/timeout/invalid JSON/dimension mismatch；
- reusable Gateway contract、显式 Fake 完整 HTTP 路径和两个真实 Uvicorn process smoke。

默认 `memscope.main:app` 未接入 Fake 或 Raw Store，Health/Add/Search 仍明确返回 503。

## 2. 实现位置与依赖方向

| 能力 | 位置 |
|---|---|
| Gateway DTO/errors/port | `src/memscope/memory_gateway/{models,errors,protocol}.py` |
| deterministic Fake | `src/memscope/memory_gateway/fake.py` |
| Raw + Gateway application orchestration | `src/memscope/application/memory_operations.py` |
| application conflict / HTTP 409 | `src/memscope/operations.py`、`api/{errors,routes}.py` |
| Mock HTTP models/app/entry point | `src/memscope/mock_model_api/` |
| reusable Gateway behavior suite | `tests/contract/memory_gateway_contract.py` |
| Fake/application/Mock tests | `tests/{unit,contract,smoke}/test_*gateway*`、`test_*memory*`、`test_mock_*` |
| frozen contracts and decision | `docs/interfaces/memory-gateway-v1.md`、`mock-model-api-v1.md`、ADR 0004 |

Adapter depends on `ContestOperations`; `MemoryOperations` depends only on RawStore and
MemoryGateway ports. Gateway core has no FastAPI/Pydantic/SQLite/HTTPX/MemOS dependency. Mock Model
API is independent from RawStore, application and Fake state.

## 3. Add/Search guarantees

Add state handling:

- NEW/PENDING build the same stable Gateway request, await Gateway success, then complete Raw state;
- COMPLETED validates the stored exact response and performs no Gateway call;
- Raw conflict becomes sanitized non-retryable 409;
- Gateway failure leaves Raw pending; same-ID retry was verified to complete with one evidence item;
- B03 does not automatically retry, scan pending outbox or hide an error as success.

Search derives the B02 logical Cube from exact user ID, requests evidence rather than answers,
drops foreign user/Cube provenance, preserves provider order, and truncates to `top_k`. It neither
filters by session nor selects options.

## 4. Fake and Mock boundaries

Fake Search uses the explicitly named `fake-token-overlap-v1`; it only proves wiring, order,
visibility, idempotency and isolation. It is process-local, non-durable and cannot support proxy
quality scoring, lifecycle semantics or a baseline release.

Mock Model v1 supports only health, non-streaming Chat completions and string/string-array
Embeddings. Unknown common request fields are ignored; streaming, tools, token arrays and Rerank
are absent. Default Chat content and embedding dimension are test fixtures, not verified MemOS
requirements. Fault injection is a test-only allowlisted internal header and is never wired into the
default runtime.

## 5. 测试与质量结果

执行环境：CPython 3.11.16、SQLite 3.53.1、Linux x86_64、既有 B00 `.venv`。

| 门禁 | 结果 |
|---|---|
| `uv lock --check --offline` | 通过，32 packages；lock 未变化 |
| `ruff format --check .` | 通过 |
| `ruff check .` | 通过 |
| `mypy src tests` | 通过，58 source files |
| `pytest` | 通过，318 passed，6.01 s |
| 总体语句覆盖率 | 1461/1486，98.32% |
| 总体分支覆盖率 | 333/340，97.94% |
| coverage.py 综合覆盖率 | 98.25% |
| B03 新模块语句覆盖率 | 546/552，98.91% |
| B03 新模块分支覆盖率 | 126/126，100% |

覆盖的关键行为包括严格模型、request/message conflict、并发 exact replay、user/Cube 隔离、
NEW/PENDING/COMPLETED、malicious provenance、Gateway/complete failure、取消传播、pending 重试
收敛、HTTP 409、Mock deterministic/golden/faults、默认 503 和真实进程干净关闭。

测试只写 temporary directory 和临时 localhost port；未使用 Key、外网、正式样本、完整 MemOS 源码
或代理评分。

## 6. 本机分段延迟

测量方式：每 case 30 samples，warm local run；SQLite WAL + FULL，Fake 进程内；Mock 使用
HTTPX ASGI transport。数值不是正式硬件/SLA、真实 MemOS/模型延迟或 CI hard assertion。

### 6.1 Raw/Fake/application

| messages | segment | P50 | P95 | P99 |
|---:|---|---:|---:|---:|
| 1 | Raw prepare / Gateway add / Raw complete / application Add / Gateway Search | 7.712 / 0.026 / 6.992 / 14.745 / 0.138 ms | 10.891 / 0.049 / 10.992 / 20.297 / 0.231 ms | 18.734 / 0.108 / 23.676 / 33.382 / 0.296 ms |
| 20 | Raw prepare / Gateway add / Raw complete / application Add / Gateway Search | 10.146 / 0.051 / 7.359 / 18.893 / 0.620 ms | 20.479 / 0.116 / 17.181 / 27.291 / 2.745 ms | 20.559 / 0.138 / 18.152 / 34.302 / 2.966 ms |
| 100 | Raw prepare / Gateway add / Raw complete / application Add / Gateway Search | 11.266 / 0.110 / 6.187 / 19.451 / 3.034 ms | 25.731 / 0.290 / 10.883 / 39.311 / 11.322 ms | 33.889 / 0.354 / 14.031 / 44.228 / 14.742 ms |

Search case 在先前 30 次写入的累积候选上测量，因此 100-message case 包含 3000 条 Fake evidence
扫描；该线性行为是测试 Fake 的已知限制，不代表未来 Real Gateway 策略。

### 6.2 Mock endpoints

| items/messages | Chat P50 / P95 / P99 | Embeddings P50 / P95 / P99 |
|---:|---:|---:|
| 1 | 0.284 / 0.407 / 1.538 ms | 0.289 / 0.388 / 0.984 ms |
| 20 | 0.303 / 0.358 / 0.396 ms | 0.520 / 0.592 / 0.644 ms |
| 100 | 0.438 / 0.689 / 0.722 ms | 1.519 / 2.180 / 2.880 ms |

## 7. 安全、依赖与固定上游

- `pyproject.toml`、`uv.lock` 未变化，无安装或新增依赖；
- MemOS 仍为 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`；
- 未修改 B02 RawStore Schema、migration、canonical payload 或 ID 算法；
- 未修改 app/main/Profile/Compose，未创建默认数据库；
- 日志 allowlist 可记录 bounded component/endpoint/result/duration/error 字段，不记录 ID、内容、
  query、model、prompt/input、vector、fault header、DB path 或底层异常文本；
- Fake/Mock 错误只暴露稳定 code/message/retryable，不携带 provider/body 细节。

## 8. 偏差与实现期强化

无批准范围、依赖、默认 composition、RawStore contract 或比赛 HTTP 成功响应偏差。

实现期有一项 additive 可观测性澄清：`MemoryOperations` 总耗时使用
`component_duration_ms`，Fake Gateway 自身耗时使用 `gateway_duration_ms`，避免分段性能误标；PLAN
第 14 节已同步。Gateway/application 的 typed failure 也统一输出安全 `failed` result 和 error code。

受限 Codex sandbox 对 `asyncio.to_thread`/localhost 的限制沿用 B02 已记录环境条件；SQLite、全量测试
和 process smoke 均在获批的正常执行环境通过。这不是产品代码失败。

## 9. 已知限制与后续依赖

- 没有 Real MemOS Gateway、真实 Chat/Embedding/Rerank 兼容性或 baseline-v0；
- Fake restart 后不会恢复已完成的外部 evidence；它不得用于提交候选；
- PENDING 只有 evaluator same-ID retry 可被动恢复，B07 才实现主动 worker/lease/backoff/readback；
- 无 Update/Forget/Reflect 执行语义、current-effective lifecycle、FTS/fusion/rerank/fallback；
- 无生产 timeout/retry/concurrency/degradation 参数；
- 默认 runtime 仍 503，B04 才设计运行服务 topology/lifecycle；
- 主办方 API/Key、硬件/超时/并发/失败策略、Compose/网络/构建和决赛交付要求仍未知。

## 10. Gate 2 验收结论

用户于 2026-09-02 明确批准 B03 Gate 2 验收，B03 更新为 `Accepted/Frozen`。后续可以依赖
`memory-gateway-v1.md`、`mock-model-api-v1.md` 和本 Handoff 明示的公共边界，但不得把 Fake/Mock
结果解释为真实 MemOS 兼容性或 baseline 质量证据。本次验收未授权 B04 方案或代码实施。

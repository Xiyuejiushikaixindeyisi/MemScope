# B03 无 Key 双层替身代码方案

> 状态：Code Review / Gate 2 Pending，2026-09-02 Gate 1 已批准
> Batch：B03
> 基线提交：`a7822047640cac26a46e25663be9b60542f7d47b`
> 实施分支：`batch/b03-no-key-doubles`
> 方案依据：B01/B02 `Accepted/Frozen` 交接、`contest-http-v1.md`、`raw-store-v1.md`，以及
> `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md` 第 2、5、6、7.2～7.5、8.4、9～12、16～19 节
> 边界：本次批准仅授权 B03，不授权进入 B04

## 1. 目标

B03 建立两个彼此独立的无 Key 替身层，并首次验证 Adapter→application→RawStore→Gateway 完整接线：

1. 定义 framework-independent async `MemoryGateway` v1 端口、严格 DTO 和安全 typed errors；
2. 实现进程内 `FakeMemoryGateway`，确定性保存消息、幂等处理 Add、按 user/cube 隔离 Search；
3. 实现 `MemoryOperations`，组合 B01 `ContestOperations`、B02 `RawStore` 和 Gateway；
4. 明确处理 RawStore NEW/PENDING/COMPLETED，并以 Gateway 幂等重放收敛 pending；
5. 将 B02 `IdempotencyConflictError` 转换为应用层 `RequestConflictError` 并映射 HTTP 409；
6. 在显式注入的 Fake 测试 app 中验证 Health 200、同步 Add、立即 Search 和 exact replay；
7. 定义可由未来 Fake/Real Gateway 共用的行为契约测试；
8. 提供独立、可启动的 Mock Model ASGI API，覆盖 Chat/Embedding 的 OpenAI-shaped 最小子集；
9. 使用 SHA-256 生成跨进程稳定的确定性 embedding，不使用 Python randomized `hash()`；
10. 为 Fake Gateway 和 Mock Model API 提供显式、可测试的 429/5xx/timeout/protocol 故障分类；
11. 证明两个替身可以独立定位“MemScope 编排接线问题”和“模型 HTTP 协议问题”；
12. 保持无外网、无 Key、无 MemOS/Qdrant/Neo4j、无新增依赖的完整测试路径；
13. 保持默认 `memscope.main:app` 未组装后端时 Health/Add/Search 继续 503。

## 2. 非目标

B03 明确不实现：

- Real MemOS Gateway、MemOS REST 调用或固定源码映射；
- MemOS user/Cube 创建、ACL、provider Cube ID 校验或真实字段转换；
- Qdrant、Neo4j、Docker、Compose、持久卷或 service health dependency；
- 将 Fake Gateway 或 Mock Model API 装入 organizer/baseline 候选；
- `APP_PROFILE=mock` 的生产 Composition/lifespan；B04/B05 再组装真实服务栈；
- 修改 B02 Schema、migration、canonical payload、ID 算法或事务语义；
- durable outbox worker、lease、attempt、后台恢复、自动 retry 或 readback；
- Raw FTS、fallback、RRF、rerank、去重、状态过滤或生命周期执行；
- Update、Forget、Reflect 的业务语义或质量判断；
- 真实模型结构化抽取 Schema；默认 Mock Chat 内容不代表 MemOS 可消费的最终 Schema；
- 完整 OpenAI API、流式输出、tool calls、token arrays、batch、audio/image 或 tokenizer 计费；
- Rerank endpoint；仅在 B05 对固定 MemOS 源码确认必需后设计；
- 正式样本、代理评分、Chat/Embedding/Rerank Key 或语义质量验证；
- 正式超时、重试、熔断、降级、并发或提交部署参数冻结；
- B04 及以后 Batch 的代码。

## 3. 前置条件与依赖

### 3.1 Hard dependencies

- 用户明确批准本 Gate 1 方案；
- B00、B01、B02 均为 `Accepted/Frozen`；
- B01 Contest HTTP/`ContestOperations` 和 B02 RawStore v1 不变量保持不变；
- 实施前 MemScope HEAD、工作区和基线仍与本文一致；
- MemOS 保持 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`；B03 不读取或修改其源码；
- 继续使用 CPython 3.11.16、uv 0.12.9、SQLite 3.53.1 和现有锁文件；
- 现有 FastAPI/Pydantic/HTTPX 已足够实现 Mock API 和契约测试。

### 3.2 Soft dependencies

以下缺失不阻塞 B03：

- 主办方 Chat/Embedding/Rerank API 与 Key；
- 正式硬件、请求/整轮超时、并发和失败策略；
- Compose、网络和构建限制；
- 固定 MemOS 的实际 Chat/Embedding 请求细节和结构化抽取 Schema；
- Rerank 是否为固定 MemOS 路径必需；
- 决赛交付要求。

Mock Model v1 只冻结一个明确标注的测试子集；B05 首次定向建立 MemOS 源码映射后，若协议不匹配，
通过 additive endpoint/model fields 或新版本接口演进，不把 B03 Mock 结果解释为真实接线成功。

## 4. 边界冲突、模糊点与本方案取值

| 模糊点 | B03 取值 | 理由 |
|---|---|---|
| B03 是否改变默认 HTTP 为可用 | 不改变；只有显式注入 `MemoryOperations` 的测试 app 为 200，`memscope.main` 仍 503 | 尚无持久真实 Memory Gateway，避免 Fake 进入默认/提交候选 |
| PENDING replay 如何处理 | 重新调用幂等 Gateway，再执行 `complete_add` | 首次调用可能在 Gateway 成功后崩溃；不能把 pending 当成功，也不能永久卡死 |
| COMPLETED replay 是否再调 Gateway | 不调用，直接接受 RawStore 已保存成功响应 | 维持 B02 replay 语义，避免正常路径重复外部 I/O |
| Fake 重启后 completed Raw 仍在但 Fake 丢失 | 明确不支持 Fake 跨进程恢复；Fake 只用于单进程接线测试 | 假装内存 Fake durable 会掩盖真实 MemOS/恢复问题 |
| HTTP 409 应在哪层映射 | application 捕获 B02 conflict 并抛 `RequestConflictError`；API 只依赖 application error | 避免 API→SQLite/RawStore 反向依赖 |
| Gateway 是否暴露 provider HTTP/业务 code | 不暴露；统一成 typed transport-independent errors | Fake/Real 共享稳定契约，具体 HTTP 解析留 Real Gateway |
| Gateway 是否单独 `create_cube` | v1 不单列；`add()` 对所给 user/cube 的 ensure/create/write 负责 | B03 无 provider lifecycle；B05 可在 Real 实现内部组装并以契约验证结果 |
| Search 如何取得 Cube | 使用 B02 冻结的 `cube_id_for_user(user_id)` 计算 expected logical cube | B02 v1 没有 lookup API；逻辑 ID 可确定推导，provider 映射以后 additive 演进 |
| Fake Search 是否代表质量 | 不代表；使用命名的 `fake-token-overlap-v1` 确定性规则 | 只验证 query/隔离/order/top_k/格式，不作为 LoCoMo/MemOps 证据 |
| Fake 如何模拟非法 JSON/429 | 高层 Fake 抛等价 typed failure；实际畸形 JSON 由 Mock HTTP API 直接返回 | 不把 HTTP 细节泄漏进 Gateway interface |
| Mock API 是否完整 OpenAI-compatible | 否，明确为 OpenAI-shaped v1 subset | 当前尚未核验 MemOS client 全部字段，避免过度承诺 |
| Mock Chat 默认返回什么 | 合法 chat envelope，content 为固定 canonical `{"memories":[]}`，app factory 可注入其它合法 JSON string | 验证 HTTP envelope；B05 依据真实 prompt Schema 冻结可消费 fixture |
| Mock 故障控制如何暴露 | 仅内网测试 header `X-MemScope-Mock-Failure`，值为 allowlist | 无管理状态、无 query/content 魔法；organizer profile 永不包含 Mock |
| timeout 是否真等待 | Mock 使用短、构造参数限定的 delay；客户端以更短 timeout 验证 | 可测试真实取消/timeout，不引入长时间阻塞 |
| Rerank | B03 不实现，未知路径请求明确 404 | 主计划只要求固定 MemOS 必需时实现，当前无依据冻结协议 |

## 5. 预计文件与允许修改范围

### 5.1 Gate 1 当前只新增

- `docs/batches/B03/PLAN.md`
- `docs/batches/B03/CONTEXT.md`

### 5.2 Gate 1 批准后预计新增

```text
src/memscope/
├── application/
│   ├── __init__.py
│   └── memory_operations.py
├── memory_gateway/
│   ├── __init__.py
│   ├── errors.py
│   ├── fake.py
│   ├── models.py
│   └── protocol.py
└── mock_model_api/
    ├── __init__.py
    ├── app.py
    ├── deterministic.py
    ├── main.py
    └── models.py
tests/
├── contract/
│   ├── memory_gateway_contract.py
│   ├── test_fake_gateway_contract.py
│   ├── test_memory_operations_http.py
│   └── test_mock_model_api.py
├── smoke/
│   ├── test_fake_memory_path.py
│   └── test_mock_model_process.py
└── unit/
    ├── test_fake_memory_gateway.py
    ├── test_gateway_models.py
    ├── test_memory_operations.py
    └── test_mock_model_deterministic.py
docs/
├── interfaces/
│   ├── memory-gateway-v1.md
│   └── mock-model-api-v1.md
├── adr/
│   └── 0004-two-layer-no-key-test-doubles.md
└── batches/B03/
    └── HANDOFF.md             # 仅在 Gate 2 交付时创建
```

### 5.3 Gate 1 批准后预计修改

- `src/memscope/operations.py`：additive `RequestConflictError` application error；不改既有 DTO/Protocol；
- `src/memscope/api/errors.py`：将 application conflict 映射为脱敏 409；
- `src/memscope/api/routes.py`：Add OpenAPI 增加 409 声明；
- `src/memscope/logging_config.py`：增加 bounded application/gateway/mock operation fields；
- `tests/contract/test_contest_api.py`、既有 unit tests：锁定 409、默认 503 和日志 allowlist 回归；
- `README.md`、`docs/PROJECT_CONTEXT.md`、`docs/CODEMAP.md`：记录 B03 组件和非默认组装边界；
- `docs/interfaces/contest-http-v1.md`：additive 409 契约说明；
- `docs/batches/B03/PLAN.md` / `CONTEXT.md`：只同步已批准修订和实际上下文。

### 5.4 明确不修改

- `pyproject.toml`、`uv.lock` 和依赖版本；
- `src/memscope/app.py`、`src/memscope/main.py`、AppProfile 和默认 composition；
- B02 `src/memscope/raw_store/**`、Schema、migration 和冻结接口；
- B00～B02 已接受的 Batch/ADR/interface（除上述 additive contest HTTP 409 文档）；
- `.vendor-src/MemOS/**`；
- `docs/achieve/**`、任务书、调测指南、评测集和 `official/**`；
- Docker/Compose/Qdrant/Neo4j、Real Gateway、FTS、worker 或正式模型配置；
- `.env.example`、`.env`、数据库、Key、日志、缓存或虚拟环境。

若实现必须越过范围，立即暂停并重新 Gate 1。

## 6. 模块职责与依赖方向

```text
Contest HTTP Adapter
        │ ContestOperations
        ▼
application.MemoryOperations
   ├── RawStore protocol ──────────> SqliteRawStore (B02)
   └── MemoryGateway protocol ─────> FakeMemoryGateway (B03)
                                      RealMemoryGateway (B05 future)

Mock Model API (independent ASGI process)
        ▲
        └── MemOS model client (B05 future; B03 does not connect it)
```

依赖约束：

- Gateway models/errors/protocol 不依赖 FastAPI、Pydantic、SQLite、HTTPX 或 MemOS；
- Fake 只依赖 Gateway contract 和 Python 标准库，不依赖 RawStore/FastAPI；
- `MemoryOperations` 依赖 B01 commands/evidence、RawStore protocol/identity 和 Gateway protocol；
- API 只依赖 application-level `RequestConflictError`，不导入 RawStore/SQLite errors；
- Mock Model API 可以依赖 FastAPI/Pydantic，但不得依赖 application、RawStore 或 Fake Gateway；
- Fake 和 Mock 不共享内存、故障状态或数据结构，避免一个替身掩盖另一个错误；
- Real Gateway 后续必须通过同一 reusable contract suite，不另建测试专用接口。

## 7. Memory Gateway v1 内部接口

计划提供 frozen dataclasses：

```python
GatewayMessage(
    message_id: str,
    request_position: int,
    role: str,
    content: str,
    timestamp_ms: int | None,
)

GatewayAdd(
    request_id: str,
    payload_sha256: str,
    user_id: str,
    session_id: str,
    cube_id: str,
    messages: tuple[GatewayMessage, ...],
)

GatewaySearch(
    query: str,
    user_id: str,
    cube_id: str,
    top_k: int,
    options: tuple[str, ...] | None,
)

GatewayEvidence(
    id: str,
    content: str,
    user_id: str,
    cube_id: str,
    score: float | None,
    created_at: datetime | None,
)

class MemoryGateway(Protocol):
    async def is_ready(self) -> bool: ...
    async def add(self, request: GatewayAdd) -> None: ...
    async def search(self, request: GatewaySearch) -> Sequence[GatewayEvidence]: ...
    async def close(self) -> None: ...
```

模型验证：ID/content/role 非空、positions 非负连续、digest 为 lowercase SHA-256、timestamp 为 exact
int-or-none、top_k 为 1～100、score finite、created_at timezone-aware、GatewayAdd message IDs 唯一。

计划错误：

| 类型 | code | retryable | 语义 |
|---|---|---:|---|
| `GatewayRateLimitedError` | `gateway.rate_limited` | true | 等价上游 429 |
| `GatewayUnavailableError` | `gateway.unavailable` | true | 等价连接/5xx/未就绪 |
| `GatewayTimeoutError` | `gateway.timeout` | true | 上游调用超时 |
| `GatewayProtocolError` | `gateway.protocol_invalid` | false | 业务失败/非法 JSON/结构 |
| `GatewayConflictError` | `gateway.request_conflict` | false | Gateway request ID 被不同内容复用 |

异常不携带 provider body、URL、ID、message、query 或底层错误文本。

## 8. FakeMemoryGateway 语义

- 进程内、非持久、asyncio-safe；用一个 lock 保护 Add/Search/close 状态快照；
- Add 以 request ID 和完整 frozen `GatewayAdd` 判断幂等：完全相同 no-op，不同内容 typed conflict；
- message ID 全局唯一；同一 exact duplicate 不重复，冲突的 message ID fail closed；
- 每条消息成为一条 active test evidence，保留 exact content、user、cube 和可选 timestamp；
- Search 只读取 exact user/cube，绝不按 session 过滤；
- `fake-token-overlap-v1`：Unicode casefold + `\w+` token，score 为 query unique tokens 的覆盖率；
- 只返回 score > 0 的消息，按 score descending、首次 ingestion sequence ascending 稳定排序；
- 最多返回 GatewaySearch.top_k；options 被接收但不选择答案或改变 v1 排序；
- timestamp_ms 转为 UTC datetime；缺失时 created_at=None，不伪造；
- close 幂等；close 后 readiness=false，其它操作 safe unavailable；
- 可选构造注入 `FaultInjector(operation)` 只用于测试，按调用抛上述 typed errors，不解析赛事内容触发故障。

Fake 不能用于代理分数、Update/Forget/Reflect 验证、重启持久性或 baseline 标记。

## 9. MemoryOperations 编排

### 9.1 Readiness

RawStore 和 Gateway 都 ready 才返回 true；任一 false 或探测异常返回 false。B03 不设置探测 timeout，正式
timeout 等主办方条件并在 I/O Batch 冻结。

### 9.2 Add

```text
RawStore.prepare_add(command)
  ├── conflict  → RequestConflictError → HTTP 409
  ├── COMPLETED → 校验 stored response exact IDs → return，不调用 Gateway
  ├── NEW       → build GatewayAdd → Gateway.add → RawStore.complete_add → return
  └── PENDING   → build same GatewayAdd → Gateway.add idempotent replay
                                  → RawStore.complete_add → return
```

- GatewayAdd message IDs 使用 B02 `message_id_for_position`；cube 使用 prepared logical cube；
- 只有 Gateway.add 和 RawStore.complete_add 都成功后 HTTP Add 才能 200；
- Gateway 失败保留 Raw pending/outbox，错误向上传播为脱敏 5xx，不自动 retry/fallback；
- complete 失败时 Gateway 可能已经成功；相同 request 重试依靠 Gateway 幂等后完成 Raw；
- 并发相同请求允许 at-least-once Gateway 调用，但 Fake/未来 Real 的可观察写入必须唯一；
- B03 不自动扫描历史 pending；只有 evaluator 重试相同 request 时恢复，B07 才主动派发。

### 9.3 Search

```text
derive expected logical cube from exact user_id
  → Gateway.search(query/user/cube/top_k/options)
  → discard evidence whose user/cube differs
  → validate/map exact id/content/finite score/aware created_at
  → preserve Gateway order and truncate to top_k
```

Search 不访问 gold、不选择 options、不生成最终答案、不按 session 过滤、不读取 Raw messages。B03 不提供
Gateway failure 的 empty fallback；错误保持明确 5xx。

## 10. HTTP 409 与默认 composition

- 在 `operations.py` additive 定义 `RequestConflictError(code="request.conflict")`；
- `MemoryOperations` 捕获且不泄漏 B02 infrastructure error，转换为 application error；
- API error handler 将该 application error 映射为 409，body 仍用统一安全 envelope；
- Add OpenAPI 显式声明 409；`contest-http-v1.md` 同步；
- 默认 `create_app()` 和 `memscope.main:app` 继续使用 `UnavailableContestOperations`；
- B03 只有测试/示例显式构造 SqliteRawStore + FakeGateway + MemoryOperations 后注入 `create_app`；
- 不修改 app factory signature、AppProfile、startup/lifespan 或默认数据库创建行为。

## 11. Mock Model API v1

### 11.1 Endpoint subset

| Method/path | 行为 |
|---|---|
| `GET /health` | 200 `{"status":"ok"}`，无外部依赖 |
| `POST /v1/chat/completions` | 接收 nonblank model 和 ordered role/content messages；返回非流式 chat envelope |
| `POST /v1/embeddings` | 接收 nonblank model 和 string/string-array input；返回同序 deterministic vectors |

Chat 默认 assistant content 为 canonical `{"memories":[]}`；`create_mock_model_app` 可注入其它合法 JSON
string 和 embedding dimension（默认 16，范围 1～4096）。未知常见请求字段允许但忽略，`stream=true`
明确 422，不静默伪装流式。

Embedding 算法 `mock-sha256-vector-v1`：seed 为
`b"memscope.mock.embedding.v1\0" + item.encode("utf-8")`；从 counter=0 起计算
`sha256(seed + counter.to_bytes(4, "big"))`，依次按 big-endian uint32 取值，映射为
`2 * value / 4294967295 - 1`，取满 dimension 后做 L2 normalization。零范数时固定第一维为 1.0。
同 input/dimension 跨进程相同，不同 input 可区分，空 string 合法，并以 golden vectors 冻结。

Response 使用稳定测试 ID/created=0、原 model、ordered index、usage=0。该 API 不声称 tokenizer、模型
语义、抽取质量或完整 OpenAI compatibility。

### 11.2 故障注入

测试请求可带单个 `X-MemScope-Mock-Failure`：

- `rate_limit` → 429 safe error envelope；
- `upstream_error` → 500 safe error envelope；
- `timeout` → await 构造时固定短 delay；
- `invalid_json` → HTTP 200 + 故意畸形 JSON body；
- `dimension_mismatch` → 仅 embeddings 返回 dimension+1 向量。

未知或多值 header 返回 400。故障控制值不来自 prompt/input，日志不记录 header、body、model 或 vector。
Mock app 只应位于测试/Compose 内网，organizer profile 不启动它。

## 12. 超时、重试、取消、降级与恢复

- B03 application 不增加超时、自动重试、熔断或 fallback；Fake typed faults 立即返回；
- Mock `timeout` 只用于客户端 timeout 测试，delay 有界且可注入；
- Add 协程取消向当前 Raw/Gateway await 传播；已经提交的 Raw/Gateway 状态按各自幂等契约收敛；
- Search 取消不转换为空结果；
- Gateway failure 后 Raw request/outbox 保持 pending，evaluator same-ID retry 可被动恢复；
- 无后台任务、startup scan、dead-letter 或跨进程 Fake 恢复；
- HTTP 409 non-retryable；gateway 429/timeout/unavailable retryable 但 B03 不自行重试；
- strict/empty、strict/raw_fallback 的最终选择仍等待主办方失败策略并属于 B07。

## 13. 配置与启动校验

B03 不增加 memory-api 环境变量、不改变 `APP_PROFILE=core`。Fake 仅构造注入。

Mock app factory 参数：

| 参数 | 默认/范围 | 语义 |
|---|---|---|
| `chat_content` | `{"memories":[]}`，必须为合法 JSON string | 固定 assistant content |
| `embedding_dimension` | 16；1～4096 | deterministic vector dimension |
| `timeout_delay_ms` | 100；10～5000 | timeout fault 的有界 delay |

参数在 app 创建时 fail fast。`mock_model_api.main:app` 使用安全默认值；B04/B05 根据固定 MemOS 源码增加
集中环境配置和 Compose，不在 B03 猜测最终 dimension/model/port。

## 14. 可观测性与敏感数据

新增日志 allowlist：

- `component_operation`：readiness/add/search/close；
- `component_result`：success/new/pending/completed/conflict/unavailable/filtered/failed；
- `component_duration_ms`；
- `gateway_duration_ms`；
- `model_endpoint`：health/chat/embeddings；
- `model_result`：success/rate_limited/upstream_error/timeout/invalid_json/dimension_mismatch；
- `model_duration_ms`；
- 既有 `error_code`、`retryable`、HTTP/storage fields。

禁止记录 request/user/session/cube/message/evidence ID、query/options、role/content、timestamp、payload hash、
model name、prompt/input、embedding/vector、Mock fault header、DB path、provider body 或底层异常文本。

## 15. 可扩展点与延后能力

- Gateway protocol 是 Fake/Real 变化边界，Real 实现可以组合 HTTP client、Cube lifecycle 和 MemOS DTO；
- Gateway DTO 保留 exact provenance，使 application 能独立做 user/cube 二次隔离；
- Fake ranking 独立命名且只存在 Fake 内，不污染未来 retrieval 策略；
- Mock app factory 可注入 chat fixture/dimension，B05 可根据固定源码扩展而不改测试故障机制；
- B04 负责运行服务和 lifecycle，B05/B06 负责 Real Add/Search，B07 负责可靠性策略；
- 本轮不为未知决赛预建通用 provider SDK、插件系统、事件总线或持久 Fake。

## 16. 测试与质量矩阵

| 层级 | 关键用例 | 通过标准 |
|---|---|---|
| 单元：Gateway models | strict types、ID/digest、message order/unique、score/time/top_k | 非法组合 fail fast；无框架依赖 |
| 单元：Fake Add | first、exact duplicate、request/message conflict、closed、fault injection | 唯一可观察写；typed safe errors |
| 单元：Fake Search | overlap/tie/order/top_k/options/empty/timestamp | deterministic；不改 content；不按 session |
| 单元：Operations Add | NEW/PENDING/COMPLETED、conflict、Gateway/complete failure | 仅完整成功返回；pending 可被动恢复 |
| 单元：Operations Search | mapping/order/truncate/foreign provenance/empty/fault | exact user/cube 隔离；不生成答案 |
| 契约：Gateway shared suite | readiness、Add/search、duplicate、isolation、close | Fake 通过；B05 Real factory 必须复用 |
| 契约：HTTP Fake path | Health/Add/Search、same/different request、multi-user、top_k | immediate visibility；conflict 409；响应形状不变 |
| 契约：Mock Chat | request variants、envelope、injected JSON、stream reject | deterministic valid subset |
| 契约：Mock Embedding | str/list/order/dimension/determinism/Unicode/empty | finite normalized vector；跨进程 golden |
| 故障：Gateway | rate-limit/5xx/timeout/protocol、partial success simulation | safe 5xx；Raw pending；same-ID recovery |
| 故障：Mock HTTP | 429/500/timeout/invalid JSON/dimension mismatch/bad header | 可由客户端精确分类；无请求泄漏 |
| 并发 | same request、different requests、Add/Search snapshot、close | 无重复 evidence、无跨 user、无 dict mutation race |
| 取消 | Raw 后、Gateway 中、complete 前取消 | 不伪成功；retry 收敛；无未分类异常 |
| Smoke | 显式 Fake 全链、Mock Uvicorn 进程、默认 main | Fake path 200；Mock clean shutdown；默认仍 503 |
| 回归 | 全部 B00/B01/B02 tests | Raw Schema/identity 和 HTTP 默认无变化 |
| 性能测量 | 1/20/100 messages Fake Add/Search、Mock chat/embedding | 报告 P50/P95/P99 和分段；不设硬件 hard assertion |

质量门禁：

```text
uv lock --check --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

- coverage.py 综合覆盖率至少 95%；
- 新增 B03 模块语句覆盖至少 95%、分支覆盖至少 90%；
- tests 只写 pytest/system temp，不写仓库 `data/`；
- 默认测试不读取 Key、外网、MemOS 源码或正式样本；
- 依赖 to_thread/localhost 的测试沿用 B01/B02 已记录的授权执行环境；
- Gate 2 报告 Fake application/Raw/Gateway 分段和 Mock endpoint 本机性能，不把它当模型质量。

## 17. 主要风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| Fake 被误当 baseline | 虚假质量结论或错误提交 | 默认不组装、文档/日志标识 fake、禁止代理分数和 milestone |
| Mock subset 与 MemOS 不匹配 | B05 接线失败 | 明确 provisional subset；B05 先做固定源码 map，再 additive 演进 |
| pending 被当成功 | Add 返回但 Gateway 不可检索 | PENDING 必须重放 Gateway + complete 后才返回 |
| Gateway 成功、complete 失败 | 外部已有数据而 Raw pending | Gateway request/message 幂等；same-ID retry 收敛；B07 主动恢复 |
| concurrent pending 重放 | Gateway 被调用多次 | Gateway contract 强制 exact duplicate no-op；Fake 并发测试 |
| completed replay + Fake 重启 | Raw completed 但 Fake 已失忆 | 明确 Fake 非 durable，不做跨进程恢复证明，不用于提交候选 |
| API 直接依赖 Raw error | 层次反转、Real backend 耦合 | application error translation，API 只映射 RequestConflictError |
| Fake 排序污染真实策略 | 代理质量误导 | `fake-token-overlap-v1` 封装在 Fake，Real contract 不规定评分算法 |
| provenance 错误导致串 user | 隐私/取消资格风险 | DTO exact user/cube + application 二次过滤 + malicious Gateway test |
| 故障注入被外部滥用 | 可用性风险 | Mock 只内网，organizer 不启动，allowlist header，不从内容触发 |
| embedding 不稳定/NaN | Qdrant 测试漂移 | SHA-256 counter + L2 + golden/finiteness tests |
| 默认 readiness 过早 200 | 评测误启动 | app/main 不修改；仅显式注入的测试 app ready |
| 日志泄漏 prompt/对话/vector | 合规风险 | formatter allowlist、值禁入、故障和日志测试 |
| 无正式 timeout/并发信息 | 参数冻结错误 | B03 不冻结生产策略，仅报告本机测量和可替换边界 |

## 18. 回滚方式

- Gate 1 批准后从 `a782204...` 创建独立 B03 分支；B02 验收分支/提交保持不变；
- 不新增依赖、不修改锁文件、不改 B02 Schema/数据库；
- 测试 SQLite 只在 tmp_path，Fake 仅进程内，Mock 无持久状态；
- 实施提交按“Gateway/编排”“Mock API”“测试/文档”等单一目的拆分；
- 删除显式 B03 组件即可恢复默认 B02 503；默认 composition 无迁移/数据回滚；
- 若 Gateway contract、HTTP 409、Mock endpoints 或 B01/B02 冻结接口需实质变化，暂停并重新 Gate 1；
- 禁止破坏性 Git 历史重写和自动删除用户数据。

## 19. Gate 1 待审批点

请明确批准或修改：

1. B03 同时交付 Gateway/Fake、MemoryOperations 和独立 Mock Model API，但不接真实 MemOS；
2. 只有显式 Fake 测试组装路径成功，默认 app/main/Profile 继续 503 且不创建数据库；
3. 批准 MemoryGateway v1 DTO、方法、typed errors 和依赖方向；
4. Gateway.add 内部负责 ensure user/cube，不单列 create_cube API；
5. PENDING replay 必须重放幂等 Gateway；COMPLETED replay 不再调用 Gateway；
6. Application 增加 `RequestConflictError`，HTTP Add 将不同 payload 映射 409；
7. Search 使用冻结逻辑 cube derivation，并对 Gateway provenance 做二次 user/cube 过滤；
8. Fake 使用非持久、asyncio-safe、exact duplicate idempotency；不证明跨进程恢复；
9. Fake 使用明确限定的 `fake-token-overlap-v1`，只作接线验证、不作质量判断；
10. Fake transport faults 用 typed errors 表示，故意畸形 JSON 由 Mock HTTP API 测试；
11. 批准 Mock 的 health/chat/embeddings OpenAI-shaped v1 subset 和非兼容性声明；
12. Mock Chat 默认 `{"memories":[]}`、embedding 默认 dimension=16，均为 app factory 可注入测试值；
13. Mock 故障使用内网 allowlist header；不实现 Rerank/stream/tool calls/token arrays；
14. B03 application 不加 timeout/retry/fallback/background recovery，失败保持 pending 或明确 5xx；
15. 不新增环境变量/依赖，不修改 app.py/main.py、AppProfile、B02 RawStore 或 Compose；
16. 批准本文文件范围、共享契约测试、故障/并发/取消/Smoke 和覆盖率门禁；
17. 批准后才创建 `batch/b03-no-key-doubles`，完成后停在 Gate 2，不进入 B04。

## 20. Definition of Done

B03 进入 `Code Review` 前必须同时满足：

1. Gateway models/errors/protocol 不依赖 FastAPI/Pydantic/SQLite/HTTPX/MemOS；
2. Fake 和未来 Real 变化边界由 `memory-gateway-v1.md` 及 reusable contract suite 锁定；
3. Fake exact Add duplicate 无副作用，不同 request/message 内容冲突 fail closed；
4. Fake Search deterministic、user/cube 隔离、不按 session、≤top_k、content exact；
5. MemoryOperations 正确处理 NEW/PENDING/COMPLETED；只有 Gateway + complete 成功才 Add 返回；
6. Gateway/complete failure 后 Raw 保持 pending，同 ID retry 可恢复且无重复 evidence；
7. 不同 payload HTTP 409 使用 application error，API 不依赖 RawStore/SQLite；
8. 显式 Fake ASGI path Health/Add/Search 全成功，Add 后立即 Search 可见；
9. 多 user 相同文本、同 session 多 chunk、并发 same request 和 malicious provenance 均不串数据；
10. Mock health/chat/embedding envelope、顺序、dimension、Unicode、空 input 和 golden vector 通过；
11. Mock 429/500/timeout/invalid JSON/dimension mismatch 和 invalid header 均可重复触发；
12. Mock Uvicorn 可独立启动、探测并干净 shutdown，无 Key/外网；
13. 默认 `memscope.main` 三条合法比赛路径仍为明确 503，且不创建 Raw DB；
14. Settings、日志和错误不泄漏 ID、内容、prompt、model、vector、fault header 或路径；
15. `pyproject.toml`、`uv.lock`、B02 RawStore Schema/identity/migration 和 MemOS pin 未变化；
16. README、Gateway/Mock interfaces、ADR、CODEMAP、PROJECT_CONTEXT 和 Handoff 与实现一致；
17. Ruff、Mypy strict、Pytest、总体/B03 覆盖门禁全部通过；
18. Gate 2 报告测试、覆盖、Fake/Mock 分段性能、偏差、Mock 非兼容范围和环境限制；
19. 未读取正式样本/完整 MemOS 源码，未运行代理评分，未创建 B04 分支或基础设施。

## 21. 重新评审触发器

发生任一情况立即停止并重新 Gate 1：

- 修改 B01 ContestOperations/HTTP 请求响应或 B02 RawStore 公共接口/Schema/identity；
- 改变 NEW/PENDING/COMPLETED、409、同步 Add、provenance isolation 或外部一致性语义；
- 修改默认 app/main/Profile，使 Fake/Mock 自动进入运行路径；
- Gateway contract 增加 provider-specific MemOS/HTTP/Pydantic 类型；
- Mock 声称完整 OpenAI compatibility、实现 Rerank/stream/tool calls 或需要新模型协议；
- 引入 HTTP client/runtime/数值库或其它第三方依赖；
- 增加 Compose、数据库、后台任务、自动 retry/fallback 或持久 Fake；
- 需要读取/修改 MemOS 源码、正式样本或扩大 allowed changes；
- MemOS tag/commit、hard dependency、文件范围或完成标准改变；
- 无法达到批准的共享契约、故障、隔离、覆盖率或性能报告要求。

# B01 比赛 HTTP 协议代码方案

> 状态：Code Review，2026-09-02 Gate 1 已批准并完成实施
> Batch：B01
> 基线提交：`714e5581104cd84a41cbb05d46a12e89ae10cdda`
> 计划分支：`batch/b01-api-contract`（仅在 Gate 1 明确批准后创建）
> 方案依据：B00 `Accepted/Frozen` 交接、比赛 API 契约，以及
> `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md` 第 2、4、11、12、16、18、19 节
> 边界：本方案只供评审；批准仅授权 B01，不授权进入 B02

## 1. 目标

B01 只冻结比赛对外 HTTP 边界和与后续业务实现之间的应用端口：

1. 实现 `GET /health`、`POST /add`、`POST /search` 的 FastAPI 路由；
2. 用严格类型的 Pydantic 模型表达请求和响应，保持比赛字段、状态码和 JSON 形状稳定；
3. 将 HTTP 模型转换为不依赖 FastAPI/Pydantic 的内部命令和证据模型；
4. 定义一个实际被 Adapter 使用的异步 `ContestOperations` 应用端口，供 B02/B03 以后实现；
5. 支持默认关闭、可配置启用的共享 Key 鉴权，并兼容 Bearer、Token 和 X-Api-Key；
6. 建立脱敏、稳定的 HTTP 错误模型和异常映射；
7. 验证 Add 必须等待应用操作完成后才返回，Search 只透传已排序证据；
8. 在无 Key、无数据库、无 MemOS 和无外部服务时完成全部 B01 默认测试；
9. 保留 B00 的 app factory、配置、日志和异常公共接口兼容性。

## 2. 非目标

B01 明确不实现：

- Raw Store、SQLite、FTS、迁移、`request_id` 持久幂等或 payload 冲突检测；
- `user_id` 到 MemCube 的映射、跨用户隔离的存储实现；
- Fake/Real MemOS Gateway、Mock Model API、MemOS、Qdrant 或 Neo4j；
- 记忆提取、排序、去重、融合、Update、Forget、Reflect 或最终答案生成；
- Search strict/empty、Raw fallback、重试、熔断、outbox 或恢复；
- `/health/details` 和组件级 readiness 聚合；
- Docker/Compose、提交包或真实 API/Key 调测；
- 正式样本、`official/questions.jsonl` 或代理分数运行；
- 为了通过 Smoke 而在生产默认组装中伪造 Add 成功或返回虚假记忆；
- B02 及以后 Batch 的代码。

官方 Smoke 脚本只有在后续 Batch 提供可用的 `ContestOperations` 实现后，才能对默认进程完整成功。
B01 的成功路径由注入式契约测试验证，测试替身不进入运行时代码。

## 3. 前置条件与依赖

### 3.1 Hard dependencies

- 用户明确批准本 Gate 1 方案；
- B00 已为 `Accepted/Frozen`，实现提交为
  `ff2484b7732671c3c96f35ad3dd25b4da108618c`；
- B01 实施前 MemScope HEAD、工作区和基线仍与本方案一致；
- MemOS 保持 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`；B01 不读取或修改其源码；
- 继续使用 B00 锁定的 Python 3.11.16、uv 0.12.9 和现有依赖锁。

### 3.2 Soft dependencies

以下缺失不阻塞 B01：

- 主办方 Chat/Embedding/Rerank API 与 Key；
- 正式硬件、超时、并发和失败策略；
- Compose、网络和构建限制；
- 决赛交付要求。

B01 不增加第三方依赖，不访问网络，不需要主办方凭据。

## 4. 契约冲突、模糊点与本方案取值

| 模糊点 | B01 取值 | 理由 |
|---|---|---|
| 当前 `official/` 不是主办方字节级正式包 | 以 `api_contract.md` 的规则级契约为当前权威，并把变化设为重新评审触发器 | 避免把本地重建数据误当正式协议 |
| 路径可自定义 | 固定 `/health`、`/add`、`/search` | 与任务书、调测脚本和主计划一致，减少部署配置风险 |
| Health 成功响应正文未规定 | 200 + `{"status":"ok"}` | 评测只依赖任意 2xx；固定小响应便于运维 |
| B01 尚无 Raw/MemOS 后端 | 默认 `/health`、合法 Add/Search 返回 503；注入 ready 实现时才返回成功 | 不伪造 ready、持久化或同步可检索保证 |
| 请求额外字段未明确禁止 | 忽略但不使用额外字段；响应只输出已声明字段 | 样本 Schema 未禁额外字段，兼顾前向兼容且不扩大能力 |
| `role` 合法枚举未规定 | 接受并原样保留任意非空字符串 | 契约和样本 Schema 都未限定 user/assistant 枚举 |
| 字符串是否 trim 未规定 | 用 trim 判断非空，但保留原始值 | 三 ID 必须原样回传，内容也不应被 Adapter 改写 |
| `top_k` 通用上限未规定 | 接受严格整数 1～100 | 正式评测固定 100，主计划消融值不超过 100，避免无界响应 |
| 鉴权选择和多 Header 语义未规定 | 一个共享 Key；三种载体三选一；多凭据或畸形凭据统一拒绝 | 避免 Header 歧义和请求走私式解析差异 |
| 错误 JSON 格式未规定 | 定义稳定、脱敏的私有错误 envelope；使用标准 HTTP 状态码 | 便于测试和后续组件统一映射，不影响成功契约 |
| 非法请求应为 400 还是 422 | 统一 422 `request.invalid` | 延续 FastAPI 结构化校验语义；两者均为标准 4xx |
| `/health/details` 何时提供 | 延后至存在真实组件状态的 Batch | B01 没有可展示的组件，不制造空协议 |
| 请求体和字符串最大长度未知 | B01 不猜测硬上限 | 正式超时/资源条件未知；获得条件后再评审安全上限 |

## 5. 预计文件与允许修改范围

### 5.1 Gate 1 当前只新增

- `docs/batches/B01/PLAN.md`
- `docs/batches/B01/CONTEXT.md`

### 5.2 Gate 1 批准后预计新增

```text
src/memscope/
├── operations.py
└── api/
    ├── __init__.py
    ├── auth.py
    ├── errors.py
    ├── models.py
    └── routes.py
tests/
├── contract/
│   └── test_contest_api.py
└── unit/
    ├── test_api_auth.py
    ├── test_api_errors.py
    ├── test_api_models.py
    └── test_operations.py
docs/
├── interfaces/
│   └── contest-http-v1.md
├── adr/
│   └── 0002-contest-adapter-boundary.md
└── batches/B01/
    └── HANDOFF.md             # 仅在 Gate 2 交付时创建
```

### 5.3 Gate 1 批准后预计修改

- `.env.example`：增加非密钥鉴权模式示例和 Key 注释；
- `README.md`：更新 B01 启动、默认 unavailable 行为和测试说明；
- `src/memscope/app.py`：注册路由、错误处理和可注入应用端口；
- `src/memscope/settings.py`：增加鉴权枚举、SecretStr 字段及组合校验；
- `src/memscope/logging_config.py`：只增加固定、无请求正文的 HTTP/耗时字段 allowlist；
- `tests/smoke/test_minimal_app.py`：把 B00 的“赛事路径必须 404”替换为 B01 路由注册/默认不可用 Smoke；
- `tests/unit/test_app.py`、`tests/unit/test_settings.py`、`tests/unit/test_logging_config.py`：扩展冻结接口测试；
- `tests/support.py`：增加显式 Settings 和测试端口工厂；
- `docs/PROJECT_CONTEXT.md`、`docs/CODEMAP.md`：仅在实现后记录当前有效事实；
- `docs/batches/B01/PLAN.md` / `CONTEXT.md`：只同步已批准修订和实际上下文。

### 5.4 明确不修改

- `pyproject.toml`、`uv.lock` 和运行时依赖版本；
- `.vendor-src/MemOS/**`；
- `docs/batches/B00/**` 和 B00 冻结实现接口；
- `docs/achieve/**`；
- 任务书、调测指南、评测集、`official/**`、Smoke 数据与代理脚本；
- Docker、Compose、Raw Store、Gateway 或模型文件；
- 任何 `.env`、Key、运行数据、缓存或虚拟环境。

若实现必须越过范围，立即暂停并重新进行 Gate 1 评审。

## 6. 模块职责与依赖方向

```text
memscope.main
  └── memscope.app.create_app
        ├── memscope.api.routes          FastAPI Adapter
        │     ├── memscope.api.models    外部 JSON 契约
        │     ├── memscope.api.auth      HTTP 凭据解析
        │     └── memscope.operations    内部命令、证据与应用端口
        ├── memscope.api.errors          HTTP 错误映射
        ├── memscope.settings
        └── memscope.logging_config

B02/B03+ implementation ──implements──> ContestOperations
tests-only recorder       ──implements──> ContestOperations
```

依赖约束：

- `operations.py` 只依赖 Python 标准库和 `memscope.errors`，不依赖 FastAPI、Pydantic、数据库或 MemOS；
- `api.models` 只表达外部协议，不承载存储、检索或答案逻辑；
- `api.routes` 只做鉴权、外部/内部模型转换、调用和响应截断；
- `api.errors` 是唯一 HTTP 状态与错误 envelope 映射位置；
- `app.py` 只组装，不实现 Add/Search 业务；
- 运行时默认实现只表示 unavailable；任何成功测试替身必须位于 `tests/`；
- 后续 Raw Store、Gateway 或融合实现不得反向依赖 FastAPI 模型。

## 7. 外部 HTTP API

### 7.1 Health

```http
GET /health
```

- 无鉴权；
- 应用端口 ready 时返回 200：`{"status":"ok"}`；
- 未装配或 not ready 时返回 503 错误 envelope；
- 不访问正式样本，不泄漏组件配置；
- B01 不提供 `/health/details`。

### 7.2 Add

请求模型：

```json
{
  "request_id": "non-empty string",
  "user_id": "non-empty string",
  "session_id": "non-empty string",
  "messages": [
    {"role": "user", "content": "non-empty string", "timestamp": 1704067200000}
  ]
}
```

约束：

- 四个顶层字段必填；`messages` 至少一条；
- `role`、`content` 用 trim 判空但不改写；
- `timestamp` 可省略，存在时必须为严格整数，boolean 不视为整数；
- 合法调用必须等待 `ContestOperations.add()` 正常完成；
- 完成后返回 HTTP 200，`success` 必须是 JSON boolean `true`，三 ID 原样回传；
- operation 未配置、失败或取消时绝不返回 `success=true`；
- B01 只保证“等待被调用操作完成”，真实持久化、立即可检索和幂等由 B02/B03+ 实现并验证。

### 7.3 Search

请求模型：

```json
{
  "query": "non-empty string",
  "user_id": "non-empty string",
  "top_k": 100,
  "options": ["A. ...", "B. ..."]
}
```

约束：

- `query`、`user_id`、`top_k` 必填；`options` 可省略；
- `top_k` 必须为严格整数 1～100；
- `options` 可省略或为 `null`；非 `null` 时必须为字符串数组，空数组和空字符串元素不由 Adapter 改写；
- options 原样传入应用端口，仅可用于后续检索扩展；B01 不选择选项；
- 响应固定为 `{"data":[...]}`，无结果为 `{"data":[]}`；
- 每项 `id`、`content` 非空；`score` 可省略但存在时必须为有限数；
- `created_at` 可省略但存在时必须为带时区的 ISO-8601 时间；
- 保留应用端口返回顺序，超过 `top_k` 时 Adapter 安全截断并记录协议违例；
- 不按 `session_id` 过滤，不接收或读取 gold，不生成答案。

### 7.4 Pydantic 策略

- 请求使用 strict 类型，禁止数字到字符串、字符串到数字和 boolean 到整数的隐式转换；
- 外部额外字段 `extra="ignore"`，不传入内部命令，也不进入日志；
- 模型冻结，路由不原地修改请求；
- 非空校验不改变原始字符串；
- 响应模型显式构造，不直接序列化下游任意对象；
- OpenAPI 由同一模型生成，但 OpenAPI 不是比 `api_contract.md` 更高的权威来源。

## 8. 内部接口和数据模型

计划提供以下 framework-independent 公共端口：

```python
@dataclass(frozen=True, slots=True)
class MemoryMessage:
    role: str
    content: str
    timestamp: int | None

@dataclass(frozen=True, slots=True)
class AddCommand:
    request_id: str
    user_id: str
    session_id: str
    messages: tuple[MemoryMessage, ...]

@dataclass(frozen=True, slots=True)
class SearchQuery:
    query: str
    user_id: str
    top_k: int
    options: tuple[str, ...] | None

@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    id: str
    content: str
    score: float | None = None
    created_at: datetime | None = None

class ContestOperations(Protocol):
    async def is_ready(self) -> bool: ...
    async def add(self, command: AddCommand) -> None: ...
    async def search(self, query: SearchQuery) -> Sequence[MemoryEvidence]: ...
```

并将 app factory 向后兼容扩展为：

```python
def create_app(
    settings: AppSettings | None = None,
    *,
    operations: ContestOperations | None = None,
) -> FastAPI: ...
```

不传 `operations` 时装配立即失败的 unavailable 实现。B00 的 `create_app(settings)` 和
`memscope.main:app` 调用方式保持有效。

内部不变量：

1. `AddCommand` 和 `SearchQuery` 不引用 HTTP header、Request 或 Response；
2. 三 ID 和消息顺序从入口到应用端口不变；
3. `options=None` 与显式空数组保持可区分；
4. Search 证据顺序由应用层决定，Adapter 不重新打分；
5. Adapter 最多截断，不补造、改写或合并证据；
6. 端口调用是 async，避免后续网络/存储实现阻塞 ASGI 事件循环；
7. `ContestOperations` 是 Adapter 到应用编排层的端口，不等同于 B03+ 的 `MemoryGateway`。

## 9. 配置和鉴权

新增配置：

| 环境变量 | 类型/允许值 | 默认值 | 组合约束 |
|---|---|---|---|
| `CONTEST_AUTH_MODE` | `none` / `shared_key` | `none` | `none` 时 Key 必须为空；`shared_key` 时 Key 必须为非空 |
| `CONTEST_API_KEY` | SecretStr / absent | absent | 只从 Settings/env 读取，不得出现在日志、错误、repr 或文档真值中 |

`shared_key` 模式仅对 Add/Search 生效，Health 始终无鉴权。每个请求必须恰好提供一种：

- `Authorization: Bearer <key>`；
- `Authorization: Token <key>`；
- `X-Api-Key: <key>`。

scheme 大小写不敏感；Key 不做大小写转换；使用 `secrets.compare_digest` 比较。缺失、空值、未知
scheme、多凭据或错误 Key 都返回同一个 401 `auth.invalid`，不泄漏失败原因。401 带标准
`WWW-Authenticate: Bearer`。`none` 模式不检查请求携带的凭据。

`safe_summary()` 只增加 `contest_auth_mode` 和 `contest_api_key_configured: bool`，不得包含 Key。
无效组合在 ASGI ready 前通过现有 `ConfigurationError` 脱敏失败。

## 10. HTTP 错误模型

统一响应：

```json
{
  "error": {
    "code": "request.invalid",
    "message": "Request validation failed",
    "retryable": false
  }
}
```

映射：

| 场景 | HTTP | code | retryable |
|---|---:|---|---|
| JSON/Pydantic 请求校验失败 | 422 | `request.invalid` | false |
| 缺失、畸形或错误凭据 | 401 | `auth.invalid` | false |
| 默认未装配、not ready、readiness 探测异常或已知依赖不可用 | 503 | `service.unavailable` | true |
| 路径不存在 | 404 | `http.not_found` | false |
| 方法不允许 | 405 | `http.method_not_allowed` | false |
| 已知 `MemScopeError` 未专门映射 | 500 | 保留其安全 code/message | 取异常值 |
| Add/Search 等非 Health 路径的未知异常 | 500 | `internal.error` | false |

规则：

- 不返回 Pydantic 原始 errors、请求 body、消息 content、header、Key 或异常 repr；
- 只有 `MemScopeError.message` 被视为可向外输出的安全消息；未知异常固定通用消息；
- Health 的 readiness 探测异常统一表示“当前不可用”并返回 503；其它未知异常返回 500；
- 错误日志只含固定事件、HTTP 元数据、`error_code`、`retryable` 和异常类型；
- 422 前不得调用应用端口；401 前后都不得记录凭据；
- Client disconnect/cancellation 不转换为成功或重试，由 ASGI 取消语义传播。

## 11. 正常流程、异常流程和状态转换

### 11.1 启动

```text
load_settings
  → 校验鉴权组合
  → configure_logging
  → 选择显式 operations 或 UnavailableContestOperations
  → 注册错误处理、HTTP 观测和三条赛事路由
  → ASGI ready
```

ASGI 进程可 ready 不代表记忆后端 ready；只有 `/health` 2xx 才表示评测机可以开始调用。

### 11.2 Add

```text
HTTP JSON
  → strict contract validation
  → optional auth
  → map AddRequest to AddCommand
  → await operations.add(command)
  → only on success: 200 + exact ID echo
```

### 11.3 Search

```text
HTTP JSON
  → strict contract validation
  → optional auth
  → map SearchRequest to SearchQuery
  → await operations.search(query)
  → validate/map evidence
  → preserve order and truncate to top_k
  → 200 + {"data": [...]}
```

### 11.4 状态

```text
APP_READY + OPERATIONS_UNAVAILABLE → /health 503, Add/Search 503
APP_READY + OPERATIONS_READY       → /health 200
ADD_IN_FLIGHT                       → success response prohibited
ADD_COMPLETED                       → 200 success response allowed
SEARCH_COMPLETED                    → validate/truncate → 200 data response
ANY_FAILURE                         → safe HTTP error; never false success
```

## 12. 超时、重试、降级、幂等和恢复

- 超时：B01 不包裹应用端口超时；正式值和各下游调用边界尚未知，由首次外部 I/O Batch 评审；
- 重试：无；Adapter 不重试 Add，避免未来非幂等操作重复；
- 降级：无；Add 不伪成功，Search 不把失败降级为空数组；
- 幂等：B01 只原样传递 `request_id`；持久幂等和冲突检测属于 B02；
- 恢复：无本地状态；后端 unavailable 时返回 503，恢复后由 readiness 自然转为 200；
- 一致性：B01 只保证 await 边界，不声称持久化、重启或 Add 后立即 Search；
- 并发：路由无可变全局请求状态；真实并发和隔离由后续实现验证；
- 取消：请求取消向应用端口传播，不吞掉 `CancelledError`，不生成成功响应。

## 13. 日志与性能观测

B01 只记录固定 allowlist：

- `http_method`、`http_path`、`status_code`；
- `total_duration_ms`；
- 已知错误的 `error_code`、`retryable`；
- 未知异常只记录 `exception_type`。

禁止记录 URL query、Authorization、X-Api-Key、request/user/session ID、消息、Search query、options
和返回 content。赛事路由使用 monotonic clock 记录总耗时；B01 没有 Raw/MemOS 等阶段，不伪造不存在的
分段耗时。后续 Batch 增加真实阶段时扩展同一 allowlist。

Gate 2 报告本机、进程内、无外部 I/O 的 Health/Add/Search P50/P95/P99。剔除应用端口等待后，
Adapter P95 目标不超过主计划暂定的 50 ms；性能测试报告数据但不使用易受共享执行器波动影响的硬断言。

## 14. 可扩展点与延后能力

- `ContestOperations` 隔离 HTTP 与后续 Raw/MemOS 编排；B02/B03 只需实现同一小端口；
- HTTP request/response 与内部 dataclass 显式映射，未来比赛字段变化不会渗入存储接口；
- 错误映射集中，后续超时、冲突、限流和 fallback 可以新增类型而不散落状态码；
- 鉴权策略集中，正式规则变化时可替换 header policy；
- app factory 注入使 Fake、真实和故障实现共享同一 Adapter 契约测试；
- 保留未知决赛演进空间，但本轮不预建多租户权限框架、插件系统或版本路由。

## 15. 测试与质量矩阵

| 层级 | 关键用例 | 通过标准 |
|---|---|---|
| 单元：请求模型 | 必填、strict 类型、空白、message 顺序、timestamp、options、额外字段、top_k 边界 | 非法输入确定性拒绝；合法输入不改写 |
| 单元：响应模型 | boolean success、空 data、非空 id/content、有限 score、时区时间 | 不产生协议外字段或 NaN/Infinity |
| 单元：内部模型/端口 | frozen dataclass、默认 unavailable、async 协议 | 不依赖 FastAPI/Pydantic/外部 I/O |
| 单元：鉴权 | none、Bearer、Token、X-Api-Key、scheme 大小写、缺失、错误、畸形、多 Header | 三种单一正确载体通过，其余统一 401；Key 不泄漏 |
| 单元：Settings | 默认、shared_key、缺 Key、none+Key、空 Key、safe summary | 非法组合启动前失败；摘要只有 configured boolean |
| 单元：错误映射 | validation、auth、unavailable、已知/未知错误、404/405 | 状态、code、retryable 稳定；无请求原值 |
| 契约：Health | ready、not ready、异常、带/不带凭据 | ready 200；其它 503；始终无鉴权 |
| 契约：Add | 完整/无 timestamp、多消息、等待完成、三 ID 原样回显 | 仅操作成功后 200；`success is true` |
| 契约：Search | options 有/无、空结果、排序保留、top_k 截断、可选字段 | 顶层 data；数量不超过 top_k；输出可 JSON 解析 |
| 契约：拒绝路径 | malformed JSON、缺字段、错类型、空白、未鉴权 | 4xx；应用端口零调用；错误无正文/Key |
| 契约：故障 | unavailable、已知错误、未知异常、取消 | 标准错误；不返回假成功或假空结果 |
| OpenAPI | 三路径、方法、请求/响应 schema | 与已批准接口模型一致 |
| 进程 Smoke | 默认 Uvicorn 启停、Health/Add/Search 已注册但 unavailable | 无外部服务可启动；默认 503 而非 404/伪 200 |
| 回归 | B00 Settings、日志、异常、app factory 行为 | 除 B00 明示的“赛事路径 404”被 B01 替换外均保持通过 |
| 性能测量 | 注入立即完成端口，预热后重复 Health/Add/Search | 报告 P50/P95/P99；Adapter P95 目标 ≤ 50 ms |

质量门禁：

```text
uv lock --check --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

- 总体 coverage.py 覆盖率继续至少 95%；
- 新增 B01 模块语句覆盖至少 95%、分支覆盖至少 90%；
- 默认测试不得读取 Key、数据库、MemOS、网络或正式样本；
- 真实 localhost Uvicorn Smoke 继续验证干净启停；
- Gate 2 单独报告语句、分支、契约用例和耗时。

## 16. 主要风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| 本地重建契约与主办方真实包有差异 | 正式请求 4xx 或响应解析失败 | 入站额外字段兼容；正式契约一到立即 diff 并触发重审 |
| 默认 503 被误认为 B01 未完成 | 误用无后端进程进行正式 Smoke | 文档明确区分 ASGI ready 与 memory ready；成功路径由注入契约测试证明 |
| 伪造 Add 成功 | 后续 Search 不可见，整样本失分 | unavailable 默认失败；只在 awaited operation 成功后回 200 |
| Pydantic 隐式转换掩盖评测错误 | ID/type 不一致或响应格式失败 | strict 模型和边界测试 |
| 错误详情泄漏对话或 Key | 安全和合规风险 | 固定 envelope、allowlist 日志、禁止原始 validation details |
| 多鉴权 Header 解析歧义 | 绕过或正式鉴权失败 | 恰好一种凭据、统一解析、constant-time 比较 |
| 无请求大小上限 | 资源耗尽 | 当前评测有约 20 消息/2000 词分块；正式资源信息后设置并评审上限 |
| Adapter 截断掩盖下游超量 | 质量或实现缺陷不易发现 | 保证合规响应同时记录协议违例；契约测试要求正常实现不超量 |
| B01 端口与未来 Gateway 混淆 | 分层反转、扩展困难 | 明确端口属于应用编排层；MemoryGateway 仍由 B03+ 单独定义 |
| 过早实现失败策略 | 与未知主办方超时/整轮策略冲突 | B01 只使用显式 4xx/5xx，无重试和降级 |

## 17. 回滚方式

- B01 在批准后从 `714e558...` 创建独立分支；B00 分支和提交保持不变；
- 不新增依赖、不修改锁文件、不产生迁移或持久数据；
- 回滚只需停止 B01 分支使用并回到 B00 验收提交；
- 实施提交按“接口模型/应用端口”“Adapter/鉴权/错误”“测试与文档”等清晰目的拆分；
- 禁止使用破坏性历史重写；若公共接口在评审后变化，新增修订提交并重新 Gate 1。

## 18. Gate 1 待审批点

请明确批准或修改以下决策：

1. B01 只冻结 HTTP Adapter 与 `ContestOperations` 应用端口，不实现 B02/B03 能力；
2. 默认运行时不带成功 Fake：Health/Add/Search 在后端未装配时返回 503；
3. 外部请求 strict typed、trim 判空但原样保留，未知字段忽略；
4. `messages` 至少一条，`top_k` 允许 1～100，role 不做枚举限制；
5. Search 只保序并截断，不排序、不生成答案、不使用 gold；
6. 鉴权模式为 `none|shared_key`，一个 Key 兼容三种互斥载体；
7. 使用本文的 401/404/405/422/500/503 脱敏错误 envelope；
8. B01 无重试、降级、幂等持久化、超时或恢复；
9. 日志只增加固定 HTTP 元数据和总耗时，不记录任何请求业务内容或 ID；
10. 不新增依赖，不修改 `pyproject.toml` / `uv.lock`；
11. 批准本文文件范围、测试矩阵、覆盖率和本机性能报告要求；
12. 批准后才创建 `batch/b01-api-contract` 并实施，完成后停在 Gate 2。

## 19. Definition of Done

B01 进入 `Code Review` 前必须同时满足：

1. 三个规范路径已注册，方法和成功 JSON 与契约一致；
2. 注入 ready 测试端口时 Health 200、Add 200 且严格等待完成、Search 200 且 evidence 合规；
3. 默认生产组装无后端时三接口明确 503，不存在假成功；
4. Add 三 ID 原样回传，消息顺序、timestamp 和 options 正确映射；
5. Search 无结果为空数组，结果保序且不超过 `top_k`；
6. 认证关闭和三种启用载体通过，非法组合启动前失败，Key 全链路不泄漏；
7. 请求校验、HTTP、已知内部错误和未知异常都返回批准的安全映射；
8. `ContestOperations` 与内部 DTO 不依赖 FastAPI/Pydantic/存储/MemOS；
9. B00 公共接口保持兼容，只有赛事路径 404 不变量按批准方案被替换；
10. 无新第三方依赖，锁文件未变化，MemOS tag/commit 未变化；
11. Ruff、Mypy strict、Pytest、总覆盖率和新增模块分支门禁全部通过；
12. 真实 Uvicorn 无 Key启动/停止 Smoke 通过，并报告 Adapter 本机延迟；
13. `contest-http-v1.md`、ADR、CODEMAP、PROJECT_CONTEXT 和 B01 HANDOFF 与实现一致；
14. Gate 2 交付列出提交、测试、覆盖率、偏差、限制和后续依赖；
15. 未创建 B02 分支、文件或实现。

## 20. 重新评审触发器

发生任一情况立即停止实施并重新 Gate 1：

- 主办方提供的新契约改变路径、字段、状态码、鉴权或同步语义；
- 改变 `ContestOperations`、内部 DTO 或错误 envelope 的批准公共接口；
- 需要新增依赖、运行服务、数据库、后台任务或持久状态；
- 需要实现重试、超时、降级、幂等、恢复或新的 readiness 语义；
- 需要扩大 allowed changes 或修改 B00 冻结文档/接口；
- MemOS tag/commit 改变；
- 无法达到批准的测试、覆盖率或性能完成标准。

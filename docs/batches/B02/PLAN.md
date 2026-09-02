# B02 Raw Store 与身份基础代码方案

> 状态：Accepted/Frozen，2026-09-02 Gate 2 已验收
> Batch：B02
> 基线提交：`2f846a06e9c6f6b399a4753ad32bd3b565fd5fff`
> 实施分支：`batch/b02-raw-identity`
> 方案依据：B01 `Accepted/Frozen` 交接、`contest-http-v1.md`，以及
> `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md` 第 2、7.2、8、9、11、12、16、18、19 节
> 边界：本次批准仅授权 B02，不授权进入 B03

## 1. 目标

B02 交付后续 B03～B07 可以共同依赖的持久化和身份地基：

1. 使用 Python 标准库 `sqlite3` 实现可替换的异步 `RawStore` 端口和 SQLite 实现；
2. 原子保存 Add 请求、原始有序消息、user/cube 映射和 durable MemOS outbox；
3. 以版本化 canonical payload SHA-256 实现 `request_id` 持久幂等和冲突检测；
4. 区分首次请求、同 payload 处理中重放、已完成重放和不同 payload 冲突；
5. 以版本化 SHA-256 从外部 `user_id` 生成稳定逻辑 `cube_id`；
6. 为每条原始消息生成稳定 ID，并保存请求内位置与同 user/session 的持久顺序；
7. 提供内嵌、校验 checksum、并发安全、可重复执行的 Schema migration 机制；
8. 明确 SQLite 事务、WAL、同步级别、busy timeout、重启和崩溃边界；
9. 提供恢复所需的状态和 outbox 记录，但不提前实现 B07 的派发、租约和重试；
10. 在无 Key、无 MemOS/Qdrant/Neo4j、无网络时验证持久化、重启、并发和故障原子性；
11. 保持 B00/B01 已冻结的 HTTP、应用端口和默认不伪成功行为。

## 2. 非目标

B02 明确不实现：

- `ContestOperations` 的可用生产实现或默认 app 组装；
- HTTP Add 200、Search 证据返回或 `/health/details`；
- Fake/Real `MemoryGateway`、Mock Model API 或任何 MemOS 调用；
- MemOS user/Cube 创建、ACL、provider cube ID 验证或写入；
- outbox worker、lease、attempt 增长、退避、重试、dead-letter 或启动恢复任务；
- FTS5、Raw Search、Raw fallback、RRF、rerank、去重或排序；
- Update、Forget、Reflect 的状态解析和生命周期执行；
- SQLite 与 MemOS 的分布式 exactly-once 声明；
- 真实 API/Key、Docker/Compose、正式样本或代理评分；
- 请求体大小、正式并发、最终超时和降级参数冻结；
- B03 及以后 Batch 的代码。

B02 的组件测试可以模拟“外部写入完成”以验证状态转换，但不会把该模拟作为运行时 Gateway。

## 3. 前置条件与依赖

### 3.1 Hard dependencies

- 用户明确批准本 Gate 1 方案；
- B00、B01 均为 `Accepted/Frozen`；
- B01 `ContestOperations`、内部 DTO、HTTP 契约和默认 unavailable 语义不变；
- 实施前 MemScope HEAD、工作区和基线仍与本方案一致；
- MemOS 保持 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`；B02 不读取或修改其源码；
- 继续使用 CPython 3.11.16、uv 0.12.9 和现有锁文件；当前解释器 SQLite 为 3.53.1。

### 3.2 Soft dependencies

以下缺失不阻塞 B02：

- 主办方 Chat/Embedding/Rerank API 与 Key；
- 正式硬件、请求/整轮超时、并发和失败策略；
- Compose、网络和构建限制；
- MemOS 对 provider cube ID 的最终格式约束；
- 决赛交付要求。

B02 只冻结内部逻辑 cube ID；B05 首次接入固定 MemOS 源码时验证 provider ID 兼容性。

## 4. 边界冲突、模糊点与本方案取值

| 模糊点 | B02 取值 | 理由 |
|---|---|---|
| 主计划把 Raw Store D04-A 全部列为必需，但 B07 才做可靠性闭环 | B02 建表、原子 enqueue、状态和恢复依据；B07 增加派发/租约/重试 | 保证当前数据模型可恢复，又不提前实现无调用方 worker |
| B02 已有 Raw Store，Health 是否应 200 | 继续 503 | 没有 Search 路径时 Add 仍不满足“返回后可检索”，不能伪造完整 readiness |
| 同 request_id 同 payload 但首请求仍 pending | 返回内部 `PENDING` disposition，不返回成功 replay | 尚无已保存成功响应；未来编排层必须等待/处理，不可假成功 |
| 同 request_id 不同 payload 的 HTTP 409 | B02 抛出 typed `IdempotencyConflictError`；HTTP 409 映射延后到首次组装 Batch | B02 不实现 `ContestOperations`，避免基础设施反向依赖 FastAPI |
| payload 的“相同”未定义 | 使用版本化 canonical JSON，对 B01 归一化后的完整 `AddCommand` 哈希 | 结果确定、跨重启稳定，并保留消息顺序和原始字符串差异 |
| 缺失 timestamp 与 JSON null | B01 都归一化为 `None`，canonical payload 都编码为 null | HTTP 层已把二者定义为相同内部语义 |
| Unicode 是否规范化 | 不做 NFC/NFKC，按 Python 字符串 UTF-8 精确编码 | 避免无授权改写 ID 或消息；视觉相同但编码不同视为不同 payload |
| Cube ID 的 MemOS 长度/字符限制未知 | 冻结 `cube_v1_<64 hex>` 逻辑 ID；B05 如需另增 provider ID，不改逻辑 ID | 满足稳定映射，并隔离未知供应方限制 |
| 多 chunk 的 session_position | 按事务提交顺序为同 user/session 连续分配，request_position 记录 chunk 内顺序 | 契约没有可信全局 chunk 序号；数据库提交顺序是唯一可持久观察顺序 |
| SQLite 默认 durability/performance 取值 | 文件 DB 固定 WAL + `synchronous=FULL`，busy timeout 默认 5000 ms | B02 先保证正确性；正式硬件到位后再测量是否调整 |
| migrations 是否引入 Alembic | 不引入；使用版本化 Python migration tuple + checksum ledger | 无新依赖，适合小型单 SQLite Schema，且可测试完整性 |
| runtime 默认数据库路径 | `data/memory.db`；B04 容器 profile 显式覆盖 `/data/memory.db` | 保持本地可运行且目录已 gitignore，不提前冻结容器形态 |
| 原始消息是否可直接用于 Search | 不可；B02 只提供按 user/request 隔离的恢复读取 | FTS/Raw retrieval 属于 D04-B，不能偷渡为未评测 Search |

## 5. 预计文件与允许修改范围

### 5.1 Gate 1 当前只新增

- `docs/batches/B02/PLAN.md`
- `docs/batches/B02/CONTEXT.md`

### 5.2 Gate 1 批准后预计新增

```text
src/memscope/raw_store/
├── __init__.py
├── errors.py
├── identity.py
├── migrations.py
├── models.py
├── protocol.py
└── sqlite.py
tests/
├── component/
│   ├── test_raw_store_migrations.py
│   └── test_sqlite_raw_store.py
└── unit/
    ├── test_raw_identity.py
    └── test_raw_models.py
docs/
├── interfaces/
│   └── raw-store-v1.md
├── adr/
│   └── 0003-sqlite-raw-store-and-idempotency.md
└── batches/B02/
    └── HANDOFF.md             # 仅在 Gate 2 交付时创建
```

### 5.3 Gate 1 批准后预计修改

- `.env.example`：增加本地数据库路径和 SQLite busy timeout；
- `README.md`：说明 B02 组件能力、默认仍 unavailable 和本地数据目录；
- `src/memscope/settings.py`：增加数据库路径与 busy timeout 的集中校验；
- `src/memscope/logging_config.py`：增加不含 ID/内容/路径的 Raw Store 固定观测字段；
- `tests/unit/test_settings.py`、`tests/unit/test_logging_config.py`：覆盖新增安全配置与日志 allowlist；
- `tests/support.py`：增加确定性 UTC clock 等纯测试工厂；
- `docs/PROJECT_CONTEXT.md`、`docs/CODEMAP.md`：实现后记录当前有效事实；
- `docs/batches/B02/PLAN.md` / `CONTEXT.md`：只同步已批准修订和实际上下文。

### 5.4 明确不修改

- `pyproject.toml`、`uv.lock` 和依赖版本；
- B01 `operations.py`、`app.py`、`api/**`、HTTP 契约和测试；
- `docs/batches/B00/**`、`docs/batches/B01/**` 及已接受 ADR/interface；
- `.vendor-src/MemOS/**`；
- `docs/achieve/**`；
- 任务书、调测指南、评测集、`official/**`、Smoke 数据和代理脚本；
- Docker、Compose、Gateway、Mock model、FTS 或 worker 文件；
- `.env`、真实数据库、Key、日志、缓存或虚拟环境。

若实现必须越过范围，立即暂停并重新 Gate 1。

## 6. 模块职责与依赖方向

```text
memscope.operations (B01 application contract)
          ▲
          │ future B03 orchestration
          │
memscope.raw_store.protocol
          ▲
          └── memscope.raw_store.sqlite
                 ├── migrations
                 ├── identity
                 ├── models / errors
                 └── stdlib sqlite3 + asyncio.to_thread

settings ──> path/timeout values only
tests    ──> RawStore public interface, never private connection fields
```

依赖约束：

- `models`、`errors`、`identity`、`protocol` 不依赖 FastAPI、Pydantic、SQLite 或 MemOS；
- `sqlite` 实现 `RawStore`，可以依赖上述模块和标准库；
- `RawStore` 不依赖 B01 HTTP/Pydantic 模型，直接接收冻结的 `AddCommand`；
- B02 不实现 `ContestOperations`，也不修改 app composition；
- 业务层以后依赖 `RawStore` protocol，不依赖 `SqliteRawStore` 私有 SQL/connection；
- migration 只能通过公开 migration runner 执行，运行模块不得散落 DDL；
- 所有数据库操作通过参数绑定，不拼接赛事输入。

## 7. 公共内部接口

计划提供：

```python
class AddDisposition(StrEnum):
    NEW = "new"
    PENDING = "pending"
    COMPLETED = "completed"

@dataclass(frozen=True, slots=True)
class StoredAddResponse:
    success: bool
    request_id: str
    user_id: str
    session_id: str

@dataclass(frozen=True, slots=True)
class UserCube:
    user_id: str
    cube_id: str
    status: str

@dataclass(frozen=True, slots=True)
class PreparedAdd:
    disposition: AddDisposition
    payload_sha256: str
    cube: UserCube
    response: StoredAddResponse | None

@dataclass(frozen=True, slots=True)
class PersistedAdd:
    request_id: str
    payload_sha256: str
    user_id: str
    session_id: str
    status: str
    messages: tuple[PersistedMessage, ...]
    response: StoredAddResponse | None

class RawStore(Protocol):
    async def is_ready(self) -> bool: ...
    async def prepare_add(self, command: AddCommand) -> PreparedAdd: ...
    async def complete_add(
        self,
        request_id: str,
        payload_sha256: str,
        response: StoredAddResponse,
    ) -> None: ...
    async def load_add(self, user_id: str, request_id: str) -> PersistedAdd | None: ...
    async def close(self) -> None: ...

class SqliteRawStore:
    @classmethod
    async def open(
        cls,
        database_path: Path,
        *,
        busy_timeout_ms: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> Self: ...
```

`RawStore` 是实际变化边界，后续可增加测试 in-memory 实现或其它持久层，而不改变编排层。B02 不提供
长期运行的 in-memory 成功实现，组件测试使用临时文件数据库。

## 8. 版本化身份与 payload 算法

### 8.1 Canonical Add payload

哈希输入固定为 UTF-8 JSON：

```json
{
  "schema": "memscope.add.v1",
  "request_id": "exact value",
  "user_id": "exact value",
  "session_id": "exact value",
  "messages": [
    {"role": "exact", "content": "exact", "timestamp": null}
  ]
}
```

序列化固定 `sort_keys=True`、`separators=(",", ":")`、`ensure_ascii=False`，不做 Unicode 或空白
规范化。`payload_sha256` 为 64 位小写 hex，另存 `payload_schema_version=1`。消息数组顺序、timestamp、
三 ID、role/content 任一变化都会改变 hash。

### 8.2 Cube ID

```text
cube_id = "cube_v1_" + sha256(user_id.encode("utf-8")).hexdigest()
```

- 相同 user 跨请求、重启和进程得到相同逻辑 ID；
- 不同 user 不共享记录；数据库对 `user_id` 和 `cube_id` 都有唯一约束；
- hash 不是加密或匿名化保证，Raw Store 仍按敏感持久数据处理；
- B05 若发现 MemOS provider ID 限制，只能增加映射字段/迁移，不得改变逻辑 ID。

### 8.3 Message ID 与顺序

```text
message_id = "msg_v1_" + sha256(canonical_json([request_id, request_position])).hexdigest()
```

- `request_position` 从 0 开始，精确保存 chunk 内顺序；
- `session_position` 在 `BEGIN IMMEDIATE` 中取当前同 user/session 最大值加一并连续分配；
- 重放不重复插入；同 session 多 chunk 按事务提交顺序衔接；
- 契约未提供并发 chunk 的权威全局序号，因此 B02 不解析 request_id 文本猜测顺序。

这些算法写入 `raw-store-v1.md` 并用固定 golden vectors 锁定。

## 9. SQLite Schema v1

```text
schema_migrations
  version PK, name, checksum, applied_at

user_cubes
  user_id PK, cube_id UNIQUE, mapping_version,
  status, created_at, updated_at

add_requests
  request_id PK, payload_schema_version, payload_sha256,
  user_id, session_id, cube_id, status, response_json,
  created_at, updated_at

raw_messages
  row_id INTEGER PK, message_id UNIQUE, request_id FK,
  user_id, session_id, request_position, session_position,
  role, content, timestamp_ms, ingested_at,
  UNIQUE(request_id, request_position),
  UNIQUE(user_id, session_id, session_position)

memos_outbox
  request_id PK/FK, cube_id FK, status, attempts,
  last_error_code, next_retry_at, created_at, updated_at
```

Schema 约束：

- foreign keys 开启，删除采用 RESTRICT；B02 不提供删除接口；
- `add_requests` 同时保存 `cube_id`，并以 `(user_id, cube_id)` 复合外键绑定唯一 user/cube 映射；
- `raw_messages` 的 `(request_id, user_id, session_id)` 复合外键保证冗余隔离键与所属请求一致；
- `memos_outbox` 的 `(request_id, cube_id)` 复合外键保证任务不会指向其它请求的 Cube；
- Add status v1 只允许 `pending|completed`；completed 必须有 `response_json`；
- outbox status v1 只允许 `pending|completed`，attempts 非负；
- 新 cube 初始 status 为 `reserved`，不表示 MemOS Cube 已创建；
- `raw_messages` 同时保存 user/session 以支持带 user 条件的隔离读取和索引；
- content、role 和所有 ID 使用 TEXT 原样存储，不截断、不全文索引；
- timestamp_ms 可空且按严格整数原值保存；应用生成时间统一为 UTC ISO-8601 `Z`；
- 建立 request、user/session/order、outbox status 所需 B-tree 索引，不创建 FTS 表。

## 10. Migration 机制

- migration 是按版本排序的不可变 Python tuple，每项包含名称、SQL statement tuple 和源码 checksum；
- 首次 open 使用 `BEGIN EXCLUSIVE` 创建 ledger 并从 0 顺序升级到当前版本；
- 每条 SQL 使用 `connection.execute`，不使用会隐式提交的 `executescript`；
- migration 与 ledger 插入、`PRAGMA user_version` 更新在同一事务提交；
- 已应用版本 checksum 不一致、版本缺口、数据库版本高于代码或 DDL 失败均 fail closed；
- 失败事务 rollback，不以部分 Schema 进入 ready；
- 重复 open 不重跑已应用 migration；并发 open 由 SQLite exclusive transaction 串行化；
- B02 不实现 downgrade；回滚使用数据库备份/删除纯开发临时库和 Git 代码回退；
- migration 错误包装为不含 SQL、路径或 SQLite 原始消息的安全异常。

## 11. 正常流程与事务边界

### 11.1 Open

```text
validate path and timeout
  → create parent directory if needed
  → open one short-lived sqlite connection
  → foreign_keys=ON, busy_timeout, WAL, synchronous=FULL
  → acquire migration transaction
  → verify/apply migrations
  → quick_check + schema version
  → close migration connection
  → READY
```

除 migration/open 外，不在 import 或 Settings 构造时创建目录或数据库。
`SqliteRawStore` 实例只保存已校验的配置和关闭状态，不长期持有 connection。每个公开数据库操作在
`to_thread` 内创建、配置并最终关闭自己的短连接；所有连接都重新设置 foreign keys、busy timeout 和
`synchronous=FULL`，并验证目标 Schema/WAL，不依赖连接间继承 PRAGMA。

### 11.2 首次 prepare_add

```text
compute canonical payload hash and stable cube/message IDs
  → BEGIN IMMEDIATE
  → request_id absent
  → INSERT/verify stable user_cubes reservation
  → allocate session positions
  → INSERT add_requests(status=pending)
  → INSERT all raw_messages
  → INSERT memos_outbox(status=pending, attempts=0)
  → COMMIT
  → return NEW + hash + cube + no response
```

任何一步失败都 rollback；不得留下孤立 request、message、cube 或 outbox。

### 11.3 重复 prepare_add

```text
BEGIN IMMEDIATE → SELECT add_requests by request_id
  ├── digest differs     → rollback/read-only end → IdempotencyConflictError
  ├── same + pending     → no write → PENDING, response=None
  └── same + completed   → parse/validate stored response → COMPLETED + response
```

重复请求不得更新 timestamps、session positions、outbox attempts 或原始消息。

### 11.4 complete_add

未来 Gateway/编排层确认外部写入成功后调用：

```text
BEGIN IMMEDIATE
  → verify request exists and digest matches
  → pending: atomically store canonical response_json,
             set add_requests=completed and outbox=completed
  → completed + same response: idempotent no-op
  → completed + different response: invariant failure
  → COMMIT
```

若外部写入成功后进程在 complete 前崩溃，outbox 保持 pending；未来 B07 依靠 provenance 和幂等
Gateway 做 at-least-once 恢复。B02 不声称跨 SQLite/MemOS exactly-once。

## 12. 异常、超时、重试、取消与恢复

计划异常：

| 类型 | code | retryable | 语义 |
|---|---|---:|---|
| `IdempotencyConflictError` | `request.conflict` | false | 同 request_id 不同 payload |
| `RawStoreUnavailableError` | `storage.unavailable` | true | DB locked/closed/I/O 暂时不可用 |
| `RawStoreInvariantError` | `storage.invariant_failed` | false | 状态/响应/关联数据不一致 |
| `MigrationError` | `storage.migration_failed` | false | Schema 版本、checksum 或 DDL 失败 |

所有异常消息固定且安全；SQLite 原始异常、SQL、DB path、payload hash、业务 ID 和消息不得进入 HTTP 或
日志。原异常只作为内部 cause 供受控调试，不序列化。

- 超时：仅 SQLite `busy_timeout`，默认 5000 ms；没有应用层重试或无限等待；
- 重试：B02 不重试事务；冲突不重试，暂时 unavailable 交由未来编排策略决定；
- 降级：无；Raw Store 写失败时绝不允许 Add 成功；
- 幂等：SQLite 内对 request/messages/outbox exactly-once；跨 MemOS 仅准备 at-least-once 恢复；
- 取消：阻塞 sqlite 工作通过 `asyncio.to_thread` 执行；调用协程取消不等于线程事务中止，事务必须自行
  完成 commit/rollback 并关闭该操作独占的短连接，调用方重试由 request_id 幂等收敛；
- 恢复：重启重新 open/migrate；pending request/outbox 保留，B02 只验证可读取，不自动派发；
- close：幂等且不需关闭共享 connection；阻止新操作，已进入 worker thread 的操作允许完成自身事务和
  连接清理；close 后 is_ready=false，其它新操作返回 safe unavailable。

## 13. 并发模型

- 项目仍默认单 Uvicorn worker，但 Raw Store 不依赖进程内锁保证正确性；
- 每次阻塞操作独占一个短连接，阻塞调用放入 thread pool；实例不跨线程共享 connection；
- 同一实例允许并发调用，写事务由 SQLite 锁和约束串行裁决，不能依赖 event-loop lock 保证正确性；
- 多实例/未来多进程正确性依赖 `BEGIN IMMEDIATE`、unique/FK/check constraints 和 busy timeout；
- 同 request 并发最多一个 `NEW`，其它为 `PENDING/COMPLETED` 或明确 conflict；
- 同 user 的不同首次请求产生同一个 cube mapping；
- 同 session 并发 chunk 的位置按获得 SQLite 写锁并提交的顺序确定；
- 不把 Python mutex、内存 cache 或 `SELECT` 后无事务判断作为唯一一致性依据；
- B02 压测线程并发，不提前承诺正式 worker 数量或吞吐。

## 14. 配置和启动校验

新增 Settings：

| 环境变量 | 类型/范围 | 默认值 | 语义 |
|---|---|---|---|
| `DATABASE_PATH` | 非空文件路径；禁止 `:memory:` 和 `file:` URI | `data/memory.db` | 本地 Raw SQLite 文件；B04 容器覆盖 `/data/memory.db` |
| `SQLITE_BUSY_TIMEOUT_MS` | int 100～60000 | 5000 | SQLite lock bounded wait，不是 HTTP 总超时 |

Settings 构造只校验值，不访问文件系统。`safe_summary()` 只增加 `database_path_kind`（relative/absolute）
和 busy timeout，不记录完整路径。测试显式使用 `tmp_path`，不依赖开发机 `.env`。

固定而不做环境开关：journal mode WAL、synchronous FULL、foreign keys ON、Schema target latest。正式硬件
和提交形态明确后，任何 durability 降级都必须单独评审并用崩溃/性能数据支持。

## 15. 可观测性与敏感数据

Raw Store 日志固定 allowlist：

- `storage_operation`：open/migrate/prepare_add/complete_add/load_add/close；
- `storage_result`：success/new/pending/completed/conflict/unavailable；
- `schema_version`；
- `raw_store_duration_ms`；
- 既有 `error_code`、`retryable`、`exception_type`。

禁止记录完整 DB path、SQL、payload/hash、request/user/session/cube/message ID、role/content、timestamp、
response JSON 或 SQLite 异常文本。组件性能按操作聚合记录，不给每条消息打日志。

## 16. 可扩展点与延后能力

- `RawStore` protocol 隔离业务编排与 SQLite；
- embedded migration 支持以后增加 provider cube ID、outbox lease 和 lifecycle 字段；
- `payload_schema_version`、cube/message ID 前缀使算法可演进且旧数据可辨识；
- pending/completed 状态为 B05 同步写入和 B07 恢复提供最小稳定语义；
- 按 user/request 的读取接口允许恢复，不开放无隔离 Raw Search；
- B03 可实现组合 `ContestOperations`，但不能绕过 RawStore 事务或改变 B01 HTTP 契约；
- 本轮不为未知决赛预建分库、分片、加密插件、事件总线或通用 ORM。

## 17. 测试与质量矩阵

| 层级 | 关键用例 | 通过标准 |
|---|---|---|
| 单元：canonical hash | 重复、字段变化、消息顺序、timestamp null、Unicode、空白 | golden vector 稳定；语义相同相等，精确变化不等 |
| 单元：身份 | cube/message ID 重复、不同输入、版本前缀、Unicode | 跨调用确定，格式固定，无原始值拼接 |
| 单元：模型 | frozen、枚举、response/disposition 不变量、UTC clock | 非法组合拒绝，不依赖框架 |
| 单元：Settings | 默认、相对/绝对路径、空/内存/URI、timeout 边界、safe summary | 构造不触碰 FS；完整路径不进摘要/错误 |
| 组件：migration | 新库、重开、并发 open、future version、checksum 篡改、DDL 失败 rollback | 原子升级；错误 fail closed；无部分 ready |
| 组件：SQLite 参数 | WAL、FULL、FK、busy timeout、Schema version | 每次 open 后符合固定值 |
| 组件：首次 Add | request/cube/messages/outbox 全量写入、原值和顺序 | 单事务提交且 disposition=NEW |
| 组件：同 payload | pending 重放、completed 重放、timestamps/outbox/messages 不变化 | 无重复行和副作用，response 可恢复 |
| 组件：冲突 | user/session/content/role/timestamp/顺序任一变化 | typed conflict；原记录完全不变 |
| 组件：complete | pending→completed、相同重复、hash/response/状态错误 | 原子双表转换；非法转换 fail closed |
| 组件：多 chunk | 同 user/session 多 request | request_position 重置，session_position 连续 |
| 一致性：重启 | prepare/complete 后 close/reopen | 数据、状态、response、cube 和顺序一致 |
| 一致性：并发 request | 双实例同/异 payload，同 user 不同 request | 单 NEW、确定 replay/conflict、单 cube、无锁外竞态 |
| 故障：事务中断 | trigger/constraint/locked DB/close 后调用 | rollback 无孤儿；bounded failure；错误脱敏 |
| 隔离 | 相同文本不同 user、错误 user load、SQL 特殊字符 | 读取必须带 user 且不串数据；参数绑定 |
| 回归：B01 | 全部 HTTP/鉴权/错误/Uvicorn 测试 | 默认仍 503，冻结契约无变化 |
| 性能测量 | file DB prepare、duplicate、complete、load，含 1/20/100 messages | 报告 P50/P95/P99、DB/WAL 大小；不设硬件相关硬断言 |

质量门禁：

```text
uv lock --check --offline
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

- 总体 coverage.py 覆盖率继续至少 95%；
- 新增 B02 模块语句覆盖至少 95%、分支覆盖至少 90%；
- SQLite 组件测试只写 pytest `tmp_path`，不写仓库 `data/`；
- 默认测试不读取 Key、外网、MemOS 源码或正式样本；
- Gate 2 报告语句/分支、事务/重启/并发用例、SQLite 版本和本机性能。

## 18. 主要风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| Add raw committed 后外部 MemOS 前后崩溃 | 重复外部写或 pending 永久存在 | durable outbox + provenance 基础；B07 实现恢复；不声明 distributed exactly-once |
| 错误 canonicalization | 同 payload 冲突或不同 payload误重放 | 明确 v1 格式、golden vectors、全字段变更测试 |
| SQLite 部分写 | 消息/outbox/cube 不一致 | 单个 `BEGIN IMMEDIATE` 事务、FK/unique/check、故障注入 rollback |
| 并发重复 request/cube | 重复消息或多 Cube | DB 唯一约束为最终裁决，不依赖内存锁 |
| 默认 Health 过早 200 | 评测开始后 Search 不可用 | B02 不组装 operations，默认保持 503 |
| pending 重放被当成功 | Add 返回但不可检索 | 显式 PENDING，无 response；未来编排层必须处理而非 success |
| provider cube ID 不兼容 | B05 接入阻塞 | 逻辑/provider ID 分层，必要时新增 migration，不改 v1 logical ID |
| WAL/FULL 性能不够 | Add 超时 | 先保正确性并测量；正式硬件后以数据评审 synchronous/批量策略 |
| busy timeout 过长或过短 | 请求堆积或频繁锁错误 | 有界可配置、默认 5 s、组件锁竞争测试；最终值等待主办方条件 |
| 原始对话和 ID 泄漏 | 隐私、合规或取消资格风险 | 文件目录忽略、参数绑定、日志/错误 allowlist、禁止提交 DB/WAL/SHM |
| migration 漂移/篡改 | 旧数据被错误解释 | ledger checksum、future/gap 检测、fail closed、无 downgrade |
| `to_thread` 取消误解 | HTTP 已取消但事务仍提交 | 每操作独占短连接，事务自洽并最终关闭，依靠 request_id 重试收敛 |

## 19. 回滚方式

- Gate 1 批准后从 `2f846a0...` 创建独立 B02 分支；B01 验收分支和提交保持不变；
- 不新增依赖、不修改锁文件、不触碰正式数据；
- 测试数据库全部位于 `tmp_path`，失败后由 pytest 清理；
- 开发期未交付数据库可删除后重建；任何需要保留的数据先备份，禁止自动 downgrade；
- 实施提交按“Schema/模型”“SQLite 事务”“测试/文档”等单一目的拆分；
- 若已应用 Schema 或公共 RawStore 接口需变更，新增 forward migration/修订提交并重新 Gate 1；
- 禁止破坏性 Git 历史重写和对用户真实数据库执行无确认删除。

## 20. Gate 1 待审批点

请明确批准或修改：

1. B02 只交付 RawStore 基础，不实现/组装 `ContestOperations`，默认 HTTP 继续 503；
2. 使用 stdlib sqlite3、async `RawStore` + `asyncio.to_thread`；每操作独占短连接，不引入 ORM/Alembic/aiosqlite；
3. 采用本文 canonical Add v1 和完整 SHA-256 幂等算法；
4. 同 payload 状态为 NEW/PENDING/COMPLETED，不同 payload 抛 typed conflict；HTTP 409 延后到组装 Batch；
5. `cube_v1_<64hex>` 作为逻辑 cube ID，provider 约束由 B05 验证；
6. 消息保存 request_position，并按 SQLite 事务提交顺序分配 session_position；
7. 批准 Schema v1 五张表、复合外键一致性约束、索引及 pending/completed 状态模型；
8. prepare 与 complete 的事务边界，以及 SQLite 内 exactly-once/外部 at-least-once 边界；
9. outbox 只建 durable 记录，不实现 B07 worker、lease、retry；
10. 默认 `data/memory.db`、busy timeout 5000 ms、WAL + FULL + FK ON；
11. migrations 使用内嵌 statement tuple + checksum ledger，只 forward、失败 fail closed；
12. 取消不保证停止已进入 thread 的 SQLite 事务；该操作以独占短连接完成清理，并以持久幂等收敛；
13. 不做 FTS/Raw Search/HTTP 成功路径/正式样本运行；
14. 不新增依赖、不修改 B01 冻结代码，批准本文文件范围与测试矩阵；
15. 批准后才创建 `batch/b02-raw-identity`，完成后停在 Gate 2，不进入 B03。

## 21. Definition of Done

B02 进入 `Code Review` 前必须同时满足：

1. `RawStore` protocol、SQLite 实现、typed errors 和冻结模型职责清晰且不依赖 FastAPI/MemOS；
2. 新数据库自动原子迁移到 Schema v1，重开无副作用，篡改/future/失败 migration fail closed；
3. WAL、FULL、foreign keys、busy timeout 和当前 Schema 经过组件测试验证；
4. 首次 prepare 原子写入 add_request、全部 raw_messages、user_cube 和 pending outbox；
5. canonical payload、cube ID、message ID 有固定版本和 golden vector；
6. 同 payload pending/completed 重放不产生任何重复或 timestamp 更新；
7. 不同 payload 冲突不会改变既有数据；
8. complete 原子更新 request/response/outbox，重复 complete 幂等，非法状态 fail closed；
9. 同 session 多 chunk 顺序、跨 user 隔离、特殊字符和 exact timestamp 均通过；
10. 同实例/双实例并发同 request/cube 测试通过，无共享连接竞态、重复行或未分类 locked 错误；
11. 故障注入证明事务 rollback 后无孤儿记录，错误与日志无业务内容/ID/path/SQL；
12. close/reopen 后数据、状态、response、cube 和顺序完全恢复；
13. Settings/.env/README、RawStore interface、ADR、CODEMAP、PROJECT_CONTEXT 与实现一致；
14. `pyproject.toml`、`uv.lock`、B01 HTTP/operations、MemOS tag/commit 均未变化；
15. Ruff、Mypy strict、Pytest、总体和新增模块覆盖门禁全部通过；
16. Gate 2 报告 SQLite 版本、测试结果、覆盖率、性能、DB/WAL 大小、偏差和限制；
17. 默认 Uvicorn 仍可无 Key 启停，合法比赛接口仍为明确 503；
18. 未创建 B03 分支、Gateway、worker、FTS 或模型实现。

## 22. 重新评审触发器

发生任一情况立即停止并重新 Gate 1：

- 修改 B01 HTTP、`ContestOperations` 或默认 readiness/成功语义；
- 修改本文 RawStore 公共接口、canonical hash、ID 算法、Schema/状态机或事务边界；
- 引入 ORM、aiosqlite、Alembic 或其它第三方依赖；
- 实现 FTS、Gateway、outbox worker、后台任务、HTTP 409/成功路径或 app lifespan 组装；
- 改变 WAL/FULL、busy timeout 默认、取消或 distributed consistency 语义；
- 需要读取/修改 MemOS 源码、正式样本或扩大 allowed changes；
- MemOS tag/commit 或 hard dependency 改变；
- 无法达到批准的迁移、并发、故障、覆盖率或性能完成标准。

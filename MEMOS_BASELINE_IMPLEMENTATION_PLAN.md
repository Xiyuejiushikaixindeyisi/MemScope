# MemOS Baseline 最终实现方案

> 状态：Final，D01～D15 评审结论已合并。  
> 当前目标：先完成无 API/Key 可联调的 `memos-scaffold-v0`；主办方提供真实 API/Key 后完成 MemOS 全链路调测并冻结 `baseline-v0`；之后基于 baseline 逐项调优。  
> 实施节奏：由用户主动控制；本文只规定阶段依赖、完成标准和技术边界。

历史方案：

- [原始实现方案](./docs/achieve/MEMOS_BASELINE_IMPLEMENTATION_PLAN.md)
- [v0 评审稿](./docs/achieve/MEMOS_BASELINE_V0_IMPLEMENTATION_PLAN.md)

## 1. 总体目标

主方案固定为：

```text
Contest Adapter + MemOS + Qdrant + Neo4j + 主办方模型 API
```

系统分三个阶段交付：

### 1.1 `memos-scaffold-v0`

在没有主办方 API/Key 的情况下完成真实项目骨架：

- 比赛 Add/Search/Health Adapter；
- 固定版本的 MemOS、Qdrant、Neo4j；
- user_id、session_id 和 MemCube 生命周期；
- 比赛协议与 MemOS 协议双向转换；
- Fake MemOS Client 和 Mock Model API；
- Raw Store、幂等、outbox 和故障策略；
- Docker Compose profiles、测试和提交文档骨架。

Mock 结果只证明工程接线，不产生 baseline 分数。

### 1.2 `baseline-v0`

主办方提供 API/Key 后：

- 使用真实模型资源运行 MemOS；
- 完成真实同步 Add/Search；
- 完成隔离、持久化、读后写和返回格式验证；
- 跑通代表性样本、数十题和公开 1000 题代理评测；
- 记录准确率、延迟、token、限流、错误和资源信息；
- 冻结代码、MemOS commit、模型、配置、镜像和报告。

只有该冻结版本命名为 `baseline-v0`。

### 1.3 baseline 后调优

每次只改变一个主要变量，记录题目正负翻转、性能和故障率，与 baseline-v0 对比后决定是否升级。

## 2. 架构

```text
评测机
  │
  ├── GET  /health
  ├── POST /add
  └── POST /search
          │
          ▼
Contest Adapter（FastAPI，唯一对外入口）
  ├── 契约校验、可选鉴权和响应转换
  ├── request_id 幂等和 payload 冲突检测
  ├── user_id → MemCube 映射
  ├── 超时、限流、熔断和故障策略
  ├── 结果过滤、去重和截断
  │
  ├── Raw Store（SQLite + 可选 FTS5）
  │     ├── 原始消息和顺序
  │     ├── 幂等、Cube 映射和 outbox
  │     ├── MemOS 写入状态和恢复依据
  │     └── 可关闭的 Raw Search/fusion 实验能力
  │
  └── MemOS Gateway
        ├── FakeMemOSClient
        └── RealMemOSClient
              │
              ▼
          MemOS Server
            ├── Qdrant：语义向量候选召回
            ├── Neo4j：关系、版本和生命周期
            └── Model Provider
                  ├── Mock Chat/Embedding（无 Key）
                  └── Organizer API（真实调测）
```

### 2.1 组件定位

- **Adapter**：屏蔽比赛契约与 MemOS API 差异，不生成答案，不实现平台 Judge。
- **MemOS**：baseline-v0 的主记忆系统，负责抽取、结构化、生命周期和检索。
- **Qdrant**：保存 Embedding，提供语义候选召回。
- **Neo4j**：保存实体关系、版本状态和 Update/Forget 生命周期信息。
- **Raw Store**：保存赛事原始输入、幂等和恢复状态，不替代 MemOS 的当前有效记忆。

## 3. 技术选型

- Python 3.11；
- FastAPI + Pydantic；
- Uvicorn，baseline 默认单 worker；
- SQLite WAL + FTS5；
- MemOS 官方仓库：`git@github.com:MemTensor/MemOS.git`；
- Qdrant、Neo4j 使用固定镜像版本和 digest。

单 worker 用于降低 SQLite 写竞争、Cube 初始化竞争、进程内锁和后台恢复任务的复杂度。取得正式并发信息后，通过压测决定是否增加 worker；扩容前必须保证幂等、Cube 创建、outbox 和限流状态跨进程安全。

开发阶段可以通过 SSH 克隆 MemOS；提交包不得依赖裁判环境的 GitHub SSH Key。最终使用固定 commit 的 vendored 源码，或无需认证且带完整性校验的固定源码包。

## 4. Adapter 性能边界

Adapter 是比赛请求的必经路径，从第一版开始拆分记录：

```text
total_duration
contract_validation_duration
raw_store_duration
cube_resolution_duration
memos_duration
fusion_and_format_duration
```

本地暂定目标：剔除 MemOS/模型等待后，Adapter 自身 Add/Search P95 均不超过 50 ms。取得正式机器和并发信息后重新校准。

baseline 冻结后按数据评估：

1. HTTP 连接池和 keep-alive；
2. JSON 序列化和响应长度；
3. SQLite 索引、事务和批量写入；
4. Cube 映射缓存；
5. 实验性双路并行 Search；
6. 去重、窗口和候选上限；
7. Uvicorn worker 数量。

## 5. 服务与部署 Profiles

| Profile | 服务 | 用途 |
|---|---|---|
| `core` | memory-api | Adapter/Raw 单独开发与应急验证 |
| `mock` | memory-api + memos + qdrant + neo4j + mock-model-api | 无 Key 真实 MemOS 接线 |
| `organizer` | memory-api + memos + qdrant + neo4j | 真实 API/Key 调测与提交候选 |
| `contingency-raw` | memory-api | API 始终不可用时的应急提交 |

约束：

- 只暴露 `memory-api:8080`；
- 其它服务只在 Compose 内网可见；
- MemOS 必须等待数据库和当前模型 profile 健康；
- organizer profile 不包含 Mock；
- 禁止源码 bind mount、默认数据库密码和运行时下载；
- 不使用 `main`、`latest` 或未记录的依赖版本；
- 如果主办方不支持 Compose，单独评审部署收缩方案。

## 6. 无 Key 联调

采用两层替身，分别验证 Adapter 和真实 MemOS 栈。

### 6.1 Fake MemOS Client

Adapter 内部替换 RealMemOSClient，用于验证：

- Add/Search 请求字段转换；
- user/cube/session 映射；
- Search 响应格式化；
- 空结果、业务失败、429、5xx、超时和非法 JSON；
- 熔断、幂等和 Raw fallback。

此层不启动真实 MemOS。

### 6.2 Mock Model API

真实 MemOS、Qdrant、Neo4j 保持运行，只替换尚未提供的模型资源：

- Mock Chat 返回固定合法的结构化抽取结果；
- Mock Embedding 生成固定维度的确定性向量；
- Rerank 仅在固定 MemOS 版本必需时实现；
- 支持注入 429、5xx、超时和非法输出。

该层验证 MemOS 初始化、模型协议、Embedding 维度、数据库写入、Cube 和 Search 接线，不评价真实抽取、语义召回和 Update/Forget 质量。

如果 MemOS 的 LLM 输出 Schema 高度动态，优先 mock MemOS 的 LLM client 边界，不维护脆弱的通用 Prompt 解析器。

## 7. MemOS 接入

### 7.1 版本固定

搭建时记录：

- MemOS tag、commit 和源码哈希；
- 必要补丁和原因；
- Qdrant/Neo4j 镜像 digest；
- Python 与依赖锁；
- THIRD_PARTY_NOTICES。

### 7.2 User/Cube 生命周期

1. 对比赛 user_id 做稳定、带版本前缀的 SHA-256 映射；
2. SQLite 保存 user_id、cube_id 和创建状态；
3. 首次 Add 前创建/注册 MemOS user 和 Cube；
4. 建立 owner/write/read 权限；
5. 使用持久化唯一约束防止并发重复创建；
6. Search 前校验 Cube 属于当前 user；
7. Adapter 对 MemOS 返回 provenance 再次校验。

### 7.3 Add 字段转换

| 比赛字段 | MemOS 处理 |
|---|---|
| `user_id` | MemOS user_id + Cube 映射 |
| `session_id` | MemOS session_id |
| `role/content` | 原样保留 |
| `timestamp` | 保存原毫秒值，并转换为 MemOS `chat_time` |
| `request_id` | Adapter 幂等键，并写入 MemOS provenance/info |
| message index | 生成稳定 message_id/provenance |

明确使用：

- `writable_cube_ids`；
- `async_mode=sync`；
- 可配置且最终冻结的 `mode=fast/fine`。

### 7.4 Search 参数

显式配置并记录：

- `readable_cube_ids`；
- candidate top_k；
- fast/fine/mixture mode；
- relativity；
- dedup；
- rerank；
- preference memory；
- neighbor discovery。

禁止由 MemOS 默认值静默决定比赛行为。

### 7.5 Search 响应转换

- 只解析明确启用的记忆类型；
- id/content 必须非空；
- score 必须有限且越大越相关；
- created_at 缺失或非法时省略，不伪造；
- 过滤非当前 user/cube；
- 过滤 deleted/archived 等无效状态；
- 数量不超过比赛 top_k；
- 不调用 Chat 生成最终答案。

## 8. Raw Store

### 8.1 必需范围 D04-A

- 同步保存原始消息；
- request_id 幂等和 payload 冲突检测；
- user/Cube 映射；
- MemOS 写入状态；
- durable outbox 和恢复依据。

### 8.2 实验范围 D04-B

- SQLite FTS5 fallback；
- 原始证据补充；
- MemOS/Raw 双路 RRF 融合。

D04-B 默认可用但必须可关闭；baseline-v0 正常 Search 不启用融合。

### 8.3 核心表

```text
add_requests
  request_id, payload_sha256, user_id, session_id,
  status, response_json, created_at

raw_messages
  message_id, request_id, user_id, session_id,
  session_position, role, content, timestamp_ms, ingested_at

raw_messages_fts
  content index + user_id/raw row reference

memos_outbox
  request_id, cube_id, status, attempts,
  last_error, next_retry_at, updated_at

user_cubes
  user_id, cube_id, status, updated_at
```

### 8.4 一致性边界

- 同 request_id + 同 payload：返回已保存响应；
- 同 request_id + 不同 payload：返回 409；
- SQLite 内部通过事务实现 exactly-once；
- SQLite 与外部 MemOS 不声明分布式 exactly-once；
- MemOS 路径使用 outbox、provenance 和 Search 去重，提供可恢复的 at-least-once。

## 9. Add 流程

### 9.1 正常流程

1. 严格校验比赛请求；
2. 计算规范化 payload hash；
3. SQLite 原子写入 add_request、raw_messages、可选 FTS 和 outbox；
4. 创建或获取 user Cube；
5. 调用 MemOS 同步 Add；
6. 校验 HTTP 状态和 MemOS 业务 code；
7. 更新 outbox/memos_status；
8. 按配置执行首个 Cube、测试环境或抽样读回；
9. 返回赛事标准响应。

正常请求不固定追加一次 Search，避免为约 5,562 次 Add 额外制造同量级的 Search/Embedding 调用。Add 后立即可检索由契约测试、新 Cube 首次验证和可配置抽样检查；异常时可临时开启全量读回。

### 9.2 MemOS Add 失败

```text
MEMOS_ADD_FAILURE_POLICY=strict | raw_fallback
```

- `strict`：返回 5xx，用于 baseline 调测和冻结；
- `raw_fallback`：Raw 已同步可检索时返回成功并标记 `raw_only`，用于故障测试和可能的最终可用性策略。

触发 Raw fallback 的运行不能作为干净的 baseline-v0 成绩冻结。最终提交模式在取得主办方失败策略后确定。

Raw Store 失败必须返回 5xx。

## 10. Search 流程

### 10.1 baseline-v0

- 正常路径只使用 MemOS Search，形成可解释的 MemOS baseline；
- MemOS 失败时使用 Raw FTS fallback；
- 两条路径都严格限制 user_id/cube；
- 完成状态过滤、去重、排序、截断和格式转换；
- 不按 session_id 过滤；
- 返回数量不超过请求 top_k。

### 10.2 baseline 后融合实验

`FUSION_ENABLED=true` 时同时运行 MemOS 和 Raw FTS，使用 Reciprocal Rank Fusion 合并两路排名。禁止直接相加 BM25 和 MemOS relativity。

### 10.3 Options

Options 可以用于检索扩展和候选覆盖，但服务不选择选项、不返回最终答案。

### 10.4 K 消融

至少测试：

```text
5 / 10 / 20 / 40 / 100
```

根据代理准确率、旧值泄漏、噪声、响应字符数和延迟共同冻结。

### 10.5 全失败

```text
SEARCH_FAILURE_POLICY=strict | empty
```

- `strict`：返回 5xx，用于 baseline 调测；
- `empty`：返回 HTTP 200 + `{"data":[]}`，用于评测器会因单次 5xx 中断整轮时的可用性策略。

两种模式都记录内部错误，最终提交值等待主办方策略。

## 11. Health 与鉴权

| Profile | `/health` 返回 2xx 的条件 |
|---|---|
| `core` / `contingency-raw` | Adapter + Raw Store 可用 |
| `mock` | Adapter、Raw、MemOS、Qdrant、Neo4j、Mock Model API 全部可用 |
| `organizer` baseline | Adapter、Raw、MemOS、Qdrant、Neo4j、真实模型探测全部可用 |

额外提供 `/health/details` 显示组件状态；赛事仍只依赖 `/health`。Health 无鉴权。

比赛接口鉴权默认关闭，同时支持配置 Bearer、Token 和 X-Api-Key。所有 Key 只从环境变量读取，不进入源码、镜像和日志。

## 12. 配置

```text
APP_PROFILE=mock | organizer | core | contingency-raw
HOST=0.0.0.0
PORT=8080
DATABASE_PATH=/data/memory.db

MEMOS_ENABLED=true
MEMOS_BASE_URL=http://memos:8000
MEMOS_ADD_TIMEOUT=...
MEMOS_SEARCH_TIMEOUT=...
MEMOS_ADD_MODE=...
MEMOS_SEARCH_MODE=...
MEMOS_RELATIVITY=...
MEMOS_RERANK=...

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=
RERANK_BASE_URL=
RERANK_API_KEY=
RERANK_MODEL=

RAW_STORE_ENABLED=true
RAW_FALLBACK_ENABLED=true
FUSION_ENABLED=false
SEARCH_RETURN_K=...
MEMOS_ADD_FAILURE_POLICY=strict
SEARCH_FAILURE_POLICY=strict
STRICT_HEALTH=true

CONTEST_AUTH_MODE=none
CONTEST_API_KEY=
```

启动层负责将统一模型变量显式翻译为固定 MemOS 版本实际读取的变量。日志只能记录配置是否存在，不记录值。

## 13. API/Key 到位后的门控

### 13.1 Capability Probe

- Base URL 和鉴权；
- Chat completion；
- JSON/structured output；
- Embedding endpoint、模型和维度；
- Rerank 是否存在及协议；
- 429、5xx、超时和连接复用；
- 容器内可达性。

### 13.2 最小链路

1. 创建测试 user/Cube；
2. Add 一条事实；
3. 检查 HTTP 和 MemOS 业务响应；
4. Search 同一事实；
5. 重启后再次 Search；
6. 使用独立测试命名空间。

### 13.3 代表性样本

- LoCoMo 单跳、时序、多跳各 1 个；
- MemOps Remember、Update、Forget、Reflect 各 1 个。

七类样本全部通过后才扩大到数十题；数十题 MemOS Add/Search 成功率达到 100% 后才运行 1000 题并冻结 baseline。

## 14. Baseline 冻结

baseline 报告至少包含：

- Git commit；
- MemOS tag/commit 和源码哈希；
- Qdrant/Neo4j 镜像 digest；
- 模型名称、用途和非密钥配置；
- Add/Search 和 Adapter 分段 P50/P95/P99；
- 模型调用次数和 token；
- 429、5xx、超时；
- MemOS 成功率和 Raw fallback 比例；
- 总体代理分；
- LoCoMo single/temporal/multi-hop；
- MemOps Remember/Update/Forget/Reflect；
- MemOps eval axis；
- 返回 K、平均响应字符数；
- 错误分类和已知限制。

正常 baseline 回归要求 MemOS Add/Search 成功率 100%、Raw fallback 为 0。公开重建包报告必须标记 `official=false`。

## 15. 调优规则

1. 从 baseline-v0 创建实验版本；
2. 一次只改一个主要变量；
3. 先跑小样本，再跑固定验证集；
4. 记录题目正翻转和负翻转；
5. 合规、隔离或超时退化则拒绝；
6. 保留集有收益才进入候选。

建议顺序：

1. MemOS API、格式和同步稳定性；
2. Add fast/fine 和成本；
3. Search top_k、relativity、dedup、rerank；
4. MemOS/Raw RRF；
5. Update/Forget 状态过滤；
6. temporal/multi-hop 证据组织；
7. Adapter、并发、超时和熔断；
8. 最后考虑更换模型或大改 prompt。

## 16. 测试与验收

### 16.1 契约

- Health 2xx；
- Add ID 原样回显，success 为 boolean；
- Search 顶层对象和 data 数组；
- id/content 非空；
- score 有限；
- created_at 合法或省略；
- top_k 上限；
- options/timestamp 可选；
- 无结果空数组；
- Search 不生成最终答案。

### 16.2 一致性和隔离

- 同 request_id 同 payload；
- 同 request_id 不同 payload；
- 同 session 多 chunk；
- Add 后立即 Search；
- 服务重启；
- 并发创建 Cube；
- 多 user 相同/不同文本；
- MemOS、Raw、融合路径分别验证隔离。

### 16.3 故障

- 429、5xx、超时和断连；
- HTTP 200 + 业务失败；
- 非法 JSON/结构化输出；
- Embedding 维度不匹配；
- Qdrant/Neo4j 未就绪；
- Add 成功但 Search 不可见；
- strict/raw_fallback；
- strict/empty；
- Docker 重启恢复。

### 16.4 能力

- LoCoMo 单跳、时序、多跳；
- MemOps Remember、Update、Forget、Reflect；
- 旧值、新值、tentative、retracted；
- 过遗忘、多目标绑定和噪声；
- FTS 特殊字符。

## 17. 实施阶段

推进节奏由用户主动控制。未经明确指令，不自动进入下一阶段。

### 阶段 I：Adapter 和 Fake Client

完成 Adapter 契约、MemOS Gateway、Fake Client、Raw Schema 和基础 Compose。

退出条件：Fake Client 路径通过契约 Smoke。

### 阶段 II：真实 MemOS 无 Key 骨架

启动 MemOS/Qdrant/Neo4j，完成 Cube、字段转换和 Mock Model API。

退出条件：真实 MemOS 栈完成至少一条 Mock Add/Search。

### 阶段 III：可靠性与 Scaffold 冻结

完成 Raw Store、可选 FTS、幂等、outbox、故障策略、重启和隔离测试。

退出条件：形成 `memos-scaffold-v0`。

### 阶段 IV：真实 API 与 baseline-v0

完成 capability probe、最小链路、七类样本、数十题和 1000 题门控。

退出条件：满足第 14 节冻结条件并标记 `baseline-v0`。

### 阶段 V：调优和提交冻结

按第 15 节实验；完成干净构建、冷启动、Smoke、文档、许可证和 solution.zip。

## 18. 提交目录

```text
solution/
├── INSTRUCTION.md
├── SDD.md
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── THIRD_PARTY_NOTICES.md
├── code/
│   ├── adapter/
│   ├── raw_store/
│   ├── memos_gateway/
│   ├── mock_model_api/
│   └── tests/
├── vendor/
│   └── memos/
└── scripts/
    ├── smoke.py
    ├── capability_probe.py
    ├── run_proxy_eval.sh
    └── package.sh
```

## 19. 主要风险与回退

| 风险 | 影响 | 回退 |
|---|---|---|
| API/Key 到达太晚 | 无法完成真实 baseline | 保持 scaffold；`contingency-raw` 应急提交 |
| API 协议不兼容 | MemOS 初始化或解析失败 | provider adapter 和能力探测 |
| 无 Embedding API | MemOS Search 无法工作 | 预装小型本地 Embedder 或 Raw FTS；不运行时下载 |
| MemOS Add 200 但未入库 | 数据缺失 | 业务 code、首 Cube/抽样读回和 Raw Store |
| Cube/权限错误 | 空结果或跨用户 | 持久化映射、ACL 测试和二次过滤 |
| 同步 Add 太慢 | 全量超时 | fast/fine 消融、总超时和可配置 fallback |
| Update/Forget 泄漏 | MemOps 失分 | MemOS 状态过滤和后续状态层 |
| Compose 不支持 | 四服务无法部署 | 重新评审部署收缩或应急 profile |
| 构建/运行无外网 | 依赖不可获得 | 固定并预装依赖，禁止运行时下载 |
| Adapter 开销过高 | Add/Search 超时 | 分段测量后专项优化 |
| 返回过长 | Answer 超上下文或噪声 | K 和总字符数消融 |

`contingency-raw` 只用于外部资源始终不可用时避免无法参赛，不命名为 MemOS baseline-v0。

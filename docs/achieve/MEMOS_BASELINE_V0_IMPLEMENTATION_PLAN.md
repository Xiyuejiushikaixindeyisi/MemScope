# MemOS Baseline 实现方案（评审稿 v2）

> 文档状态：Draft，评审通过后开始搭建。  
> 比赛周期：6 天，比赛已经开始。  
> 当前状态：主办方尚未提供模型 API、Key、限流、超时、机器资源、网络和鉴权信息。  
> 项目目标：现在先完成基于 MemOS 的项目骨架和无 Key 联调能力；拿到主办方 API/Key 后完成真实 MemOS 调测，形成 baseline-v0；之后所有算法和工程优化都与 baseline-v0 对比。

## 1. 目标澄清

本方案不把 Raw Store 作为最终 baseline 的主记忆系统。主路线始终是：

```text
赛事 Adapter + MemOS + Qdrant + Neo4j + 主办方模型 API
```

由于目前没有 API/Key，项目分为三个明确阶段：

### 阶段 A：MemOS Scaffold（现在完成）

这是“待接真实模型的工程骨架”，不是最终性能 baseline。

完成内容：

- 比赛 Add/Search/Health Adapter；
- MemOS 固定版本和部署栈；
- user_id → MemCube 的创建、权限和映射；
- 比赛消息到 MemOS 请求的字段转换；
- MemOS 响应到比赛 Search 响应的转换；
- Mock Model API 和 Fake MemOS，用于无 Key 接线和故障测试；
- Raw Store，用于原始证据、幂等、审计和故障回退；
- Docker Compose、配置、测试和提交文档骨架。

阶段 A 的目标是：拿到 API/Key 后原则上只需要填写配置和修正模型兼容差异，不重新设计项目。

### 阶段 B：baseline-v0（拿到 API/Key 后形成）

完成内容：

- 使用真实主办方 Chat/Embedding/Rerank 资源启动 MemOS；
- 验证同步 Add 后真实 MemOS 立即可检索；
- 验证 Cube、用户隔离、时间字段和返回格式；
- 运行 Smoke、代表性样本和公开 1000 题代理评测；
- 记录准确率切片、延迟、超时、token、限流和失败率；
- 冻结 MemOS commit、模型配置、prompt、参数和 Docker 镜像。

这个冻结版本才命名为 `baseline-v0`。

### 阶段 C：baseline 优化

每次只修改一个主要变量，与 baseline-v0 做题目翻转和性能对比，例如：

- MemOS fast/fine Add；
- 检索 top_k 和 relativity；
- MemOS/Raw 双路融合；
- Update/Forget 状态处理；
- rerank、去重和窗口；
- timeout、并发和熔断。

## 2. 项目成功标准

### 2.1 Scaffold 完成标准（无 Key）

1. `docker compose up` 可以启动 Adapter、MemOS、Qdrant、Neo4j 和 Mock Model API；
2. 对外只暴露 Adapter 端口，默认 `8080`；
3. Adapter 的 Health/Add/Search 契约测试全部通过；
4. Fake MemOS 路径可验证请求转换、响应转换、超时和错误回退；
5. 如果 Mock Model 能满足所固定 MemOS 版本的结构化输出，完整 MemOS 栈可以完成至少一条 Add/Search；
6. Mock 只用于工程联调，任何 Mock 结果不得作为 baseline 分数；
7. 真实模型配置全部通过环境变量注入；
8. 切换 `MODEL_PROFILE=organizer` 时不需要修改业务代码；
9. Raw Store 在 MemOS 不可用时仍能保存和返回原始证据；
10. INSTRUCTION、SDD 和测试框架已经具备。

### 2.2 baseline-v0 完成标准（有 Key）

1. 真实 MemOS Add/Search 端到端通过；
2. Add 返回 HTTP 200 前，真实 MemOS 记忆已经可检索；
3. MemOS Add 返回成功后进行读回验证，不能只相信 HTTP 200；Raw 可检索不能替代此项验收；
4. 相同 request_id 重试不产生可见重复结果；
5. 不同 user_id 零串扰；
6. Search 只返回证据，不生成最终答案；
7. 公开 1000 题代理评测完整跑通；
8. 形成 benchmark、operation 和 eval axis 切片；
9. 正常 baseline 回归中 MemOS Add/Search 成功率为 100%、Raw fallback 为 0；同时记录调用次数、token、P50/P95/P99、429、5xx 和超时；
10. Docker 冷启动、故障回退和干净环境复现通过；
11. 固定代码、依赖、模型、配置和报告，生成 `baseline-v0` tag。

## 3. 总体架构

```text
评测机
  │
  ├── GET  /health
  ├── POST /add
  └── POST /search
          │
          ▼
Contest Adapter（FastAPI，唯一对外入口）
  ├── 契约校验与响应转换
  ├── 可选比赛鉴权
  ├── request_id 幂等和 payload 冲突检测
  ├── user_id → MemCube 映射
  ├── 超时、限流、熔断和降级
  ├── 结果过滤、融合、去重和截断
  │
  ├── Raw Store（SQLite + FTS5）
  │     ├── 同步保存原始消息
  │     ├── 保留 session、role、顺序和 timestamp
  │     ├── 保存 MemOS 写入状态和 outbox
  │     └── MemOS 异常时提供合法证据回退
  │
  └── MemOS Gateway
        ├── FakeMemOSClient（Adapter 单测）
        └── RealMemOSClient
              │
              ▼
          MemOS Server
            ├── MemCube / lifecycle / retrieval
            ├── Qdrant
            ├── Neo4j
            └── Model Provider
                  ├── Mock OpenAI-compatible API（无 Key）
                  └── Organizer API（有 Key）
```

架构定位：

- MemOS 是 baseline-v0 的主记忆系统；
- Raw Store 是可靠性、幂等、审计和回退层；
- Fake/Mock 只解决无 Key 开发，不代表真实模型行为；
- Adapter 屏蔽比赛契约与 MemOS API 的差异。

### 3.1 Adapter 性能边界

Adapter 是比赛请求的必经路径，必须从第一版开始独立测量其耗时，避免把 Adapter 开销误归因于 MemOS 或模型。

每个请求至少拆分记录：

```text
total_duration
contract_validation_duration
raw_store_duration
cube_resolution_duration
memos_duration
fusion_and_format_duration
```

baseline 阶段先保证正确性和可观测性，不提前进行复杂优化；baseline 冻结后，根据分段数据依次评估：

- HTTP 连接池和 keep-alive；
- JSON 序列化与响应体大小；
- SQLite 索引、事务范围和批量写入；
- Cube 映射缓存；
- MemOS/Raw 双路并行 Search；
- 去重、窗口拼接和格式转换的候选上限；
- Uvicorn worker 数量。

本地暂定目标：剔除 MemOS/模型等待时间后，Adapter 自身 Add 和 Search 的 P95 分别不超过 50 ms。该目标在取得正式机器和并发信息后重新校准。

## 4. 服务与容器

### 4.1 Scaffold Compose

| 服务 | 职责 | 默认对外暴露 |
|---|---|---|
| `memory-api` | 比赛 Adapter + SQLite Raw Store | `8080` |
| `memos` | 固定版本的 MemOS REST 服务 | 否 |
| `qdrant` | MemOS 向量存储 | 否 |
| `neo4j` | MemOS 图存储 | 否 |
| `mock-model-api` | 无 Key 模型协议替身，只用于开发测试 | 否，仅 mock profile |

Compose profile：

```text
core       memory-api
mock       memory-api + memos + qdrant + neo4j + mock-model-api
organizer  memory-api + memos + qdrant + neo4j
```

如果主办方最终不支持 Compose，再将 organizer profile 合并或改成单容器；当前先按 MemOS 官方自建形态完成骨架。

D08 附加约束：

- 只有 `memory-api:8080` 对外暴露；
- MemOS 必须等待 Qdrant、Neo4j 和当前模型 profile 真正健康后再 ready；
- organizer profile 不得包含 Mock 服务；
- 提交配置不得使用源码 bind mount、默认数据库密码或运行时下载；
- 保留 `core`/`contingency-raw` 应急 profile；
- 如果主办方不支持 Compose，再单独评审部署收缩方案。

### 4.2 版本固定

搭建前必须记录：

- MemOS tag 和 commit；
- MemOS 源码引入方式；
- Qdrant/Neo4j 镜像 tag 和 digest；
- Python 和依赖锁文件；
- MemOS 需要的补丁及其原因；
- THIRD_PARTY_NOTICES。

不得直接依赖 `main` 或 `latest`。

## 5. 无 Key 开发策略

无 Key 阶段使用两层测试替身，避免把“Adapter 已接好”和“MemOS 算法已验证”混为一谈。

### 5.1 Fake MemOS Client

直接替换 Adapter 内的 MemOS Gateway，用于测试：

- Add 请求字段转换；
- user/cube/session 映射；
- Search 响应解析；
- 空结果；
- HTTP 200 但业务 code 失败；
- 429、5xx、慢响应、断连、非法 JSON；
- 熔断和 Raw fallback。

这一层不启动真实 MemOS，目标是让比赛 Adapter 先稳定。

### 5.2 Mock Model API

为真实 MemOS Server 提供最小 OpenAI-compatible Chat/Embedding 接口：

- Chat 返回固定、合法的结构化抽取结果；
- Embedding 对输入生成固定维度的确定性向量；
- Rerank 只有在固定 MemOS 版本确实需要时才实现；
- 支持注入 429、5xx、超时和非法结构化输出。

限制：

- Mock 只验证 MemOS 初始化、网络、Schema、数据库写入和查询接线；
- 不评价记忆抽取质量、冲突处理或语义检索能力；
- 如果 MemOS prompt 对输出 Schema 高度动态，优先在 LLM client 层 mock，不为追求“假端到端”编写大量脆弱规则。

### 5.3 配置 profile

```text
MODEL_PROFILE=mock | organizer

# Organizer profile：拿到资源后填写
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
```

Adapter/启动脚本负责把统一变量显式翻译为所固定 MemOS 版本真正读取的变量，例如 `MEMRADER_API_*`、`MOS_EMBEDDER_*`，不能假设名称自动兼容。

## 6. MemOS 接入设计

### 6.1 Cube 和用户生命周期

1. 对 user_id 做稳定、带版本前缀的 SHA-256 映射，生成合法 cube_id；
2. SQLite 保存 user_id、cube_id 和创建状态；
3. 首次 Add 前创建/注册 MemOS user 和 Cube；
4. 建立 owner/write/read 权限；
5. 通过唯一约束和持久化状态防止并发重复创建；
6. Search 前校验目标 Cube 属于当前 user；
7. Adapter 收到 MemOS 结果后再次校验 user/cube provenance。

不得仅因为 MemOS Add 返回 200 就认为不存在 Cube 创建问题。

### 6.2 比赛消息到 MemOS 的转换

| 比赛字段 | MemOS 字段/处理 |
|---|---|
| `user_id` | MemOS user_id + Cube 映射 |
| `session_id` | MemOS session_id |
| `messages[].role` | 原样保留 |
| `messages[].content` | 原样保留，不加入 gold |
| `messages[].timestamp` | 保存原毫秒值，并转换成 MemOS `chat_time` 所需格式 |
| `request_id` | 写入 Adapter 幂等表，并作为 MemOS provenance/info |
| message index | 生成稳定 message_id/provenance |

Add 明确使用：

- `writable_cube_ids`，不依赖 deprecated `mem_cube_id`；
- `async_mode=sync`；
- `mode=fast/fine` 通过配置选择，baseline-v0 冻结一个实测值。

### 6.3 MemOS Search 参数

必须显式设置并记录：

- `readable_cube_ids`；
- 内部 candidate top_k；
- `mode=fast/fine/mixture`；
- `relativity`；
- `dedup`；
- `rerank`；
- preference memory 是否启用；
- neighbor discovery 是否启用。

不能让 MemOS 的默认 `top_k`、阈值或 rerank 静默决定比赛行为。

### 6.4 MemOS 响应转换

统一转换为：

```json
{
  "data": [
    {
      "id": "memos_xxx",
      "content": "memory evidence",
      "score": 0.91,
      "created_at": "2026-09-01T10:00:00Z"
    }
  ]
}
```

规则：

- 解析 text、preference 等启用的记忆类型；
- id/content 必须非空；
- score 必须有限且越大越相关；
- created_at 缺失或非法时直接省略，不伪造；
- 过滤非当前 user/cube；
- 过滤 deleted/archived 等无效状态；
- 数量不超过比赛 top_k；
- 不返回 Chat 生成答案。

## 7. Raw Store 定位

Raw Store 不与 MemOS 争夺主方案定位。评审后拆成两个范围：

- **D04-A（已批准、必需）**：同步原文、request_id 幂等、user/Cube 映射、MemOS 状态和恢复 outbox；
- **D04-B（已批准为实验能力）**：Raw FTS Search fallback、原始证据补充和后续双路融合，默认可用但必须可以关闭。

Raw Store 整体承担四项职责：

1. Add 同步原始证据保障；
2. request_id 幂等和 payload 冲突检测；
3. MemOS 写入状态、错误和恢复 outbox；
4. MemOS 不可用时的 Search fallback，以及后续双路召回候选。

### 7.1 数据表

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

SQLite 启用 WAL、foreign keys、busy_timeout 和持久化 volume。

### 7.2 幂等边界

- 相同 request_id + 相同 payload：返回已保存响应；
- 相同 request_id + 不同 payload：返回 409；
- Raw Store 内部通过事务实现 exactly-once；
- SQLite 和外部 MemOS 之间不存在分布式事务；
- MemOS 路径采用 durable outbox、provenance 和 Search 去重，明确为可恢复的 at-least-once。

## 8. Add 流程

### 8.1 正常路径

1. 严格校验比赛请求；
2. 计算规范化 payload hash；
3. 在 SQLite 原子写入 add_request、raw_messages、FTS 和 outbox；
4. 创建或获取 user Cube；
5. 调用真实 MemOS 同步 Add；
6. 校验 HTTP 状态和 MemOS 业务 code；
7. 更新 outbox/memos_status；
8. 按配置执行首个 Cube、测试环境或抽样读回验证；
9. 返回比赛标准成功响应。

正常请求不固定追加一次 Search 读回，避免为约 5,562 次 Add 额外制造同量级的 Search/Embedding 调用。Add 后立即可检索通过契约测试、每个新 Cube 的首次验证和可配置抽样持续检查；发现版本或模型异常时可以临时开启全量读回。

### 8.2 MemOS 失败路径

如果 Raw Store 成功、MemOS 失败：

- 保存 `raw_only` 状态和可恢复 outbox；
- Search 只使用已完成的 MemOS 结果和 Raw fallback；
- `MEMOS_ADD_FAILURE_POLICY=strict`：返回 5xx，用于 baseline 调测和冻结；
- `MEMOS_ADD_FAILURE_POLICY=raw_fallback`：Raw 已可检索时返回成功，用于故障测试和可能的最终可用性策略；
- 最终提交使用哪种模式，在拿到主办方评测失败策略后冻结。

如果 Raw Store 失败：返回 5xx，不能伪造成功。

### 8.3 同步口径

正式 baseline-v0 要求 MemOS 同步完成并可读回，同时设置总超时，避免单个模型调用拖死整轮评测。触发 Raw fallback 的请求仍可用于验证服务可用性，但该次运行不能作为干净的 baseline-v0 成绩冻结。

需要分别记录：

- `raw_committed`；
- `memos_add_ok`；
- `memos_read_after_write_ok`；
- `response_success`。

这样可以明确判断是接口成功、Raw 成功还是 MemOS 真正成功。

## 9. Search 流程

### 9.1 baseline-v0 主召回

1. MemOS Search：主记忆候选；
2. 正常情况下只返回 MemOS 结果，形成干净、可解释的 MemOS baseline；
3. MemOS Search 失败时，使用 Raw FTS fallback；
4. 两条路径均严格限定 user_id/cube；
5. 内容去重、状态过滤和格式转换；
6. 按配置截断，但不超过请求 top_k；
7. 转换为比赛响应。

### 9.1.1 baseline 后的融合实验

`FUSION_ENABLED=true` 时，同时运行 MemOS 和 Raw FTS，使用 Reciprocal Rank Fusion 合并两路内部排名。该能力默认可用但在 baseline-v0 中关闭，作为 baseline 后的第一批实验之一；不能直接相加 BM25 和 MemOS relativity。

### 9.2 options

如果 Search 带 options：

- query 仍是主检索内容；
- options 可用于检索扩展和候选覆盖；
- 不在服务内选择选项；
- 不返回最终答案。

### 9.3 返回量

baseline-v0 初始测试：

```text
5 / 10 / 20 / 40 / 100
```

冻结值必须根据代理准确率、旧值泄漏、噪声、响应字符数和延迟共同决定，不能预设 K=20 一定最佳。

### 9.4 失败语义

- MemOS 失败：Raw fallback；
- Raw 失败：MemOS；
- 两者都失败时由 `SEARCH_FAILURE_POLICY` 决定；
- `strict`：返回标准 5xx，用于 baseline 调测；
- `empty`：返回 HTTP 200 + `{"data":[]}`，用于评测器会因单次 5xx 中断整轮时的可用性策略；
- 两种模式都必须记录内部错误，最终提交值在取得主办方策略后冻结。

## 10. Health 与就绪

Health 区分 core readiness 和 MemOS readiness：

```json
{
  "status": "ok",
  "adapter_ready": true,
  "raw_store_ready": true,
  "memos_ready": false,
  "model_profile": "mock",
  "degraded": true
}
```

不同 profile 的 2xx 条件：

| Profile | `/health` 返回 2xx 的条件 |
|---|---|
| `core` / `contingency-raw` | Adapter + Raw Store 可用 |
| `mock` | Adapter、Raw、MemOS、Qdrant、Neo4j、Mock Model API 全部可用 |
| `organizer` baseline 调测 | Adapter、Raw、MemOS、Qdrant、Neo4j、真实模型探测全部可用 |

额外提供 `GET /health/details` 显示各组件状态；赛事仍只依赖 `/health`。

最终提交阶段再根据主办方故障策略选择：

- `STRICT_HEALTH=true`：MemOS、Qdrant、Neo4j 和模型探测全部成功才返回 2xx；
- `STRICT_HEALTH=false`：Raw fallback 可用即可返回 2xx。

Health 本身无鉴权。

## 11. 配置与密钥

统一配置由 Adapter/启动脚本管理，禁止 Key 进入源码、镜像和日志。

```text
APP_PROFILE=mock | organizer
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

日志只能记录配置项是否存在，不能记录值。

## 12. 主办方 API 到位后的能力探测

拿到 API/Key 后不直接跑全量，按固定顺序执行：

### 12.1 协议探测

- Base URL 和鉴权格式；
- Chat completion 基本调用；
- JSON/structured output；
- Embedding endpoint、模型和维度；
- Rerank 是否存在及协议；
- 错误码、429、超时和连接复用；
- Docker 容器内可达性。

### 12.2 MemOS 最小链路

1. 创建一个测试 user/Cube；
2. Add 一条事实；
3. 检查 MemOS 业务响应；
4. Search 同一事实；
5. 重启服务后再次 Search；
6. 删除测试数据或使用独立命名空间。

### 12.3 代表性样本

至少选择：

- 1 个 LoCoMo 单跳；
- 1 个 LoCoMo 时序；
- 1 个 LoCoMo 多跳；
- 1 个 MemOps Remember；
- 1 个 Update；
- 1 个 Forget；
- 1 个 Reflect。

只有这组全部通过后才扩大到数十题；数十题的 MemOS Add/Search 成功率达到 100% 后，才运行 1000 题并冻结 baseline。

## 13. baseline-v0 评测和冻结

baseline 报告必须包含：

- Git commit；
- MemOS tag/commit；
- Qdrant/Neo4j 镜像 digest；
- 模型名称和用途；
- 所有非密钥配置；
- Add/Search P50/P95/P99；
- 模型调用次数和 token；
- 429、5xx、超时；
- MemOS 成功率和 Raw fallback 比例；
- 总体代理分；
- LoCoMo single/temporal/multi-hop；
- MemOps Remember/Update/Forget/Reflect；
- MemOps eval axis；
- 返回 K 和平均响应字符数；
- 错误分类和已知限制。

本地公开包属于规则级重建，报告必须标注 `official=false`，不能声称是主办方正式成绩。

## 14. baseline 后的调优规则

每次实验：

1. 从 baseline-v0 分支创建；
2. 只改变一个主要变量；
3. 先跑小样本；
4. 再跑固定验证集；
5. 记录题目正翻转和负翻转；
6. 合规、隔离或超时退化则直接拒绝；
7. 只有保留集有收益才成为新候选。

建议优化顺序：

1. MemOS API/格式/同步稳定性；
2. MemOS Add fast/fine 与成本；
3. Search top_k、relativity、dedup、rerank；
4. MemOS/Raw RRF 融合；
5. Update/Forget 状态过滤；
6. temporal 和 multi-hop 证据组织；
7. 并发、超时和熔断；
8. 最后才考虑更换模型或大改 prompt。

## 15. 测试矩阵

### 15.1 契约

- Health 2xx；
- Add 字段、类型和 ID 原样回显；
- Search 顶层对象和 data 数组；
- id/content 非空；
- score 有限；
- created_at 合法或省略；
- top_k 上限；
- options/timestamp 可选；
- 无结果空数组。

### 15.2 一致性和隔离

- 同 request_id 同 payload；
- 同 request_id 不同 payload；
- 同 session 多 chunk 顺序；
- Add 后立即 Search；
- 服务重启；
- 并发创建同一 Cube；
- 两个 user 写相同文本；
- MemOS、Raw、融合三条路径分别验证隔离。

### 15.3 Mock/Fake 故障

- 429；
- 5xx；
- 慢响应和连接失败；
- HTTP 200 + 业务失败；
- 非法 JSON；
- 非法结构化 LLM 输出；
- Embedding 维度不匹配；
- Qdrant/Neo4j 未就绪；
- Add 成功但 Search 读不到；
- MemOS 失败时 Raw fallback。

### 15.4 能力

- LoCoMo 单跳、时序、多跳；
- MemOps Remember、Update、Forget、Reflect；
- 旧值、新值、tentative、retracted；
- 过遗忘；
- 多目标绑定；
- 噪声长对话；
- query 中的 FTS 特殊字符。

## 16. 提交目录草案

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
│   └── memos/                 # 或固定依赖方式，评审后决定
└── scripts/
    ├── smoke.py
    ├── capability_probe.py
    ├── run_proxy_eval.sh
    └── package.sh
```

## 17. 实施阶段与控制权

本文不规定按天节奏。实施顺序、暂停、提前或延后均由用户主动控制；每个阶段只有依赖关系和退出条件。

### 阶段 I：Adapter 和 Fake Client

- 固定 MemOS commit、API Schema 和依赖；
- 建立 solution 目录、Compose 和配置 profile；
- 完成 Health/Add/Search 路由和比赛请求模型；
- 定义 MemOS Gateway、Fake Client 和 Raw Store Schema。

退出条件：Adapter 使用 Fake Client 通过契约 Smoke。

### 阶段 II：真实 MemOS 无 Key 骨架

- 启动 MemOS、Qdrant、Neo4j；
- 完成 user/Cube 创建和映射；
- 完成比赛字段与 MemOS 字段转换；
- 建立 Mock Model API 或 LLM client mock；
- 完成至少一条 mock Add/Search 接线测试。

退出条件：无 Key 环境下完整工程可启动，真实 MemOS 接线可验证。

### 阶段 III：可靠性与 Scaffold 冻结

- 完成 Raw Store、可选 FTS、幂等和 outbox；
- 完成 MemOS 响应解析、二次隔离和故障策略；
- 完成 Docker 重启恢复和契约测试。

退出条件：形成待接真实 API 的 `memos-scaffold-v0`。

### 阶段 IV：真实 API 调测与 baseline-v0

- 运行 capability probe；
- 完成最小链路、7 类代表样本和数十题门控；
- 运行公开 1000 题代理评测；
- 记录准确率、延迟、token、限流和 fallback；
- 冻结第一版真实配置，标记 baseline-v0。

退出条件：满足 2.2 和第 13 节的全部冻结条件。

### 阶段 V：调优与提交冻结

- 按第 14 节逐变量调优；
- 干净构建、冷启动、Health、Smoke、重启和故障回退；
- 完成 SDD、INSTRUCTION、许可证和已知限制；
- 生成并检查 solution.zip；
- 保存最终 commit、配置和测试报告。

用户明确下达进入下一阶段的指令前，不自动推进实施节奏。

## 18. 风险与回退

| 风险 | 影响 | 回退 |
|---|---|---|
| API/Key 到达太晚 | 无法完成真实 baseline 全量调测 | 保持 scaffold 完整，Raw-only 作为应急提交模式 |
| API 不是 OpenAI-compatible | MemOS 初始化或解析失败 | provider adapter；Mock fixture 定位差异 |
| 没有 Embedding API | MemOS Search 无法工作 | 镜像内小型本地 Embedder 或 Raw FTS；不在运行时下载 |
| MemOS Add 200 但未入库 | baseline 数据缺失 | 业务 code + read-after-write + Raw Store |
| Cube 创建/权限错误 | 空检索或跨用户 | 持久化映射、ACL 测试、二次过滤 |
| 同步 Add 太慢 | 全量评测超时 | fast/fine 消融、总超时、Raw fallback |
| Update/Forget 旧值泄漏 | MemOps 失分 | MemOS 状态过滤 + Raw 操作证据 + 后续状态层 |
| Compose 不被支持 | 无法部署四服务 | 获得环境信息后确认；必要时评审部署收缩或启用应急模式 |
| 构建/运行无外网 | 镜像或模型不可获得 | 固定依赖并预装；禁止运行时下载 |
| 返回内容过长 | Answer 超上下文或噪声 | K 和总字符上限消融 |

## 19. 逐项评审清单

| 编号 | 待评审决策 | 当前建议 | 状态 |
|---|---|---|---|
| D01 | 当前阶段名称 | `memos-scaffold-v0`，不是性能 baseline | 已通过 |
| D02 | baseline-v0 定义 | 拿到真实 API/Key、完成 MemOS 全链路调测后冻结 | 已通过 |
| D03 | 主方案 | Adapter + MemOS + Qdrant + Neo4j + 主办方模型 API；Adapter 独立记录分段耗时，baseline 后专项优化 | 已通过 |
| D04-A | Raw Store 必需职责 | 同步原文、幂等、user/Cube 映射、outbox 和恢复依据 | 已通过 |
| D04-B | Raw 检索能力 | FTS fallback、原始证据补充和双路融合；默认可用但可关闭 | 已通过，实验能力 |
| D05 | 无 Key 联调 | Fake MemOS Client + 最小 Mock Model API 两层测试 | 已通过 |
| D06 | MemOS 引入 | SSH 源：`git@github.com:MemTensor/MemOS.git`；搭建时固定 tag/commit，禁止 main/latest | 已通过 |
| D07 | API 技术栈 | Python 3.11 + FastAPI + Uvicorn；baseline 默认单 worker，取得正式并发信息后通过压测决定是否增加 | 已通过，附带条件 |
| D08 | 部署骨架 | 五服务 mock profile、四服务 organizer profile；服务隔离、完整 healthcheck、禁止运行时下载，保留应急 profile | 已通过，附带条件 |
| D09 | Add 正常语义 | Raw 原子写入 + MemOS sync Add + 业务校验 + 状态记录；不固定为每次 Add 追加 Search | 已通过，修改后 |
| D10 | MemOS Add 失败 | `strict`/`raw_fallback` 双模式；baseline 使用 strict，最终提交值待主办方策略 | 已通过 |
| D11 | Search | baseline-v0 正常路径 MemOS-only；Raw 仅故障回退；RRF 作为默认关闭的后续实验 | 已通过，修改后 |
| D12 | Search 全失败 | `strict`/`empty` 双模式；baseline 使用 strict，最终值待主办方策略 | 已通过 |
| D13 | Health | mock 和 baseline 均等待完整栈 ready；core/应急 profile 可 Raw-ready；最终提交支持 strict 开关 | 已通过，修改后 |
| D14 | API 到位后的顺序 | capability probe → 最小链路 → 7 类样本全部通过 → 数十题成功率 100% → 1000 题 | 已通过，附带门槛 |
| D15 | API 始终不到的回退 | `contingency-raw` 应急提交，不称为 MemOS baseline-v0 | 已通过 |

D01～D15 已完成评审。实施阶段和推进节奏由用户主动控制。

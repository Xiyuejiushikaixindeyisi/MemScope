# MemOS Baseline 实现方案
 
> 目标：在一周内交付一套可直接提交、支持 Docker 部署、符合赛事 Add/Search/Health 契约的 MemOS baseline，并在此基础上围绕评测通过率、返回格式、性能和超时逐步调优。  


## 1. 背景与范围

初赛正式子集共 1000 道 Search 题：

- LoCoMo-Refined：500 题；
- MemOps：500 题。

评测机先按 chunk 调用 Add 写入完整历史，再逐题调用 Search。选手服务只负责记忆写入和证据检索；Answer 和 Judge 由主办方固定执行。

本方案遵循以下本地文档：

- [赛题任务书](./技术难题-Agent-Memory-任务书-1.0.md)
- [调测指南](./技术难题-Agent-Memory-调测指南-1.0.md)
- [评测集说明](./技术难题-Agent-Memory-评测集（开源）-1.0/README.md)
- [Add/Search/Health 契约](./技术难题-Agent-Memory-评测集（开源）-1.0/api_contract.md)
- [代理评测说明](./技术难题-Agent-Memory-评测集（开源）-1.0/PROXY_EVAL.md)

本阶段不实现平台 Answer/Judge，不使用 gold，不允许 Search 直接生成最终答案。

## 2. 实施原则

1. **先交付、后优化**：第一版必须能够独立启动、完整跑通并直接提交。
2. **同步可检索**：Add 返回 HTTP 200 前，新增内容必须已经持久化且可被 Search 检索。
3. **可靠性优先**：MemOS 或外部模型异常时，服务退化为原始证据检索，而不是整次请求失败。
4. **版本可回退**：每项优化通过 Feature Flag 隔离，并保留上一版镜像、配置和评测报告。
5. **一次只改一个变量**：检索数量、融合权重、并发、超时、状态策略分别做消融，避免无法定位分数变化原因。
6. **严格用户隔离**：任何存储、缓存、检索和后台任务都必须携带并校验 `user_id`。
7. **暂不修复评测数据**：保留原始文本、原始时间字段和事件顺序，不静默补全缺失日期。

## 3. 第一版 Baseline 的完成定义

第一版 `baseline-v0` 必须满足：

- 可通过 `docker compose up` 非交互启动；
- 只向评测机暴露统一服务端口，默认 `8080`；
- `GET /health`、`POST /add`、`POST /search` 完全符合统一契约；
- Add 强制使用 MemOS 同步写入模式；
- Add 返回前，至少原始消息已经同步写入本地 Raw Store；
- MemOS 正常时返回 MemOS 记忆，异常时自动回退到 Raw Store；
- 重复提交同一 `request_id` 不产生重复记忆；
- 不同 `user_id` 之间零串扰；
- Search 返回证据，不返回最终答案；
- 能跑完正式 1000 题，不因单题错误中断整轮评测；
- API Key 仅通过环境变量注入，不进入镜像、源码或日志。

需要分别统计两个概念：

- **接口通过率**：请求成功、格式合规、未超时的比例；
- **题目通过率**：平台 Answer/Judge 判定正确的比例。

接口通过率应优先达到接近 100%，之后再优化题目通过率。

## 4. 总体架构

```text
评测机
  │
  ├── GET  /health
  ├── POST /add
  └── POST /search
          │
          ▼
  Contest Adapter（FastAPI，唯一对外入口）
    ├── 契约校验与响应格式化
    ├── request_id 幂等控制
    ├── user_id → MemCube 映射
    ├── 超时、限流、重试、熔断
    ├── 结果过滤、融合、去重和截断
    │
    ├── Raw Store（SQLite + FTS5）
    │     ├── 同步保存原始消息
    │     ├── 保留 session、时间和消息顺序
    │     └── MemOS/模型异常时提供兜底检索
    │
    └── MemOS
          ├── 同步 Add
          ├── 图/向量记忆和纠错能力
          ├── Qdrant
          └── Neo4j
```

推荐 Docker Compose 服务：

| 服务 | 职责 | 对外暴露 |
|---|---|---|
| `memory-api` | 比赛适配层和 Raw Store | `8080` |
| `memos` | MemOS 服务 | 否，仅 Compose 内网 |
| `qdrant` | 向量存储 | 否，仅 Compose 内网 |
| `neo4j` | 图存储 | 否，仅 Compose 内网 |

MemOS、Qdrant 和 Neo4j 使用固定版本或镜像 digest。不得在比赛构建阶段默认跟随 `latest`。

## 5. 配置与密钥

组委会提供的模型 API 和 Key 通过环境变量注入。建议统一支持以下配置：

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
EMBEDDING_BASE_URL
EMBEDDING_API_KEY
EMBEDDING_MODEL
RERANK_BASE_URL
RERANK_API_KEY
RERANK_MODEL
```

实施前必须验证：

1. API 是否为 OpenAI-compatible；
2. Chat、Embedding、Rerank 是否分别提供；
3. MemOS 所需结构化输出是否受支持；
4. 模型名称、限流、最大上下文和请求超时；
5. 评测容器是否允许访问对应模型服务；
6. Docker Compose 是否按任务书约定可用。

如果只提供 Chat API、没有 Embedding API，应在镜像内准备已验证的本地 Embedding 方案；禁止依赖容器首次启动时在线下载模型。

## 6. Add 接口设计

### 6.1 请求流程

1. 使用 Pydantic 严格校验 `request_id`、`user_id`、`session_id` 和 `messages`。
2. 查询幂等表：
   - 已成功处理：返回之前保存的同一响应；
   - 正在处理：等待同一任务或返回可重试错误，不重复写入；
   - 未处理：创建处理记录。
3. 将原始消息同步写入 SQLite Raw Store。
4. 使用稳定哈希将 `user_id` 映射为合法的 MemOS Cube ID。
5. 首次访问时创建 Cube；使用 per-user lock 避免并发重复创建。
6. 调用 MemOS Product API，并强制 `async_mode="sync"`。
7. 记录 MemOS 写入状态：`memos_ok`、`raw_only` 或 `failed`。
8. 返回严格符合比赛契约的响应。

### 6.2 Raw Store 字段

至少保存：

```text
request_id
user_id
session_id
message_id
message_index
role
content
timestamp
created_at
memos_status
```

唯一约束建议为：

```text
(request_id, message_index)
```

所有 Search SQL 必须显式包含 `user_id = ?`。

### 6.3 成功响应

```json
{
  "success": true,
  "request_id": "...",
  "user_id": "...",
  "session_id": "..."
}
```

`success` 必须是 JSON boolean。三个 ID 必须与请求完全一致。

### 6.4 MemOS 异常时的语义

如果 Raw Store 已成功写入，但 MemOS 或模型 API 超时：

- 中止或取消当前 MemOS 调用；
- 将本次写入标记为 `raw_only`；
- 可以返回成功，因为新增消息已经持久化并可由 Search 检索；
- 可选地将 MemOS 增强任务写入持久化队列，但后台增强不得成为正确性的必要条件。

如果 Raw Store 写入也失败，必须返回 5xx，不能伪造成功。

## 7. Search 接口设计

### 7.1 第一版召回流程

第一版采用双路召回：

1. 根据 `user_id` 找到对应 MemCube，调用 MemOS Search；
2. 查询 SQLite FTS5，以 session 或相邻消息窗口作为证据单元；
3. 对两路结果进行：
   - `user_id` 二次过滤；
   - 空内容过滤；
   - ID 去重和内容近重复去重；
   - 分数归一化；
   - 排序融合；
   - 按配置数量截断，但不得超过请求 `top_k`；
4. 转换为统一比赛响应。

第一版可以配置为：

- 正常状态：MemOS + Raw Store 融合；
- MemOS 超时：仅 Raw Store；
- MemOS 尚无对应 Cube：仅 Raw Store；
- Raw Store 异常：仅 MemOS；
- 两者都失败：返回标准 5xx，而不是格式错误的 200。

### 7.2 返回格式

```json
{
  "data": [
    {
      "id": "memos_xxx",
      "content": "原始证据或记忆内容",
      "score": 0.91,
      "created_at": "2026-09-01T10:00:00Z"
    }
  ]
}
```

约束：

- 顶层必须是对象，且必须包含 `data` 数组；
- `id`、`content` 为非空字符串；
- `score` 如提供，必须是有限数值且越大越相关；
- `created_at` 如提供，必须是合法 ISO 时间；
- 无结果返回 `{"data":[]}`；
- 返回数量不得超过 `top_k`；
- 不得直接生成最终答案或将答案伪装为记忆。

### 7.3 返回数量

正式评测传入 `top_k=100`，但它是返回上限，不是必须返回数量。第一版建议：

```text
SEARCH_RETURN_K=20
```

后续对 `10/20/40/100` 做消融实验。严格 Judge 下，过多陈旧、矛盾或弱相关证据可能降低准确率。

## 8. Health 与启动就绪

`/health` 不能只检查 FastAPI 进程，应检查：

- Adapter 是否完成初始化；
- Raw Store 是否可读写；
- MemOS 是否可访问；
- Qdrant 是否可访问；
- Neo4j 是否可访问；
- 模型 API 是否配置；
- 熔断器是否开启。

建议区分：

- `ready=true`：Adapter 和 Raw Store 可用，能够合法接受 Add/Search；
- `memos_available=true/false`：MemOS 增强能力是否可用；
- `degraded=true/false`：是否处于 Raw Store 降级模式。

只要 Raw Store 可用，服务可以处于降级就绪状态。启动时仍应等待 MemOS、Qdrant、Neo4j 至少完成一次健康检查，并将真实状态暴露给日志和内部指标。

## 9. 调优方案

### 9.1 阶段 0：可提交 baseline

验收：

- 契约 Smoke 全部通过；
- 同一 Add 重试不会产生重复记录；
- Add 后立即 Search 能检索到新增证据；
- 不同用户之间零串扰；
- MemOS、模型 API 断开时 Add/Search 仍能通过 Raw Store 工作；
- Docker 冷启动后无需人工操作；
- 可以跑完至少一次正式 1000 题代理评测。

版本标记：`baseline-v0`。

### 9.2 阶段 1：题目通过率

报告至少按以下维度切片：

- LoCoMo：single-hop、temporal、multi-hop；
- MemOps：Remember、Update、Forget、Reflect；
- MemOps eval axis；
- MemOS 命中、Raw Store 命中和融合命中；
- 返回结果数量；
- 新值、旧值、tentative、retracted 和噪声证据情况。

错误分类：

```text
未召回
召回但排序过低
返回过多噪声
返回旧值或撤回值
缺少多跳证据
时间信息不完整或错误
MemOS 抽取丢失原始细节
Answer 模型被冲突证据误导
```

只有明确错误类型后再修改抽取 prompt、融合权重或返回数量。

### 9.3 阶段 2：格式合规

将格式验证做成独立自动化测试：

- `success` 是 boolean；
- 三个 ID 原样回显；
- Search 顶层为 `{"data": [...]}`；
- `data` 长度不超过 `top_k`；
- `id/content` 非空；
- `score` 为有限数值；
- `created_at` 为合法 ISO 时间；
- 无结果为标准空数组；
- 错误响应不返回半截 JSON；
- Search 不包含最终答案字段。

格式层目标为 100% 通过，并应独立于算法功能锁定。

### 9.4 阶段 3：性能

必须记录：

- Docker 冷启动时间；
- Add、Search 的 P50/P95/P99；
- 单样本累计 Add 时间；
- MemOS/模型调用次数和 token 数；
- Qdrant、Neo4j 延迟；
- Raw Store 降级比例；
- 请求并发数、排队时间、重试次数和限流次数；
- 单用户串行写入与跨用户并行写入的吞吐。

优化顺序：

1. HTTP 连接池和 keep-alive；
2. 模型调用并发限制；
3. Cube 创建缓存和并发锁；
4. request_id 幂等；
5. 批量 Embedding；
6. Search 双路并行；
7. 减少无价值抽取和重复写入；
8. 最后调整数据库参数。

### 9.5 阶段 4：超时与可用性

所有超时和并发参数通过环境变量配置：

```text
MODEL_CONNECT_TIMEOUT
MODEL_REQUEST_TIMEOUT
MEMOS_ADD_TIMEOUT
MEMOS_SEARCH_TIMEOUT
REQUEST_TOTAL_TIMEOUT
MAX_ADD_CONCURRENCY
MAX_SEARCH_CONCURRENCY
CIRCUIT_BREAKER_THRESHOLD
CIRCUIT_BREAKER_COOLDOWN
```

在主办方正式超时规则公布前，不将超时写死。总请求预算应预留约 20% 给结果格式化和回退。

熔断行为：

- 连续多次模型或 MemOS 超时后，短时间跳过 MemOS 增强；
- Add 进入 Raw Store 同步路径；
- Search 使用已有 MemOS 结果或 Raw Store；
- 冷却期后以少量探测请求恢复 MemOS；
- 熔断状态必须记录，不能静默吞掉异常。

## 10. 风险与回退方案

| 风险 | 影响 | 预防/监控 | 回退方案 |
|---|---|---|---|
| MemOS 默认异步写入 | Add 后立即 Search 查不到 | 强制 `async_mode=sync`，加入读后写集成测试 | Raw Store 同步检索 |
| 模型 API 限流或超时 | Add 大量失败、评测超时 | 并发信号量、连接池、有限重试、熔断 | `raw_only` 模式 |
| API 不支持结构化输出 | MemOS 抽取解析失败 | 第一天验证 JSON/结构化输出 | 切换兼容模型；原文入库 |
| 没有 Embedding API | MemOS 检索无法启动 | 提前确认资源类型 | 使用镜像内固定本地 Embedder；最差回退 FTS5 |
| Qdrant/Neo4j 未就绪 | 冷启动或查询失败 | Compose healthcheck、启动依赖和重试 | 仅启用 Raw Store |
| Docker Compose 受限 | 完整 MemOS 栈无法部署 | 提前用干净环境模拟并向组委会确认 | 单容器 Adapter + Raw Store 可提交版本 |
| Cube 创建并发冲突 | 数据丢失或串扰 | 稳定哈希、唯一约束、per-user lock | Raw Store 按 `user_id` 强隔离 |
| 重试导致重复 Add | 噪声、存储和性能恶化 | `request_id` 幂等表 | Search 内容去重；重建受影响 Cube |
| Search 返回大量噪声 | Judge 被旧值或弱相关证据误导 | 返回量和分数分布监控 | 回退到已验证的 `K=20` |
| Update/Forget 返回旧值 | MemOps 失分 | 错误切片、旧值率和泄漏率监控 | 关闭高风险重排，回退原文检索；后续加状态层 |
| 运行时下载模型 | 冷启动失败或无网络 | 镜像预装并校验文件哈希 | API Embedding 或 FTS5 |
| 磁盘持续增长 | 后半程写入失败 | 监控磁盘和数据库大小 | 限制日志；按评测 run 隔离，不在运行中清库 |
| 版本漂移 | 本地和官方行为不一致 | 固定 commit、镜像 digest 和锁文件 | 使用已验证镜像标签 |
| Key 泄漏 | 安全事故或资源失效 | 仅环境变量读取、日志脱敏 | 轮换 Key；无需改代码或镜像 |

## 11. Feature Flag 与版本管理

建议配置：

```text
MEMOS_ENABLED=true
RAW_STORE_ENABLED=true
RAW_FALLBACK_ENABLED=true
FUSION_ENABLED=true
RERANK_ENABLED=false
STATE_LEDGER_ENABLED=false
SEARCH_RETURN_K=20
```

版本演进：

| 版本 | 内容 | 回退基线 |
|---|---|---|
| `baseline-v0` | 契约 + MemOS + Raw Store | 最小单容器 Raw Store |
| `baseline-v1` | 格式、幂等和隔离稳定 | `baseline-v0` |
| `baseline-v2` | 性能、限流、熔断和超时 | `baseline-v1` |
| `baseline-v3` | 双路检索融合和返回量调优 | `baseline-v2` |
| `baseline-v4` | Update/Forget 状态层和旧值控制 | `baseline-v3` |

每个版本必须保存：

- Git commit；
- Docker 镜像标签和 digest；
- `.env.example` 与实际配置快照（不含密钥）；
- 1000 题代理评测报告；
- 格式、延迟和超时报告；
- 相对上一版的题目翻转清单；
- 已知风险和启用的 Feature Flag。

只有同时满足以下条件，新版本才能替换提交候选：

- 格式合规率不下降；
- 请求成功率不下降；
- 超时率不增加，或有明确且可接受的准确率收益；
- 总体准确率或目标切片准确率有可解释提升；
- Docker 冷启动和干净环境 Smoke 通过。

## 12. 一周实施计划

### 第 1 天：可启动骨架

- 固定 MemOS commit 和第三方镜像版本；
- 验证组委会 API、Key、模型能力和限流；
- 建立 Docker Compose；
- 实现 Adapter 的 Health/Add/Search 路由；
- 完成 MemOS Product API 的同步 Add/Search 调用；
- 通过契约 Smoke。

退出条件：6 小时内如 MemOS 完整链路仍无法工作，立即启用 Adapter + Raw Store 可提交路径，MemOS 转为可选增强，不能阻塞整体交付。

### 第 2 天：可靠性基线

- 实现 SQLite Raw Store 和 FTS5；
- 实现 request_id 幂等；
- 实现稳定 Cube 映射和用户隔离；
- 实现 MemOS 异常回退；
- 完成故障注入测试。

目标：形成可提交的 `baseline-v0`。

### 第 3 天：全量评测与错误切片

- 跑完整 1000 题代理评测；
- 生成 benchmark、operation、eval axis 切片；
- 记录 MemOS、Raw Store 和融合命中来源；
- 建立错误分类和题目翻转基线。

### 第 4 天：格式与检索调优

- 锁定响应格式和 schema 测试；
- 对返回量 `10/20/40/100` 做消融；
- 调整 MemOS/Raw Store 融合和去重；
- 检查陈旧值、时间题和多跳证据。

### 第 5 天：性能与超时

- 压测 Add/Search 并记录 P50/P95/P99；
- 调整连接池、并发、限流、重试和熔断；
- 验证 API 限流和网络异常下的退化行为；
- 优化冷启动和镜像体积。

### 第 6 天：MemOps 定向优化

- 优先处理 Update 旧值率和 Forget 泄漏/过遗忘；
- 如时间允许，增加独立状态账本；
- 保留原始证据和 provenance，不物理删除历史；
- 重新跑完整代理评测和翻转分析。

### 第 7 天：冻结与提交演练

- 冻结 commit、配置、prompt、依赖和镜像 digest；
- 在干净环境仅依据 `INSTRUCTION.md` 启动；
- 跑 Docker 冷启动、Health、Smoke、故障回退和全量回归；
- 生成 `solution.zip`；
- 不再引入新算法，只修复阻断提交的问题。

## 13. 测试矩阵

### 13.1 契约测试

- 正常 Health；
- 正常 Add/Search；
- Add ID 原样回显；
- 无结果 Search；
- 非法消息、空内容、非法 top_k；
- 重复 request_id；
- Search 返回数量上限；
- JSON 类型和 ISO 时间校验。

### 13.2 隔离和一致性测试

- 两个用户写入相同文本后分别检索；
- 同一 session 多 chunk 顺序写入；
- Add 返回后立即 Search；
- 并发创建同一用户 Cube；
- 服务重启后继续检索；
- 评测过程中不得自动清库。

### 13.3 故障注入

- 模型 API 连接失败、429、5xx、慢响应；
- MemOS 不可用；
- Qdrant 不可用；
- Neo4j 不可用；
- Raw Store 只读或磁盘空间不足；
- Adapter 在 Add 中途重启；
- Search 单路超时但另一条检索路径可用。

### 13.4 能力测试

- LoCoMo 单跳、时序、多跳；
- MemOps Remember、Update、Forget、Reflect；
- tentative/retracted/旧值干扰；
- 多目标绑定；
- 噪声长对话；
- 原始证据是否保留足够上下文。

## 14. 可观测性

每个请求使用 `request_id` 串联日志，但日志不得记录密钥或完整敏感请求头。

建议指标：

```text
http_requests_total
http_request_duration_seconds
add_success_total
search_success_total
contract_error_total
memos_add_duration_seconds
memos_search_duration_seconds
memos_timeout_total
model_rate_limit_total
raw_fallback_total
circuit_breaker_state
search_result_count
search_empty_total
user_isolation_violation_total
```

日志应包含：请求类型、耗时、用户哈希、session 哈希、MemOS 状态、Raw Store 状态、返回条数和错误分类。不要直接记录 `user_id` 原文或完整对话内容。

## 15. 提交包结构

```text
solution/
├── INSTRUCTION.md
├── SDD.md
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── code/
│   ├── adapter/
│   ├── raw_store/
│   ├── memos_client/
│   └── tests/
├── scripts/
│   ├── smoke.sh
│   ├── run_proxy_eval.sh
│   └── package.sh
└── THIRD_PARTY_NOTICES.md
```

### INSTRUCTION.md 必须说明

- 系统和 Docker 版本要求；
- 必需环境变量和模型资源；
- 构建、启动、停止命令；
- 监听端口和完整 Health/Add/Search URL；
- 鉴权方式；
- 就绪判定；
- 数据卷和磁盘要求；
- 常见启动错误和诊断方式；
- 一条完整 Smoke 命令。

### SDD.md 必须说明

- 使用的 MemOS 版本和许可证；
- 记忆抽取、存储和检索路径；
- Raw Store 的目的和边界；
- 用户隔离、幂等和一致性策略；
- Update、Forget、Reflect 的处理方式；
- 使用的 LLM、Embedding、Rerank 模型及用途；
- 超时、熔断和降级策略；
- 已知限制和未来扩展点。

## 16. 最终提交判定

提交候选必须同时通过：

1. 干净环境 Docker 构建；
2. 非交互启动；
3. 冷启动 Health；
4. 契约 Smoke；
5. Add 后立即 Search；
6. user_id 隔离；
7. 模型/MemOS 故障回退；
8. 1000 题完整代理评测；
9. 格式合规报告；
10. 延迟和超时报告；
11. 仅根据 `INSTRUCTION.md` 可完成部署；
12. 提交包内无明文 Key、缓存、临时文件和评测结果大文件。

最终实现目标是：**MemOS 正常时提供完整的抽取、图/向量记忆和检索能力；MemOS、数据库或模型资源异常时，系统仍能通过同步 Raw Store 合法地保存和返回原始证据，从而保证第一版可提交，并为后续准确率优化保留稳定回退路径。**

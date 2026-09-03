# Agent Memory 赛题验收清单

> 核对日期：2026-09-03
>
> 依据：仓库内任务书 1.0、调测指南 1.0、`api_contract.md`，以及用户后续明确约束
>
> 用法：区分“正式要求”“项目自设质量门禁”“待确认项”，不得把建议实现写成赛事红线

## 1. 事实分级

| 等级 | 含义 | 使用规则 |
|---|---|---|
| 正式要求 | 任务书、调测指南、API 契约明确写出 | 实现和提交必须满足 |
| 用户批准的项目决策 | 用户为 MemScope 明确批准，但不代表赛事通用要求 | 默认执行；变更需重新评审 |
| 项目质量门禁 | 为可复现、可维护和审计主动增加 | 不得冒充官方评分公式 |
| 待确认 | 当前材料没有权威答案 | 不得假设为允许或禁止；在受影响冻结点前解决 |

规范信息冲突时遵循 `docs/README.md` 的权威性顺序。

## 2. 正式接口要求

### 2.1 端点

| 端点 | 方法 | 强制行为 |
|---|---|---|
| `/health` | GET | 无鉴权；任意 2xx 表示就绪 |
| `/add` | POST | 校验输入、完成记忆处理并同步持久化；返回 HTTP 200 后须立即可检索 |
| `/search` | POST | 只在请求 `user_id` 范围内检索并按相关性排序；只返回记忆证据 |

路径可自定义，但必须在 `INSTRUCTION.md` 写明完整 URL。

### 2.2 Add 契约

- 请求必填：`request_id`、`user_id`、`session_id`、有序且非空的 `messages`。
- 每条消息包含 `role`、非空 `content`，可选 Unix 毫秒 `timestamp`。
- 响应 `success` 必须是 JSON boolean `true`，三个 ID 必须原样回传。
- 禁止 202、task id 和异步轮询；返回前必须完成持久化并可被 Search 检索。
- 评测机不会发送 `metadata`、`app_id`、`agent_id` 或 `async_mode`。
- 单会话默认一次 Add；超过约 20 条消息或 2000 词时评测机可能按边界分块。

### 2.3 Search 契约

- 请求必填：`query`、`user_id`、`top_k`；选择题可带 `options`。
- 正式评测固定 `top_k=100`；响应条数不得超过请求值。
- 响应必须是 `{"data": [...]}`；空结果是 `{"data":[]}`。
- 每个条目的 `id`、`content` 必须是非空字符串；`score`、`created_at` 可选。
- 平台按返回顺序读取，因此服务必须在返回前完成相关性排序。
- Search 不按 `session_id` 过滤；`user_id` 是强隔离键。
- 禁止返回最终答案、使用金标或将金标伪装成记忆。
- 评测机不会发送 `filters`、`rerank` 或 `keyword_search`。

### 2.4 鉴权和错误

- Health 无鉴权。
- 契约支持 Bearer、Token、X-Api-Key；Smoke 可无鉴权，正式密钥由赛题组配置。
- 使用标准 HTTP 状态码；即使 HTTP 200，响应缺必填字段也会导致该评测阶段失败。

## 3. 正式评测边界

- 正式子集共 1000 道 Search 题：LoCoMo-Refined 500、MemOps 500。
- 每个样本先按 chunk 完成全部 Add，再逐题 Search。
- 参赛服务只负责写入和返回排序后的记忆证据；Answer/Judge 由主办方固定执行。
- LoCoMo 关注单跳、时序、多跳和跨会话召回；MemOps 关注 Remember、Update、Forget、Reflect 和噪声。
- 最终得分为 70% 客观分 + 30% 主观分。主观项约为架构合理性 15%、工程质量 8%、创新扩展性 7%。
- 超时和可用性作为稳定性参考；当前没有独立的 top_k 加分公式。
- 公开 Smoke 仅用于契约联调，不计正式分；本地自测不等于官方成绩。

六项记忆能力要求是 Extract、Store、Recall、Update、Forget、Anti-noise。它们应在 SDD 中得到解释，
但正式材料没有给出“六个评分维度与六个 SDD 章节一一映射”的规则。

## 4. 正式提交物

解压后至少是：

```text
solution/
├── INSTRUCTION.md
├── SDD.md
├── code/
└── Dockerfile / docker-compose.yml  # 正式材料标为可选
```

- `INSTRUCTION.md`：环境、依赖/镜像/代理、必要环境变量、构建和非交互启动、端口、完整 API URL、
  鉴权方式、Health 与就绪判定。
- `SDD.md`：记什么、怎么存、怎么召回、更新/遗忘、短长记忆边界、内部模型及限制。
- `code/`：完整源码、依赖声明和运行所需配置。
- 缺少 `INSTRUCTION.md`、无法按文档启动或需要人工交互，会使客观评测无法执行。

具体 Python 模块名、文件行数、FAISS/BM25/RRF、目录层级或“必须裸机启动”均不是正式硬约束。MemScope
可按自身架构组织源码，只需提交结构、服务行为和文档一致。

## 5. 用户批准的当前部署决策

- 提交物是源码 ZIP，由赛题组构建和启动，不是预构建镜像。
- B04 使用一份 Compose、三个单职责容器：MemOS、Neo4j、Qdrant；不是单容器多进程。
- 平台不提供托管数据库；比赛只依赖同一次部署生命周期内连续 Add→Search。
- 数据目录和挂载路径可配置；比赛暂不依赖跨重启持久化，但项目会测试 same-host named volume。
- 开发机不能访问华为 AI Gateway；真实模型/API 和语义质量必须在调测机验证。
- 当前 Docker 质量口径：MemOS 镜像约 985 MB，用户批准 1 GB；OCI history 元数据差异和已记录的
  Trivy 高危债务不阻塞 B04，但不能写成漏洞为零。
- B05、B06 分别在新 Session 开发，均需 Gate 0、Gate 1、Gate 2；B04 通过不授权自动进入 B05。

## 6. 项目提交前硬检查

- [ ] 干净环境仅按 `INSTRUCTION.md` 可非交互构建和启动
- [ ] `/health` 无鉴权返回 2xx，且不在依赖未就绪时假健康
- [ ] `/add` HTTP 200、boolean `success=true`、三个 ID 原样、返回前可检索
- [ ] `/search` 返回 `data` 数组，条目 `id/content` 非空，数量不超过 `top_k`
- [ ] Search 只返回记忆证据，结果已排序
- [ ] 不同 `user_id` 不串数据，Search 不错误地限制在单 session
- [ ] Update 旧值、Forget 泄漏/过遗忘和噪声场景有结果
- [ ] Add 在 120 秒、Search 在 60 秒总预算内；429/5xx/timeout 策略有证据
- [ ] 端口、鉴权、环境变量和实际启动行为与文档一致
- [ ] 源码、镜像层、日志和 ZIP 中无密钥或 token
- [ ] 第三方源码、模型和参考代码具有许可证及来源记录
- [ ] 最终 ZIP、基准 commit、依赖、镜像、模型和配置都有版本及 SHA-256

## 7. 两机验收分工

开发机完成：契约/Mock/组件/故障测试、源码与依赖审计、B05/B06 三道门禁、初版 SDD、B09 调优
指南及带校验值的调测交接 ZIP。

调测机完成：真实 Docker 二次验收、华为网关能力探测、资源和可观测性、Smoke/单样本/数十题/1000
题基线、单变量调优及最终提交 ZIP。详细流程和回传要求见
`docs/collaboration/TWO_MACHINE_WORKFLOW.md`。

## 8. 待确认项

下列信息当前不得当作已知事实：

- 正式评测硬件、平台架构、可用磁盘/内存/GPU 和网络白名单；
- 最终公开端口/入口命令及 Add/Search 是否强制入站鉴权；
- 是否允许把开源 Embedding/reranker 权重放入 `code/`，以及许可证/上传/镜像大小限制；
- 正式密钥可调用的 Embedding model ID、维度、限流和真实协议能力；
- Qwen/GLM 精确订阅 model ID、上下文/输出上限及 tools/JSON 字段组合；
- Docker Hub、PyPI 或内网镜像源可达性；
- `solution.zip` 的正式大小上限。现有正式 Markdown 没有支持“≤5GB”的条款，因此 5GB 只能作为
  未证实信息，不能作为硬门禁。

这些问题分别在受影响的 B05/B06 设计、B09 离线交付冻结或真实调测开始前解决并写回 Markdown。

# B06 Gate 1：Real Search 精确实施计划

> 状态：2026-09-04 经用户明确批准并实施；Gate 2 已验收并冻结。
>
> 实施未自动进入 Gate 2；Docker 仍遵循代码冻结后一次最终构建的边界。
>
> 唯一设计基线是已冻结的 [Gate 0 R1](GATE0.md)；Search 算法调测边界见
> [SEARCH_DESIGN_AND_TUNING.md](SEARCH_DESIGN_AND_TUNING.md)。

## 0. 计划身份

- 计划基线分支：`batch/b05-real-add`；
- 计划基线 HEAD：`3e735b3e0aa49c8b66436123fa245c9bc974dee7`；
- B05 实现冻结提交：`e7abf5f`；后续冻结/流程提交：`c1d92d7`、`fc164a9`、`39a635e`、
  `3e735b3`；
- 实施分支：`batch/b06-real-search`；
- Gate 1 开发机实现与证据见 `HANDOFF.md`；Gate 2 已验收，实现提交为 `1507317`。

## 1. 目标、成功条件与继承边界

B06 将 B05 已冻结的真实同步 Add 接成完整的 Real Search，并且只在 Raw Store、Gateway receipt、
当前 MemOS health 和启动 Search capability probe 全部成立时开放公共 Health。

Gate 1 的完成条件是：

1. `POST /search` 通过固定 MemOS v2.0.32 `POST /product/search` 返回真实、排序后的 memory
   evidence，不生成答案，也不以 Raw 或空列表掩盖技术失败；
2. Search 从应用入口到返回前处理使用一个 55 秒 hard deadline，50 秒告警，严格低于比赛 60 秒
   上限；
3. 每条公开 evidence 同时通过请求用户、唯一 logical Cube、`activated` 状态、允许类型和 B05
   provenance 校验；
4. 保持上游排名，只做稳定精确去重并截断到公开 `top_k`；不足时允许少于 `top_k`；
5. `/health` 只有在完整 Add + Search runtime 可尝试时返回 2xx；
6. Python unit/contract、静态检查和无密钥最小真实栈验证通过，分支覆盖率保持至少 95%；
7. 提供主办方可独立执行、覆盖 Add + Search + Health 的非 Docker 部署指南；
8. B05 Add 的 receipt、同用户 lane、115 秒 deadline、无重试和无 raw-text fallback 语义不变。

以下内容不进入本批：公共 Schema 变化、按 `session_id` 隔离、最终模型/Prompt 选择、答案生成、
Answer/Judge、查询时 LLM 冲突裁决、不可逆 organizer、Raw Search/RRF、外部 reranker、MMR/BM25/
full-text 默认启用、额外服务、多 worker、后台任务或自动重试。

## 2. 实施后端到端路径

```text
POST /search（公开 Schema 不变）
  -> Contest Adapter 校验 query/user_id/top_k/options
  -> MemoryOperations 重算 user_id 对应 logical Cube，建立单一 monotonic deadline
  -> MemoryGateway.search(request, timeout_seconds=remaining)
  -> MemOS POST /product/search（唯一 readable_cube_ids；省略 session_id/options）
  -> 校验 HTTP、大小、JSON 和 Product envelope
  -> 严格解析 text_mem bucket/item
  -> user/Cube + activated + type + B05 provenance 后过滤
  -> 稳定精确 ID/content 去重，保留上游顺序
  -> application 再校验 user/Cube 并截断 top_k
  -> Adapter 最终安全截断并返回 evidence
```

Search 不进入 B05 的 `UserLanes`，不重试，也不设置独立于应用 deadline 的第二套总预算。Gateway
收到的是应用单调时钟计算出的剩余预算，HTTP connect/read/write/pool、读取响应、解析和后处理均
只能消费该预算；应用外层 `asyncio.timeout()` 覆盖完整 Search。

## 3. 冻结的运行配置和请求映射

### 3.1 新增 typed 配置

在 `src/memscope/settings.py` 增加并在启动时校验：

| 环境变量 / 字段 | 默认值 | 校验与映射 |
|---|---:|---|
| `SEARCH_DEADLINE_SECONDS` | `55.0` | finite；`0 < warn < deadline < 60` |
| `SEARCH_WARN_SECONDS` | `50.0` | finite；严格小于 deadline |
| `MEMOS_SEARCH_MODE` | `fast` | typed enum：`fast`/`fine`/`mixture` |
| `MEMOS_SEARCH_RELATIVITY` | `0.0` | finite，`0.0 <= value <= 1.0` |
| `MEMOS_SEARCH_DEDUP` | `exact` | typed enum：`exact`/`no`/`sim`/`mmr`；`exact` 映射 JSON `null` |
| `MEMOS_SEARCH_RERANK` | `true` | strict boolean |

这些非密钥值进入 `safe_summary()`。现有 profile 字符串 `memos_add` 保持不变，避免破坏部署配置；
它在 B06 后代表完整 Real Add + Search profile，不做无收益重命名。模型、URL、Key 和上述普通 Search
参数都通过环境变量改变，不要求重建镜像。

### 3.2 Product payload

`MemosMemoryGateway` 对每个公开请求构造以下精确 payload：

```json
{
  "query": "<公开 query 原值>",
  "user_id": "<公开 user_id 原值>",
  "readable_cube_ids": ["<由 user_id 重算的唯一 logical Cube>"],
  "mode": "fast",
  "top_k": 100,
  "relativity": 0.0,
  "dedup": null,
  "rerank": true,
  "search_memory_type": "All",
  "include_preference": false,
  "search_tool_memory": false,
  "include_skill_memory": false,
  "internet_search": false,
  "neighbor_discovery": false
}
```

示例中的 `top_k` 以实际公开值代入，其余四个可调参数以已校验配置代入。payload 不包含
`session_id`、公开 `options`、chat history、答案候选、gold、neighbor discovery 或任意跨 Cube
fallback。`options` 只保持在公开与应用内部契约中，不发送给不支持它的 Product Search。

## 4. 返回解析、信任边界和稳定去重

### 4.1 结构失败与候选丢弃

新增独立 Search DTO/parser，不放宽 B05 `ProviderMemory` 的 Add readback 规则。

- Product envelope 缺少严格的 `code=200`、非空 `message` 或 `data`，以及 `data`、`text_mem`、bucket、
  item 的容器结构畸形，属于 `GatewayProtocolError`；
- bucket `cube_id` 不等于预期 Cube，候选不得公开；
- item 的 ID/content 为空，metadata 不为 object，或同一 ID 出现不同 content，属于 provider
  协议矛盾并使请求失败；
- 外用户、外 Cube、非 `activated`、不支持的 memory type、缺失/非法 B05 provenance、非有限 score
  只丢弃该候选并记录无敏感值的原因计数；
- `created_at` 只有解析为 timezone-aware `datetime` 时才输出；缺失、naive 或非法值只省略时间，
  不伪造 UTC；
- 只接受 `text_mem` 中的 `WorkingMemory`、`LongTermMemory`、`UserMemory`。其它 bucket/category 不
  转成公开 evidence。

字段映射固定为：`item.id -> evidence.id`、`item.memory -> evidence.content`、
`metadata.relativity -> evidence.score`、`metadata.created_at -> evidence.created_at`。score 缺失时输出
`null`，但存在时必须是 finite number；不从未冻结的其它评分字段猜测替代值。

B05 provenance 的最低有效集合固定为：`memscope_cube_id`、64 位小写
`memscope_payload_sha256`、合法的 `memscope_result_index/result_count`，以及 `vector_sync=success`；
其中 user/Cube 必须和当前请求一致。`resolving` 即使曾被 B05 Add readback 接受，也不得进入 Search。

### 4.2 去重与排序

按上游返回顺序单次扫描：

1. ID 完全相同且 content 相同，保留第一次；
2. ID 不同但 `content.strip()` 完全相同，保留第一次；
3. 同一 ID 对应不同 content，作为协议矛盾失败；
4. 不做 case-fold、Unicode 重写、标点删除、模糊/近义合并或分数二次排序；
5. 过滤和去重后再截断到 `top_k`，不 overfetch 补齐。

这只能保证隔离、状态和确定性重复控制；没有可靠 fact key/version/tombstone 时，不宣称 Top 100
任意两条语义上互不冲突。

### 4.3 长度边界

当前公开契约只冻结 `top_k <= 100`，未公布 Answer 输入上限，也没有单条 evidence 字符/token
上限。R1 因此不截断单条 memory content，避免把证据切成错误语义；硬边界继承 Gateway 的
`MEMOS_RESPONSE_MAX_BYTES=1 MiB` 响应上限、公开 `top_k` 和 deadline。测试及调测报告额外记录
返回条数、总字符数和 UTF-8 字节数（只记录计数，不记录原文），在真实 baseline 后通过 K/
relativity 单变量消融决定是否需要更小的 evidence budget。若必须增加总字符/token 截断策略，
视为新的可见排序策略，须单独审批而不能在 Gate 1 静默加入。

## 5. 超时、取消、错误和日志

### 5.1 应用和 Gateway

- `MemoryGateway.search` 精确变更为
  `search(request, *, timeout_seconds: float) -> Sequence[GatewayEvidence]`；Fake 和 Real 实现都拒绝
  bool、非数值、NaN/Inf 和非正预算；
- `MemoryOperations` 新增 Search deadline/warn 构造参数和 `SearchTimeoutError`，错误码为
  `search.timeout`、`retryable=true`；
- 外层 deadline 耗尽映射为该应用错误；已有 Gateway timeout、429、408/504、其它 4xx/5xx、断连、
  非 JSON、超大响应和 business-code 失败继续使用脱敏 Gateway typed error；
- `CancelledError` 原样传播，不转换为空结果或普通成功；
- Search 不自动重试。公开错误继续使用既有统一 error envelope，不改公共 Schema。

### 5.2 固定 MemOS 窄补丁

在 `docker/memos/apply_patchset.py` 和 `PATCHSET_LOCK.json` 中增加 hash-guarded B06 patch：

1. 修改固定 `single_cube.py::_search_text()`，删除 catch-all 后返回 `[]` 的错误成功，让异常传播给
   Product handler；真实零命中仍返回成功空集合；
2. 修改 `searcher.py` 的直接原始 query 日志，只保留长度/短 hash、候选计数、阶段和耗时；
3. 同时清理 `task_goal_parser.py` 的 fine-mode prompt/query/response 原文日志。baseline 虽为 fast，
   但 `mode` 是运行期可调项，不能留下可达的明文日志路径；
4. 继续验证补丁前/后 SHA-256、幂等拒绝、固定源码漂移拒绝和 Python compile。

不改第三方 archive、上游 commit、模型实现或其它无关日志。MemScope 日志只允许 query 字符数/短
hash、参数指纹、候选/过滤数量、耗时、结果分类和 typed error code；禁止 query/options/content、
完整响应、凭据和不必要的 user/Cube 原值。

## 6. Readiness 设计

`MemosMemoryGateway.verify_upstream()` 在启动阶段用一个最多 10 秒的共享 monotonic budget 完成：

1. MemOS `GET /health` 必须返回固定健康结构；
2. 对专用不存在 Cube 执行一次无写入 `POST /product/search` capability probe：`top_k=1`、唯一
   `readable_cube_ids`、其余 conservative 参数；合法空结果通过，任何技术/协议错误失败；
3. 成功后仅缓存“本进程已验证 Search capability”标志，不在每次公共 Health 中重复 embedding。

运行期 `MemosMemoryGateway.is_ready()` 同时要求：Gateway 未关闭、receipt store ready、启动 Search
probe 已成功、当前 MemOS health 成功。`MemoryOperations.is_ready()` 继续将其与 Raw Store readiness
合取。任何检查抛错都收敛为公共 503，不泄漏依赖细节。

启动 probe 证明 Search 路径可调用，不替代部署验收的真实 Add + Search smoke。模型凭据或能力在
启动后变化时，真实请求必须失败而非返回空成功；恢复完整能力需要通过部署 smoke，必要时重启以
重做 capability probe。B06 不为此引入后台探测 worker。

## 7. 逐文件变更清单

### 7.1 生产代码

| 文件 | 精确变更 | 明确不改 |
|---|---|---|
| `src/memscope/settings.py` | Search enum、6 个配置、关系校验、safe summary | Add 默认值和 profile 字符串 |
| `src/memscope/memory_gateway/protocol.py` | Search 加必填剩余预算 | Add contract |
| `src/memscope/memory_gateway/fake.py` | 接受/校验 Search 预算，保持确定性排名 | Fake 算法不作为质量实现 |
| `src/memscope/memory_gateway/memos_models.py` | 独立 Search envelope/bucket/item parser、过滤统计和精确去重 | B05 Add parser 不放宽 |
| `src/memscope/memory_gateway/memos.py` | Product payload、单 deadline HTTP、严格转换、readiness/probe | receipt/Add/reconcile 语义 |
| `src/memscope/application/memory_operations.py` | 50/55 秒告警与外层 deadline、剩余预算、二次隔离/截断 | Add lane/deadline/receipt |
| `src/memscope/runtime.py` | Search 配置注入、启动健康+capability probe、失败逆序清理 | 多 worker/后台任务 |

预计无需修改 `src/memscope/api/models.py`、`api/routes.py`、`operations.py`、Raw Store Schema 或 receipt
Schema；若实现发现必须改变这些冻结边界，立即停止并请求修订，不顺手扩 scope。

### 7.2 固定源码、部署和文档

| 文件 | 精确变更 |
|---|---|
| `docker/memos/apply_patchset.py` | 新增异常传播和 Search 日志脱敏的受控 transform |
| `docker/memos/PATCHSET_LOCK.json` | 记录新增目标的精确 pre/post hash |
| `deploy/compose.env.example` | 增加 6 个 Search 参数示例，不放真实 URL/Key |
| `compose.yaml` | 注入 Search 参数；memory-api healthcheck 改为严格检查公共 `/health` 2xx/`ok` |
| `docs/batches/B06/NATIVE_DEPLOYMENT.md` | 完整非 Docker Add + Search + Health 部署、验证、故障与回退 |
| `docs/interfaces/memory-gateway-v1.md` | 新 Search budget、Real Search、过滤/错误/readiness 契约 |
| `docs/integrations/MEMOS_V2_0_32_MAP.md` | Product Search、recall/rerank/status、兼容补丁源码路由 |
| `SDD.md` | B06 完成后生成与实际代码一致的初版，覆盖记忆、存储、召回、更新/遗忘边界和限制 |
| `README.md`、`docs/README.md`、`docs/CODEMAP.md`、`docs/PROJECT_CONTEXT.md` | 只同步实际完成状态和导航，不提前宣称 Gate 2 |

不在开发迭代中构建镜像。Compose 的镜像标签只在源码冻结后的候选打包阶段统一更新，避免为标签
变更提前触发构建。

## 8. 确定性测试矩阵

### 8.1 单元与契约测试

| 测试文件 | 必须覆盖 |
|---|---|
| `tests/unit/test_settings.py` | 默认值、enum、bool、deadline 关系、relativity 范围/finite、safe summary |
| `tests/contract/memory_gateway_contract.py`、`tests/unit/test_fake_memory_gateway.py` | 必填预算、非法预算、关闭/取消/故障、原有排序隔离不回退 |
| `tests/unit/test_memory_operations.py` | 预算传递、50/55 秒 fake-clock 告警/超时、取消、无 lane、二次 user/Cube 过滤和截断 |
| `tests/unit/test_memos_models.py` | 成功/空/畸形结构、状态/类型/provenance/score/time、重复与矛盾 ID |
| `tests/unit/test_memos_memory_gateway.py` | 精确 payload、跨 session、options 不发送、HTTP/business 错误、剩余预算、health/probe/receipt readiness |
| `tests/unit/test_runtime.py` | 配置接线、probe 成败、失败清理、完整 operations ready |
| `tests/unit/test_b06_memos_patchset.py` | hash/compile、异常不再变空成功、fast/fine 可达日志无 query/prompt/response 原文、漂移拒绝 |
| `tests/contract/test_contest_api.py` | 公开 Schema 不变、排序/top_k/options、统一错误 envelope |
| `tests/contract/test_memory_operations_http.py` | 完整 profile Health 200/503、真实组合 Search timeout/error；Add 回归 |

所有耗时行为用 fake clock、事件或 stub transport 确定性驱动，不等待 50/55 秒真实时间。

### 8.2 执行顺序和命令

用户批准实现后按最短反馈顺序运行：

```bash
uv run pytest tests/unit/test_memos_models.py tests/unit/test_memos_memory_gateway.py \
  tests/unit/test_memory_operations.py tests/unit/test_runtime.py
uv run pytest tests/contract/test_contest_api.py \
  tests/contract/test_memory_operations_http.py tests/unit/test_b06_memos_patchset.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

不得用跳过测试、降低 95% branch-aware coverage 门槛或宽化 parser 来换取通过。

### 8.3 原生/源码挂载最小真实验证

在不启动 Docker、不安装新依赖的前提下，优先复用已运行的 Neo4j/Qdrant/MemOS，并以 Mock Model
执行：

1. 启动固定 patch 后的 MemOS 和原生 memory-api，各自单 worker；
2. 确认 Search probe 成功后公共 Health 为 200；
3. 同一 user 跨两个 session Add，立即 Search 能看到 `activated` evidence；
4. 相同 Add replay 不重复；另一 user 用相同 query 得到空结果；
5. 注入 MemOS Search 内部错误，确认不是 HTTP 200 空结果；
6. 注入 inactive/resolving/foreign/missing-provenance/重复候选，确认过滤、顺序和 top_k；
7. 捕获 memory-api/MemOS 日志，用 canary query/options/content 验证原文均未出现；
8. 记录启动、Add、Search、Health 的命令、非密钥配置、耗时和结果。

新增一个仅使用 Python 标准库的 `scripts/verify_b06_candidate.py` 固化上述公开 HTTP contract smoke；
它不启动/删除服务、不修改 provider 数据结构，只针对调用方提供的 base URL 和带命名空间测试用户
运行。Mock 路径要求非空 Search 命中；真实模型路径还必须由调测机人工/报告确认语义结果。

## 9. 华为调测机任务与单变量调优

开发机可以验证 payload、结构、过滤、超时、错误、日志和 Mock 闭环，但不能声称真实模型 ID、
Embedding 维度、真实分数分布、P95/max 延迟或语义准确率。

调测机收到已标识 commit/ZIP 后严格执行：

1. 校验 SHA-256；在 10 分钟内选择原生或 Docker 路径；
2. 探测实际 Chat/Embedding 模型 ID、协议、维度、timeout 和 429；不得把这些运行事实写成代码
   假设；
3. 先做一条真实 Add + Search + Health smoke，再跑小样本 baseline；
4. baseline 可复现后才按 `SEARCH_DESIGN_AND_TUNING.md` 做单变量实验：relativity、rerank、mode、
   dedup 各自独立；
5. 每次只记录候选 ID、commit、唯一变量、非密钥配置、数据切片、分数、P95/max、失败数、结论和
   回退点；
6. 任一候选 Search 达到 60 秒、出现错误成功/跨用户泄漏或 accuracy 无收益，立即回退 R1 baseline。

外部 reranker、BM25/full-text、MMR 三倍候选和混合检索均不是首轮调测前置项；需要新的明确审批
才可进入最终候选。

## 10. 非 Docker 与 Docker 交付边界

非 Docker 指南是 B06 P0 的正式产物，必须覆盖：固定源码 archive/hash/patch、两个 Python 环境、
Neo4j/Qdrant 前置、MemOS 与 memory-api 非密钥环境变量、启动顺序、单 worker、Health、Add replay、
跨 session Search、跨用户隔离、超时/错误定位、数据路径和回退。指南必须能在 Docker 不可用时
独立完成 Add + Search + Health。

Docker 仅在源码冻结后进入：

1. daemon/Compose、host port、cgroup、镜像 manifest、包源、磁盘预检最多 10 分钟；
2. 任一阶段排障累计最多 30 分钟，到点转原生路径，不重置计时；
3. 普通模型/Prompt/URL/Key/阈值/Search 参数变化不构建镜像；
4. 冻结候选最多做一次最终镜像构建；clean-room 复现仅在已有可评分候选且环境正常时追加；
5. Docker 失败只记录为 P4 未完成项，不阻塞 P0～P3。

## 11. 风险、停工条件与回退

| 风险 | 计划内防线 | 必须停工并请求用户决定的条件 |
|---|---|---|
| 跨用户/Cube 泄漏 | 唯一 readable Cube + metadata/provenance + 应用二次校验 | 任一外用户候选进入公开响应 |
| 错误成功 | 固定源码补丁 + strict HTTP/envelope + fault test | 内部异常仍可变成 200 空结果 |
| 旧值/forget 泄漏 | 只放 `activated`，不查询时写状态 | 要求保证 B05 尚未提交的 tombstone/version 语义 |
| B05 `resolving` 接缝 | Add/Search 真实状态 smoke；Search 严格排除 | 正常 Add 成功但只有 `resolving` 可见，须正式修订 B05 |
| top_k 噪声/延迟 | 不 overfetch、稳定 exact dedup、55 秒 deadline | baseline 达 60 秒或必须引入新检索架构 |
| readiness 假阳性 | Raw+receipt+current health+startup probe+部署 smoke | 无法在现有依赖完成无写 probe 或真实 smoke |
| 日志泄密 | 双侧窄补丁、canary 扫描 | query/content/Key 在可达日志出现 |
| provider 结构漂移 | 严格 parser 和 patch hash | 固定源码或真实响应结构与已核验事实冲突 |
| Embedding 维度变化 | 仅调测机探测，不自动迁移索引 | 需要重建/迁移现有索引或改变持久化契约 |

出现上述条件、需要公共 Schema/额外服务/新 worker、或 Docker 到时且无原生路径时，停止扩大实现并
报告。回退点是 B05 Accepted/Frozen commit `e7abf5f` 及其后权威冻结文档；不得 reset/覆盖用户
工作，通过新分支或 revert 型提交保持可审计。

## 12. 执行顺序、提交边界和 Gate 2 入口

用户批准本计划后才依次执行：

1. 从当前已核验 HEAD 创建 `batch/b06-real-search`，先保存已批准 Gate 0/Gate 1 文档身份；
2. 实现 Search DTO/parser 和固定 payload，不触碰公共 Schema；
3. 实现 Gateway Search deadline、错误映射、readiness/probe；
4. 接入 application/settings/runtime，并让 Fake/contract 同步；
5. 实施固定 MemOS 异常传播与日志脱敏 patch，更新 hash lock；
6. 完成逐层单元/契约测试和全量静态/覆盖率门禁；
7. 编写并实际走通非 Docker 指南与 Mock 原生闭环；
8. 若现有 daemon 能在时间盒内工作，源码冻结后做一次最终候选镜像构建；否则记录 P4 defer；
9. 产出与实际代码一致的初版 `SDD.md`，以及 B06 `CONTEXT.md`、`HANDOFF.md`、测试/耗时/日志/
   部署证据和已知限制；
10. 只在实现与证据齐备后请求进入 Gate 2，由用户验收。

建议提交按可回退边界拆分为：`Search parser/Gateway`、`application/runtime/tests`、`fixed-source
patch/deployment/docs`；若时间要求合并，仍须在 handoff 中逐文件列出。不得在 Gate 1 自动提交、推送、
进入 Gate 2 或声称 Accepted/Frozen。

## 13. 当前审批门

- B06 Pre-Gate：已通过；
- B06 Gate 0 R1：已冻结；
- B06 Gate 1：本计划已获用户明确批准并完成开发机实施；
- B06 Gate 2：用户已于 2026-09-04 明确验收，`Accepted/Frozen`。

真实模型能力、Add/Search 语义 smoke、延迟和评分由华为调测机补证，不得用开发机推断替代。

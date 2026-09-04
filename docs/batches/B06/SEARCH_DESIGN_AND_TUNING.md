# B06 Search 设计讨论与调测机调优指南

> 状态：设计点讨论已结束；B06 Gate 0 已于 2026-09-03 完成一次最小修订并正式冻结为 R1。
> Gate 1 实施计划已获用户明确批准，开发机候选已进入 Gate 2 评审。冻结边界见
> [GATE0.md](GATE0.md)，实施计划见 [PLAN.md](PLAN.md)。
>
> 当前覆盖：设计点 1（混合召回、rerank、Top-K 冲突/互补和遗忘语义）已于
> 2026-09-03 经用户确认并冻结；用户确认没有其它设计点。

> **48 小时紧急约束：**任何实现或调测必须遵守
> [48 小时交付止损规则](../../collaboration/48H_DELIVERY_GUARDRAILS.md)。准确性优先，但
> Search 端到端必须小于 60 秒；Docker 是 P4 加分项，不能阻塞核心 Search 开发和调优。

## 1. 文档用途与边界

本文持续记录 B06 Search 设计点的：

1. 已核验的仓库和固定 MemOS v2.0.32 源码事实；
2. 用户逐项确认的设计结论；
3. 可在调测机独立验证的候选优化；
4. 不能由 B06 静默改变的 B05 冻结语义和待决接缝。

本文不是 B06 `PLAN.md`，不授权实现。公开 Search 仍只返回排序后的记忆证据，不生成最终答案；
正式 `top_k=100` 是响应上限，不要求填满。评测机不会传入内部 `rerank`、`filters` 或
`keyword_search` 参数，内部映射由 MemScope 负责：
[正式评测边界](../../acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md#23-search)。

## 2. 设计点 1：混合召回、rerank、Top-K 冲突/互补和遗忘

### 2.1 已确认结论

1. baseline 保留固定栈已有的本地 `cosine_local` reranker，不在首版引入外部 reranker。
2. 混合召回与 rerank 分层处理；BM25、full-text 和外部 reranker 必须作为彼此独立的消融项，
   不能同时打开后归因。
3. `top_k=100` 是响应上限；状态正确、相关且有用优先于填满 100 条。
4. MMR 只用于减少重复和改善多样性，不承担语义冲突判定，也不能替代 Add 的
   update/forget 状态提交。
5. 遗忘采用 Search tombstone/状态转移语义；普通 Search 不返回 forgotten 内容，受保护的 Raw、
   provenance 和审计证据不因普通遗忘而被物理删除。
6. 当前 B05 尚不能保证为普通 Add 对话产生可靠的 update/forget 状态。若要求端到端保证，必须
   正式修订 B05 接缝；不得在 B06 Search 中偷带 organizer 或查询时状态写入。

### 2.2 reranker 的职责和 baseline 边界

reranker 只负责在候选已经召回后重新估计查询相关性和排序。它不能恢复未召回证据，也不能修复
跨用户数据、旧版本、已遗忘内容或未提交状态。固定前置顺序保持为：

```text
user/Cube isolation
    -> committed/status/version/tombstone filtering
    -> relevance candidate recall
    -> exact/source deduplication
    -> rerank
    -> best-effort complementary selection
    -> stable ordering and truncation
```

固定 Product Search 默认 `rerank=true`：
[请求模型](../../../.vendor-src/MemOS/src/memos/api/product_models.py#L425-L430)。当前 Compose 明确
使用 `cosine_local`：
[运行配置](../../../compose.yaml#L171-L172)。该实现复用查询与候选 embedding 做余弦重排，不调用
外部模型：
[CosineLocalReranker](../../../.vendor-src/MemOS/src/memos/reranker/cosine_local.py#L52-L110)。

不能在保持其它参数不变时直接关闭 rerank。固定 Searcher 会为未 rerank 的候选赋 `0.0` 分，再由
Product Search 的默认 `relativity=0.45` 过滤，存在合法召回被清空的风险：
[禁用分支](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/retrieve/searcher.py#L80-L102)、
[relativity 默认值](../../../.vendor-src/MemOS/src/memos/api/product_models.py#L400-L430)。

`rerank_knowledge_mem()` 的名称不能作为存在第二次模型重排的证据。固定源码没有使用传入的
reranker，只按已有 `relativity` 排序 knowledge memory：
[formatter 实现](../../../.vendor-src/MemOS/src/memos/api/handlers/formatters_handler.py#L169-L234)。

### 2.3 混合召回的源码事实

固定 MemOS 对非 WorkingMemory 候选并行执行图结构召回和向量召回，并在配置启用时追加 BM25 与
full-text，最后按 memory ID 合并：
[GraphMemoryRetriever.retrieve](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/retrieve/recall.py#L81-L184)。
这一步是候选生成，不等于 rerank。

固定 API 配置中 `FAST_GRAPH`、`BM25_CALL` 和 `FULLTEXT_CALL` 均默认关闭；当前 Compose 和原生
指南进一步显式固定 `FAST_GRAPH/BM25_CALL/VEC_COT_CALL/FULLTEXT_CALL=false`，避免继承宿主环境
变量而意外启用。因此当前 baseline 的实际候选路径主要是图召回加向量召回：
[搜索策略配置](../../../.vendor-src/MemOS/src/memos/api/config.py#L1263-L1268)。是否启用其它通路只能
由独立实验决定。固定上游 BM25/full-text 源码仍有原 query/query-term 日志；未来启用任一路径前，
必须先增加固定源码脱敏补丁和对应 canary 测试，不能仅切换环境变量上线。

### 2.4 Top-K 的硬保证与互补性边界

B06 可承诺的硬保证是：

1. 结果必须属于请求 `user_id` 对应的唯一 logical Cube，并通过 provider provenance 复核；
2. 只允许已提交且符合当前可见状态/版本/tombstone 的结果；
3. 对 memory ID、规范化内容和来源位置执行确定性去重；
4. 同一可识别事实槽只保留当前有效版本，历史或时间查询仅按明确时间语义选择历史证据；
5. 丢弃非有限分数，提供确定性并列排序，并在最终输出处截断至 `top_k`；
6. 高质量候选不足时返回少于 100 条，不使用低相关、重复或失效内容补齐。

语义上的“任意两条都不冲突”不能只由 Search 保证。若 Add 没有生成稳定事实 key、版本支配关系或
tombstone，Search 无法仅靠相似度可靠判断哪条是当前真值。经确认的 B05 原则同样规定：查询时
压制冲突不能替代 Add 的 update/forget 状态发布：
[B05 状态与互补性结论](../B05/ADD_DESIGN_AND_TUNING.md#36-对-graphmemix-参考观点的核验)。

互补选择属于 best effort：必须先满足状态与相关性门槛，再抑制高度相似结果，并优先覆盖与查询
有关的不同 `entity/key/time` 事实槽、clarification、corroboration 或多跳桥接证据。普通 MMR
只衡量相关性与相似度多样性，不得被表述为逻辑冲突检测。

固定 Product Search 在 `dedup=sim/mmr` 时将内部 `top_k` 放大三倍：
[候选扩张](../../../.vendor-src/MemOS/src/memos/api/handlers/search_handler.py#L87-L115)。其 MMR 再计算
候选相似度矩阵并迭代选择：
[MMR 实现](../../../.vendor-src/MemOS/src/memos/api/handlers/search_handler.py#L331-L565)。因此公共
`top_k=100` 下，MMR 的候选规模、缺失 embedding 补算、CPU/内存和端到端延迟必须实测；它不是
无成本的默认正确性组件。

### 2.5 遗忘语义与当前 B05 接缝

目标语义已经冻结为逻辑状态转移：更新发布新 `activated` 版本并抑制旧版本；遗忘同步发布 Search
tombstone；普通 Search 始终排除 forgotten 内容。历史状态和受保护 Raw 不应因普通遗忘一律物理
删除：
[B05 状态转移结论](../B05/ADD_DESIGN_AND_TUNING.md#34-状态转移流程与依据)。

固定 MemOS 的实现并不统一：

- metadata 定义 `activated`、`resolving`、`archived`、`deleted`：
  [状态字段](../../../.vendor-src/MemOS/src/memos/memories/textual/item.py#L109-L127)；
- `soft_delete()` 将节点标为 `deleted`：
  [软删除](../../../.vendor-src/MemOS/src/memos/memories/textual/tree.py#L621-L642)；
- organizer merge 将旧节点标为 `archived`，但 fallback hard-update 会直接删除旧节点：
  [冲突处理](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/organize/handler.py#L131-L190)；
- 当前部署关闭 scheduler 和 reorganizer：
  [Compose 开关](../../../compose.yaml#L180-L183)。

因此当前不能声称用户在 Add 对话中表达 forget 后一定生成 tombstone。B06 只能过滤 provider 已经
提供且可信的状态，不能在 Search 时调用 LLM 推断遗忘、修改状态或合并记忆。

另有一个尚未解决的正式接缝：B05 committed readback 接受 `activated` 或 `resolving`：
[B05 provider parser](../../../src/memscope/memory_gateway/memos_models.py#L121-L123)；安全 Search 的既定
前置顺序却要求排除 `resolving`：
[B05 Search 屏障](../B05/ADD_DESIGN_AND_TUNING.md#35-发布原子性顺序和-search-屏障)。若真实 Add 能以
`resolving` 完成，就可能出现 Add 成功但 Search 不可见；若 Search 放行它，则可能暴露中间态或冲突。
Gate 0 R1 决定：B06 Search 严格排除 `resolving`，当前不修改 B05 已冻结的 readback 规则；Gate 1
必须验证正常 Add 产生 `activated`。若真实路径出现 Add 成功但只有 `resolving`，立即停止并请求
正式 B05 接缝修订，不得由 Search 放行中间态。

### 2.6 调测与止损顺序

在状态、隔离、错误传播和 60 秒 deadline 尚未验证前，不启用外部 reranker。之后使用固定保留集
逐项比较：

1. `fast + cosine_local` baseline；
2. 单独改变 dedup/MMR；
3. 单独启用 BM25 或 full-text；
4. 仅在仍有充足延迟余量时比较外部 reranker。

每项同时记录端到端分数、useful/duplicate/stale/distractor 比例、空结果率、Search
P50/P95/P99/max、模型调用和 429/5xx/timeout。任何跨用户泄漏、确定性 forget 泄漏、旧值支配、
错误成功或 Search 达到 60 秒均为硬淘汰条件。

## 3. 调测机存储初始化与候选隔离

调测机必须把“模型配置”和“存储身份”作为一个候选整体管理。固定 MemOS 会自动尝试创建
Qdrant `neo4j_vec_db` 和 Neo4j 索引，但它不会在已存在 collection 时强制拒绝错误维度，Neo4j
部分建索引异常也只记录 warning。因此，容器 healthy、MemOS `/health` 或一次空结果 Search 都不能
证明候选已经正确初始化。

### 3.1 每个候选的固定身份

每份调测记录至少绑定以下非密钥信息：

- 代码 commit/交接包 SHA-256 和 MemOS patchset hash；
- Embedding provider、精确模型 ID、实测输出维度；
- Chat/extractor 模型 ID；
- Neo4j/Qdrant 固定版本及持久目录或 Compose project/volume 标识；
- Search mode、relativity、dedup、rerank 和其它本轮唯一变量；
- 初始化方式是全新存储、兼容复用还是经过批准的迁移。

普通 Search 参数变化不需要重建镜像或重建数据库。Embedding 模型或输出维度变化时，即使维度数字
碰巧相同，也不得把新向量写入旧模型的向量空间；同时隔离 Neo4j 和 Qdrant 数据，或执行经批准的
全量重嵌入迁移。仅更换 Qdrant 而保留含旧 embedding 的 Neo4j 数据同样不是干净候选。

### 3.2 调测启动顺序

每个全新模型候选严格执行：

1. 用最终 API 实测 Embedding 输出维度，写入候选记录；
2. 选择空的、候选专属 Neo4j/Qdrant 持久目录或卷，确认磁盘和写权限；
3. 启动 Neo4j/Qdrant，分别通过 `RETURN 1` 和 `/readyz`；
4. 单 worker 启动 MemOS，确认没有 authentication、permission、disk、collection、index 或
   dimension warning/error；
5. 启动 memory-api，让有界无写 Product Search probe 通过；
6. 运行 `scripts/verify_b06_candidate.py --require-hit`，使首次创建、真实写入、readback、Search、
   replay 和用户隔离在受控 smoke 中完成；
7. 再核对 Qdrant collection dimension/distance，以及 Neo4j 必要索引的 `ONLINE` 状态；
8. 保存不含正文和凭据的结果后，才开始 baseline/消融题集。

首次 cold run 和后续 warm run 分开记录。cold run 用于发现镜像、模型握手、collection/索引初始化
和缓存成本；正式 Add `<120s`、Search `<60s` 的验收仍必须在正常服务状态下成立，不能靠忽略第一次
失败或自动重试得到成功。

### 3.3 硬淘汰与止损

以下任一条件出现，当前候选立即停止，不进入调优，也不改阈值掩盖基础设施错误：

- Qdrant collection 不存在、不可用、distance 非 cosine 或维度不等于实测输出；
- Neo4j 必要索引缺失、`FAILED`，或在有界等待后仍未 `ONLINE`；
- Add/Search 出现 vector dimension、认证、权限、磁盘或数据库连接错误；
- 公共 Health 成功但真实 Add→Search 闭环失败；
- 通过返回空 `200`、跨 Cube fallback、Raw fallback、自动重试或修改 deadline 才能通过；
- 不同 Embedding 模型/维度共用同一组已有 Neo4j/Qdrant 数据。

处置顺序是：保存配置指纹、结构状态、阶段耗时和 typed error；停止 memory-api/MemOS；保留数据
快照；确认无正式数据后才换全新持久目录/卷重跑。已有正式数据时不得删除 collection、索引或节点，
必须回传并进入迁移/重嵌入评审。日志和回传材料不得包含 query、memory content、向量、Key 或完整
provider response。

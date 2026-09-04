# B06 Gate 0：Real Search 核心设计（R1）

> 状态：2026-09-03 经用户确认完成唯一一次最小 Gate 0 修订，正式冻结为 R1。
>
> 本文冻结 B06 必须进入 Gate 1 计划的设计边界，不授权代码开发。Gate 1 计划已提交，当前待用户
> 明确批准，见 [PLAN.md](PLAN.md)。
> 设计核验和调测顺序见 [SEARCH_DESIGN_AND_TUNING.md](SEARCH_DESIGN_AND_TUNING.md)。

## 1. 目标和范围

B06 负责把 B05 已冻结的真实同步 Add、Contest Adapter、Raw Store、`MemoryOperations` 和固定
MemOS v2.0.32 接成可评分的真实 Search，并在完整 Add + Search 路径可用时开放公共 Health。

B06 只实现：

- Product Search 请求映射和严格响应转换；
- `user_id -> logical Cube` 强隔离及 provider provenance 复核；
- 状态、来源和类型过滤；
- 排序保持、保守精确去重和 `top_k` 截断；
- 单一 Search deadline、typed failure 和完整 readiness；
- Search 路径必要的固定源码窄兼容补丁与脱敏观测；
- 面向主办方、覆盖 Add + Search + Health 的非 Docker 部署指南。

B06 不改变比赛公开请求/响应 Schema，不按 `session_id` 隔离，不生成最终答案，不使用 gold，不以
Raw Search 伪装成功，也不引入最终模型选择、prompt 调优、Answer/Judge、不可逆 organizer、额外
服务、多 memory-api worker 或自动重试。

Gate 0 优先级固定为：

1. 公开契约、用户/Cube 隔离、状态与 provenance 正确性、禁止错误成功；
2. Search 端到端严格低于 60 秒；
3. Add + Search + Health 形成可启动、可验证、可回退的 P0 闭环；
4. 得到首个真实可复现 baseline 后才做单变量准确率优化；
5. Docker 只作为 P4 加分项，不阻塞 P0～P3。

## 2. R1 冻结的 conservative baseline

### 2.1 Product Search 请求

首个 baseline 显式发送以下内部参数，不依赖固定 Product API 的隐式默认值：

| 参数 | R1 默认值 | 边界 |
|---|---|---|
| `query` | 公开请求原值 | 不重写、不拼接 options |
| `user_id` | 公开请求原值 | 仅作 provider 信息；不作为唯一 ACL |
| `readable_cube_ids` | `[expected_logical_cube]` | 必须显式指定唯一 Cube |
| `session_id` | 省略 | Search 跨该用户所有 session |
| `mode` | `fast` | 执行 query embedding，不调用 Search LLM |
| `top_k` | 公开 `top_k` | 最终仍由 MemScope 再截断 |
| `relativity` | `0.0` | 接线 baseline；运行期可调，不是最终准确率值 |
| `dedup` | `null` | 使用上游精确文本去重，不触发 MMR/三倍扩张 |
| `rerank` | `true` | 使用当前 `cosine_local` |
| `search_memory_type` | `All` | 输出仍仅接受批准的文本记忆类型 |
| preference/tool/skill | 全部关闭 | 不召回当前 Add 未启用的类别 |
| internet/neighbor discovery | 全部关闭 | 不增加外部来源、邻居泄漏或额外延迟 |

公开 `options` 继续原样穿过公开和应用契约，但固定 Product Search 不支持该字段；Gateway 不发送
它，也不选择答案。

`mode`、`relativity`、`dedup` 和 `rerank` 必须作为集中、typed、启动时校验的普通 Search 配置，
使调测机无需修改代码或重建镜像即可做单变量实验。R1 默认关闭 BM25、full-text、MMR 和外部
reranker。

依据：

- [Product Search 参数](../../../.vendor-src/MemOS/src/memos/api/product_models.py#L366-L520)
- [MMR/sim 候选扩张](../../../.vendor-src/MemOS/src/memos/api/handlers/search_handler.py#L87-L115)
- [固定搜索策略默认值](../../../.vendor-src/MemOS/src/memos/api/config.py#L1263-L1268)
- [当前本地 reranker](../../../compose.yaml#L171-L172)

### 2.2 结果信任边界

只有同时满足下列条件的 Product `text_mem` item 才能成为公开 evidence：

1. bucket `cube_id` 等于 MemScope 根据请求 `user_id` 重算的 logical Cube；
2. metadata `user_id` 和 `memscope_cube_id` 分别等于请求用户和预期 Cube；
3. B05 provider provenance 存在且格式有效；
4. `status` 严格为 `activated`；
5. memory type 是当前允许的 `WorkingMemory`、`LongTermMemory` 或 `UserMemory`；
6. ID 和 content 非空，score 缺失或为有限数值；
7. `created_at` 只有能解析为 timezone-aware 时间时才输出，否则省略。

`resolving`、`archived`、`deleted`、未知状态、外用户/外 Cube、缺失 provenance、未知 bucket/类型和
畸形 item 一律不进入公开结果。不同 recall 分支是否已经过滤状态不能替代这层统一后过滤：
[固定 recall 分支差异](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/retrieve/recall.py#L273-L344)。

Gateway 对相同 ID 或完全相同的规范化内容执行稳定、保守的精确去重，保留上游第一个最高排序
候选；不做近义合并或查询时冲突推断。应用再次校验 user/Cube、保持 Gateway 顺序，并在 Adapter
最终安全截断至公开 `top_k`。

`top_k=100` 是上限而非填充目标。状态/来源过滤后不足 100 条时直接返回较少结果，不 overfetch
低质量内容补齐。

## 3. R1 必须增加的正确性护栏

### R1-01：禁止 Search 错误成功

固定 MemOS `_search_text()` 当前捕获所有异常并返回空列表，外层仍生成成功 envelope：

- [异常吞并](../../../.vendor-src/MemOS/src/memos/multi_mem_cube/single_cube.py#L190-L221)
- [成功响应](../../../.vendor-src/MemOS/src/memos/api/handlers/search_handler.py#L144-L152)

Gate 1 必须通过最窄兼容补丁让技术异常传播为失败。MemScope 继续校验 HTTP 状态、JSON content
type/大小和 Product `code/message/data` envelope，并映射为既有脱敏 typed Gateway 错误。只有真实
零命中可以返回 `{"data":[]}`；禁止恢复旧计划中的 error-to-empty 策略，禁止自动重试。

### R1-02：单一 55 秒 Search deadline

Search 使用从应用操作入口覆盖 Gateway HTTP、响应解析、状态过滤、结果转换和返回前处理的单一
monotonic deadline：

- hard deadline 默认 55 秒，必须满足 `0 < deadline < 60`；
- 慢请求告警默认 50 秒，必须小于 hard deadline；
- `MemoryGateway.search` 接收调用方传入的有限正数剩余预算；
- HTTP connect/read/write/pool 等待只能消费剩余预算；
- deadline/取消向上传播为失败，不能转换为空成功；
- Search 不进入 Add 的同用户写 lane，也不增加重试。

当前接口和实现尚无 Search timeout：
[Gateway port](../../interfaces/memory-gateway-v1.md#search-contract)、
[application Search](../../../src/memscope/application/memory_operations.py#L174-L205)。

### R1-03：`resolving` 接缝的保守决策

B05 readback 接受 `activated` 或 `resolving`，但 B06 Search 只允许 `activated`。R1 暂不修改已经
冻结的 B05 Add 成功语义，因为当前 organizer 关闭且新节点默认 `activated`。Gate 1 必须加入正常
Add 状态探测和 `resolving` 排除测试。

若真实栈出现 Add 成功但结果只有 `resolving`，必须停止并请求正式 B05 接缝修订；不能让 B06
Search 放行中间态，也不能静默改变 B05 parser：
[B05 provider parser](../../../src/memscope/memory_gateway/memos_models.py#L121-L123)。

B06 同样不能为 B05 未生成的事实 key、版本关系或 forget tombstone 补造状态。当前 update/forget
能力限制必须在最终 SDD 中披露；是否正式扩展 B05 只能由独立审批决定。

### R1-04：完整且有界的 readiness

固定 MemOS `/health` 只报告进程健康，不探测 Embedding、Neo4j、Qdrant 或 Product Search：
[固定 health](../../../.vendor-src/MemOS/src/memos/api/server_api.py#L53-L60)。

R1 readiness 必须同时要求：

1. Raw Store 和 Gateway receipt store 可用；
2. MemOS 当前 health 成功；
3. 启动阶段已完成一次有界、隔离、无写入的 Product Search capability probe；
4. probe 使用专用不存在 Cube、`top_k=1` 和 conservative 参数，合法空结果可通过，技术错误不可
   通过；
5. 每次公共 `/health` 不重新调用 Embedding，也不写入测试记忆；
6. 部署验收另行执行一次真实 Add + Search smoke，失败时公共 Health 不得作为完整就绪证据。

公共 Health 只有在上述完整运行 profile 就绪时返回 2xx。ASGI 启动、socket 存活或单独的 MemOS
health 均不足以宣称 ready：
[公开 Health 契约](../../interfaces/contest-http-v1.md#public-paths)。

### R1-05：Search 日志和配置脱敏

MemScope 与固定 MemOS Search 日志不得记录原始 query、options、memory content、完整 provider
response、凭据或不必要的 user/Cube 标识。允许记录 query 字符数/短 hash、候选与过滤数量、参数
配置指纹、阶段耗时、结果分类和 typed error code。

固定 handler 已有安全摘要，但 Searcher 仍直接记录 query，Gate 1 必须用窄补丁消除并加入 canary
测试：

- [安全请求摘要](../../../.vendor-src/MemOS/src/memos/log.py#L38-L64)
- [Searcher 原始 query 日志](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/retrieve/searcher.py#L123-L125)

## 4. Gate 1 计划必须覆盖的验收项

Gate 1 计划至少包含以下确定性验证，不得以真实模型分数替代：

1. Product payload 精确映射唯一 Cube、跨 session、conservative 参数和 options 不选答；
2. 成功 envelope、合法空结果和 text-memory bucket/item 严格解析；
3. foreign user/Cube、缺 provenance、非 `activated`、未知类型、NaN/Inf score 和 naive/非法时间被
   正确拒绝或省略；
4. exact ID/content 去重、上游顺序保持、稳定并列和不超过 `top_k`；
5. 429、408/504、其它 4xx、5xx、断连、超时、非 JSON、超大响应和非 200 business code 映射；
6. 固定 MemOS 内部异常不再变成空结果 HTTP 200；
7. 50 秒告警、55 秒 hard deadline、剩余预算和取消传播可确定性验证；
8. readiness 的成功、任一依赖失败、Search probe 失败及恢复条件；
9. Search 日志 canary 在 memory-api 和 MemOS 输出中均无敏感原文；
10. 正常 B05 Add 的结果是 Search 可见 `activated`，`resolving` 不泄漏；
11. Mock Model + 固定 MemOS 的最小真实 Add/Search，复用已有 Neo4j/Qdrant/MemOS；
12. 面向主办方的非 Docker 完整部署指南覆盖 Add、Search、Health、配置和故障定位。

验证顺序固定为：

```text
Python unit/contract tests
    -> memory-api native or source bind mount
    -> reuse running Neo4j/Qdrant/MemOS
    -> code freeze
    -> one final image build
```

Pre-Gate 和 Gate 0 不运行 Docker。未来 Docker 前置能力检查最多 10 分钟，单阶段排障最多 30 分钟；
Docker 不可用时，非 Docker 指南是正式兜底路径。

## 5. 明确延后的算法优化

以下内容不进入 R1 baseline：

- MMR、sim dedup、三倍候选扩张或为填满 100 条而 overfetch；
- 外部 BGE/cross-encoder reranker；
- BM25、full-text、`fine`/`mixture` Search；
- Raw Search、RRF、双路融合或 raw-text 成功 fallback；
- Search 时调用 LLM 判断冲突、更新、遗忘或选项答案；
- 新 organizer、后台任务、额外服务、自动重试或多 worker；
- 在没有真实失败证据时修订 B05 Add 状态机。

首个真实 baseline 可评分且硬约束全部通过后，才按
[SEARCH_DESIGN_AND_TUNING.md](SEARCH_DESIGN_AND_TUNING.md#26-调测与止损顺序) 做单变量实验。真实 model
ID、Embedding 维度、relativity 阈值、最终 evidence 数量、分数分布与质量收益都是调测事实，不是
Gate 0 阻塞项。

## 6. 门禁状态

- B06 Pre-Gate Context Review：用户已确认通过；
- B06 Gate 0 R1：用户已确认并正式冻结；
- B06 Gate 1：精确实施计划已获用户明确批准，开发机候选已经形成；
- B06 Gate 2：用户已于 2026-09-04 明确验收，`Accepted/Frozen`；
- 后续不得把本文件明确延后的算法静默加入 baseline。

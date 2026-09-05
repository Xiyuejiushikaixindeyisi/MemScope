# MemScope 双 Session 调优与单 Session 汇合方案

> **归档说明：最终 session 分工、停止规则和可复制 prompt 以 [FINAL_TUNING_EXECUTION_APPROVAL_PLAN.md](../../../FINAL_TUNING_EXECUTION_APPROVAL_PLAN.md) 为唯一准绳；本文保留拓扑分析。**

> 状态：本 session 只产出方案；M1/M2/M3 方法学已批准；T00/DS 执行仍待审批，不自动启动 Docker、模型调用、实验、测试或构建  
> 日期：2026-09-05  
> 关联总计划：[24H_TUNING_APPROVAL_PLAN.md](24H_TUNING_APPROVAL_PLAN.md)  
> 已确认：T07 已拒绝；T02 内部 `0.92` 锁定；不含 MMR 或自动 prompt 搜索；prompt 最低优先级

参数依赖和数学选参方法见：[TUNING_INTERACTIONS_AND_MODELING.md](TUNING_INTERACTIONS_AND_MODELING.md)。
T00 观测项与五样本冻结清单见：[T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md](../../../T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md)。
主办方澄清的规则边界与技术核验见：[ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md](../../../ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md)。

## 1. 审批结论摘要

采用“先在当前 Add 配置上冻结 T00 store，再双 Session 并行 Search，最后单 Session 汇合”的默认结构。prompt 调优不再位于默认 Search 前置链：

```text
单 Session：T00 baseline
       │
       ├─ 冻结当前 Add 配置与五样本 store
       ├─ 验证 T05 endpoint，建立共同的 T05-only 对照
       │
       ├─────────────── 双 Session 分叉 ───────────────┐
       │                                               │
Session A：T01 + T05                         Session B：T02 + T05
调 relativity，dedup 固定 exact               调 dedup=sim，relativity 固定 0
       │                                               │
       └────────────── 汇合为单 Session ──────────────┘
                               │
                 测 T01 + T02 + T05 组合交互
                               │
                 单栈复跑质量、延迟、失败与回退
                               │
              仅无可接受 Search 候选且有明确 Add 错误时
                  再讨论 T04；T03/T06 prompt 最后另审
                               │
                         T90 最终交付
```

这样处理接受“reranker 通常有利”的工程先验，把 T05 作为两条 Search lane 的共同底座，同时保留三个必要证据：

1. `T05-only` 相对本地 cosine baseline 是否真有净收益。
2. T01/T02 在 T05 已开启时分别贡献多少增益。
3. T01、T02、T05 三者组合是否发生负交互。

## 2. Add 依赖与最低优先级 prompt 的处理

T03、T04、T06 会改变写入的记忆内容、数量、分片和分数分布。如果先在旧存储上完成 T01/T02/T05，再接受一个 Add 候选，则 Search 参数必须全部重测。

用户已明确 prompt 调优最低优先级，因此默认顺序调整为：

1. T00 建立 baseline 和错误分桶。
2. 冻结当前 Add 配置和唯一 store，优先执行已批准方法学所需的 Search 实验。
3. 只有没有可接受 Search 候选、T00 又证明 Add 错误是主因且剩余时间足够，才另行审批 T04。
4. T03/T06 prompt 排在最后，不做自动搜索；若后续接受任何 Add 候选，全部 Search 结论在新 store 上作废并重跑。

### 2.1 串行 Add 决策

| 发现 | 串行操作 | 后续 |
|---|---|---|
| Add 没有形成主要失败簇 | 跳过 T03/T04/T06 | 直接进入双 Session Search |
| example 诱导、角色误归因、抽取边界错误明显 | 记录错误簇，先完成 Search 路线；T03 最后另审 | 不做自动 prompt 搜索 |
| 长距离指代/切片错误明显 | 运行 T04 的单方向、单值实验 | 不与 T03 同时改变 |
| 同时存在两类错误 | 优先非 prompt 的 T04；T03 保持最后 | 最多选择一个；组合不进入 24 小时计划 |
| T03 无效且仍有大量同构系统性错误 | T06 只形成赛后/紧急备选说明 | 不自动执行，不做自动 prompt 搜索 |

T06 是代码级升级路径，不能与其他 session 同时编辑共享工作树或构建同名镜像。默认方案不预授权 T03/T06；若以后单独批准 prompt patch，只能依据成熟实现提炼一个可解释规则并做单变量实验。

## 3. 双 Session 的 Docker 拓扑

推荐使用一个冻结的 backend，而不是启动两个完整四服务栈：

```text
Session A -> memory-api-A :18081 --\
                                    shared MemOS (external BGE reranker)
Session B -> memory-api-B :18082 --/        │
                                         Neo4j + Qdrant
                                         冻结、只读 baseline
```

可行依据：

- `MEMOS_SEARCH_RELATIVITY` 和 `MEMOS_SEARCH_DEDUP` 位于 memory-api，作为每次 Product Search 请求参数发送。
- `MOS_RERANKER_BACKEND` 位于 MemOS 进程，因此两个 lane 可以共享同一个已启用 T05 的 MemOS backend。
- 双 lane 期间禁止 `/add`，保证 Neo4j/Qdrant 中的候选集合一致。
- 两个 memory-api 前端使用独立端口、独立本地卷、独立私密 env 和独立输出目录。

这比两个完整 Compose project 更合适：少启动一套 MemOS/Neo4j/Qdrant，避免复制非确定性 Add 数据，也把容器资源上限从两个完整栈约 17 GiB/18 CPU 降为一个完整 backend 加一个额外 memory-api。

实现边界：使用开发专用、release 之外的 Compose override 或等价容器启动方式；不得修改最终 `compose.release.yaml`，不得并行 build，不得改变共享 image tag。

## 4. 分叉前的共同对照

双 Session 启动前由主 session 串行完成：

### C0：当前本地基线

```text
relativity=0.0
dedup=exact
rerank=true
MOS_RERANKER_BACKEND=cosine_local
```

C0 复用 T00 的固定数据集结果；若 Add 配置发生变化，则必须在冻结的新存储上重跑 C0。

### C5：T05-only 共同对照

```text
relativity=0.0
dedup=exact
rerank=true
MOS_RERANKER_BACKEND=http_bge
```

进入并行阶段前必须满足：

- reranker capability probe 通过，不打印 key、query 或 document 原文。
- 使用拟进入最终评测的 endpoint/模型，或明确标记为“仅开发证据、不能进入 release”。
- 目标 endpoint/model 必须能由主办方在内网提供并通过配置注入凭证；开发侧公网 endpoint 不能替代该确认，真实 key/租户信息不得进入仓库或镜像。
- C5 完成两轮相同查询，未出现 401/403/404/429/5xx/timeout/schema error。
- Search max 小于 60 秒，P95 相对 C0 仍有安全余量。
- 由于 Session B 的 `sim` 会将内部 `top_k=100` 放大到约 300，目标 reranker endpoint 必须先通过 1/100/300 个脱敏文档的容量探测，并完成一次真实最大候选 Search；否则取消 Session B，不临时修改适配器分批/截断逻辑。

C5 不要求先证明一定提分才允许短时分叉，但若 C5 明显低于 C0，两条并行 lane 立即取消，回到 local cosine。

## 5. Session A：T01 + T05

**唯一可变项：`MEMOS_SEARCH_RELATIVITY`**

固定项：

```text
MEMOS_SEARCH_DEDUP=exact
MEMOS_SEARCH_RERANK=true
MOS_RERANKER_BACKEND=http_bge
```

执行：

1. 先以 relativity=0 收集 external reranker score，按实际 score breakpoint 离线选出 `tau_exact`，不做等间隔大网格。
2. 最多在线确认两个阈值，每个阈值运行两轮相同 query 集，顺序固定。
3. 记录相对 C5 的质量翻转、空结果率、返回条数、错误率和墙钟时间。
4. 选择 A-best；若两个阈值都不优于 C5，则 A-best=C5，即 relativity 保持 0.0。

硬淘汰：空结果率不可接受、相关证据被系统性过滤、任何跨用户/状态泄漏、60 秒超时或远端错误增长。

## 6. Session B：T02 + T05

**唯一可变项：`MEMOS_SEARCH_DEDUP`**

固定项：

```text
MEMOS_SEARCH_RELATIVITY=0.0
MEMOS_SEARCH_RERANK=true
MOS_RERANKER_BACKEND=http_bge
```

执行：

1. 默认只测试 `dedup=sim`，与 C5 的 `dedup=exact` 比较。
2. 运行两轮相同 query 集，顺序固定。
3. 记录相对 C5 的质量翻转、重复率、证据覆盖、错误率、墙钟时间和脱敏 score；在该 arm 单独估计 `tau_sim`。
4. 选择 B-best；若 `sim` 不优于 C5，则 B-best=C5，即保持 exact。Session A 的 `tau_exact` 不直接作为 sim 的最终阈值。

MMR 及其参数在本轮明确排除，不因 `sim` 结果自动恢复审批。`sim` 保持内部 `0.92` 不变，并会把上游候选量放大三倍。

## 7. 双 Session 的并发限制

两个 session 可以同时工作，但不能把并行压力当成最终性能数据：

1. 两边使用相同 query 集 hash、同一冻结 store ID、同一 commit/image ID 和相同 T05 endpoint/model。
2. 禁止 Add、重启共享 backend、修改共享 env、修改源码或 build。
3. 每个 session 只写自己的私密结果目录；结果文件不得包含凭据和正文。
4. 两边共享 embedding/reranker API 配额。先从全局 Search 并发 2 开始；出现 429、排队或 P95 明显抬升，降为 1，此时停止并行请求，但两个 agent-session 仍可并行分析已有结果。
5. 并行阶段只比较质量和功能错误。所有候选延迟必须在汇合后单栈、串行复跑。
6. 任一 session 不得独立决定最终候选，也不得自行修改 release 配置。

## 8. 汇合为单 Session

两条 lane 完成后，停止并行请求，由单一主 session 接管：

### 8.1 先验收两个结果包

必须一致：

- commit、image ID、Add 配置、store ID、数据切分/hash、query 顺序和 T05 endpoint/model。
- C5 对照定义。
- 质量指标计算方式。

任一身份不一致则不能横向比较，相关 lane 作废或重跑。

### 8.2 决策表

| A-best | B-best | 汇合动作 |
|---|---|---|
| 无增益 | 无增益 | 保留 C5；再比较 C5 与 C0 |
| 有增益 | 无增益 | 串行复跑 `T01+T05` |
| 无增益 | 有增益 | 串行复跑 `T02+T05` |
| 都有增益 | 都有增益 | 新增一次 `T01+T02+T05` 组合实验，不直接相加两边收益 |

### 8.3 三变量组合实验

若 A、B 均为净正，使用：

```text
relativity=<在 sim+T05 arm 重新估计的 tau_sim>
dedup=<B-best，通常为 sim>
rerank=true
MOS_RERANKER_BACKEND=http_bge
```

组合候选必须与 C0、C5、A-best、B-best 比较。先用 `tau_exact` 做固定阈值的 T01×T02 交互分析，再只在线确认一次 `tau_sim+sim+T05`。若组合不如最佳单 lane，选择最佳单 lane，不为“功能更多”牺牲得分或可靠性。

### 8.4 最终无竞争复验

最终候选在单 backend、单评测 session 下完成：

- 两轮冻结五样本确认；该集合已参与选参，不称为独立 holdout。
- Search success、质量、空结果率、重复率、P50/P95/max。
- 401/403/404/429/5xx/timeout/schema error。
- reranker endpoint 断开时确认显式失败，并验证切回 `cosine_local` 后服务可恢复。

评测端目标 reranker endpoint 未验证、两轮收益方向不一致、或 Search 尾延迟缺乏安全余量时，T05 不得进入 release。此时在剩余时间内只复验 local cosine 下的 T01 或 T02 最佳单项。

## 9. 24 小时时间线

冻结点 H14 不后移，H14～H24 留给 T90：

| 时间 | Session 结构 | 工作 | 止损 |
|---|---|---|---|
| H0～H2 | 单 session | T00 五样本 baseline、错误分桶、冻结当前 store | 120 分钟硬止损；无 baseline 则转 T90 |
| H2～H3 | 单 session | T05 probe 与 C5 | C5 明显退化或协议失败，取消 T05 双 lane |
| H3～H6 | 双 session | A=`T01+T05`；B=`T02+T05@sim(0.92)` | 429/资源争用则请求串行、分析仍并行 |
| H6～H8 | 汇合单 session | 验收结果；按 M3 最多确认一次 `T01+T02+T05` | 最多一个组合候选 |
| H8～H10 | 单 session | 无可接受 Search 候选且 Add 错误明确时，才另审 T04；prompt 默认跳过 | 任一 Add 变化会触发 Search 重校准 |
| H10～H14 | 单 session | 最终五样本复验、无竞争延迟、目标 endpoint 与回退验证 | H14 强制冻结 |
| H14～H24 | 单 session | 全量检查、四镜像、TAR/hash、离线拉起、评测机 smoke | 禁止新调优 |

T03/T06 不在默认时间线内，也不做自动 prompt 搜索。若 H8 后仍要启动 prompt patch，必须单独审批，并同时接受缩减/取消后续 Search 重校准的代价；H14 冻结点不后移。

## 10. 风险与回退顺序

主要风险：

- T05 将 Search 增加一个外部同步依赖；当前适配器 fail-closed，远端失败会成为 Search 失败。
- 并行两个 lane 会共同消耗 embedding/reranker 配额，可能造成 429 和延迟污染。
- relativity、dedup、reranker 位于同一候选处理链，单项正收益不保证组合正收益。
- 双 memory-api 前端不是最终发布拓扑，只用于开发评估；release 仍保持一个 memory-api worker。

最终回退顺序：

```text
T01+T02+T05
-> 最佳的 T01+T05 或 T02+T05
-> T05-only
-> local cosine + 最佳 T01/T02（若已复验）
-> C0 baseline
```

## 11. 审批项

执行仍建议拆成三个 gate。M1/M2/M3 已批准，只解决“怎么选参”，不等于以下 gate 已获执行授权：

### DS0：baseline 与冻结当前 store

授权当前主 session 完成 T00 五样本 baseline，并冻结当前 Add store；baseline 不交给调优
agent，不自动授权 T03/T04/T06。

### DS1：双 Session Search 阶段

授权建立 C5，并并行运行：

- Session A：T01+T05，最多两个 relativity 候选。
- Session B：T02+T05，仅 `sim`，不含 MMR。

DS1 的硬前置是一个只发送 Search 的 runner。现有 `local_proxy_eval.py --base-url` 会先执行
Add，不能直接用于两个独立 memory-api 前端，否则各自的 SQLite receipt store 会让同一数据
再次写入共享 MemOS backend。Search-only runner 必须从 T00 manifest 重建 user/query 顺序，
禁止调用 `/add`，并把结果写入各 lane 独立的私密目录；可以是仓库外一次性受审脚本，是否将其
产品化为仓库 harness 需另行审批。

### DS2：汇合阶段

授权在两边均净正时测试一次 `T01+T02+T05`，然后由单 session 做无竞争复验；不包含 T90 最终制品构建。

**建议审批口令：**

```text
批准 DS0、DS1、DS2；T02 仅 sim 且内部 0.92 锁定，不含 MMR；T03/T04/T06 和 T90 仍需单独审批；不做自动 prompt 搜索；未验证最终 reranker endpoint 时不得将 T05 写入 release。
```

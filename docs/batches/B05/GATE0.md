# B05 Gate 0：Real Add 核心算法设计（R1）

> 状态：2026-09-03 经用户确认完成最小修订；Gate 1 后续已获批准并进入实现验证。
>
> 本文冻结 B05 Gate 0 的设计边界和必须进入 Gate 1 计划的正确性要求，不授权实现。
> 三个设计点的论文核验、详细推理和调测矩阵见
> [ADD_DESIGN_AND_TUNING.md](ADD_DESIGN_AND_TUNING.md)。

## 1. 目标和范围

B05 负责把已经冻结的 Contest Adapter、Raw Store、`MemoryOperations` 和固定 MemOS v2.0.32
连接成真实、同步、可审计的 Add baseline。B05 不实现最终答案，不改变公开 HTTP 契约，也不完成
B06 的正式 Search 排序算法。

Gate 0 的优先级保持为：

1. API 契约、`user_id` 隔离、幂等和禁止 gold；
2. Add 端到端严格低于 120 秒；
3. 成功 Add 的持久化、基础索引和关键状态立即安全可见；
4. 通过上述硬约束后，优先提高冻结 holdout 的端到端准确率；
5. 同等准确率下再比较尾延迟、调用量和资源。

## 2. 保持不变的 baseline

本次 R1 不改变原 Gate 0 已批准的主路线：

- 通过 MemOS Product API 接入，不绕过它直接拼装 Neo4j/Qdrant 写入；
- 使用 `SimpleStructMemReader` 的 `async_mode="sync" + mode="fine"`；
- baseline 使用一个主抽取 LLM；`fast` 只作为诊断对照，不是静默降级；
- 使用稳定逻辑 Cube 映射，并通过 `writable_cube_ids` 指定写入目标；
- 原始消息保持 role、timestamp 和输入顺序；Raw Store 继续承担请求幂等和原始证据；
- 单个外部 Add request/chunk 是独立同步提交单元，不等待不存在的 `final_chunk`；
- B05 默认不执行不可逆的 LLM merge/delete，不丢弃状态历史和 provenance；
- Gateway、LLM、Embedding 的精确 model ID 和能力必须由调测机探测，不能按公网名称猜测；
- B05 只建立真实 Add 路径；完整 Search 仍属于独立的 B06 Gate 0～2；
- 在 B06 完成真实 Search 和整体依赖 readiness 前，公开 Health 不得宣称完整服务 ready；
- 不增加盲目自动重试、raw-only 成功降级或后台 pending worker；可靠性闭环仍属于后续 Batch。

## 3. R1 必须增加的正确性护栏

### R1-01：显式区分抽取结果和技术失败

LLM 返回合法 schema 且 `memory list` 为空，是有效的“本段没有长期记忆”；LLM 调用异常、空响应、
截断或 JSON/schema 解析失败则是技术失败。两者不得合并。

baseline 禁止把技术失败时的整段原文伪装成正常 `UserMemory` 后返回成功。只有合法抽取结果或合法
空结果可以继续提交；技术失败必须映射为脱敏的 typed failure，不完成 Raw Store 的成功响应，保留
`PENDING` 以支持相同 `request_id` 的既有被动恢复语义。

这条约束修复固定源码中 `_safe_generate/_safe_parse` 失败后以原文构造记忆的风险，但不在 Gate 0
决定具体异常类名或补丁位置：

- [当前 fallback](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L258-L313)
- [Raw Store Add 状态机](../../interfaces/raw-store-v1.md#add-state-machine)

### R1-02：确定性窗口顺序、任务隔离和 provenance

在进入任何并行抽取前，为 request、chunk、message、outer window 和 inner window 分配稳定序号。
可以并行调用模型，但必须按原始窗口序号重组结果，不能按 future 完成顺序决定写入顺序。

每个并行任务获得独立、不可交叉修改的输入视图；禁止多个任务共享并 `pop`/修改同一个 metadata
字典。每条抽取结果必须能追溯到当前 request 的 source message ID/ordinal 和原始 timestamp。

两级 overlap 继续作为上下文时，只允许根据稳定 source identity 去除可证明的精确重复。相似文本、
近义事实或不同时间的同一属性不得在 baseline 中自动合并。

源码依据：

- [inner token window](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L315-L356)
- [共享 metadata 与处理入口](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L358-L370)
- [outer futures 按完成顺序回收](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L659-L715)
- [outer message window](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L784-L869)

### R1-03：逐 Add committed visibility 和非破坏性状态边界

每个 Add 返回 HTTP 200 前，至少完成：本次原始证据持久化、合法抽取结果持久化、基础索引可见，
以及由本次请求产生的关键 update/forget 抑制效果发布。不能在第一次 Search、空闲定时器或下一个
session 到达时才完成这些工作。

baseline 使用非破坏性的事实版本、tombstone/状态证据和 provenance；无法安全消解的矛盾保留为
显式 unresolved，不由后台任务猜测后删除历史。异步任务只允许生成不影响当前事实或遗忘可见性的
派生关系/摘要；若固定 MemOS 的后台 organizer 无法满足这个边界，baseline 必须禁用其权威写操作或
通过窄兼容层隔离。

B05 必须为 B06 留下单一的 committed-visibility/state-filter 接缝和可测试 readback；是否采用完整
generation pointer、具体存储字段和事务映射留给 Gate 1 冻结，不能在 Gate 0 假定上游已经原子实现。

依据：

- [正式 Add/Search 时序](../../acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md#3-正式评测边界)
- [应用层成功顺序](../../../src/memscope/application/memory_operations.py#L56-L103)

### R1-04：单一端到端 deadline 和取消传播

Add 使用从 Contest Adapter 入口覆盖到 Raw Store `complete_add` 的单一 monotonic deadline。所有
Gateway/LLM/Embedding/持久化等待只能消费剩余预算；取消和 deadline exceeded 必须向上传播为失败，
不能转换为成功或触发无界等待。

生产内部 deadline 必须严格小于正式 120 秒，并为响应序列化、持久化和网络抖动保留余量。精确值
由 Gate 1 提供可校验初值，再由调测机依据比赛式并发下的 P99/max 调整；105 秒目前只作为观测告警
线，不是未经实测的强制截断值。baseline 不自动重试语义写入。

### R1-05：最小可替换点，默认行为冻结

Gate 1 只为真实变化边界建立小接口或受校验配置，不建设通用插件系统：

| 变化点 | baseline 默认值 | 调测边界 |
|---|---|---|
| extractor model | 单个运行期精确 model ID | 能力探测后在相同 prompt 下 bake-off |
| prompt | 固定 upstream P0，带稳定 ID/hash | P1/P2 在可复现 baseline 后单变量实验 |
| window policy | 稳定 request-local 窗口 | 大小/overlap 真实调测 |
| carry-over | 关闭 | 有界同-session tail 独立实验 |
| extra LLM/reviewer | 关闭 | 必须证明净正向翻转和 120 秒内尾延迟 |
| raw pre-cluster/reorder | 禁止 | 不作为候选 |
| post-extraction grouping | 关闭 | key/entity/time 小候选实验 |
| Markdown evidence | 关闭 | B06 query-time serialization 实验 |
| destructive organizer | 关闭或非权威 | 只允许经过状态与故障测试的候选 |

配置必须集中、typed、启动时校验，并能生成不含凭据的稳定摘要。feature flag 关闭时不得产生额外
模型调用、后台任务或隐式状态变化。

### R1-06：可复现观测，不记录敏感正文

每个 Add 至少产生可聚合的脱敏观测：

- request outcome 分类；
- Adapter、Raw prepare、Cube ensure、抽取 LLM、Embedding、provider write/index、Raw complete 的耗时；
- outer/inner window 数、模型调用次数、输入/输出 token（能力可得时）、合法空结果和 parse failure 数；
- 抽取记忆数量、精确 overlap duplicate 数、状态 unresolved 数；
- timeout、取消、429/5xx 和非密钥配置指纹。

日志、指标和调测报告不得包含 Key/IAM token、完整私密对话或不必要的完整模型响应。

## 4. Gate 1 必须覆盖的确定性验收项

除既有 Gateway contract、Raw Store 幂等和 HTTP contract 外，Gate 1 计划至少必须包含：

1. 合法空抽取成功；LLM 异常、空响应、截断、非法 JSON/schema 明确失败；
2. 乱序完成的模型 futures 仍产生稳定窗口顺序和相同持久结果；
3. 并行窗口不共享可变 metadata；原始 role/timestamp/source ordinal 不丢失；
4. 双层 overlap 不产生可证明的精确重复，且不误合并不同时间或不同 source 的事实；
5. 每个 chunk 独立提交，不依赖 final marker、首个 Search 或后台 scheduler；
6. Add 200 后执行最小 readback 可见性检查；后台 scheduler 停止时关键结果不变化；
7. 同一用户并发请求保持持久化顺序，不同用户完全隔离；
8. deadline/取消在各阶段注入时不返回成功、不错误完成 Raw response、不产生无界重试；
9. feature flag 默认关闭时没有额外调用和状态副作用；
10. 日志与配置摘要不泄露凭据和完整敏感正文。

开发机使用 Fake/Mock/fixture 验证确定性契约，不声称模型质量；真实 model ID、协议、P95/P99/max、
429、token 和端到端得分由调测机补证。

## 5. 明确延后的算法优化

以下内容不进入 B05 baseline：最终 GLM/Qwen 胜者、prompt P1/P2、extra LLM、语义相似去重、全量
session 重放、原始对话聚类、Markdown dossier、GraphMemix 式互补召回、完整 generation pointer、
自动重试/熔断和最终 Search evidence budget。

它们只能在 baseline 可复现、硬约束通过后，由调测机按单变量实验、冻结 holdout、正负翻转和
可回退证据决定。公开 gold、题号、options 或 Judge 特征不得进入 Add prompt 或调优规则。

## 6. 门禁状态

- B05 Gate 0 R1：已由用户确认；
- B05 Gate 1：已批准，按 [PLAN.md](PLAN.md) 完成实现验证；
- 用户明确批准 `PLAN.md` 后才可创建实现分支和编写核心业务代码；
- Gate 1 不得把本文件列为“延后”的算法静默加入 baseline。

# 主办方澄清与 MemScope 调优影响

> 状态：调优方案输入；本 session 只产出方案，不运行 Docker、模型、评测或测试  
> 记录日期：2026-09-05  
> 来源：用户转述的主办方回复；只对赛题规则、允许边界和提交要求视为权威，技术路线仍需证据与实测验证  
> 关联方案：[T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md](T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md)

## 1. 先区分规则、许可和技术假设

主办方对“什么允许提交、什么算违规、评测如何接入”有最终解释权；这不等于其提出的记忆实现方式天然最优。后续方案按三类处理：

### A. 有约束力的规则/交付门槛

1. **Search 只能返回记忆证据，不能针对题目直接作答，也不能把 gold 伪装成 memory。**
2. **API Key、租户凭证和 token 不得随代码或制品提交。** 模型依赖必须可配置，并在说明文档写明内网要求；自训练模型或其他特殊依赖需与课题组确认。
3. **最终压缩包名和压缩目标文件夹名必须为 ASCII。**

这三项是合规或可部署性 gate；无论通用论文或博客如何建议，都不能越过。

### B. 主办方确认的允许范围，不是强制实现

1. Search evidence **可以**包含由 Add 输入的 session time 与相对时间推导出的绝对日期或时间区间。
2. Add **可以**提取、总结、改写和结构化，不要求逐字保存原对话。

“可以”只消除了违规疑虑，不证明该做法一定提高最终分数，也不要求 MemScope 必须采用某一种 evidence schema。

### C. 必须用数据验证的技术假设

1. 在 Add 阶段主动把 `yesterday/last week` 正规化为日期或区间，可能比只保存原文与 session timestamp 更利于下游 Answer。
2. 自包含的结构化 summary 可能比原文片段更容易检索和回答。
3. 保留 `event_time`、`observed_at`、状态和 provenance 可能改善 temporal/update/forget，但也会改变向量文本与 score 分布。

这些只作为候选策略。它们必须在冻结困难样本上与“原文/原始时间戳保留”对照；未验证前不写成最终硬约束。

## 2. 对主办方技术判断的核验

| 主张 | 外部/仓库证据 | 结论与可信度 |
|---|---|---|
| 时间信息应进入长期记忆链路 | LoCoMo 官方数据把每个 session 与 `session_<num>_date_time` 成对提供，原论文以 temporal event graph 构造数据；MemScope 当前 Add 适配器也已把每条输入 timestamp 转成 `chat_time` | **方向成立，高可信。** 时间戳不是可忽略元数据；但这只证明需要保留时间锚点，不证明必须在 Add 中提前生成唯一绝对日期 |
| 按 episode 时间解析相对表达有工程先例 | Graphiti 当前实现明确要求用 per-episode timestamp 解析相对时间，并维护 `valid_at`/`invalid_at` | **可行，中高可信。** 是成熟开源实现证据，不是本赛题上的因果收益证明；仍需防 timezone、模糊表达和伪精确 |
| Add 总结/结构化通常更好 | LoCoMo含 event summarization；多种 agent-memory 系统使用抽取或结构化表示 | **仅证明常见，不证明净收益，中可信。** MemOps 强调 exact user-span provenance、stale-value、over-forget 和 unsupported reflection；有损总结可能恰好破坏这些能力 |
| Search 返回正规化日期 evidence 会帮助 Answer | 主办方确认允许；LoCoMo temporal QA 确实依赖 session 时间 | **合理但未验证，中可信。** 正确对照应是“原文+timestamp”“原文+正规化字段”“仅 summary”三类，而不是直接认定后者优胜 |
| 主办方会自动提供任意外部模型的鉴权 | 回复只要求预留配置并说明内网，自训练模型或其他情况还要求联系确认 | **不能推出，低可信/未确认。** T05 的最终 reranker model、endpoint、协议和凭证必须单独确认；不能把开发端可用等同于评测端可用 |

核验来源：

- [LoCoMo 官方数据说明](https://github.com/snap-research/LoCoMo)：session 与 timestamp 是正式数据结构的一部分。
- [LoCoMo ACL 2024 论文](https://aclanthology.org/2024.acl-long.747/)：数据生成和评测明确包含 temporal event graph 与事件总结。
- [Graphiti 时间抽取实现](https://github.com/getzep/graphiti/blob/main/graphiti_core/utils/maintenance/edge_operations.py)：按 episode timestamp 解析相对时间，并维护事实有效区间。
- [MemOps 官方仓库](https://github.com/MemTensor/MemOps)：强调 provenance、update stale-value、forget leakage/over-forget 与 reflect evidence support；仓库也明确标注为 research preview，因此适合作为本赛题诊断口径，不应被当作已充分验证的通用最优实践。

主办方对 Answer 输入结构未公开带来的代理评测不确定性仍然存在。其回复澄清了允许边界，但没有证明某种 memory 文本一定最适配隐藏 Answer；最终应优先返回自包含、可追溯的 evidence，并同时观察 retrieval 指标与 proxy Answer，而不是只优化单一 judge 分数。

## 3. 时间类问题的允许边界与候选策略

### 3.1 允许的 evidence

若某条消息发生于 2023-05-08，内容是“我昨天完成了项目”，Add 可以形成：

```text
On 7 May 2023, the user completed the project; this was stated in the 8 May 2023 session.
```

Search 返回这类 self-contained memory evidence 是允许的，但当前仅作为待验证候选。它同时包含：

- 事件；
- 从会话时间推导出的事件时间；
- 必要时包含 observation/session 时间与推导关系；
- 主体和来源语境。

### 3.2 禁止的输出

```text
Answer: 7 May 2023
```

如果它只是针对当前题目生成的最终答题句，或者来自 gold 而非 Add 输入，就不符合 evidence-only 约束。

### 3.3 若采用正规化，不确定时间不能伪精确

- `yesterday` 在已知 session date/timezone 时通常可以解析为具体日期。
- `last week` 若原文没有具体星期几，应保留为前一自然周或相对区间，不能编造某一天。
- `recently`、`a while ago` 等模糊表达应保留不确定性。
- 只使用输入 timestamp/session time 作锚点；不得用服务运行当天时间代替历史 observation time。
- timezone 缺失时按评测输入约定处理并记录假设，不能静默跨日偏移。

## 4. 对 T00 的直接修改

T00 除原有 baseline 和错误分桶外，新增 `temporal_grounding` 诊断块：

| 指标 | 含义 |
|---|---|
| `timestamp_ingest_coverage` | 带 timestamp 的输入是否完整传到 memory reader |
| `relative_time_detection_rate` | yesterday/last week/before/after 等表达是否被识别 |
| `absolute_or_interval_grounding_rate` | 能精确解析的是否转成绝对日期，不能精确的是否保留区间/不确定性 |
| `temporal_attribution_error` | 日期是否绑定到错误主体或错误事件 |
| `temporal_anchor_error` | 是否错用当前时间、另一 session 时间或错误 timezone |
| `temporal_evidence_recall` | 时间题所需的带时证据是否进入 Search 结果 |
| `answer_like_output_rate` | Search content 是否退化为针对题目的直接答案句 |

LoCoMo `locomo_conv-41` 的 26 道 temporal 题全部进入该切片。T00 应区分：

```text
timestamp 未进入 Add
-> timestamp 已进入但抽取未落到 memory
-> memory 有时间但 Search 未召回
-> Search 已召回，proxy Answer/Judge 仍失败
```

最后一种不能直接归因给记忆服务，也不能通过把最终答案写进 Search 来规避。

## 5. 对 Add 提取/压缩的影响

主办方明确允许 Add 做总结改写，因此总结可以进入候选集；但默认基线仍保持当前实现，不因为“允许”就自动改写。候选目标是形成适合后续 Answer 的、自包含、可追溯的证据，同时保留足以审计的来源关系。

若实施结构化候选，推荐保留的 evidence 属性：

- `subject`：事实属于用户、对话中的其他人，还是 assistant 建议；
- `fact/event`：原子化但保留必要语境；
- `event_time`：精确日期、时间区间或明确的不确定性；
- `observed_at`：必要时保留事实在哪个 session 被陈述；
- `state`：current/tentative/superseded/forgotten 等生命周期语义；
- `source/provenance`：可以追溯到输入消息，而不是来自问题或 gold。

对总结候选必须同时评估：

```text
atomic fact coverage
subject/role fidelity
temporal grounding accuracy
update/forget state fidelity
self-contained evidence rate
unsupported fact rate
compression ratio（只作成本指标，不作首要目标）
```

允许总结不意味着总结一定优于原文。任何压缩若丢失数字、否定、主体、时间、更新链或 Forget 边界，均直接否决。

## 6. 对 T01～T06 的影响

| 项目 | 澄清后的处理 |
|---|---|
| T01 | 无需改变方法；threshold 必须作用于包含时间语义的最终 memory 分布上 |
| T02 | 内部 `0.92` 继续锁定；相似去重必须特别检查不同日期/状态的事实是否被误合并 |
| T03 | 删除 example 仍属于最低优先级 prompt 实验；主办方允许改写不构成自动批准 |
| T04 | window 变化可能改变 relative expression 与 session timestamp 的共同上下文；若进入实验需增加 temporal slice |
| T05 | reranker query-document 输入中应保留时间和状态词；只有主办方可访问的内网 endpoint/model 获确认后才具备 release 资格 |
| T06 | 若未来另审，只允许一个人工、来源明确的规则补丁；优先规则是 timestamp grounding、主体归因或 state fidelity，不做自动 prompt 搜索 |

如果未来另行批准的 Add 侧候选改变了时间正规化或总结内容，既有 T01/T02/T05 分数分布全部失效，必须在新 store 上重新校准。当前批准的 M1/M2/M3 与 Search 路线不以新增正规化代码为前置。

## 7. 凭证与内网模型 gate

最终候选必须满足：

1. 代码、镜像、示例 env、日志、TAR 和文档中不含真实 API Key、租户 ID 或 token。
2. 所有模型相关值通过明确的配置项注入：endpoint、model、credential env name、timeout；说明文档注明内网依赖。
3. 在课题组确认会提供所需 endpoint/model/凭证的前提下，评测人员注入配置后可以非交互启动；不得要求评测人员改源码。
4. 必需凭证缺失或 endpoint/model 不兼容时 fail fast/readiness false，不能健康但静默换模型。
5. 开发侧 SiliconFlow 或其他公网 endpoint 的成功只证明适配器协议，不证明评测内网可用。
6. T05 若需要一个主办方未承诺提供的 reranker model，必须先联系课题组确认；未确认时最终回退 `cosine_local`。

因此 T05 的 release 条件是以下三项同时成立：

```text
五样本质量净正
+ 目标内网 endpoint/model 协议与容量通过
+ 主办方确认可注入所需凭证
```

缺一项，T05 只能保留为开发结论，不能写入最终 release 默认配置。

## 8. 最终压缩包与目录命名

不新增一套制品命名。沿用仓库当前 `build_candidate_delivery.py` 已实现的 ASCII 名称：

```text
solution-<12hex>.zip
memscope-images-<12hex>-linux-amd64.tar
output/extraction target: an ASCII-only candidate directory
```

命名规则：

```text
^[A-Za-z0-9._-]+$
```

最终方案中的 T90 必须把以下内容列为硬 gate：

- 压缩包 basename 仅 ASCII；
- 压缩目标/输出文件夹仅 ASCII；
- `INSTRUCTION.md` 中所有解压/启动示例使用 ASCII 目录名；
- 不在临近提交时为了命名规则大范围重命名源码目录；
- 本地公开评测集的中文目录不是交付必需项时，不纳入最终 release allowlist。

当前澄清明确提到压缩包名和压缩目标文件夹名，没有明确要求 TAR 内所有子路径必须 ASCII。最终方案只按已确认范围做 gate，不因主办方回复推导出更广的重命名要求；若课题组进一步要求所有 archive entries 均为 ASCII，再单独收紧 allowlist。

## 9. 仍需主办方确认的 release 问题

这些问题不阻塞方案设计，但会影响最终候选：

1. 评测内网实际提供哪些 Add LLM、embedding、reranker model ID 与协议。
2. 租户凭证具体通过哪些环境变量或挂载文件注入。
3. timestamp 的 timezone/缺省时区约定，以及 session 级和 message 级时间冲突时谁优先。
4. ASCII 要求是否只覆盖压缩包和顶层目录，还是覆盖 TAR 内全部文件路径。

在未得到回复前，最终计划使用显式保守假设，不通过现场修改代码解决。

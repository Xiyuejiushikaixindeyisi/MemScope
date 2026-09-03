# B05 Add 设计讨论与调测机调优指南

> 状态：B05 已于 2026-09-03 通过 Gate 2 并冻结。本文是设计讨论和真实环境调优的优先输入，
> 不替代正式任务书、API 契约、B05 `PLAN.md` 或调测报告。
>
> 当前覆盖：设计点 1、2、3 均已确认并沉淀。本文记录已确认的设计约束和候选调优方向；
> 最小修订后的权威 Gate 0 边界见 [GATE0.md](GATE0.md)，已冻结实现范围以
> [PLAN.md](PLAN.md) 和 [HANDOFF.md](HANDOFF.md) 为准。

> **48 小时紧急约束：**调测机在开始任何 Docker 或调优工作前，必须先阅读并执行
> [48 小时交付止损规则](../../collaboration/48H_DELIVERY_GUARDRAILS.md)。Docker 是 P4 加分项，
> 10 分钟预检、单阶段 30 分钟止损；不得为每轮模型、prompt 或配置实验重复构建镜像。

## 1. 文档用途

本文持续记录 Add 路径三个设计点的：

1. 已核验的事实和参考依据；
2. 当前讨论结论及其适用边界；
3. 可继续提高评测集分数的方向；
4. 调测机应执行的能力探测、受控实验和回传要求；
5. 尚未决策或需要真实环境证据的问题。

三个设计点分别是：

1. 是否使用 LLM 抽取、extra LLM 选型和 prompt 调优；
2. 状态处理、异步状态转移及其与 Search 的一致性；
3. Add 与 Search 的执行时序、粒度和分组方式。

全程遵循以下优先级：

1. API 契约、`user_id` 隔离、禁止使用 gold 等合规要求不可退化；
2. Add 总耗时必须小于 120 秒，且应为 Adapter、持久化、索引和抖动保留安全余量；
3. 满足硬约束后，以未参与调优的验证/保留集准确率为第一优化目标；
4. 延迟、调用量和资源占用作为同等准确率候选之间的次级选择依据。

正式规则允许内部模型是可选组件，但使用的提取、摘要、Embedding 等模型必须在 SDD 中披露。
主办方固定执行 Answer 和 Judge，MemScope 不实现或替换它们。

## 2. 设计点 1：LLM 抽取、选型与 prompt 调优

### 2.1 当前讨论结论

1. B05 的准确率 baseline 使用 LLM 执行 `simple_struct + fine` 抽取。
2. `fast` 原文窗口不作为准确率主方案，只作为诊断对照；是否成为故障降级路径留待专门的
   失败语义设计决定。
3. baseline 默认只配置一个主抽取 LLM，不默认增加第二遍 LLM 复核或独立 general LLM。
4. GLM 和 Qwen 均进入同一受控 bake-off，不根据通用聊天、编码或 Agent 榜单预选最终赢家。
5. 模型选择采用硬约束优先的字典序：协议/隔离 -> 超时 -> 保留集端到端得分 -> 稳定性 ->
   延迟/调用量/资源。
6. prompt 的任务契约现在即可审查；基于分数的语义调优在真实模型能力探测和可复现 baseline
   建立后开始。
7. 若 prompt 变化，必须重新交叉验证两个 finalist；不得假定一次模型排序对所有 prompt 都成立。
8. MemReader 等任务专用模型可作为 baseline 后的独立实验候选，不在 B05 初始 baseline 中暗中
   引入新的主动状态机或额外模型依赖。

### 2.2 为什么准确率主路径需要 LLM

固定 MemOS v2.0.32 的 `SimpleStructMemReader` 有两条不同路径：

- `fast`：直接把对话窗口保存成记忆，不调用 LLM；
- `fine`：逐窗口调用主 LLM，解析 `memory list`，再生成结构化记忆节点。

源码依据：

- [SimpleStructMemReader fast/fine 分支](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L358-L429)
- [上游结构化抽取 prompt](../../../.vendor-src/MemOS/src/memos/templates/mem_reader_prompts.py#L1-L111)

本赛题要求处理的不只是文本切片，还包括代词和别名消解、相对时间归一化、用户与 assistant
事实归因、隐含偏好/计划、原子事实拆分、信息价值判断和不确定性约束。这些任务不适合仅靠正则、
聚类或向量相似度完成。因此，非 LLM 方法可以承担确定性的预处理和校验，但不应替代 baseline
的语义抽取器。

“需要 LLM”不等于“需要最大通用模型”。任务专用小模型可能超过更大的通用模型，模型规模只能
作为先验，不能作为选型结论。

### 2.3 对参考观点的判断

#### 观点 A：Agentic RL 训练后的模型更适合抽取

判断：**有条件正确，不能泛化为任意 agentic/coding RL 模型都更好。**

[MemReader](https://arxiv.org/html/2604.07877v2) 在相同 Qwen3-4B 底座上比较了 SFT 与 GRPO。
它的动作空间直接对应 `add_memory`、`search_memory`、`buffer_memory` 和 `ignore_memory`，奖励覆盖
格式有效性、动作选择、内容正确/完整、避免幻觉和推理效率。论文报告的受控结果包括：

- LoCoMo Overall：4B-SFT 77.33%，4B-GRPO 81.42%；
- LongMemEval Overall：80.00% -> 83.00%；知识更新 85.80% -> 91.03%；时序推理
  78.19% -> 84.21%；
- HaluMem memory extraction F1：96.61% -> 98.21%。

这支持“**面向记忆写入决策专门设计的 Agentic RL**”有效，但证据仍有边界：该结果来自预印本
作者自报，所用 response/judge 配置与比赛固定 Answer/Judge 不完全相同，且尚无本项目独立复现。

GLM-5 系列公布了异步 Agent RL 和长程工程任务训练，但主要证据来自 coding、terminal、tool-use
等任务；Qwen3.6-27B 公布的主要指标也集中于 coding、知识和推理。它们没有提供与本项目同构的
记忆抽取对比，因此通用 agentic 能力只能作为候选先验，不能作为选择依据：

- [GLM-5 技术报告](https://arxiv.org/abs/2602.15763)
- [GLM-5.1 官方模型页](https://huggingface.co/zai-org/GLM-5.1)
- [Qwen3.6-27B 官方模型页](https://huggingface.co/Qwen/Qwen3.6-27B)

#### 观点 B：选择 LLM 比调整 prompt 更关键

判断：**部分正确，但目前不足以建立固定优先级。**

模型决定语义理解、时序/指代推理和指令遵循的能力上限；prompt 与输出 schema 决定模型实际被
要求优化的目标。二者存在交互，不能用单次单 prompt 排名拆开判断。

当前 MemOS prompt 本身存在高影响风险：

- 规则要求 assistant 信息只有在用户认可或回应后才提取；
- 示例却把只有 assistant 发言、未经用户确认的推荐保存为长期记忆；
- prompt 同时要求连较小细节也不要遗漏，并明确完整性优先于简洁性。

这些要求可能导致 assistant 误归因、过度抽取和噪声累积。更强的指令遵循模型也无法稳定消解
相互冲突的目标，因此 prompt 不是低优先级装饰变量。

公开研究已经确认模型对保持语义的 prompt 改写可能敏感，但这种影响强弱随模型和任务变化：

- [What Did I Do Wrong?](https://aclanthology.org/2025.naacl-long.73/)
- [POSIX](https://aclanthology.org/2024.findings-emnlp.852/)

因此本项目用小型 `model x prompt` 矩阵获得证据，而不预设“模型一定比 prompt 重要”或相反。

### 2.4 可使用的公开评测依据

目前没有可信的公开榜单直接回答“GLM-5.1 与 Qwen3.6-27B 哪个更适合 MemOS 记忆抽取”。建议按
下列相关性使用公开 benchmark：

| 层级 | Benchmark | 用途 | 不能证明什么 |
|---|---|---|---|
| 直接诊断 | [HaluMem](https://arxiv.org/abs/2511.03506) | 分开测抽取、更新、QA；观察 recall、precision、错误记忆、幻觉和遗漏 | 其系统榜单不是固定 MemOS 下的 GLM/Qwen extractor 榜单 |
| 系统能力 | [LongMemEval](https://arxiv.org/abs/2410.10813) | 信息抽取、跨会话、时序、知识更新和拒答 | 结果混合了抽取、索引、检索和回答能力 |
| 端到端 | [LoCoMo](https://aclanthology.org/2024.acl-long.747/) | 长对话单跳、时序、多跳、跨会话 QA | 不能单独定位 extractor 优劣 |
| 间接先验 | SWE-bench、Terminal-Bench、MMLU、GPQA、Arena | 了解通用能力和 agent/coding 倾向 | 不能代替记忆抽取或比赛内验证 |

公开集用于方法开发时必须划分 tuning/dev/holdout。Add prompt 不得接收评测问题、options、gold 或
由它们派生的提示；最终选择必须以未参与 prompt 调优的 holdout 为准。

### 2.5 GLM/Qwen 候选的初始假设

这些只是待证伪假设，不是最终结论：

| 候选 | 值得验证的准确率假设 | 主要风险/探测点 |
|---|---|---|
| GLM-5.1/实际订阅变体 | 大规模模型和长程 agent 训练可能更擅长歧义、跨轮信息和复杂时间关系 | 一次性 JSON 抽取未必利用长程 agent 优势；输出冗长、thinking、托管延迟和限流必须实测 |
| Qwen3.6-27B/实际订阅变体 | 27B dense 模型可能以更低延迟提供足够的结构化抽取质量 | 时序、隐含关系和复杂更新召回可能低于更强候选；默认 thinking 和 JSON 稳定性必须实测 |

仓库当前只记录了预期的华为网关候选 `GLM-V5.2-DX`、`Qwen-V3.6-27B-bf16`，并明确指出精确
订阅 ID 和能力仍是运行期事实：

- [当前模型资源边界](../../PROJECT_CONTEXT.md#organizer-and-environment-boundaries)

调测机不得把公开名称与网关 ID 按名称猜测映射，必须以 `/v1/models`、控制台和最小请求结果为准。
如果只能安排测试顺序，可先运行 GLM 作为准确率上限候选，再运行 Qwen 作为延迟/稳定性对照；
该顺序不表示生产选择。

### 2.6 extra LLM 的边界

固定版本的 `SimpleStructMemReader` 可以配置主 `llm`、`general_llm` 和其它可选模型，但当前
`fine` chat 抽取主循环调用的是主 `llm`。baseline 不因为配置入口存在就启用所有模型。

第二个 LLM 只有满足以下全部条件才进入候选：

1. 有明确且单一的职责，例如仅做冲突验证或高风险记忆复核；
2. 相对单模型 baseline 在固定 holdout 上产生可重复的净正向翻转；
3. 不因为二次改写增加 unsupported facts、遗漏或状态冲突；
4. 在比赛并发下仍满足 Add 120 秒硬约束和内部安全余量；
5. 失败语义明确，不会把第一遍正确结果静默替换为空结果。

在满足这些条件前，二次 LLM 只会增加延迟、限流概率、故障点和结果归因难度，不进入 baseline。

### 2.7 prompt 调优时机与约束

#### 现在：审查 prompt contract

可以在不调用真实模型的情况下明确和评审：

- 哪些信息有长期价值，哪些必须忽略；
- user/assistant 归因规则；
- 时间归一化、不确定性和指代消解规则；
- 一条记忆的原子性、自包含性和语言；
- 空结果语义和严格 JSON 结构；
- 禁止生成输入不支持的信息。

状态更新、遗忘和主动 `search/buffer` 的具体表达依赖设计点 2、3，不应在这一步由 prompt 偷偷
决定架构。

#### 真实能力探测后：建立公平 baseline

两个候选使用同一份未修改 upstream prompt、相同窗口、相同采样参数和相同数据顺序。优先使用
非 thinking/直接输出模式和模型支持的最低稳定采样设置，但所有字段均须先在网关实测，不能照搬
公网 API 参数。

#### baseline 后：有限 prompt 调优

建议至少保留三个版本：

| ID | 目的 |
|---|---|
| P0 | 固定 MemOS upstream prompt，作为可复现基线 |
| P1 | precision-oriented：强化长期价值、assistant 认可边界和 unsupported abstention |
| P2 | balanced：在 P1 基础上恢复必要的 recall，兼顾时序、计划和隐含偏好 |

一次只改变一个主要语义规则，记录正向翻转、负向翻转和未变化。选出 finalist 后，必须让另一个
候选模型运行同一 prompt，防止把 model/prompt 交互误判为单一模型优势。

### 2.8 调测机实验顺序

#### 阶段 A：网关和模型能力探测

每个候选至少记录：

| 项目 | 必须回传的脱敏事实 |
|---|---|
| 身份 | 精确 model ID、API 路径、响应中的 model 标识、探测日期 |
| 协议 | Chat Completions 可用性；支持/拒绝的 JSON、tools、reasoning、`extra_body` 字段 |
| 输出 | thinking 是否默认开启、能否关闭、JSON-only 成功率、空响应和截断行为 |
| 限制 | 上下文/输出上限、RPM/并发限制、429 的响应和恢复行为 |
| 性能 | 冷/热延迟，P50/P95/P99/max，输入/输出 token，竞争条件下的尾延迟 |
| 稳定性 | 同输入重复结果、schema 失败、字段缺失和语言漂移 |

探测日志不得包含 Key、IAM token、完整私密对话或完整敏感响应。

#### 阶段 B：固定 prompt 的 extractor bake-off

先使用小而覆盖风险的样本集，包括：

- 中文、英文及必要的混合语言；
- 单一事实、多个原子事实、无长期价值闲聊；
- assistant 建议被接受、未被接受和纯 assistant 内容；
- 代词/别名、相对时间、不确定时间；
- 更新、遗忘、反思和噪声样本，但其最终状态解释以后续设计点结论为准；
- 长窗口、多窗口和接近比赛 Add 上限的输入。

先固定 prompt 比较模型，不能一边换模型一边换 prompt。

#### 阶段 C：prompt 小矩阵和端到端验证

运行最小矩阵 `2 models x P0/P1/P2`。通过小样本后才扩大到固定 dev，最后只在冻结候选上运行
holdout。端到端评测必须固定 Embedding、索引、Search、证据预算、代理 Answer/Judge 和随机种子，
并明确本地代理分数不等于官方成绩。

### 2.9 指标和选择规则

#### 硬淘汰条件

出现以下任一情况，候选不能仅凭平均准确率进入最终方案：

- API 字段或响应协议不兼容；
- `user_id` 隔离、禁止 gold 或其它合规要求退化；
- 结构化结果不能稳定解析，或解析失败被静默当成成功空记忆；
- 在比赛式并发和代表性长输入下触发 120 秒 Add 超时；
- thinking/额外文本导致 JSON 污染或不可控 token 消耗；
- 出现不可接受的跨样本状态、隐私日志或不可恢复的失败行为。

120 秒是正式硬上限，不是建议工作点。调测机应设置内部告警线并为 Adapter、持久化、索引、网络
抖动和有限重试留出余量；在获得真实并发与尾延迟前，建议先以 105 秒作为观测告警线，而不是
新增的比赛契约。

#### 质量选择顺序

通过硬门槛后，按以下顺序比较：

1. 冻结 holdout 上的端到端客观分代理和正/负翻转；
2. MemOps Remember、Update、Forget、Reflect、旧值率、泄漏/过遗忘和噪声切片；
3. LoCoMo 单跳、时序、多跳和跨会话切片；
4. HaluMem extraction recall/precision/F1、错误记忆和遗漏；
5. 重复运行稳定性；
6. P99/max 延迟、429/5xx、调用量、token 和资源。

这落实“必须满足超时，但满足后准确率高于性能”的用户优先级。

### 2.10 调测机必须保留和回传的产物

除填写 [真实环境调测与调优报告模板](../../collaboration/TUNING_REPORT_TEMPLATE.md) 外，模型与
prompt 实验还应保留：

1. 数据集版本、split 清单和随机种子；
2. 精确模型 ID、非密钥参数和 capability probe 结果；
3. prompt 完整版本、稳定 ID 和 SHA-256；
4. MemOS commit、MemScope commit/ZIP SHA-256、运行环境和时间；
5. 每次实验唯一主变量及其它冻结变量；
6. Add 分段延迟、调用次数、token、HTTP 状态和解析结果；
7. aggregate 指标以及逐题正向/负向翻转；
8. 失败样本的脱敏分类，不回传密钥或不必要的完整私密对话；
9. `accept/reject/inconclusive` 结论和可执行回退方式。

## 3. 设计点 2：状态处理与 Search 一致性

### 3.1 已确认结论

1. 成功 Add 的语义是 **committed and immediately safe to search**，不能把仍可能返回错误状态的
   后台排队视为成功。
2. 采用“关键语义状态同步发布、非关键派生信息异步增强”。影响当前事实、更新和遗忘可见性的
   工作必须在 Add 成功前完成或建立等价的同步抑制屏障。
3. 同一用户的状态发布必须遵守持久化顺序；Search 只读取最后一个 committed snapshot/generation。
   不同用户可以并行。
4. Search 先执行用户隔离、状态有效性和时间/版本支配，再执行相关性召回以及经验证的互补组合。
5. 120 秒是 Add 的硬淘汰线。异步不能用来掩盖未完成的正确性工作；通过硬门槛后，仍以保留集
   准确率选择方案。

### 3.2 必须分离的三个状态平面

| 状态平面 | 代表状态 | 职责 | 不能代替什么 |
|---|---|---|---|
| 请求投递状态 | `NEW/PENDING/COMPLETED` | 幂等、持久化、重放和成功响应 | 不证明语义冲突已经解决 |
| 语义记忆状态 | `resolving/activated/archived/deleted` | 当前事实、处理中、历史和遗忘的可见性 | 不证明所有派生索引已发布 |
| 索引可见状态 | staging/committed generation | 让 Search 读取一致快照 | 不代替事实关系判定 |

Raw Store 的 `PENDING` 永远不是成功 Add；Gateway 完成且成功响应可持久化后才能进入
`COMPLETED`：

- [Raw Store Add 状态机](../../interfaces/raw-store-v1.md#add-state-machine)
- [当前 application Add 顺序](../../../src/memscope/application/memory_operations.py#L56-L103)

三个平面可以共享关联 ID，但不能复用同一个状态字段或把其中一个状态推导成另外两个状态。

### 3.3 同步与异步的边界

以下工作属于成功响应前的关键路径：

- 新事实的基础持久化和基本索引可见性；
- correction/update 后当前版本的切换和旧版本抑制；
- forget 的 Search tombstone/不可见屏障；
- 用户隔离、事件顺序、版本号和 provenance 绑定；
- committed generation 的发布和轻量 read-after-write 验证。

以下工作只有在失败或延迟不会改变上述语义时才允许异步：

- 非权威标签、摘要和统计；
- 不参与当前事实选择的图关系扩展；
- 离线质量分析和调测日志；
- Search 可以安全忽略的派生索引。

异步产物必须带来源版本。若其输入版本已被 supersede/forget，产物不得重新激活旧事实。任何会
改变当前真值、移除记忆或让 Search 结果随后台完成时刻变化的 organizer 工作都不属于“非关键
增强”。

固定 MemOS v2.0.32 的 `async_mode="async"` 会进入 fast 抽取并忽略 fine mode，因此不符合设计点
1 的准确率 baseline。即使选择 `sync + fine`，首次写库后仍会提交 `ADD_TASK_LABEL` 调度任务，
所以 MemOS 的 `sync` 也不能被解释为“所有生命周期处理已经收敛”：

- [sync/async 对抽取模式的实际影响](../../../.vendor-src/MemOS/src/memos/multi_mem_cube/single_cube.py#L680-L718)
- [首次写库和后续调度顺序](../../../.vendor-src/MemOS/src/memos/multi_mem_cube/single_cube.py#L727-L805)

### 3.4 状态转移流程与依据

推荐的逻辑流程：

```text
Raw pending
    -> extract candidate（Search 不可见）
    -> 读取该用户已提交的 active snapshot
    -> 判定 add / duplicate / corroborate / update / forget / ambiguous
    -> 原子或逻辑原子地发布新版本
    -> 验证新状态可读、旧状态已按规则抑制
    -> Raw completed + HTTP 200
    -> 可选异步增强
```

状态转移发生在 committed version 发布时，不发生在任务入队时。判定依据按以下优先级使用：

1. `user_id`、稳定 Cube 和访问边界；
2. 用户明确的纠正、撤销、遗忘或确认表达；
3. 原始事件时间；
4. Raw Store 的 `session_position/request_position`，作为时间缺失或相同情况下的确定性顺序；
5. 主体、属性和语义 key 是否指向同一事实槽；
6. 新旧内容属于重复、佐证、补充、细化还是矛盾；
7. 来源、用户确认程度、抽取置信度和不确定性；
8. 仅在规则无法可靠判定时调用 LLM 做关系分类。

不能单独使用数据库处理时间或 embedding 相似度。延迟到达的旧事件可能具有更晚的处理时间；
否定、纠正和状态变化也可能与旧事实具有低表面相似度。

| 输入关系 | 发布结果 |
|---|---|
| 无相关旧事实 | candidate -> `activated` |
| 重复 | 不产生第二个无差别 active；保留或合并 provenance |
| 佐证/补充 | 保留具有独立信息量的原子事实，或给当前事实增加来源；不强制合并原文 |
| 更新/纠正 | 新版本 `activated`，旧版本在同一可见性边界进入 superseded/`archived` |
| 遗忘 | 同步提交 Search tombstone；受保护的 Raw/审计记录不得被普通 Search 暴露 |
| 无法可靠判断的矛盾 | 不破坏当前指针；保存带时间和来源的限定证据，不生成两个无限定当前事实 |

历史状态不应一律物理删除。普通当前事实查询应抑制 superseded 内容；明确的历史/时间查询可以
读取与目标时间区间匹配的 archived evidence。真正的 forget 则对普通 Search 始终不可见。是否
需要物理擦除由正式契约和后续数据治理决策决定，不能由 Add prompt 隐式决定。

### 3.5 发布原子性、顺序和 Search 屏障

如果底层能在一个事务中切换新旧节点状态，应直接使用事务。如果图、向量索引和状态存储之间
没有跨库事务，则采用逻辑原子发布：

1. 新版本写入 staging generation；
2. 完成新版本必需的基础索引；
3. 原子切换该用户的 committed generation/current-version pointer；
4. Search 只读取 committed generation，并对结果再次执行状态/版本过滤；
5. Add 做轻量 committed-state readback 后才返回成功，不要求额外执行一次完整 public Search。

并发策略不采用全局锁。同用户可以并行完成不依赖旧状态的准备工作，但 resolution/publish 至少
进入 per-user ordered commit lane，并以 Raw Store 已分配的顺序为准；不同用户继续并行。这样既
防止两个相反更新因 LLM/网络完成顺序不同而倒置，也避免为正确性牺牲所有吞吐。

Search 的固定前置顺序为：

```text
user/Cube isolation
    -> committed generation
    -> 排除 resolving 和 forgotten/deleted
    -> 当前/历史时间有效性与版本支配
    -> 相关性候选召回
    -> 经验证的互补、去重和冲突控制
    -> evidence serialization
```

高相似度不能让已遗忘、未提交或对当前时间已失效的内容重新进入结果。

### 3.6 对 GraphMemix 参考观点的核验

参考观点“相同 K 下，保证记忆互补且不冲突比精确检索更重要”的判断是：**方向正确，但表述过强，
且不能作为异步状态收敛的依据。**

[GraphMemix](https://arxiv.org/html/2608.26983) 研究的是问题到来后的证据集合选择，而不是 Add 时的
状态提交。它指出独立的相似度 Top-K 容易重复占位，并遗漏低相似度的回复、状态更新和补充证据；
其 ECV 只给 `new_fact`、`clarification`、`corroboration` 等经验证的正向关系结构奖励，不给
`redundant`、`conflict` 或 `irrelevant` 关系奖励。

论文固定相同 48 个候选、节点分数和 `K=10` 的受控实验中，Recall@10 宏平均为：

| Selector | Recall@10 Avg. |
|---|---:|
| Node Utility Top-K | 56.87 |
| MMR | 56.84 |
| Generic relevance-redundancy | 56.82 |
| Facility Location | 56.80 |
| ECV Pointwise | 57.26 |
| Forest Proposal | 57.74 |

因此可以推出：

1. 普通多样性或“相互不相似”并不自动提高质量；
2. 经关系验证的互补组合在候选集已经较好的前提下有额外价值；
3. 节点相关性仍是必要基础，GraphMemix 联合使用相关性和关系，而非用互补性替代精确召回；
4. 固定 K 的宏平均增益为 0.87 个百分点，不能证明互补性普遍比相关性更重要；
5. 查询时压制冲突证据不能替代 Add 时及时发布 update/forget 状态。

GraphMemix 是 2026-08-27 提交的 v1 预印本，任务是多模态个人记忆，尚未在 MemScope 的文本数据、
`top_k=100` 和固定 Answer/Judge 上复现。其方法进入 Search 优化候选，但不能升级为本项目的已证实
收益。

### 3.7 固定 MemOS 的已知风险点

1. 新建记忆状态默认是 `activated`，而不是不可见的 staging/resolving：
   [状态字段](../../../.vendor-src/MemOS/src/memos/memories/textual/item.py#L109-L127)。
2. organizer 的关系检测先以 embedding threshold `0.8`、`top_k=5` 取候选，再逐个用 LLM 判断
   contradictory/redundant，可能漏掉表面不相似的状态更新：
   [NodeHandler.detect](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/organize/handler.py#L22-L74)。
3. fallback hard-update 按 `updated_at` 选择新旧并直接删除旧节点，处理时间与事件时间混淆时存在
   错误覆盖和历史丢失风险：
   [NodeHandler._hard_update](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/organize/handler.py#L131-L149)。
4. merge 依次新增合并节点、复制边、archive 两个旧节点，不是源码层面显式的一次原子事务；并发
   Search 可能观察到中间态：
   [NodeHandler._resolve_in_graph](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/organize/handler.py#L151-L190)。
5. 部分 fast graph recall 显式过滤 `status="activated"`，但同一函数的非 fast metadata 分支没有
   传入 status。必须确认比赛候选实际路径并执行 archived/deleted 泄漏测试：
   [recall 分支差异](../../../.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/retrieve/recall.py#L273-L344)。

以上是审计风险，不代表所有风险都已在最终运行路径复现。Gate 1 方案必须通过能力探测和最小复现
决定复用、配置隔离还是做窄范围兼容层，不能直接大改 vendor 源码。

### 3.8 优化方向

按风险和预期收益排序：

1. 建立成功 Add 的 committed visibility barrier 和 immediate read-after-write 测试；
2. 给 Search 增加统一的 active/generation/tombstone 后过滤，消除不同 recall 分支的状态语义差异；
3. 使用事件时间加持久化顺序，不用处理时间 alone 决定 current truth；
4. 对同一用户建立有序 commit lane，只序列化必要的 resolution/publish 阶段；
5. 先用显式指令、key、时间和 provenance 规则处理确定性 update/forget，只把歧义关系交给 LLM；
6. 保留原子事实和版本链，避免不可逆 LLM fusion 吞掉能够回答历史问题的细节；
7. baseline 稳定后再验证 Search 侧的 relation-verified complementarity，不直接套用 MMR/随机多样化；
8. 如果完整同步 organizer 超时，优先缩小冲突候选、批量 embedding/关系判断和减少 LLM 调用，
   不能把关键状态工作移到 HTTP 200 之后。

### 3.9 调测机实验建议

先比较三个明确候选，禁止同时改变 extractor、prompt 和 Search：

| ID | 状态策略 | 用途 |
|---|---|---|
| S0 | 固定 MemOS 当前 sync fine + 后台调度 | 复现基线和暴露错误窗口，不作为默认正确性结论 |
| S1 | 同步关键状态屏障 + 异步非关键增强 | 推荐主候选 |
| S2 | 完整 organizer 同步收敛后返回 | 准确率上限/延迟压力诊断候选 |

必须覆盖以下序列：

- remember -> immediate Search；
- duplicate/corroboration -> Search 不被重复证据挤占；
- A -> correction B -> 当前查询只认 B，历史查询仍能认 A；
- 较早事件延迟到达 -> 不覆盖较晚事件；
- remember -> forget -> immediate Search 无泄漏；
- 无法消解的矛盾 -> 不发生静默破坏性覆盖；
- 同用户并发更新并人为反转 LLM/Gateway 完成顺序；
- 不同用户写入相同文本 -> 零交叉泄漏；
- 在 publish 各阶段故障注入并重启/重放 -> Search 只见完整旧版或完整新版；
- 人为延迟或停止后台 scheduler -> 已成功 Add 的关键查询结果不变化。

每个候选至少记录：

- immediate read-after-write 成功率；
- stale-current hit、dual-active conflict、forgotten leakage、archived leakage；
- 当前状态和历史状态 recall/precision；
- 正确 update/forget/ambiguous 转移率；
- 每阶段耗时、锁/队列等待、LLM/Embedding 调用量；
- Add P50/P95/P99/max、429/5xx/timeout；
- 并发和故障注入后的可重复性。

硬淘汰条件包括任何跨用户泄漏、确定性 forget 泄漏、成功 Add 后立即查询仍为旧当前值、Search
观察到半提交状态，或代表性比赛并发下任一 Add 达到 120 秒。调测仍使用 105 秒内部观测告警线；
它不是新增比赛契约。通过硬门槛后，以冻结 holdout 的端到端分数和逐题正/负翻转选择 S1/S2，
延迟与资源仅作为同等准确率候选的次级依据。

## 4. 设计点 3：Add/Search 时序与数据分组

### 4.1 已确认结论

1. 外部调用顺序固定为：每个样本完成全部 Add 后，评测机再逐题 Search；服务不要求或假设其它
   外部时序。
2. 每个外部 Add request/chunk 独立同步提交，不等待不存在的 `final_chunk` 或样本结束信号。
3. Add 内部允许为去重、更新、遗忘和关联判定执行局部 read-before-write，但它不是公开 Search，
   也不能绕过设计点 2 的状态发布屏障。
4. 原始消息保持 role、timestamp 和输入顺序，不在 Add 前按相似度、正则或聚类重排；只对抽取后的
   原子事实按 entity/key/time/relationship 分组。
5. 同 session 多 chunk 可以使用有界、只读的 carry-over context，但 carry-over 不得作为本次新
   evidence 重复入库。
6. Search 返回不超过 `top_k=100` 的自适应数量高质量证据，不为填满 100 条而加入低效用内容。
7. Markdown 只作为派生 evidence serialization 的实验候选，不是记忆 source of truth，不能独立
   承担 update/forget。
8. 调测主候选是稳定有序窗口、有界 carry-over、抽取后 key 分组和局部状态查询的组合；Markdown
   evidence pack 在该候选稳定后单独消融。

因此四个原始方案不是简单四选一：外部采用方案 1；内部采用受控的方案 2/4 变体；方案 3 拒绝。

### 4.2 外部时序与不可依赖的边界

正式评测按样本执行：

```text
Add(chunk 1) -> ... -> Add(chunk N) -> Search(question 1) -> ... -> Search(question M)
```

依据：[正式评测边界](../../acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md#3-正式评测边界)。单会话默认
一次 Add，较长会话可能按边界分 chunk；Add 返回前必须完成持久化并立即可检索。

服务没有 `final_chunk`、样本结束或后续问题提示，不能依赖：

- 缓冲全部历史后猜测何时一次性处理；
- 空闲时间 debounce；
- 下一个 session 到达后才整理上一个 session；
- 第一次 Search 才执行样本级关键 consolidation。

第一次 Search 虽然意味着此前 Add 已结束，但此时才整理会占用更严格的 60 秒 Search 预算，引入
首题延迟和多题并发竞态，并违反成功 Add 的立即安全可检索语义。非关键的 query-aware 证据组合
可以在 Search 中执行，关键抽取、状态和基础索引不能推迟。

### 4.3 Add 的推荐粒度和内部流程

baseline 保持一个外部 Add request/chunk 对应一个同步提交单元，不拆成逐消息 MemOS Add/Search。
推荐内部流程：

```text
ordered raw messages
    -> 当前 chunk + 有界同-session carry-over
    -> 稳定窗口抽取
    -> 按原始窗口序号重组
    -> 基于 source message ID 去除 overlap 重复
    -> 按 entity/key/time 分组抽取结果
    -> 局部读取已 committed 的相关记忆
    -> 状态判定和 ordered commit
    -> Add 200
```

同 session 多 chunk 的 carry-over 可包含上一个 chunk 的少量末尾轮次，用于指代、别名、未完成句
和 assistant 建议是否被用户接受；跨 session 只补充与当前实体/key 相关的少量已提交事实和时间
信息。carry-over 的轮数或 token 上限必须实测，不能在 Gate 0 凭经验冻结。

carry-over 是只读抽取上下文。新记忆必须能追溯到当前 chunk 的新信息或由新信息触发的状态变化；
不能把前文尾部再次当作新事实。若一个事实必须依赖跨 chunk 上下文才能成立，其 provenance 应
同时记录必要的旧、新 source，而发布事件仍属于当前 Add。

局部 read-before-write 的候选生成可以组合语义 key、实体、时间和 embedding，但只读取小型候选集。
它用于判断 `ADD/duplicate/corroborate/update/forget/ambiguous`，不执行一次完整公共 Search，也不把
搜索结果混入原始对话后重新无差别抽取。

### 4.4 聚类、正则和分组的适用边界

原始对话在抽取前不得为了“把相关内容放在一起”而重排。这样做会破坏：

- user/assistant 相邻关系和认可边界；
- 代词、别名和对话指向；
- 更新、撤销、遗忘的时间顺序；
- session provenance 和可审计性。

允许的确定性预处理限于不改变语义与顺序的规范化、稳定切窗、source ID 绑定和 overlap 标记。

抽取后可以对原子事实分组，因为此时仍保留 source position 和 event time。推荐首先使用
`subject/entity + attribute/key + time` 形成小组，再用 embedding 补充候选，最后由规则或 LLM
验证关系。普通聚类只能作为候选生成器，不能直接执行合并、覆盖或删除。

### 4.5 对“正确上下文越丰富越好”的核验

判断：**不正确。** “事实为真”不代表它与当前问题相关、非重复、当前有效或不会干扰 Answer。

- [Lost in the Middle](https://arxiv.org/abs/2307.03172) 显示，相关信息处于长上下文中部时，长上下文
  模型的利用能力可能显著下降。
- [The Distracting Effect](https://aclanthology.org/2025.acl-long.892/) 直接研究了无关检索段落使回答
  LLM 产生错误的现象。
- [Context Length Alone Hurts LLM Performance](https://aclanthology.org/2025.findings-emnlp.1264/)
  报告即使相关信息可被正确定位，单纯增加输入长度也可能降低任务性能。
- 设计点 2 已核验的 GraphMemix 固定 K 实验中，普通 MMR/多样化没有超过 node relevance Top-K。

本项目采用的准确原则是：在证据正确、相关、互补、状态有效且不超过固定 Answer 的有效上下文
预算时，增加必要证据可能有益；证据数量本身不单调提高准确率。

正式 `top_k=100` 是响应上限，不是必须填满的数量。返回数量、证据 token、有效证据覆盖率、重复和
distractor 比例必须共同调优。

### 4.6 对 Codex/session/append-only 参考观点的核验

判断：**只能作为局部类比，不能作为 MemScope 架构依据。**

官方 OpenAI 文档说明：Codex chat 保留自己的 transcript 并读取当前工作树；同一项目的不同 chat
可共享文件；本地 memories 可把有用上下文带到未来 chat；必须稳定生效的项目指导应放在
`AGENTS.md` 或 checked-in documentation，而不是只依赖记忆召回：

- [Projects and chats](https://learn.chatgpt.com/docs/projects)
- [Memories](https://learn.chatgpt.com/docs/customization/memories)

官方材料没有把 Codex 长期记忆定义为“session-only append-only”。适用于 MemScope 的安全类比是：

- Raw conversation/event log 可以 append-only；
- 原子事实保留版本、时间和 provenance；
- 当前状态是可演进的 materialized view；
- Search 按查询从当前事实、必要历史版本和原始片段中组合证据。

底层证据不可变不等于 Search 视图不可变，也不等于完整 session 应在每次查询中全部召回。Search
不得按 `session_id` 过滤，因为正式召回范围是整个 `user_id`。

### 4.7 对“Code Agent 更信赖 Markdown”的核验

判断：**Markdown 作为稳定结构化指导有工程依据，但“比精确检索更受信赖”没有直接证据。**

[官方 AGENTS.md 指南](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 建议用层级 Markdown
文件提供一致、可审计的项目指令。这证明 Markdown 适合承载规范性和稳定上下文，不证明相同事实
使用 Markdown 后天然获得更高权重，也不证明全量 Markdown 摘要优于 query-aware retrieval。

MemScope 的 source of truth 仍是带状态、时间和 provenance 的原子事实与原始证据。可以独立实验：

1. 为 entity/session 生成派生 Markdown dossier；
2. Search 找到相关原子事实后，将少量互补证据渲染成层次清晰的 Markdown evidence pack；
3. 对比相同事实、相同 token 预算下 flat evidence 与 Markdown serialization 的端到端分数。

Markdown 派生物必须绑定 source version；旧事实被 supersede/forget 后，它不能继续泄漏或重新激活
旧状态，也不能成为无法追溯的单一摘要真相。

[A-MEM](https://arxiv.org/html/2502.12110) 支持“新记忆到来时检索少量相关历史、建立关系并演化
派生表示”的方向，但其结果来自特定系统和数据，不能证明本项目全量 Markdown 或普通聚类优于
精确召回。

### 4.8 固定 MemOS 的窗口与顺序风险

固定 `SimpleStructMemReader` 当前对 chat 存在两级窗口：

1. 先按最多 10 条消息切分，并保留 2 条消息 overlap：
   [get_scene_data_info](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L785-L869)；
2. 每组内部再按默认 1024 token、200 token overlap 切分：
   [_iter_chat_windows](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L315-L356)。

外层窗口通过 futures 并行处理，当前结果按完成顺序 append，而不是按原始窗口序号重组：
[_read_memory](../../../.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py#L659-L715)。这会让写入顺序
随 LLM 尾延迟变化，并与双重 overlap 一起产生时序倒置和重复抽取风险。

`SingleCubeView` 虽然传入 `chat_history`，但该 kwargs 在当前 `_read_memory` 调用
`_process_chat_data` 时没有继续传递。因此不能假定现有 `chat_history` 已解决跨 chunk 指代问题。

Gate 1 至少应明确稳定 window/source ID、按序重组、overlap provenance 去重，以及 carry-over 的
显式接线方式。实际修复应优先放在窄兼容层或可回退的最小补丁中，不能同时重写整个 reader。

### 4.9 调测机实验建议

一次只增加一个变量：

| ID | Add 上下文与组织策略 | 用途 |
|---|---|---|
| T0 | 当前 upstream request-local 窗口 | 复现基线 |
| T1 | 稳定窗口顺序 + source-ID overlap 去重 | 消除实现噪声 |
| T2 | T1 + 有界同-session tail | 测跨 chunk 指代和建议确认 |
| T3 | T2 + 抽取后 key 分组 + 局部状态查询 | 推荐主候选 |
| T4 | 全 session 重放或原始文本聚类 | 仅作准确率/延迟诊断，不作默认方案 |
| T5 | T3 + query-time Markdown evidence pack | 单独验证 Answer 利用率 |

必须记录：

- 跨 chunk 指代、时间关系和跨 session multi-hop recall；
- Update/Forget 正确率、旧值率和遗忘泄漏；
- overlap 重复率和抽取结果顺序稳定性；
- Search evidence 的 useful/duplicate/stale/distractor 比例；
- 返回条数、证据 token 数和必要证据覆盖率；
- 端到端正向/负向翻转；
- Add/Search 分段 P50/P95/P99/max、模型调用量、429/5xx/timeout。

任何输入重排、跨用户泄漏、成功 Add 后不可立即检索、状态不一致或 Add/Search 超时都是硬淘汰项。
通过硬门槛后，以冻结 holdout 分数选择 T1/T2/T3/T5，不因“使用了聚类、图或 Markdown”本身加分。

## 5. Gate 0 最小修订结果

用户已确认执行 [B05 Gate 0 R1](GATE0.md)。修订仅增加显式失败、确定性窗口/provenance、逐 Add
committed visibility、端到端 deadline、最小调优接缝、脱敏观测和对应验收要求；没有启用新的
调优算法，也没有授权进入 Gate 1。

## 6. 当前开放项

1. 华为网关实际提供的 GLM/Qwen 精确 ID、字段能力、限流和尾延迟；
2. prompt P1/P2 的精确内容及其 feature flag/版本管理；
3. 是否以及何时把 MemReader/专用小模型加入 baseline 后实验；
4. committed generation/current-version pointer 在固定 MemOS 上的最小实现映射；
5. carry-over、状态候选数和 Search evidence budget 的真实环境最优值；
6. 内部 Add 延迟告警线在真实并发和完整链路测量后是否调整。

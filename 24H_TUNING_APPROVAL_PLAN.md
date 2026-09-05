# MemScope 赛前 24 小时调优审批清单

> 状态：本 session 只产出方案；M1/M2/M3 方法学已批准；具体实验仍待逐条审批，不自动执行任何实验、测试或构建  
> 基准：当前工作分支 `batch/b10-baseline-closure`；rootful 运行镜像绑定 `756902c`；实机证据记录于 `c925fc9`；比赛基准提交 `ca470eb`  
> 更新日期：2026-09-05  
> 首要目标：在不牺牲评测机可拉起、可评测、可回退的前提下，争取净正收益

双 Session 的具体执行与汇合方案见：[DUAL_SESSION_TUNING_APPROVAL_PLAN.md](DUAL_SESSION_TUNING_APPROVAL_PLAN.md)。
调优项之间的交互和数学参数选型见：[TUNING_INTERACTIONS_AND_MODELING.md](TUNING_INTERACTIONS_AND_MODELING.md)。
T00 观测项与冻结五样本见：[T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md](T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md)。
主办方澄清的规则边界、技术核验及其调优影响见：[ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md](ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md)。
最终方案的代码/配置改动边界见：[FINAL_TUNING_PLAN_CHANGE_SCOPE_AND_ORGANIZER_REVIEW.md](FINAL_TUNING_PLAN_CHANGE_SCOPE_AND_ORGANIZER_REVIEW.md)。

最新决策覆盖本文较早版本中的冲突表述：T02 内部 `0.92` 锁定；不测试 MMR；不做自动 prompt 搜索；T03/T06 prompt 调优降为最低优先级。默认先完成 T00 和 `T01+T05` / `T02+T05` Search 路线。

## 1. 结论先行

剩余 24 小时不适合做新的记忆架构、存储迁移或依赖扩张。建议采用以下顺序：

1. 先闭合一次真实服务 baseline；没有 baseline，不按直觉改参数。
2. 只做无需改代码、无需新增服务、可以一行环境变量回退的 Search 实验。
3. 根据 baseline 的错误类型，最多再做一个 Add 侧实验；Add 侧每个候选都使用全新存储重新灌入。
4. 最多保留两个在冻结五样本上逐层净正的改动；该集合不是独立 holdout，不夸大统计结论。
5. 至少预留最后 8 小时冻结代码、构建四个镜像、离线拉起、打包和评测机 smoke。

当前最推荐的调优顺序更新为：

`T00 五样本可观测 baseline → C5 reranker 对照 → 并行 T01+T05 / T02+T05 → 按 M3 单次汇合确认 → 单栈复验`

`T04 window` 只在明确分片错误时进入；T03/T06 prompt 调优最低优先级且另行审批；T07 保持拒绝。

## 2. 统一排序口径

- 难度：1 最低，5 最高；同时考虑开发、验证、重灌和制品重建成本。
- 预估收益：相对当前 baseline 的方向性估计，不冒充正式评测分数。
  - 高：可能修复一个主要失败簇。
  - 中：可能改善一个常见子集，整体收益取决于错误占比。
  - 低：只在窄场景有效，或主要改善延迟/稳定性。
- 评测机风险：1 最低，5 最高；重点考虑新增依赖、外网调用、镜像变化、存储兼容和超时。
- 所有候选均以“baseline 同一数据切分、同一顺序、至少重复两次”为最低比较标准。
- 没有服务级数据前，不给出虚假的百分点承诺；实验回传必须同时包含质量、空结果率、Add/Search 延迟和失败数。

## 3. 按综合优先级排序

| 顺序 | ID | 方案 | 难度 | 预估收益 | 评测机风险 | 是否改代码/重建镜像 | 是否需新存储重灌 | 建议 |
|---:|---|---|---:|---|---:|---|---|---|
| 0 | T00 | 闭合真实服务 baseline 与错误分桶 | 2 | 必做；为后续判断提供依据 | 1 | 否 | baseline 使用干净存储 | **先执行** |
| 1 | T05 | 启用外部 BGE reranker，先建 C5 | 2 | 中/高：候选召回足够但排序错误时有效 | 4 | 否；当前适配器已存在 | 否 | **作为双 lane 共同底座验证** |
| 2 | T01 | 在 T05 score 上做 breakpoint 选阈值 | 1 | 中：低相关噪声主导时收益明显 | 1 | 否，仅运行时配置 | 否 | **与 T05 联合优先实验** |
| 3 | T02 | `dedup=sim`，内部 `0.92` 锁定 | 1 | 中/低：重复证据挤占 top-k 时有效 | 2 | 否，仅运行时配置 | 否 | **与 T05 联合并行；不含 MMR** |
| 4 | T04 | 调整 chat window token 上限 | 1 | 中/低：长对话指代或切片问题主导时有效 | 3 | 否，仅运行时配置 | **是** | 有诊断证据再试 |
| 5 | T03 | `MEM_READER_REMOVE_PROMPT_EXAMPLE=true` | 1 | 中但不确定：可能提升抽取精度并降 token | 2 | 否，仅运行时配置 | **是** | **prompt 最低优先级；另审** |
| 6 | T06 | 最小化抽取 prompt 代码补丁 | 4 | 高/中：系统性角色归因、更新/遗忘抽取错误时有效 | 4 | **是** | **是** | **最低优先级；不做自动搜索** |
| 7 | T07 | 启用 BM25/fulltext 或 VEC-CoT | 4 | 中但高度不确定 | 5 | 很可能需要 | 视实现而定 | **已拒绝** |

排序原则不是单纯按“可能最高分”排序，而是优先选择：易验证、可回退、不改变交付拓扑、不会让评测机多依赖一个外部环节的方案。

### 3.1 T01～T06 的依赖关系

```text
T00：冻结 baseline 数据、服务行为和错误分桶
└── Search 联合初筛：C5 后并行 T01+T05 / T02+T05
    └── M3 单 session 汇合确认

无可接受 Search 候选且 Add 错误明确
└── 另审 T04；T03/T06 prompt 保持最低优先级
    └── 若 Add 候选获胜，在新存储上重跑全部 Search 校准
        └── T90：冻结、构建、离线拉起和交付
```

| ID | 硬前置 | 与其他项的关系 | 会使哪些旧结果失效 |
|---|---|---|---|
| T01 | T00；有可复用的冻结存储和 score/error 分布 | 与 T02/T05 都作用于 Search 候选链，单变量可并行初筛，组合必须单独验证 | T03/T04/T06 改变写入内容后，原阈值结论必须复验 |
| T02 | T00；确认重复证据确实挤占 top-k | 与 T01/T05 有候选集、排序和截断交互；内部 `0.92` 锁定，MMR 不进入 | 任一 Add 侧变化后必须复验 |
| T03 | T00；抽取错误是主要失败簇；另行审批 | 与 T04 都改 Add 语义；作为 prompt 调优排在最后 | 会改变后续 score、重复率和候选分布，使 T01/T02/T05 的最终结论失效 |
| T04 | T00；有明确的切片/长指代或超时证据 | 不依赖 T03，但两者不能在同一候选中同时变化；可隔离并行初筛 | 与 T03 相同，所有 Search 参数需在获胜存储上复验 |
| T05 | T00；已证明是排序错误而非召回缺失 | 与 T01/T02 强交互；目标评测端点兼容性是进入 release 的额外前置 | Add 侧变化后必须复验；开发供应商结果不能替代评测供应商验证 |
| T06 | T00 显示系统性抽取错误，并且另行批准人工单规则 patch | 是最低优先级升级路径；禁止自动 prompt 搜索 | 使全部 Add/Search baseline 结论需要重新确认 |

这里的“依赖”分两类：

- **决策依赖**：例如 T06 必须等 T03 的结果，不是代码上不能同时写，而是先写会浪费时间并破坏单变量归因。
- **数据依赖**：T03/T04/T06 改变数据库中的记忆，Search 参数必须在最终 Add 存储上重新校准。这是不可省略的最终串行阶段。

### 3.2 Docker 与 agent-session 并行矩阵

| 并行组合 | 技术上可行 | 24 小时内建议 | 必要隔离/限制 |
|---|---|---|---|
| T01 + T02 | 是 | **推荐做质量初筛** | 可共用一个冻结、只读的 MemOS baseline；使用不同 memory-api 前端/端口。并行时延不可作为最终 P95 |
| T01/T02 + T05 | 有条件 | 仅在硬件和 API 配额充足时 | T05 的 reranker backend 在 MemOS 进程启动时固定，应使用独立 MemOS 栈和独立存储副本 |
| T03 + T04 | 是 | **默认不建议**；只有两个完整栈和配额充足时才做 | 独立 Compose project、五个 named volumes、端口、私密 env 和输出目录；相同输入分别重灌 |
| Search 初筛 + T03 或 T04 | 是 | 可行 | Search lane 只读 baseline；Add lane 使用新存储。若 Add lane 获胜，Search 结果必须复验 |
| T06 + 任一实施型实验 | 不建议 | **禁止并行写代码/构建** | T06 是单一源码写入者；其他 session 最多做只读分析，不改共享工作树、不重建同名镜像 |

当前 Compose 每个完整 project 的资源上限合计约为 **8.5 GiB 内存、9 CPU**，并包含五个具名卷。并行两个完整栈时应按约 **17 GiB、18 CPU 上限**再加宿主机余量评估；这些是容器上限而非实际保留量，但资源争用会让时延数据失真。

并行运行的硬规则：

1. 使用唯一 Compose project 名；CLI `docker compose -p <lane>` 优先于文件中的固定 `name`。
2. 每个对外服务使用唯一 `MEMSCOPE_PUBLIC_PORT`；当前只有 memory-api 暴露宿主机端口。
3. 完整栈必须使用 project 隔离出的五个 named volumes。不得让两个 Neo4j/Qdrant 容器直接挂载同一数据卷。
4. 每个 session 使用独立的私密 env 和结果目录，禁止共同修改仓库 `.env`。
5. 并行阶段禁止 build 或改同名 image tag；所有 lane 使用同一冻结镜像。T06 只能在独立 worktree/branch 由一个 session 实施，合并后再统一构建。
6. 多栈会绕过单栈的一个 worker/per-user lane 限制，同时冲击 LLM/embedding/reranker API。未知配额时全局 Add 并发先按 1；出现 429 或尾延迟上升立即串行。
7. 并行只用于筛质量。获胜候选必须在单栈、无竞争条件下复跑延迟和成功率，才能进入 T90。
8. T05 等需要独立 backend 的 Search 实验应来自停写、静止状态下验证过的 baseline 卷快照；重新调用非确定性 LLM 灌入“相同输入”不等于相同 baseline。没有可靠快照流程时，T05 改为串行。

最实用的两 lane 安排是：

- Lane S：一个冻结 backend，加两个只做 `/search` 的 memory-api 前端，分别初筛 T01 和 T02。
- Lane A：一个完整隔离栈，只运行经 T00 选中的 T03 **或** T04。

T05 需要以 `http_bge` 启动的 MemOS backend；rootful Docker 已闭合，但评测端 reranker 尚未验证，
因此优先串行建立 C5 并由两个 Search-only 前端共享，不为它占用第三个完整栈。

## 4. 逐条审批项

### T00：真实服务 baseline 与错误分桶

**审批状态：待审批**  
**时间盒：2～4 小时；Docker 故障排查最多 30 分钟**

目的：证明当前候选能完成 `health → add → search`，建立可比较的质量和时延数据，并识别主要失败簇。

执行边界：

- 先做受控的 LLM/embedding 能力探测，再做服务级验证；不打印 key、原文或原始 query。
- Docker 可用则按发布拓扑启动；Docker 30 分钟内不可用，立即转已有 native/source-mounted 验证路线，不继续消耗调优窗口。
- 使用全新候选存储，完成 B06 `require-hit` smoke，再跑固定的小样本 baseline。
- 记录：Add 成功率、Search 成功率、Add/Search P50/P95/max、空结果率、重复结果率、主要错误分类。
- 对 LoCoMo temporal slice 记录 timestamp 是否进入 Add；若当前链路已做相对时间正规化，再记录其准确性；同时记录带时间 evidence 是否被召回，以及是否出现直接答题式 Search content。T00 不以新增正规化实现为前置。
- 错误至少分为：抽取遗漏、角色/主体错误、更新/遗忘错误、召回缺失、排序错误、重复挤占、低相关噪声、超时/服务错误。

通过条件：

- 服务能够稳定拉起并通过 `health/add/search`。
- Add 单请求小于 120 秒、Search 单请求小于 60 秒，且留有可解释的安全余量。
- baseline 数据足以判断下一步应优化 Add 还是 Search。

止损条件：

- 4 小时仍无法得到服务级 baseline：暂停所有质量调优，直接转 T90 交付闭环。
- 若主要问题是服务拉不起、状态污染或超时，不开始 prompt/rerank 实验。

**建议审批口令：** `批准 T00，完成 baseline 后停止并回传结果。`

### T01：搜索 relativity 阈值小扫描

**审批状态：待审批；依赖 T00**  
**时间盒：1～1.5 小时**

假设：baseline 已经召回相关候选，但 top-k 中被低相关记忆污染。`relativity` 是当前已有运行时开关，不改镜像、不改存储。

实验设计：

- 保留 `0.0` baseline。
- 先观察相关/不相关结果分数分布，再选择两个小阈值；不盲扫大量网格。
- 固定其他参数，包括 embedding、reranker、dedup 和数据存储。
- 每个候选至少重复两轮，比较质量、空结果率和 Search 延迟。

预估收益：**中**。若低相关噪声是主要失败簇，可能得到最便宜的净正收益；若主要问题是召回缺失，收益接近 0，阈值过高还会伤害 recall。

风险与回退：

- 风险：阈值对 query 和数据分布敏感，可能产生更多空结果。
- 评测机风险低：只改变一个环境变量。
- 回退：恢复 `MEMOS_SEARCH_RELATIVITY=0.0` 并重启服务。

接受条件：冻结五样本加权质量净改善且关键层不退化；空结果率没有不可接受上升；Search P95 不退化；两轮方向一致。

**建议审批口令：** `批准 T01；只测试两个候选阈值，结果回传后停止。`

### T02：相似去重；内部 0.92 锁定，不含 MMR

**审批状态：待审批；依赖 T00 显示重复挤占 top-k**  
**时间盒：1～1.5 小时**

假设：Search 已召回有用证据，但多个近重复结果占满有限 top-k。本轮只比较 `dedup=exact` 与 `dedup=sim`，保持内部相似阈值 `0.92` 不变；不测试 MMR 或其参数。

预估收益：**中/低，强条件化**。重复结果占比高时可能提升 evidence 覆盖；重复率低时几乎没有收益。

风险与回退：

- `sim` 可能错误合并相似但不同时间/状态的事实，并会让上游内部候选量放大三倍。
- `sim+T05` 在正式 `top_k=100` 下可能向 reranker 发送约 300 个 documents；当前适配器不分批，必须先通过目标 endpoint 的 1/100/300 容量与 TPM/尾延迟 gate，否则取消该 lane。
- MMR 会计算候选相似度矩阵并迭代选择，增加 embedding/CPU 成本；本轮已明确排除。
- 不改变 Add 数据；回退到 `dedup=exact` 即可。

接受条件：相关证据覆盖提升；时间/状态不同的事实不被错误吞并；Search P95 仍有充分余量。

**当前边界：** `T02 仅 sim；内部 0.92 锁定；不含 MMR。`

### T03：移除 memory reader prompt example

**审批状态：最低优先级、待另行审批；依赖 T00 显示 Add 抽取错误主导**  
**时间盒：1.5～2.5 小时**

改动：设置 `MEM_READER_REMOVE_PROMPT_EXAMPLE=true`。这是已有运行时 seam，无需改代码或镜像，但它会改变写入内容，必须使用全新存储并重新灌入同一数据。

预估收益：**中但不确定**。可能减少 example 对比赛分布的错误诱导、缩短上下文；也可能失去格式和抽取边界示范，导致 recall 或 JSON 稳定性下降。

风险与回退：

- 最大风险不是服务启动，而是静默质量回退。
- 需要重新 Add，消耗模型配额和比赛时间。
- 回退到 `false` 并切回 baseline 存储；禁止在同一存储内混合两种抽取配置。

接受条件：抽取遗漏、角色归因或无效记忆至少一个失败簇明显改善；Add 成功率不降；Add P95 和 API 错误率不退化。

**建议审批口令：** `暂不启动 T03；完成 Search 路线后，仅在明确 Add 主错误仍未解决时另审。`

### T04：chat window token 上限的诊断式调整

**审批状态：待审批；不建议无条件执行**  
**时间盒：2～3 小时**

当前基线为 `MEM_READER_CHAT_WINDOW_MAX_TOKENS=1024`。只允许根据错误证据选择一个方向：

- 长距离指代、上下文割裂明显，且 Add 延迟余量充足：只试一个更大的窗口。
- JSON 截断、超时或单次上下文过重明显：只试一个更小的窗口。

预估收益：**中/低，诊断依赖很强**。它可能改善跨句语义，也可能增加单次推理延迟；缩小窗口则可能增加调用次数和事实碎片化。

风险与回退：

- 会改变 Add 语义，必须新存储重灌。
- 大窗口可能触发 Add 115 秒内部 deadline；小窗口可能触发 RPM、调用次数和合并问题。
- 不与 T03 同时变化，否则无法归因。
- 回退到 1024 并切回 baseline 存储。

接受条件：目标失败簇改善，且 Add max 明显低于 120 秒硬上限；任何超时或 429 增长都直接否决。

**建议审批口令：** `暂不批准 T04；待 T00 错误分桶后决定方向。`

### T05：外部 BGE reranker

**审批状态：待审批；默认不批准进入最终候选**  
**时间盒：1～2 小时，只允许影子对比**

当前代码已有受限、鉴权、失败关闭的 SiliconFlow BGE reranker 适配器，因此开发侧可以低成本试验。但最终评测环境使用的供应商端点/模型兼容性尚未得到同等级服务验证；启用它会给每次 Search 增加一次外网依赖。

预估收益：**中/高，前提是候选召回正确但排序错误**。如果相关记忆根本没有进入候选集，reranker 不会补回 recall。

主要风险：

- 外网延迟、429、鉴权、供应商协议差异和模型可见性。
- 增加 Search 尾延迟，逼近 60 秒硬上限。
- 开发供应商上的正收益不能直接证明评测供应商同样可用。
- 主办方评测环境要求模型通过可配置的内网资源接入；开发侧公网 endpoint 只证明协议。未确认内网提供对应 reranker model 和凭证注入方式时，T05 不具备 release 资格。
- 当前适配器是 fail-closed：远端失败会显式传播为 Search 失败；不会静默回退，但会直接损害评测成功率。

接受条件：冻结五样本有足够大的稳定净收益；Search P95 安全；评测机目标端点完成同适配器的受控探测。三者缺一，不进入最终环境。五样本不是独立 holdout，因此结果只能支持工程决策，不能预测官方分数。

回退：`MOS_RERANKER_BACKEND=cosine_local` 和 `MOS_FEEDBACK_RERANKER_BACKEND=cosine_local`，不需要重灌。

**建议审批口令：** `批准 T05 影子实验，不批准写入最终 release 配置。`

### T06：最小化抽取 prompt 代码补丁

**审批状态：最低优先级、未批准；高风险条件项**  
**时间盒：最多 4 小时；仅剩余时间大于 10 小时时可启动**

只有在 T00 证明存在大量、同构的系统性抽取错误，而 T03 无效时才讨论。例如：持续把 assistant 建议写成用户事实，或自然语言 Update/Forget 无法转成正确状态。

约束：

- 当前没有通用自定义 prompt 的稳定运行时 seam，因此这不是简单调参，而是固定 MemOS patch/源码变化。
- 不做自动 prompt 搜索；若以后批准，只能基于成熟开源实现提炼一个人工、可解释的规则。
- 一次只修一个失败簇，不重写整个 memory pipeline。
- 必须新增回归测试、跑全量测试、重建镜像，并使用新存储重灌。

预估收益：**高/中**，但仅限系统性错误占比足够高时；否则高工程风险换来局部收益。

止损：2 小时内不能形成最小补丁和针对性回归测试，立即终止；任何 Add 稳定性或 JSON 解析退化直接回退。

**建议审批口令：** `暂不批准 T06；只有 T00/T03 数据满足前提时重新讨论。`

### T07：BM25/fulltext、VEC-CoT 等路径

**审批状态：已拒绝（2026-09-05，用户确认）**

原因：

- 当前已知上游 BM25/fulltext 路径可能记录原始 query 或 query terms，启用前需要先完成脱敏补丁与验证。
- fulltext/index 路径会增加启动、索引和存储兼容风险。
- VEC-CoT 可能增加 LLM 调用和 Search 延迟，收益未经本项目 baseline 证明。
- 剩余 24 小时无法同时完成质量验证、安全验证、全量回归、镜像重建和离线启动证明。

这类方案适合作为赛后 B11/B12，而不是赛前候选。

**建议审批口令：** `拒绝 T07，赛后立项。`

## 5. 基于 baseline 错误类型的选择树

| T00 的主要发现 | 下一项 | 不应做什么 |
|---|---|---|
| 低相关结果多，相关结果已在候选中 | C5 后运行 T01+T05 | 不改 Add、不盲扫固定阈值 |
| top-k 被近重复结果占满 | C5 后运行 T02+T05，固定 sim=0.92 | 不启用 MMR、不改内部阈值 |
| 抽取遗漏/角色误归因明显 | 先记录错误簇并完成 Search 路线；T03 最后另审 | 不做自动 prompt 搜索 |
| 长距离指代断裂且 Add 时延宽裕 | T04 向大窗口单点试验 | 不做全网格扫描 |
| Add 超时/截断/429 明显 | T04 向小窗口单点试验，或直接保稳定 | 不增加调用链 |
| 候选召回正确但局部排序持续错误 | T05 建 C5，再进入双 lane | 未验证目标端点前不进 release |
| 系统性抽取错误且运行时选项均无效 | T06 最低优先级、另审人工单规则 patch | 不做自动 prompt 搜索或多处重写 |
| 服务拉不起或 deadline 不稳定 | 直接 T90 | 不做任何质量调优 |

## 6. 明确冻结的变量

以下变量在本轮不建议调整：

- LLM：保持 `glm-5.1`/最终环境约定模型，thinking 关闭，JSON object 输出。
- Embedding：保持 `BAAI/bge-m3` 和 1024 维；不迁移向量维度、不换 embedding。
- `MEMRADER_MAX_TOKENS=8000`、模型 timeout 和 Add/Search hard deadline 不用来“掩盖”失败。
- worker 数量保持 1；不改变 per-user 串行和同步 Add 语义。
- 公共 `/add`、`/search`、`/health` 契约和 evidence-only 输出不变。
- 不新增数据库、队列、缓存、模型代理或系统包。
- 不引入 async write、重试风暴或跨 store 事务重构。
- 不在评测机安装依赖、构建镜像、pull 镜像或现场 patch。

## 7. 24 小时时间预算与强制止损

| 时间 | 工作 | 退出条件 |
|---|---|---|
| H0～H2 | T00：五样本 baseline、九类观测、错误分桶、冻结 store | 120 分钟硬止损；无 baseline 则转 T90 |
| H2～H3 | T05 probe 与 C5 共同对照 | endpoint/协议/尾延迟不通过则回 C0 |
| H3～H6 | 双 lane：`T01+T05` / `T02+T05@sim(0.92)` | 按 M1/M2 离线选参，不扩搜索范围 |
| H6～H8 | 单 session 汇合；按 M3 最多一次组合确认 | 没有明确净正立即回退 |
| H8～H10 | 仅在 Search 无解且 Add 错误明确时另审 T04；prompt 默认跳过 | 不允许自动 prompt 搜索 |
| H10～H14 | 五样本最终复验、无竞争延迟、endpoint/回退验证 | 最多保留一个组合候选 |
| H14 | **冻结调优** | 此后禁止新功能和新依赖 |
| H14～H18 | 全量测试、静态检查、secret scan、配置解析 | 任一失败先回退调优 |
| H18～H22 | 构建四镜像、导出 TAR、生成 manifest/hash、离线 release smoke | 必须 `--no-build --pull never` 可拉起 |
| H22～H24 | 评测机验包、smoke、正式评测缓冲 | 不在评测机现场修代码 |

### 7.1 时间盒的依据与计算方式

上述时间盒是 **24 小时倒排的决策上限 + 当前真实 smoke 的请求成本估算**。精确
`756902c` 镜像的 smoke Add 为 `10.445s`、Search 为 `0.229s`；冻结五样本共有 250 个协议
Add chunk 和 126 个 Search。顺序执行的理论下界约为 Add `43.5min`、Search `28.9s`，再为
长输入、限流、冷启动、写盘和分析留出余量，因此 T00 目标 60～90 分钟、硬止损 120 分钟。

T00 后使用以下公式替换估算：

```text
实验墙钟时间 ≈ 冷启动/切配置
             + 重复轮次 × (N_add × Add_P95 / C_add
                           + N_search × Search_P95 / C_search)
             + 结果比对
             + 30% 故障与限流余量
```

- `N_add/N_search`：该阶段实际选取的诊断样本数，不是默认假设全量正式评测。
- `C_add/C_search`：经过限流验证的有效并发。未知配额时 `C_add=1`；并行质量初筛的时延不能代入最终 P95。
- Add/Search 的保守单请求上界分别是 115/55 秒；120/60 秒是淘汰线，不是排期目标。
- 如果按 T00 实测值代入后超过时间盒，应缩小诊断集、减少候选或跳过该项，不能提高无依据并发、压缩 deadline 或挤占 T90。

| ID | 原时间盒 | 预算依据 | 未包含的内容 |
|---|---:|---|---|
| T00 | 1～2 小时 | 五样本固定 250 Add/126 Search；按真实 smoke 得到 43.5 分钟 Add 下界并增加长输入、限流和分析余量 | 全量正式评测、长期压力测试 |
| T01 | 1～1.5 小时 | 不重灌、不构建；复用 T00 baseline，只比较两个阈值、两轮诊断 Search，并预留约 20 分钟做正负翻转/空结果分析 | 大网格、全量组合实验 |
| T02 | 1～1.5 小时 | 只运行 `sim@0.92`、两轮 Search；baseline 已存在；MMR 明确排除 | 修改 0.92、MMR、盲目网格 |
| T03 | 1.5～2.5 小时 | 最低优先级且未授权；若以后批准，需独立存储、五样本重灌与 Search 重校准 | 自动 prompt 搜索、全量重灌 |
| T04 | 2～3 小时 | 与 T03 相同，再增加窗口方向诊断和 429/切片/调用次数核对；只试一个方向的一个值 | 双向扫描、与 T03 组合 |
| T05 | 1～2 小时 | 不重灌；包括 reranker capability probe、独立 MemOS 冷启动、两轮 Search 和错误传播检查 | 评测机目标端点最终验证、供应商故障演练 |
| T06 | 最多 4 小时 | 这是工程止损：2 小时形成单一最小补丁和回归测试，约 1 小时小样本重灌/复验，约 1 小时用于审查、回退和集成 | 最终四镜像构建和离线交付，归入 T90 |

最后 10 小时预留给 T90 的依据不是 pytest 时长，而是交付链的固定步骤和环境风险：干净 commit、完整检查、四镜像构建、TAR 导出、hash/manifest、干净环境 `docker load`、`--no-build --pull never` 拉起、smoke、传输和失败回退。这部分不能被调优实验借用。

当前 rootful Docker 阻塞已解除。`756902c` 的两张自研 Linux/amd64 镜像已绑定 OCI revision，
四服务 healthy、cgroup 限额和 `127.0.0.1:8080` 发布均已验证，真实 smoke 通过。计划文档提交
不改变运行镜像内容；T00 必须分别记录 runtime revision、plan revision、Compose hash 和实测 image ID。

## 8. T90：最终交付闭环（必做，单独审批）

**审批状态：待审批；不属于质量调优**

冻结候选后执行：

1. 记录精确 commit、所有生效环境变量和唯一候选存储。
2. 跑完整测试、Ruff/mypy、release allowlist 与 secret scan。
3. 构建并保存 `memory-api`、MemOS、Neo4j、Qdrant 四个固定镜像；禁止依赖评测机在线 pull。
4. 沿用当前交付脚本生成 `solution-<12hex>.zip`、`memscope-images-<12hex>-linux-amd64.tar`、manifest 和 SHA256；输出/解压目标文件夹只使用 ASCII；在干净环境验证 hash 与镜像集合。不为命名要求另造一套 archive 格式。
5. 使用与评测机一致的命令执行 `compose.release.yaml`，要求 `--no-build --pull never`。
6. 完成 `health/add/search` smoke 和 deadline 检查。
7. API Key、租户信息和 token 不进入代码、镜像或 TAR；评测机只负责验 hash、load 镜像、注入主办方提供的私密内网环境变量、启动和评测，不安装/构建/patch。

若最终候选在 release rehearsal 中失败，回退优先级为：

`关闭外部 reranker → 恢复 dedup=exact → relativity=0.0 → 恢复 Add baseline 配置/存储 → 回退到已验证 commit`

**建议审批口令：** `批准 T90；以已冻结候选生成最终离线制品，完成 smoke 后回传。`

## 9. 每个实验的统一回传模板

```text
实验 ID：
精确 commit：
唯一变化：
数据切分/存储标识：
重复轮次：

质量：baseline -> candidate
空结果率：baseline -> candidate
重复结果率：baseline -> candidate
Add success / P50 / P95 / max：
Search success / P50 / P95 / max：
429 / timeout / 5xx：

改善样例数：
退化样例数：
主要改善簇：
主要退化簇：
是否满足接受条件：
建议：保留 / 回退 / 需要再次审批
```

## 10. 方案依据与可信度

仓库内的一手约束优先于外部经验：本计划直接继承 [B05 Add 设计与调优](docs/batches/B05/ADD_DESIGN_AND_TUNING.md)、[B06 Search 设计与调优](docs/batches/B06/SEARCH_DESIGN_AND_TUNING.md)、[B10 交接记录](docs/batches/B10/HANDOFF.md)、[B10 模型 API Gate 2](docs/batches/B10/MODEL_API_GATE2.md) 和 [项目上下文](docs/PROJECT_CONTEXT.md) 中已冻结的边界。

这些资料支持“先诊断、再做小范围检索/记忆调优”的方向，但不替代 MemScope 自己的 baseline：

| 经验 | 对本计划的影响 | 来源 | 可信度 |
|---|---|---|---|
| 最佳 top-k/检索配置随问题类别变化，不能假设单一大 top-k 总是更好 | T01/T02 必须基于本地错误分桶，不做大网格 | [Mem0 memory-benchmarks](https://github.com/mem0ai/memory-benchmarks) | 中高：公开实现与实验，但任务分布不等同比赛 |
| Query/intent-aware retrieval 和结构化过滤能减少无关记忆 | 支持阈值、去重和错误类型路由思路 | [SimpleMem](https://arxiv.org/abs/2601.02553)、[PropMem](https://github.com/ProsusAI/MemEval/blob/main/PROPMEM.md) | 中：较新论文/开源说明，短期内只借鉴原则 |
| Memory 系统应分阶段评估写入、存储、召回和生成错误 | T00 强制拆分 Add/recall/ranking 错误 | [HaluMem](https://arxiv.org/abs/2511.03506) | 中：研究证据，适合诊断框架 |
| RAG 参数应按任务和失败模式选择；query expansion 不保证总是正收益 | 24 小时内拒绝盲目扩展检索链 | [RAISE](https://arxiv.org/abs/2605.30029)、[SemEval 2026 系统报告](https://arxiv.org/abs/2605.12028) | 中：任务相关性有限，但消融结论可参考 |
| Rerank 分数和阈值依赖 query/data 分布，需要本地校准 | T01 不使用拍脑袋阈值；T05 在冻结五样本校准并逐层报告 | [Cohere reranking guide](https://docs.cohere.com/docs/reranking-with-cohere) | 中高：供应商工程文档，结论通用但可能偏产品 |
| 长期记忆质量依赖 extraction、consolidation、update，而不只是向量召回 | 抽取错误主导时才进入 T03/T06 | [AWS AgentCore long-term memory deep dive](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/) | 中高：工程实践，非比赛基准 |
| 时间版本化能改善矛盾事实与状态更新 | 说明现有 exact dedup 的能力边界，但 24 小时内不引入新图时态架构 | [Graphiti](https://github.com/getzep/graphiti) | 中高：成熟开源实现；迁移成本过高 |

说明：2025～2026 的新工作发表时间短，“高引用量”尚不足以作为可靠筛选标准；本计划更看重可复现实验、公开实现、与当前失败模式的相关性，以及是否能在剩余时间内安全落地。

## 11. 建议的第一次审批

双 Session 路线已经单独细化到 [DUAL_SESSION_TUNING_APPROVAL_PLAN.md](DUAL_SESSION_TUNING_APPROVAL_PLAN.md)。若采用该路线，以其中 DS0/DS1/DS2 的 gate 和审批口令为准；MMR 本轮排除，T03/T04/T06 和 T90 仍需单独审批。

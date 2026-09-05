# MemScope 最终调优执行审批方案

> 状态：Search 主线、多 session 协作和 T90 已批准；T04/T03/T06 保留二次审批；本文件不授权当前方案 session 代替各执行 session 运行实验
> 日期：2026-09-05
> 唯一执行准绳：本文覆盖此前 24H 与双 Session 文档中的执行冲突
> 已有决策：M1/M2/M3 已批准；T02 内部 `0.92` 锁定；不做 MMR、自动 prompt 搜索；T07 已拒绝；prompt 调优最低优先级；除 winner 的必要 release 配置固化外，不批准算法代码修改

## 1. 审批结论

另一 session 已经开始 T00 baseline。它只负责完成 baseline 和结构化交接，不自行进入调优。收到 T00 结果后，采用以下流水线：

```text
S00-Baseline（已在运行，只交付 C0）
        ↓
S05-C5：身份验收 + T05 capability/C5 gate
        ↓
        ├─────────────── 并行 ───────────────┐
        │                                     │
S01-M1：T01 + T05 + M1          S02-M2：T02 + T05 + M2
exact，选 relativity 阈值            sim@0.92，relativity=0
        │                                     │
        └────────── 两个 lane 停止 ───────────┘
                              ↓
S03-M3：M3，一次联合候选 + 单栈复验
                              ↓
若 Search 无可接受候选且 T00 证明 Add 侧主导：
二次审批后依次新开 S04-Window；S05-Prompt；S06-Patch
                              ↓
S90-Release：独立新 session 冻结与交付
```

默认主线不修改应用算法代码：T01/T02/T05 均使用现有运行时配置。获胜后允许一次必要的 release 配置固化；T06、确定性时间正规化、reranker batching 等代码路径不在当前授权内。

若 T05 因协议、内网确认、容量、延迟或明显反效果失败，则不结束全部 Search 调优：由 `S05-C5` 在 HANDOFF 中把两条 lane 改为 `T01+cosine_local` 与 `T02+cosine_local`，仍按同样 M1/M2/M3 结构执行；阈值必须基于 local score 重算。若对应 `U_T01/U_T02` 也不足，则直接把 C0 交给 `S90-Release`。

### 1.1 审批总览

| 项目 | Session | 执行状态 | 最大时间 | 条件化预估提升 | 风险 |
|---|---|---|---:|---:|---|
| T00/C0 | S00-Baseline | 已开始，只交接 baseline | 从该 session 启动计 2h | 0 pp | 低；身份/数据不一致会污染全部后续 |
| T05/C5 | S05-C5 | **已批准** | 75min（含交接） | 相对 C0 `+0.5～+3.0 pp` | 高；远端依赖、配额、时延、评测端可用性 |
| T01+T05/M1 | S01-M1 | **已批准**；C5 后并行 | 105min（含交接） | 相对 C5 `+0.2～+1.5 pp` | 低/中；过度过滤、空结果 |
| T02+T05/M2 | S02-M2 | **已批准**；C5/300-doc gate 后并行 | 105min（含交接） | 相对 C5 `0～+1.5 pp` | 中；误合并状态、300-doc 负载 |
| M3 联合+单栈复验 | S03-M3 | **已批准**；A/B 均完成后一次 | 105min（含交接） | 相对最佳单 lane `-0.5～+1.0 pp` | 中；负交互，收益不可相加 |
| T04 window | S04-Window | 条件满足后再次审批 | 4h（含交接） | `+0.5～+2.5 pp` | 中/高；重灌、Add 时延、旧 Search 结论失效 |
| T03 remove example | S05-Prompt | 最低优先级、再次审批 | 4h（含交接） | `0～+1.5 pp` | 高不确定；静默漏抽取/格式退化 |
| T06 prompt patch | S06-Patch | 默认不批准、再次审批 | 4.5h（含交接） | `+0.5～+3.0 pp` | 很高；代码、测试、重灌、镜像全部变化 |
| T07 BM25/VEC-CoT | 无 | 已拒绝 | 0 | 不估计 | 很高；新索引/依赖/延迟/合规 |
| T90 交付 | S90-Release | **已批准；独立新 session** | 固定 10h | 不计质量增益 | 必做；决定评测机能否拉起 |

数值都是 baseline 前的排期先验；最终是否执行和接受只看第 3 节的 `U_i`、实际配对结果与 release gate。

## 2. Session 所有权与并行边界

| Session | 阶段 | 唯一职责 | 禁止事项 |
|---|---|---|---|
| `S00-Baseline` | 已在运行 | 完成 T00/C0、冻结身份和 store、输出错误分桶 | 不试阈值、sim、外部 reranker、window 或 prompt；不决定最终候选 |
| `S05-C5` | T00 后 | 验收 T00、执行 T05 capability/C5、生成 A/B 两份起始 prompt | 不做 T01/T02；不修改共享 store/算法/release 配置 |
| `S01-M1` | 并行 Search | 只做 `T01+T05` 与 M1 | 不 Add、不改 dedup、不改代码/镜像/release 配置 |
| `S02-M2` | 并行 Search | 只做 `T02+T05` 与 M2；内部 0.92 固定 | 不 Add、不改 relativity 在线网格、不改 0.92/MMR/代码 |
| `S03-M3` | A/B 后 | 验收两份结果、一次 M3、单栈复验；输出 winner/fallback 和条件项触发判断 | 不执行 T04/T03/T06；不新增第二个组合 |
| `S04-Window` | 二次审批后 | 只做 T04 和在新 store 上的窄 Search 重校准 | 不做 T03/T06；不扩大 window 网格 |
| `S05-Prompt` | 二次审批后 | 只做 T03 二元候选和窄 Search 重校准 | 不改 prompt 文本、不自动搜索、不进入 T06 |
| `S06-Patch` | 二次审批后 | 唯一源码写入者，做一个人工规则 patch | 其他 session 停止源码写入和同名镜像构建；不自动搜索 prompt |
| `S90-Release` | 最终 | 只读取已批准 winner/fallback，完成冻结和离线交付 | 不重开调优、不改变算法或依赖 |

并行时 S01/S02 共用同一冻结、停写的 store 和同一启用 T05 的 MemOS backend，只使用两个独立 memory-api 前端、端口、私密 env 和结果目录。并行结果只用于质量筛选；P95/max 必须由 `S03-M3` 在无竞争单栈中复验。

`S05-C5` 在 HANDOFF 中固定两个 lane 的总 Search 并发，起点最多为 2；第一次出现 429、明显排队或 P95 异常抬升即降为 1。请求转串行后，S01/S02 仍可并行分析各自已经取得的结果。任何 session 都不得并行 build 同名镜像。

### 2.1 每个 Session 的强制三件套

每个 session 必须在自己的 ASCII 路径中产出：

```text
tuning/handoffs/<session-name>/<run-id>/
├── SESSION_SUMMARY.md
├── RESULT.json
└── HANDOFF.md
```

- `SESSION_SUMMARY.md`：本 session 的问题、根因、有效经验、无效尝试、证据/推断边界、未验证项。
- `RESULT.json`：机器可读的身份、唯一变量、指标、错误、重复结果、停止原因和结论；不得包含 key、租户值或 query/memory/gold 正文。
- `HANDOFF.md`：winner/fallback、运行时状态、停写约束、回退点、下一阶段准入条件、未确认假设，以及可直接复制给下一 session 的最小上下文 prompt。

原始逐题正文只放仓库外权限为 `0700` 的私密结果目录。仓库内三件套只保存脱敏统计、hash 和私密目录位置。每个文件先写临时名，内容完整后再原子化改为正式文件名；三件套不完整等同于该 session 未交接。

### 2.2 新 Session 的状态核验 gate

新 session 只读取：本文共同协议和自己的阶段章节、直接前序三件套 `SESSION_SUMMARY.md`/`RESULT.json`/`HANDOFF.md`、阶段必需的实现/配置文件。默认不重读完整对话、旧版调优文档或所有研究材料。

开始动作必须是只读核对以下实际状态与 handoff 是否一致：

```text
full commit + dirty state
image IDs/digests/revision
Compose/config/data/query-order hash
store ID/schema/count/Add config
endpoint/model identity（无凭证）
Compose project、端口、volume、停写状态
前序 control/result checksum
```

任一不一致立即停止并写三件套，不允许自行“修到差不多再继续”。需要扩大权限、修改算法、重灌共享 store 或改变唯一变量时，必须重新审批。

### 2.3 上下文和时间预算

- 新开 session 的主要收益是减少输入上下文、TTFT/token 成本和决策漂移；长上下文下 TPOT 可能随 KV/attention 压力下降而改善，但不把 TPOT 改善作为必然结果或质量 gate。
- 每个新 session 的前 10～15 分钟用于读取最小上下文和状态核验。
- 最后强制保留 15 分钟生成三件套和下一阶段 prompt；实验必须在此之前停止。
- 80% 时间点仍无首个可比较结果时不再增加候选；100% 到点只允许完成交接。
- S01/S02 可并行写各自独立目录，禁止同时修改同一路径；S03-M3 必须等两份三件套都完整后才启动。

### 2.4 HANDOFF 最低内容

```text
本阶段结论与 stop reason
winner / fallback / rejected candidates
精确身份与 checksum
运行中/已停止的容器、project、端口、store/volume
共享 backend 是否必须停写、由谁关闭
私密结果目录和脱敏 RESULT 路径
风险、blocker、未验证假设
下一阶段准入条件与禁止事项
NEXT_SESSION_PROMPT（可直接复制）
```

## 3. 全局评价口径

### 3.1 唯一主质量分

冻结五样本按层内平均、层间加权：

```text
Q = 0.500 * Q_LoCoMo
  + 0.132 * Q_Remember
  + 0.098 * Q_Update
  + 0.115 * Q_Forget
  + 0.155 * Q_Reflect
```

本文中的 `+1.0 pp` 表示该 `Q` 提高 1 个百分点。五个 conversation cluster 不是独立大样本；bootstrap/置信区间只作稳定性提示，不声称统计显著。

### 3.2 预估提升如何计算

baseline 回传前的数值只用于时间分配，不是分数承诺。T00 后由 `S05-C5` 用实际可修复错误质量重新估计：

```text
U_i = 调优项 i 对应错误簇在总 Q 中造成的加权损失上界（百分点）
预估 ΔQ_i = U_i × 保守修复率 - 预期新增退化质量
```

若 T00 得到的 `U_i` 小于该项最低接受门槛，则该项直接跳过；不因为论文、主办方建议或“通常会提升”强行实验。

| 上界 | T00 对应错误簇 |
|---|---|
| `U_T05` | 正确证据已进入候选，但最终排名不足 |
| `U_T01` | 低相关噪声进入结果并干扰回答；必要证据 score 有分离空间 |
| `U_T02` | 近重复证据挤占 top-k，导致其他必要证据缺位 |
| `U_T04` | 事实/指代被窗口边界切断，或窗口负载导致截断/超时 |
| `U_T03` | 可归因给 example 诱导的角色、格式或抽取边界错误 |
| `U_T06` | 现有 runtime seam 都无法修复的同构抽取规则错误 |

错误簇可以重叠，组合上界按题目并集重新计算，不能直接相加。例如使用 `U_{T05∪T01}`，而不是假设 `U_T05 + U_T01` 都能被独立恢复。

### 3.3 所有候选共同硬 gate

任何一项触发即淘汰当前候选，不用总分补偿：

- 新增跨用户证据泄漏、gold/Answer-like Search 内容或凭证泄漏；
- Update stale-value、Forget leakage/over-forget 出现新的关键错误；
- Add/Search 非 2xx、schema error、不可恢复 401/403/404，或超过内部安全线：Add max `115s`、Search max `55s`；
- 最终评测依赖未确认的公网服务、现场 patch/build/pull，或无法通过配置注入；
- 候选身份、数据 hash、store ID、模型/endpoint 不一致，导致无法和 C0/C5 配对比较。

### 3.4 统一接受线

| 风险等级 | 接受条件 |
|---|---|
| 低风险、纯本地配置（T01/T02） | 两轮方向一致，`ΔQ >= +0.5 pp`；Update/Forget 不退化；空结果和时延过 gate |
| 新外部依赖（T05） | 两轮方向一致，`ΔQ >= +1.5 pp`；目标内网 endpoint/model/credential 已确认；Search P95 `<50s`、max `<55s` |
| 联合候选（M3） | 相对最佳单 lane `ΔQ >= +0.5 pp`，否则保留最佳单 lane |
| 改 Add 分布（T03/T04） | `ΔQ >= +1.0 pp` 且目标错误簇减少至少 25%；完整新 store；Search 参数重新确认 |
| 代码/prompt patch（T06） | `ΔQ >= +1.5 pp`、目标错误簇减少至少 30%、全部回归/制品 gate 通过 |

`0 < ΔQ <` 对应门槛的候选只记录为“方向性正收益”，不进入最终 release；收益不足以抵消小样本误差和新增复杂度。

T05 的 `+1.5 pp` 门槛按**最终含 T05 候选相对 C0**计算，不要求 C5 单项必须先达到 `+1.5 pp`；这样不会提前错杀 `T01+T05` 或 `T02+T05` 的有效组合。C5 只负责判断 endpoint 可用性、延迟和 T05 是否存在明显反效果。

### 3.5 防止反复试错的统一停止规则

每个调优家族同时受以下限制：

1. **风险停止**：任何共同硬 gate 触发立即回退；同一远端 arm 发生 2 次 timeout/5xx，或重试后累计 3 次 429，停止该远端 lane。
2. **达到预期停止**：候选达到对应接受线并完成两轮一致性确认后停止，不继续追求更高尖峰。
3. **时间停止**：时间盒达到 80% 仍没有首个可比较结果，不再增加候选；达到 100% 立即结束并回退到最近通过 gate 的配置。
4. **无效停止**：同一家族连续 2 个候选未达到接受线，关闭该家族；T02/T03 本身只有一个候选，失败即关闭。
5. **反效果停止**：连续 2 轮 `ΔQ <= 0`，或同一候选重复两轮收益正负号不一致，候选不得进入 release；不追加第三轮“赌结果”。
6. **组合停止**：最多运行一个 M3 联合候选；组合不优于最佳单项立即回退，不继续堆叠功能。
7. **冻结停止**：距离比赛结束 10 小时进入 T90 冻结线。达到冻结线后禁止任何新调优、prompt 修改或依赖变更。

## 4. T00/C0：baseline 与交接（`S00-Baseline`，已开始）

### 目标与依据

T00 不是调优候选，而是所有调优的硬前置。它回答错误在 Add、召回、排序、阈值、重复、生命周期还是服务，并提供 M1/M2 的 score 和 paired-query 基础。依据是 B05/B06 的分阶段诊断设计，以及 MemOps 对 provenance、stale value、forget leakage/over-forget 的分项口径。

### 时间、提升与停止

- 时间盒：从该 session 实际启动计最多 `2 小时`；已消耗时间计入，不重置。
- 预估提升：`0 pp`；产出是避免选错调优方向。
- 风险：运行身份漂移、非干净 store、结果含敏感正文、把 proxy Answer 失败全部归因给 Search。
- 停止：2 小时到点只提交已完成结果并标缺失；服务/身份不稳定则转交付修复，不开启调优。

### 必须交接的结果

```text
full commit + dirty state
image IDs/digests/revision + Compose/config 脱敏 hash
five-sample manifest/data/query-order hash
store ID/schema/count + Add 配置
C0 per-query result + Q/五层分数 + 两轮一致性
score/最终 rank/最终 memory ID（现有接口不可见字段标 not_observable）
error buckets + addressable mass U_T05/U_T01/U_T02/U_T04/U_T03/U_T06
Add/Search success、P50/P95/max、429/timeout/5xx
private result directory；仓库内不写原文、key 或租户值
```

### 可直接发给 agent 的 prompt

```text
角色：S00-Baseline。继续已经开始的 T00，不重置计时。
最小上下文：只读 FINAL_TUNING_EXECUTION_APPROVAL_PLAN.md 的第2～4、13节、T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md，以及本 session 已有运行记录；不要重读旧调优文档，除非出现 blocker。
目标：只完成冻结五样本的 C0、错误分桶和可验证交接。记录 full commit/dirty state、image digest/revision、Compose/config/data/query-order hash、唯一干净 store、模型身份、逐题结果、五层 Q、U_T05/U_T01/U_T02/U_T04/U_T03/U_T06、Add/Search 成功率和 P50/P95/max。不可见字段写 not_observable。
禁止：任何 T01～T07/T90；修改 relativity/dedup/reranker/window/prompt/源码/镜像/release 配置；把正文或凭证写入仓库。
停止：总时间从本 session 实际启动计2小时，最后15分钟只做交接；跨用户泄漏、身份不一致、Add max>=115s、Search max>=55s或服务不稳定时立即停止。
交付：在 tuning/handoffs/S00-Baseline/<run-id>/ 原子化生成 SESSION_SUMMARY.md、RESULT.json、HANDOFF.md；原始正文只放仓库外0700目录。HANDOFF 必须包含实际运行状态、回退点及可直接复制给 S05-C5 的 NEXT_SESSION_PROMPT。三件套完成后结束，不继续调优。
```

## 5. T05/C5：外部 reranker 共同 gate（`S05-C5`，独立新 session）

### 配置与依据

```text
relativity=0.0
dedup=exact
rerank=true
MOS_RERANKER_BACKEND=http_bge
```

Cross-encoder reranker 是成熟的二阶段检索模式，适合“候选已召回、排序错误”的失败簇；但不能恢复未召回证据。T05 还会引入同步远端依赖，因此必须先建立 C5，并独立证明其质量增益和评测环境可用性。

### 启动前置

- C0 身份完整，且 `U_T05 >=0.5 pp` 或 `max(U_{T05∪T01}, U_{T05∪T02}) >=1.5 pp`；否则 T05 及其联合路线没有足够理论上限，跳过。
- 课题组已确认目标内网 endpoint、model ID、协议和凭证注入方式；未确认时可以记录开发证据，但不得进入 release。
- capability probe 依次覆盖 1/100/300 个脱敏 documents；300 是 `sim + top_k=100` 的最坏候选规模。容量不过则仍可继续 S01 的 T05；S02 若 `U_T02>=0.5 pp` 可改跑 `sim+cosine_local`，否则交接 `skipped`。此时两 lane backend 不同，`combination_allowed=false`，S03 只能选最佳单 lane，不能运行联合候选；不临时写 batching。

### 时间、预估提升、风险与停止

- 时间盒：实验 `45～60 分钟`，加 15 分钟交接，总上限 `75 分钟`。
- 规划先验：相对 C0 `+0.5～+3.0 pp`；只有排序错误质量足够大时靠近上界。可信度中。
- 主要风险：401/403/404、429/TPM、协议差异、Search 尾延迟、fail-closed 导致整题失败、开发 endpoint 与评测 endpoint 不一致。
- 管控：脱敏 probe；两轮固定 query；不开并发压测；凭证仅从私密 env 注入；保留一键 `cosine_local` 回退。
- 停止：C5 连续两轮 `ΔQ<=-0.5 pp`、两轮收益符号不一致、任一不可恢复鉴权/schema 错误、2 次 timeout/5xx、累计 3 次 429、P95 `>=50s` 或 max `>=55s`，均停止 T05 路线。C5 在 `-0.5～+1.5 pp` 之间时本身不具备 release 资格，但若 T01/T02 的可修复质量足以使最终组合跨过 `+1.5 pp`，仍可启动 A/B。

### 可直接发给 agent 的 prompt

```text
角色：S05-C5。只有收到完整 S00 三件套后开始。
最小上下文：只读本文第2、3、5、13节、S00 的 SESSION_SUMMARY.md/RESULT.json/HANDOFF.md，以及 reranker 必需的配置/适配器文件。先只读核验 commit/image/config/data/query/store/model/runtime/checksum；任一不一致立即交接失败，不自行修复。
目标：在冻结停写 store 上建立 C5：relativity=0、dedup=exact、rerank=true、MOS_RERANKER_BACKEND=http_bge。先确认目标内网 endpoint/model/credential 注入方式，再做脱敏1/100/300-document capability gate和两轮固定查询；计算 C5-C0、各 U_i，并决定 S01/S02 使用 T05 还是 cosine_local fallback。
禁止：/add、T01/T02、源码/build/release 配置修改、打印 key/query/memory 正文、临时实现 batching。
停止：总上限75分钟，最后15分钟只做交接；不可恢复401/403/404/schema error、2次 timeout/5xx、累计3次429、P95>=50s、max>=55s、两轮符号不一致或连续两轮 ΔQ<=-0.5pp 时淘汰T05。
交付：在 tuning/handoffs/S05-C5/<run-id>/ 生成三件套。HANDOFF 必须固定共享 backend/store 的停写状态、S01/S02 端口/目录/总并发、C5或C0 control、两 lane backend 和 combination_allowed，并分别给出可直接复制给 S01-M1 和 S02-M2 的 NEXT_SESSION_PROMPT。完成后结束，不执行两条 lane。
```

## 6. T01+T05/M1：relativity breakpoint（`S01-M1`，独立并行 session）

### 配置与依据

固定 `dedup=exact` 和 T05；唯一变量为 `MEMOS_SEARCH_RELATIVITY`。M1 不盲扫 `[0,1]`，只枚举实际 external reranker score 改变结果集合的 breakpoint，选择稳定平台中部，最多在线确认 2 个阈值。

若 T05 gate 失败但 C0 稳定，`S05-C5` 可在 HANDOFF 中把 S01-M1 改为 `T01+cosine_local` fallback；必须重新基于 local score 计算 breakpoint，不能复用 BGE 阈值。

### 时间、预估提升、风险与停止

- 时间盒：实验最多 `90 分钟`，加 15 分钟交接，总上限 `105 分钟`。
- 规划先验：相对 C5 `+0.2～+1.5 pp`；当低相关噪声质量较大时才有收益。可信度中高。
- 风险：过滤必要证据、空结果增加、阈值过拟合五个样本、把 BGE 阈值迁移到其他 backend。
- 管控：固定所有其他变量；报告每题正/负翻转；Update/Forget 单列；选择宽平台中部；不新增第三阈值。
- 停止：`U_T01 <0.5 pp` 则不启动；任一关键状态证据被过滤或空结果明显增加立即淘汰；两个阈值均 `<+0.5 pp` 或连续为负，关闭 T01；候选达到 `+0.5 pp` 且两轮一致即停止。

### 可直接发给 agent 的 prompt

```text
角色：S01-M1。与 S02-M2 并行，只负责 T01+T05/M1。
最小上下文：只读本文第2、3、6、13节和 S05-C5 的 SESSION_SUMMARY.md/RESULT.json/HANDOFF.md；按其中 NEXT_SESSION_PROMPT、control、端口和总并发执行。先核验身份/runtime/checksum，偏差即停止。
目标：冻结 dedup=exact、rerank=true和 HANDOFF 指定的 backend；从 relativity=0 的实际 score 离线枚举结果集合 breakpoint，选稳定平台中部，最多在线确认2个阈值、每个两轮。报告 Q/五层、Recall/MRR/nDCG、空结果、stale/forget和正负翻转。
禁止：/add、修改 dedup、第三个阈值、照搬0.3/0.5、修改源码/镜像/共享 backend/env/release配置、决定最终 winner。
停止：总上限105分钟，最后15分钟只做交接；关键证据被过滤、共同硬gate、两个阈值均低于+0.5pp、连续两轮非正或符号不一致即关闭T01；达到+0.5pp且两轮一致也停止。
交付：在 tuning/handoffs/S01-M1/<run-id>/ 生成三件套。HANDOFF 必须声明共享 backend/store 未被写入、A-best/C5或C0 fallback、供 S03-M3 使用的 NEXT_SESSION_PROMPT，并明确 S03 必须等待 S02 三件套。完成后结束。
```

## 7. T02+T05/M2：sim@0.92（`S02-M2`，独立并行 session）

### 配置与依据

固定 `relativity=0.0` 和 T05；唯一变量为 `MEMOS_SEARCH_DEDUP=sim`。内部相似阈值 `0.92` 锁定，不做 MMR。M2 在 `sim+T05` arm 单独估计 `tau_sim`，只供汇合 session 使用；S02-M2 不自行增加在线阈值候选。

若 T05 gate 失败，只有 `S05-C5` 在 HANDOFF 中明确授权后才改为 `T02+cosine_local` fallback。

### 时间、预估提升、风险与停止

- 时间盒：实验最多 `90 分钟`，加 15 分钟交接，总上限 `105 分钟`。
- 规划先验：相对 C5 `0～+1.5 pp`；只有重复证据挤占 top-k 时有明显收益。可信度中。
- 风险：误合并不同日期、主体或 current/stale 状态；三倍候选量使 T05 请求接近 300 documents，触发延迟或配额问题。
- 管控：只试一个 `sim@0.92`；比较 dedup group 的日期/状态；C5 前已完成 300-document gate；不实现 batching、不修改 0.92。
- 停止：`U_T02 <0.5 pp` 或 300-document gate 未过，不启动；出现任何新的 Update/Forget 关键错误、错误合并或远端容量风险立即淘汰；单一候选 `<+0.5 pp` 即关闭 T02；达到门槛且两轮一致即停止。

### 可直接发给 agent 的 prompt

```text
角色：S02-M2。与 S01-M1 并行，只负责 T02+T05/M2。
最小上下文：只读本文第2、3、7、13节和 S05-C5 的 SESSION_SUMMARY.md/RESULT.json/HANDOFF.md；按其中 NEXT_SESSION_PROMPT、control、端口和总并发执行。先核验身份/runtime/checksum，偏差即停止。
目标：固定 relativity=0、rerank=true和 HANDOFF 指定的 backend；只运行 dedup=sim@0.92 两轮并与共同 control 配对。报告 Q/五层、重复/覆盖、日期/主体/current-stale 误合并、documents数和错误/时延；可离线估计 tau_sim，但不在线增加阈值。
禁止：/add、修改0.92、MMR、在线阈值实验、源码/build/共享backend/env/release配置、决定最终 winner。
停止：总上限105分钟，最后15分钟只做交接；300-doc gate 未过、新增 Update/Forget 错误、错误合并、共同硬gate、ΔQ<+0.5pp、两轮非正或符号不一致即关闭T02；达到+0.5pp且两轮一致也停止。
交付：在 tuning/handoffs/S02-M2/<run-id>/ 生成三件套。HANDOFF 必须声明共享 backend/store 未被写入、B-best/C5或C0 fallback、tau_sim和供 S03-M3 使用的 NEXT_SESSION_PROMPT，并明确 S03 必须等待 S01 三件套。完成后结束。
```

T05 被淘汰时，由 `S05-C5` 把以下切换内容分别写入 S01/S02 的 `NEXT_SESSION_PROMPT`；其中所有 `http_bge/C5` 分别替换为 `cosine_local/C0`：

```text
T05 已因 gate 失败淘汰，禁止继续调用或尝试修复远端 reranker，也不得把开发端结果写入 release。若 U_T01>=0.5pp，授权 S01-M1 在 cosine_local+C0 上执行 M1/T01；若 U_T02>=0.5pp，授权 S02-M2 在 cosine_local+C0 上执行 M2/T02。两边必须重新使用 local score，不能复用 BGE breakpoint。其余唯一变量、时间盒、停止规则和回传格式不变；若两个 U 都不足，停止 Search 调优并把 C0 交给 S90-Release。
```

## 8. M3：单 Session 汇合与一次联合确认（`S03-M3`，独立新 session）

### 决策和依据

先验收 A/B 的 commit、image、store、data/query hash、C5、endpoint/model 和指标定义完全一致。按以下规则汇合：

| A | B | 动作 |
|---|---|---|
| 不达标 | 不达标 | 比较 C5/C0，保留其中通过 release gate 的一方 |
| 达标 | 不达标 | 单栈复验 A |
| 不达标 | 达标 | 单栈复验 B |
| 都达标 | 只运行一次 `tau_sim + sim@0.92 + T05`；同时离线报告固定 `tau_exact` 的交互量 |

只有 S05 HANDOFF 明确 `combination_allowed=true`，且 A/B 使用同一 backend/control 时才能运行联合候选。若 S02 因 300-document gate 改用 local backend，S03 只把两个结果统一换算为相对 C0 的单 lane 候选并择优复验，不估计交互、不拼成 `sim+T05`。

阈值和去重处于同一候选处理链，单项收益不能直接相加；M3 的作用就是验证负交互。

固定同一 `tau_exact`、`backend` 和 control 时，S03 必须按以下差分中的差分计算 T01×T02 交互，而不是把两条 lane 的增益相加：

```text
I_12 = Q(tau_exact, sim, backend)
       - Q(tau_exact, exact, backend)
       - Q(0, sim, backend)
       + Q(0, exact, backend)
```

- `I_12 < 0`：阈值与 sim 互相伤害，联合候选需要特别保守。
- `I_12 ≈ 0`：在该固定阈值点近似无交互。
- `I_12 > 0`：存在协同，但仍须用 `tau_sim` 的唯一在线联合候选确认。

该公式只在 `combination_allowed=true` 且四个 cell 的 backend/control/store/data/评分定义一致时有效；否则写 `not_applicable`，不能跨 backend 计算。

### 时间、预估提升、风险与停止

- 时间盒：实验/复验最多 `90 分钟`，加 15 分钟交接，总上限 `105 分钟`。
- 规划先验：联合候选相对最佳单 lane `-0.5～+1.0 pp`，高不确定；不把 A/B 预估相加。
- 风险：threshold 与 sim 共同删除必要证据；共享并行压力污染延迟；错误地比较不同身份结果。
- 管控：A/B 停止请求后再汇合；最多一个联合 cell；最终候选在单栈跑两轮无竞争复验。
- 停止：身份不一致立即停止比较；联合候选相对最佳单 lane `<+0.5 pp` 立即回退；达到门槛且两轮一致后冻结 Search 候选；两轮符号不一致时不进入 release。

### 可直接发给 agent 的 prompt

```text
角色：S03-M3。只有 S01-M1 和 S02-M2 的三件套都完整后开始。
最小上下文：只读本文第2、3、8、13节、S01/S02 的三件套，以及两者引用的 S05 control identity/combination_allowed。停止两条 lane 的请求后，只读核验 commit/image/config/data/query/store/control/endpoint/评分代码/checksum；未被 S05 HANDOFF 预先声明的偏差即停止，不能拼接结论。
目标：按第8节汇合。只有 A/B 都达标、backend/control 相同且 combination_allowed=true，才运行唯一联合候选 tau_sim+sim@0.92+指定backend并报告 tau_exact 交互；否则只按相对C0选择单lane。随后对 winner 在单 backend、无竞争条件下两轮复验质量、success、P50/P95/max和错误码。
禁止：第二个组合、MMR、阈值网格、/add、执行T04/T03/T06、修改算法或release配置。
停止：总上限105分钟，最后15分钟只做交接；组合相对最佳单lane不足+0.5pp、共同硬gate、两轮非正或符号不一致时回退最佳单lane；通过即停止，不继续调参。
交付：在 tuning/handoffs/S03-M3/<run-id>/ 生成三件套。HANDOFF 必须给出 Search winner/fallback/release eligibility；只判断 T04/T03/T06 是否满足触发条件，不执行。若无需/未批准条件项，写给 S90-Release 的 NEXT_SESSION_PROMPT；若建议 T04，写待用户二次审批的 S04-Window prompt。完成后结束。
```

## 9. T04：window 单点候选（`S04-Window`，条件独立新 session、需再次审批）

### 触发条件与依据

只有同时满足以下条件才建议审批：

- 没有 Search 候选达到 release 接受线，或 Search winner 仍留下明确大块 Add 错误；
- T00 中可归因给跨窗指代/切片的 `U_T04 >=1.0 pp`；
- 距离 T90 冻结线至少还有 `4 小时`。

先用现有分片函数离线找真实 token breakpoint，只选择一个相邻窗口值：跨窗丢事实且时延宽裕则向大；截断/超时/调用过重则向小。当前 `1024` 作为对照，不扫任意 `512/768/1536/...` 网格。

### 时间、预估提升、风险与停止

- 时间盒：实验与窄 Search 重校准最多 `3.5 小时`，加 15 分钟交接，总上限 `4 小时`。
- 规划先验：满足触发条件时 `+0.5～+2.5 pp`；未满足时接近 0 或为负。可信度中低。
- 风险：必须新 store 重灌；大窗口增加 Add 延迟/token，小窗口增加窗口数/RPM、碎片与重复；使旧 T01/T02/T05 结论失效。
- 管控：只试一个方向的一个 breakpoint；第一轮使用全新 candidate store；只有达到接受线才建立第二个独立 candidate store 检查 Add 非确定性；不得与 T03 同时变化；通过后只重确认既有最佳 Search 配置，不重开全网格。
- 停止：首个候选目标错误簇未减少 25%、`ΔQ<+1.0 pp`、新增 Add/状态错误、Add max `>=115s`、出现 429/timeout，立即回退 1024；不试反方向第二值。实验 3.5 小时到点后只允许完成交接。

### 可直接发给 agent 的 prompt

```text
角色：S04-Window。只有用户在 S03 HANDOFF 后再次明确批准 T04 才开始。
最小上下文：只读本文第2、3、9、13节和 S03-M3 的三件套；先核验 winner/fallback、身份、旧store和 U_T04，且距 T90 冻结线>=4小时。任一不满足即交接 skipped。
目标：保持其他变量不变，用现有分片逻辑离线找1024附近真正改变边界的单一相邻值；跨窗丢失向大，截断/超时向小。第一轮全新candidate store；达到接受线才建第二个独立candidate store检查Add非确定性；随后只在新store上窄重校准既有Search winner。
禁止：第二个window值、反方向、大网格、同时改T03/prompt、复用旧store结论、算法/release配置修改。
停止：总上限4小时，最后15分钟只做交接；目标错误减少不足25%、ΔQ<+1.0pp、新增Update/Forget/角色错误、Add max>=115s、429/timeout或两次store方向不一致即回退1024和旧store。
交付：在 tuning/handoffs/S04-Window/<run-id>/ 生成三件套。HANDOFF 必须给出新/旧store winner与rollback；若仍建议T03，只生成待二次审批的 S05-Prompt NEXT_SESSION_PROMPT，否则生成 S90-Release prompt。完成后结束。
```

## 10. T03：删除 prompt example（`S05-Prompt`，条件独立新 session、最低优先级、需再次审批）

### 触发条件与依据

这是已有二元开关，不改代码，但会改变 Add 内容。只有 T00 显示 example 诱导/角色归因/抽取边界错误的 `U_T03 >=1.5 pp`，T04 不适用或已失败，且距冻结线至少 `4 小时`时才讨论。公开 prompt 实践只能提供假设，不能替代本地对照。

### 时间、预估提升、风险与停止

- 时间盒：实验与窄 Search 重校准最多 `3.5 小时`，加 15 分钟交接，总上限 `4 小时`。
- 规划先验：`0～+1.5 pp`，下行可达 `-2 pp`；可信度低。
- 风险：静默漏抽取、格式/JSON 不稳定、失去边界示范、旧 Search 参数失效。
- 管控：只比较 `false`/`true`；不改 prompt 文本、不自动搜索；第一轮全新 candidate store，达到接受线后才做第二个独立 candidate store；逐题检查角色、数字、否定、时间和生命周期。
- 停止：唯一候选 `<+1.0 pp`、目标错误减少不足 25%、任一层明显退化、Add 成功率下降或两轮不一致，立即关闭 prompt 路线；不追加 prompt patch。

### 可直接发给 agent 的 prompt

```text
角色：S05-Prompt。只有用户根据最新 S03-M3 或 S04-Window HANDOFF 再次明确批准 T03 才开始。
最小上下文：只读本文第2、3、10、13节和最新已接受阶段的三件套；核验 winner/fallback、身份、store、U_T03>=1.5pp、T04不适用/已失败且距冻结线>=4小时。偏差即交接 skipped。
目标：唯一变化 MEM_READER_REMOVE_PROMPT_EXAMPLE=true。第一轮全新candidate store；检查覆盖、角色、数字、否定、时间、生命周期、JSON和Add延迟；达到接受线才建第二个独立candidate store，再在新store上窄重校准既有Search winner。
禁止：修改prompt文本、自动搜索、同时改window/其他Add参数、复用旧store结论、算法/release配置修改。
停止：总上限4小时，最后15分钟只做交接；ΔQ<+1.0pp、目标错误减少不足25%、任何分层/稳定性退化、两次store方向不一致或共同硬gate即回退false和旧store。
交付：在 tuning/handoffs/S05-Prompt/<run-id>/ 生成三件套。失败后不得自行进入T06；若仍建议代码patch，只生成待二次审批的 S06-Patch NEXT_SESSION_PROMPT，否则生成 S90-Release prompt。完成后结束。
```

## 11. T06、T07 与 T90

### T06：单一人工 prompt/规则 patch（`S06-Patch`，条件独立新 session、默认不批准）

- 前置：T00 存在 `U_T06 >=1.5 pp` 的同构系统性错误；T03 失败；仍有至少 `4.5 小时本 session 总窗口 + 10 小时 T90`；用户单独批准代码修改。
- 依据：只有运行时 seam 无法修复的大错误簇才值得承担代码/镜像/重灌风险；成熟开源实现只用于提炼一个可解释规则。
- 时间盒：实验最多 `4 小时`，加 15～30 分钟状态核验/交接，总上限 `4.5 小时`；其中实验开始 2 小时内必须形成最小 patch 和针对性测试。
- 规划先验：`+0.5～+3.0 pp`，下行可超过 `-2 pp`；可信度低。
- 风险/管控：单一源码写入者、独立 worktree/branch、一次只改一个规则、完整测试/新 store/重构建；其他 session 禁止并行 build 或改同一文件。
- 停止：实验开始 2 小时无最小 patch+测试、首轮 `ΔQ<+1.5 pp`、目标错误减少不足 30%、任一回归/JSON/Add 稳定性失败或实验 4 小时到点，立即丢弃候选；不做第二 prompt 版本。

可直接发给 agent 的 prompt（仅再次批准后）：

```text
角色：S06-Patch，唯一源码写入者。只有用户根据最新 HANDOFF 再次明确批准 T06，并明确覆盖“默认不改算法代码”限制后才开始。
最小上下文：只读本文第2、3、11、13节、最新已接受阶段的三件套和目标错误直接相关的实现/测试；核验U_T06>=1.5pp、其他session已停止源码写入/同名镜像build、剩余时间>=4.5小时+10小时T90。
目标：在独立worktree/branch只实现一个人工、来源明确、可解释的prompt/规则修复；实验开始2小时内形成最小patch、针对性测试和变更说明，再用全新store验证五样本并窄重确认Search。
禁止：自动prompt搜索、第二prompt版本、重写memory pipeline、顺手修其他问题、自行合并或构建最终制品。
停止：总上限4.5小时，最后15分钟只做交接；2小时无patch+测试、ΔQ<+1.5pp、目标错误减少不足30%、任何测试/JSON/Add/Update/Forget回归或实验4小时到点即丢弃候选。
交付：在 tuning/handoffs/S06-Patch/<run-id>/ 生成三件套，记录commit/diff/test/result和安全rollback。HANDOFF 只能给出“建议合并/丢弃”，并生成 S90-Release 的 NEXT_SESSION_PROMPT；不得自行合并。完成后结束。
```

### T07：BM25/fulltext、VEC-CoT（已拒绝）

不分配执行 session、时间或实验额度。风险包括新索引/依赖、安全脱敏和额外 LLM 延迟，24 小时内不能完成质量、合规、镜像和离线启动闭环。任何 agent 若发现该路径，只记录为赛后建议，不得启动。

### T90：冻结与最终交付（`S90-Release`，独立新 session、不是质量调优）

- 时间：比赛结束前固定保留 `10 小时`，不可借给调优。
- 任务：固化获胜 env/release 配置；完整检查；四镜像构建；生成现有 `solution-<12hex>.zip`、`memscope-images-<12hex>-linux-amd64.tar`、manifest/SHA256；ASCII 输出目录；干净环境 `docker load`、`--no-build --pull never`、health/add/search smoke。
- 风险：最终配置未固化、凭证进入制品、镜像 revision 不一致、评测机需在线 pull/build/patch、外部 reranker 不可达。
- 停止/回退：任一 release rehearsal 失败，不做新调优，按 `联合候选 → 最佳单 lane → C5 → local T01/T02 → C0` 逐级回退到最近已证明可部署的候选。

可直接发给 agent 的 prompt：

```text
角色：S90-Release。独立新 session；冻结线已到，只做最终交付。
最小上下文：只读本文第2、3、11、13节、最新被批准 winner 的三件套、交付脚本和 release 配置；核验 winner/fallback、commit/image/config/model/store/checksum。不要读取无关调优历史。
目标：只固化已批准 winner 的必要 release 配置；完成完整检查、四镜像、solution-<12hex>.zip、memscope-images-<12hex>-linux-amd64.tar、manifest、SHA256、ASCII 输出目录和干净环境 docker load/--no-build/--pull never/身份校验/真实 health-add-search smoke。
禁止：任何新调优、prompt/算法/依赖修改、在线pull/build/patch要求、把真实凭证写入代码/镜像/日志/ZIP/TAR。
停止与回退：总时间固定10小时，最后15分钟只做交接；任一 rehearsal 失败不得重开调优，按“联合→最佳单lane→C5→local T01/T02→C0”逐级回退并重做交付闭环。
交付：在 tuning/handoffs/S90-Release/<run-id>/ 生成三件套，RESULT记录最终制品路径/hash/revision/smoke/fallback层级；HANDOFF记录评测机启动、回退和恢复步骤。该阶段为终点，明确写 NEXT_SESSION_PROMPT=none，并提供 operator runbook，而不是再启动调优session。
```

## 12. 时间线与资源止损

设 `F = 比赛结束时间 - 10 小时`，F 是不可移动的调优冻结线。另一 baseline session 已开始，因此不重新按 H0 排期：

| 相对 T00 交接 | Session | 工作 | 含交接最大墙钟 |
|---|---|---|---:|
| `B+0` | S05-C5 | 读取 S00、状态核验、T05 probe/C5、A/B prompts | 75 分钟 |
| `B+1:15` | S01-M1 / S02-M2 | 两个独立新 session 并行 | 105 分钟 |
| `B+3:00` | S03-M3 | 读取两份交接、一次 M3、单栈复验 | 105 分钟 |
| `B+4:45` | — | 默认冻结 Search winner；条件满足时请求 T04 二次审批 | — |
| 可选 | S04-Window | 仅二次审批后启动 | 4 小时 |
| 可选 | S05-Prompt | 仅二次审批后启动 | 4 小时 |
| 可选 | S06-Patch | 仅二次审批后启动 | 4.5 小时 |
| `F` | S90-Release | 独立新 session 强制进入 T90 | 10 小时 |

动态裁剪规则：

- 完整 Search 主线需要约 `4小时45分钟`；T00 交接时距离 F 不足该时间，不再压缩 session 核验/交接，默认冻结 C0 或此前已完整验证候选。
- S05-C5 HANDOFF 时距离 F `<3.5h`：不启动新的双 lane；若已有完整可比较的单 lane，只允许另开 S03-M3 做单栈验收，否则冻结 C0/C5。
- S01/S02 即使实验失败，也必须在最后15分钟形成 `reject/blocked/skipped` 三件套，S03 才能按另一 lane 与 control 决策；若任一 session 完全没有三件套，S03 不启动，直接把最近完整 control 交给 S90。
- T03/T06 不因“还有一点时间”自动启动；必须满足各自完整时间预算和再次审批。

### 12.1 时间盒依据

另一个 session 已回传真实 smoke：Add `10.377s`、Search `0.293s`。五样本包含约 250 个 Add chunks 和 126 个 Search questions，因此在不考虑长输入、限流、重试和分析时，单次完整重灌的理想 Add 下界约为：

```text
250 × 10.377s ≈ 43.2 分钟
```

这只是小请求 smoke 推出的排期下界，不当作正式性能结论。各时间盒按下列组成设置：

| 阶段 | 时间组成依据 |
|---|---|
| T00 2h | 约43分钟理想Add下界 + 126 Search + 长输入/限流余量 + 身份/错误分桶 + 最后15分钟三件套；当前 session 已消耗时间不重置 |
| S05-C5 75min | 最小上下文/身份核验包含在首段 + 1/100/300 probe + 2轮Search/C0配对 + 最后15分钟三件套；无重灌 |
| S01/S02 各105min | 最小上下文/状态核验 + 最多90分钟 M1/M2 Search实验 + 最后15分钟三件套；两者并行，不把预算相加 |
| S03-M3 105min | 两份交接核验 + 最多1个联合cell/两轮Search + 单栈无竞争复验 + 最后15分钟三件套 |
| S04/S05-Prompt 各4h | 两次理想 candidate Add 共约86.4分钟 + LLM长尾/限流 + Search窄重校准/错误审计 + 最后15分钟三件套 |
| S06-Patch 4.5h | 最小上下文/单写入者核验 + 2h patch/测试 + 约1h重灌/Search + 审查/回退 + 最后15分钟三件套；不含T90 |
| S90-Release 10h | 最小 winner 上下文 + 冻结/完整检查、四镜像、TAR/ZIP/hash、干净环境load/start/smoke、三件套、传输余量和至少一次逐级回退重演 |

T00 实测若显著慢于 smoke，下游按实际吞吐重新计算时间；只能减少候选或跳过条件项，不能压缩 T90、提高未经验证的并发或放宽 deadline。

## 13. 统一回传模板

每个 agent 必须生成三个独立文件；缺失项显式写 `not_observable/not_run`，不能静默省略。

### 13.1 `SESSION_SUMMARY.md`

```text
# <session> 问题与经验总结
## 目标与实际边界
## 遇到的问题及根因
## 有效经验
## 无效尝试与反效果
## 直接证据、推断和未验证假设
## 停止原因
## 对下一阶段的提醒
```

### 13.2 `RESULT.json`

保持合法 JSON；不得加入注释或秘密值：

```json
{
  "schema_version": "memscope.tuning-result.v1",
  "session": "S01-M1",
  "run_id": "ASCII_RUN_ID",
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601",
  "wall_seconds": 0,
  "identity": {
    "commit": "FULL_COMMIT",
    "dirty": false,
    "image_digests": {},
    "image_revisions": {},
    "compose_config_sha256": "SHA256",
    "data_sha256": "SHA256",
    "query_order_sha256": "SHA256",
    "store_id": "STORE_ID",
    "add_config_sha256": "SHA256",
    "endpoint_model_identity": "NON_SECRET_ID"
  },
  "experiment": {
    "control": {},
    "candidate": {},
    "only_changed": [],
    "fixed": []
  },
  "quality": {
    "q_control": 0.0,
    "q_candidate": 0.0,
    "delta_q_pp": 0.0,
    "strata": {},
    "positive_flips": 0,
    "negative_flips": 0
  },
  "safety": {
    "cross_user_leak": 0,
    "answer_like_output": 0,
    "stale_value": 0,
    "forget_leakage": 0,
    "over_forget": 0
  },
  "reliability": {
    "success": 0,
    "p50_ms": 0,
    "p95_ms": 0,
    "max_ms": 0,
    "http_401_403_404": 0,
    "http_429": 0,
    "http_5xx": 0,
    "timeout": 0,
    "schema_error": 0
  },
  "repetition": {
    "rounds": 0,
    "same_direction": false
  },
  "decision": {
    "status": "accept|directional-only|reject|blocked|skipped",
    "stop_rule": "RULE_ID",
    "winner": {},
    "fallback": {},
    "release_eligible": false
  },
  "artifacts": {
    "private_result_directory": "REDACTED_PATH",
    "private_result_sha256": "SHA256"
  }
}
```

### 13.3 `HANDOFF.md`

```text
# <session> → <next-session> HANDOFF
## 本阶段冻结结论、winner 与 fallback
## RESULT/checksum 与精确身份
## Runtime：Compose project、容器、端口、store、volume、停写状态
## 回退点与恢复方法
## 风险、blocker 和未验证假设
## 下一阶段准入条件
## 下一阶段禁止事项
## NEXT_SESSION_PROMPT
```

## 14. 依据与可信度

- 仓库当前实现已提供 T01/T02/T03/T04/T05 的运行时 seam，timestamp 也已作为 `chat_time` 传给 MemOS；默认主线不需要算法代码修改。
- [LoCoMo 官方仓库](https://github.com/snap-research/LoCoMo)与[原论文](https://aclanthology.org/2024.acl-long.747/)支持保留 session 时间和 temporal evidence，但不证明 Add 阶段提前正规化是唯一最优策略。
- [Graphiti 时间实现](https://github.com/getzep/graphiti/blob/main/graphiti_core/utils/maintenance/edge_operations.py)证明 episode-time/validity 建模可行；这里只借鉴诊断维度，不在赛前迁移架构。
- [MemOps](https://github.com/MemTensor/MemOps)直接对应 Remember/Forget/Update/Reflect 和 provenance 诊断，但其为 research preview，适合作为错误口径而非通用最优结论。
- Cross-encoder 两阶段 rerank 是成熟工程模式；模型 score/阈值随 query、数据和 backend 改变，因此 T01 必须在最终 T05/dedup arm 上做 breakpoint 校准，不能照搬公开阈值。
- 所有预估提升区间均为排期先验。实际 go/no-go 只服从 T00 的可修复错误质量 `U_i`、配对五样本结果、稳定性和评测机 release gate。

## 15. 已批准协作与执行边界

2026-09-05 已批准：

```text
S00-Baseline → S05-C5 →（S01-M1 || S02-M2）→ S03-M3
→ 条件性 S04-Window → 条件性 S05-Prompt → 条件性 S06-Patch
→ S90-Release。

M3 与 T04 分离；T90 使用独立新 session。
每个 session 必须产出 SESSION_SUMMARY.md、RESULT.json、HANDOFF.md，
并为下一 session 提供经过状态核验的最小上下文 prompt。
T04/T03/T06继续保留二次审批。
```

继承的执行批准：T00 交接、T05/C5 gate、A/B 双 lane、一次 M3、单栈复验及 T90。继承的禁止项：T02 内部 `0.92` 不变，不含 MMR，不做自动 prompt 搜索，T07 继续拒绝；除最终 winner 的必要 release 配置固化外，不批准算法代码修改。若未来批准 T06，必须由批准文字明确覆盖这一默认禁止项。

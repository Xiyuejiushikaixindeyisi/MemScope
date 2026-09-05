# MemScope T00 可观测基线与五样本分层调优方案

> 状态：方案稿；本 session 只产出方案；M1/M2/M3 已批准，尚未授权启动 T00 或模型调用；T00 获批后必须由当前主 session 完成，不交给调优 agent  
> 日期：2026-09-05  
> 配套清单：[T00_STRATIFIED_FIVE_SAMPLE_MANIFEST.json](T00_STRATIFIED_FIVE_SAMPLE_MANIFEST.json)  
> 延续约束：T07 已拒绝；T02 内部 `0.92` 不改；MMR 不进入本轮；不做自动 prompt 搜索；prompt 调优最低优先级

主办方关于时间证据、Add 总结、凭证和 ASCII 交付命名的回复及独立核验见：[ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md](ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md)。其中只有赛题规则、允许边界和提交要求按官方口径执行；时间正规化、总结方式等技术选择仍按候选处理，不凌驾于对照数据。

## 1. 结论

T00 不应只给出一个 baseline 分数。它必须产出一份能回答以下问题的“决策基线”：

1. 当前分数是否能归因到唯一的代码、镜像、配置、模型、数据与存储。
2. 错误发生在 Add 抽取、候选召回、rerank 排序、阈值过滤、去重，还是服务/API。
3. T01 的候选阈值应落在哪些实际 score 断点，而不是从任意区间盲扫。
4. T02 是否真的存在重复挤占，以及固定 `sim=0.92` 会不会误吞时间/状态不同的事实。
5. T05 是否改善排序，代价是否会破坏评测机成功率和尾延迟。
6. 后续应进入 `T01+T05`、`T02+T05`、T04，还是停止调优并冻结交付。

T00 的直接输出不是“最优参数”，而是：**冻结的共同对照 C0、可复用 store、逐题诊断表、候选 score 分布、运行预算模型和下一步 go/no-go 决策**。

## 2. 已有 smoke 证据如何使用

当前主 session 已取得 rootful 实机证据：

- runtime revision：`756902cebeee9e04990164885fd6706df32dfef9`
- `memory-api` image ID：`sha256:50f689d6479e4021c92e48695ff386b637cfdedfedd4e6c4940654410e1adce8`
- MemOS image ID：`sha256:07e37e7bc1abf6778b6d002044d0313836fa7e082e4dabe127df2ccce669f5c4`
- 两张自研镜像均为 Linux/amd64 并绑定该 OCI revision；四服务 healthy，宿主端口和 cgroup 限额通过
- Add `10.445s`；幂等 replay `0.003s`；Search `0.229s`；跨用户隔离 Search `0.136s`；检索命中 2 条

这足以证明 `756902c` 的真实 rootful 四服务基本闭环，因而 T00 无需重复把大量时间花在
“能否跑通”上；但它还不是调优 baseline，因为没有覆盖五个正式困难样本、逐题质量、score
分布、重复/旧值/遗忘泄漏、外部 reranker 延迟及资源/API 错误。

计划文档提交位于 runtime revision 之后，但没有改变镜像输入或 Compose。T00 将运行候选冻结为
上述 `756902c` image pair，同时单独记录实际 plan revision、Compose hash、脱敏配置 hash 和
容器 image ID。不能只记短 commit，也不能把后续纯文档提交写成 OCI runtime revision。

## 3. T00 必须提供的九类信息

| 类别 | 必须记录 | 用途 |
|---|---|---|
| 候选身份 | full commit、dirty/untracked 状态、镜像 tag/digest/revision、Compose 文件 hash、环境配置脱敏 hash | 防止两个 session 比较了不同候选 |
| 模型身份 | Add LLM、embedder、维度、reranker endpoint/model、关键能力探测结果、内网可达性与凭证注入方式；不记录真实 key/租户值 | 判断分数尺度、协议和发布可用性 |
| 数据身份 | 五个 sample ID、文件 SHA-256、题目顺序 hash、`full_conversation`、`top_k=100` | 保证所有 cell 用完全相同输入 |
| 存储身份 | Cube/user 映射、Neo4j/Qdrant collection/schema、记录数、store/snapshot ID、灌入配置 | 让 Search lane 共用唯一冻结数据 |
| Add 行为 | 每样本 session/chunk/message/token、调用数、成功/失败、P50/P95/max、抽取 memory 数、空抽取、重复、角色归因、状态变化、timestamp 传递；若当前链路已正规化相对时间，再记录其结果 | 判断是否真的需要 T03/T04 或另审时间正规化候选 |
| Search 各阶段 | 在现有响应/日志可见范围内记录初始候选数、rerank 前后 rank/score、阈值前后数量、dedup 前后数量、最终条数/字节/token | 为 M1/M2/T02 提供可离线重算的数据 |
| 逐题质量 | query ID、stratum/axis、gold evidence 命中、MRR/nDCG/Recall、proxy score、旧值率、Forget 泄漏、过遗忘、重复率、空结果率 | 避免只看总分掩盖退化 |
| 可靠性与成本 | 2xx、401/403/404/429/5xx/timeout/schema error；API 次数/token；CPU/RSS/GPU；冷启动、稳定态、重启恢复 | 决定候选能否进入评测机 |
| 决策产物 | 统一错误分桶、每项数量/严重度、下一实验、停止条件、预计剩余时间 | 让审批直接基于证据进行 |

### 3.1 Add 侧错误标签

至少保留下列互斥主标签，并允许附加次标签：

- `extract_miss`：可记事实没有形成有效记忆。
- `subject_or_role_error`：把 assistant 建议或他人事实绑定给用户。
- `temporal_resolution_error`：相对日期、事件顺序或观察时间错误。
- `update_stale_value`：旧值仍 active，或 tentative 状态覆盖了最终值。
- `forget_leak`：明确遗忘内容仍可检索。
- `over_forget`：删除目标事实时误删应保留的相关信息。
- `reflect_unsupported`：反思结论缺乏足够证据，或把一次事件泛化为稳定偏好。
- `fragment_or_duplicate`：同一事实被分片成互相挤占的多条记忆。
- `temporal_grounding_error`：时间证据不足以下游正确定位事件，或把模糊时间伪造成错误的精确日期；仅保留原文和正确 session timestamp 不自动判错。
- `answer_like_evidence`：Search content 变成针对题目的最终答案句，而不是从 Add 输入形成的记忆证据。

只有前三类/状态类形成主要、同构错误簇时才考虑 Add 侧变化。prompt 相关的 T03/T06 放在所有已批准 Search 方法之后，并需再次审批。

主办方已确认 Add 可以提取、总结、改写和结构化，也允许把 session timestamp 与 `yesterday/last week` 等表达合成为带日期或时间区间的 evidence；这是许可而非最优实现结论。T00 因而单列 `timestamp_ingest_coverage`、`temporal_evidence_recall`、`temporal_anchor_error` 和 `answer_like_output_rate`，并区分“原文+正确 timestamp 已召回”与“已正规化证据召回”。不能把 Answer/Judge 失败简单归因给记忆服务，也不能通过在 Search 中直接写答案规避。

### 3.2 Search 侧诊断必须能支持离线选参

对每个 query-candidate 尽量记录以下脱敏字段；原 query/memory/gold 只写入仓库外 0700 私密结果目录：

```text
run_id, sample_id, qid, stratum, eval_axis,
memory_id_hash, retrieval_path, raw_rank, raw_score,
reranker_backend, reranker_model, rerank_rank, rerank_score,
passed_relativity, dedup_group_hash, final_rank,
is_relevant, is_stale, is_forgotten, response_latency_ms
```

本轮不因 T00 自动授权新增 runtime instrumentation。当前公共 Search 已返回最终 `score`，它对应 T01 实际消费的 `relativity`，足以完成 breakpoint sweep。不可从现有响应/脱敏日志得到的内部 raw rank/score 必须标记 `not_observable`，可用 C0/C5 相同 memory ID 的配对顺序作辅助对照，但不得伪造；若确需打点，另行审批代码变更。

这张表同时服务于：

- M1：枚举实际 reranker score breakpoint；
- M2：在 `exact+T05` 与 `sim+T05` 上分别估计 `tau_exact` / `tau_sim`；
- M3：汇合后只在线确认一次 `tau_sim+sim+T05`；
- T02：确认重复簇是否挤占相关证据，以及 `0.92` 固定语义是否安全；
- T05：比较 rerank 前后的 MRR/nDCG/Recall，不把最终 Answer 波动误归因给排序。

## 4. 五样本分层小数据集

### 4.1 固定选择

| 层 | sample | 历史规模 | 题量 | 选择依据 |
|---|---|---:|---:|---|
| LoCoMo | `locomo_conv-41` | 32 sessions / 663 messages / 46 Add chunks | 106 | 官方样本中 session 最深；同时保留 23 单跳、26 时序、57 多跳 |
| Remember | `memops_B01_remember` | 50 / 540 / 51 | 6 | 同类最高 rubric burden：37 must + 14 harmful |
| Update | `memops_A16_update` | 50 / 506 / 50 | 4 | 同类最高 rubric burden：13 + 11；含 tentative、回退与他人状态干扰 |
| Forget | `memops_A05_forget` | 50 / 506 / 51 | 5 | 同类最高 rubric burden：30 + 9；选择性遗忘与过遗忘并测 |
| Reflect | `memops_A02_reflect` | 50 / 540 / 52 | 5 | 同类最高 rubric burden：25 + 9；要求从多次证据形成稳定偏好 |
| **合计** | **5 samples** | **232 sessions / 2755 messages / 250 Add chunks** | **126** | 全历史、全题、全干扰项 |

“五个样本”不是“五道题”。每个样本完整 Add，其全部 Search 题都保留；不裁历史、不删除 distractor、不把多跳改成单跳。这与赛题调测指南“先 1～2 个样本，再逐步扩测”的方法一致，但用五个预先固定的困难哨兵补齐了生命周期覆盖。

### 4.2 为什么它不会因缩量而主动降难度

选择规则在看到 MemScope 结果前冻结：

1. LoCoMo 先要求同时包含正式计分的单跳/时序/多跳，再优先纵向 session 深度。
2. MemOps 在每个 operation 内按 `must_include + harmful_extra` 总数选择最高样本。
3. 保留原始 `full_conversation`、longitudinal distractors、原 qid 与全部 rubric。
4. 文件和 `SOURCE_LOCK.json` 均用 SHA-256 锁定，不允许实验过程中替换“更容易”的样本。

该集合能高效淘汰明显退化候选，但不能替代官方 1000 题，也不能给出可靠的官方分数预测。只有五个独立 conversation cluster，因此 bootstrap 置信区间只能作为稳定性提示，不能声称统计显著。

### 4.3 分层计分，避免 LoCoMo 106 题吞没四个 MemOps 样本

先在每个 stratum 内求均值，再按官方 500/500 构成和 MemOps 题量比例做 macro weighting：

```text
Q = 0.500 * Q_LoCoMo
  + 0.132 * Q_Remember
  + 0.098 * Q_Update
  + 0.115 * Q_Forget
  + 0.155 * Q_Reflect
```

原始 126 题 micro average 只作为附录。主决策还必须报告每层最差值、Update 旧值率、Forget 泄漏/过遗忘和每层正负翻转；总分上升不能抵消新的状态或隐私类泄漏。

## 5. 基于成熟实践选择参数起点

### 5.1 冻结起点

| 项目 | 起点 | 搜索范围 | 依据与可信度 |
|---|---|---|---|
| C0 Search | `relativity=0.0`、`dedup=exact`、`rerank=true`、`cosine_local` | 不搜索；共同基线 | 当前仓库稳定默认 + 已有真实 smoke；**高（本项目）** |
| T05 model | `BAAI/bge-reranker-v2-m3` | 本轮不换模型 | BAAI 官方模型卡将其定位为轻量、多语言、易部署；当前适配器/镜像已实现；**高（模型身份），中（比赛收益）** |
| T05 输入 | 仅对第一阶段真实候选做 cross-encoder rerank | 不扩大公开 `top_k=100`，不引入新召回路径 | Cohere/Pinecone/Weaviate 均采用两阶段 rerank；BAAI 公开评测也 rerank top-100；**高（工程模式）** |
| T01 threshold | 第一轮 `0.0` 收集完整 score | 只枚举实际 score 中点；离线筛后最多确认 2 个 | BGE 输出可 sigmoid 到 `[0,1]`，但模型卡没有通用阈值；必须本地校准；**高（不照搬固定阈值）** |
| T02 | `exact` 对照 vs `sim` 实验 | 内部 `0.92` 锁定；不测 MMR | 用户明确约束 + 单变量归因；**高（决策边界）** |
| T04 window | 保持 `1024` | 只有 T00 证明跨窗/超时问题时，才从真实分片 breakpoint 选 1 个相邻候选 | 当前稳定默认；没有可信公开资料能直接给本任务最优窗口；**高（保守起点），低（泛化最优）** |
| T03/T06 prompt | 保持当前 prompt/example | 最低优先级；不做自动搜索；如再审批，只做一个来源明确的单规则 patch | LangMem/Mem0 的结构化 memory schema 与生命周期实现可作人工参考；迁移到 MemOS 有不确定性；**中** |

资料链接：

- [BAAI bge-reranker-v2-m3 模型卡](https://huggingface.co/BAAI/bge-reranker-v2-m3)：reranker 直接给 query-passage score，可选择 sigmoid 归一化；其公开评测以 top-100 候选做 rerank。
- [Sentence Transformers CrossEncoder evaluator](https://sbert.net/docs/package_reference/cross_encoder/evaluation.html)：同时报告 rerank 前后结果，并以 MRR@10、NDCG@10、MAP 衡量排序，而不是只看某个 score。
- [Cohere reranking guide](https://docs.cohere.com/docs/reranking-with-cohere) 与 [Pinecone rerank 文档](https://docs.pinecone.io/guides/search/rerank-results)：成熟实现均把 reranker 放在第一阶段候选之后，并通过 `top_n` 控制昂贵阶段。
- [SiliconFlow rerank API](https://docs.siliconflow.cn/cn/api-reference/rerank/create-rerank) 与 [rate-limit 文档](https://docs.siliconflow.com/en/userguide/rate-limits/rate-limit-and-upgradation)：当前适配器使用的协议支持 `documents`、`top_n` 和 trace ID；配额同时受 RPM/TPM 约束，因此必须以实际账号/端点探测为准。
- [Mem0 memory-benchmarks harness](https://github.com/mem0ai/memory-benchmarks/blob/main/README.md)：按 benchmark/问题维度保存检索与评测结果，支持 LoCoMo 等多会话 memory 测试。
- [LangMem semantic memory extraction](https://langchain-ai.github.io/langmem/guides/extract_semantic_memories/) 与 [Mem0 prompt 实现](https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py)：成熟实践强调 self-contained schema、subject/attribution、上下文、显式 insert/update/delete 和时间锚点。只作为未来人工 prompt patch 的规则来源，不作为自动搜索授权。

### 5.2 T01 的窄范围不是预设数值区间

对于当前 T05 model/store/dedup arm，排序所有唯一 score `s[i]`，候选只取结果集合会发生变化的中点：

```text
T = {0} union {(s[i] + s[i+1]) / 2}
```

离线重算每个 `tau` 的五层质量、Recall、空结果率、旧值/遗忘泄漏和返回量。选择顺序为：

1. 服务/API/跨用户错误为 0。
2. Update/Forget 安全指标不退化。
3. 五层中不出现不可接受的单层退化。
4. 最大化加权 `Q` 的 bootstrap 下置信界；小样本下同时报告均值和宽区间。
5. 若多个相邻 breakpoint 得到相同逐题结果，选该稳定平台中部，而非边缘值。
6. 每个 arm 最多把 2 个候选送入真实在线确认。

这落实了 M1，同时避免把公开示例里的 `0.3/0.5` 误当成通用阈值。

### 5.3 `sim+T05` 的 300 候选容量 gate

本仓库固定 Product Search 在 `dedup=sim` 时把内部 `top_k` 放大三倍。正式请求 `top_k=100` 时，T05 适配器可能一次发送最多约 300 个 `documents`，并把 `top_n` 设到实际候选数。当前实现没有分批逻辑。

Pinecone 托管 BGE 文档明确给出每次最多 100 documents；SiliconFlow 当前公开 schema 没写 documents 数量上限，但这不等于 300 一定安全，且 TPM 会随文档总长度增长。因此 Session B 前必须增加只读 capability gate：

1. 记录真实 `document_count`、每文档 token/字符分位数、请求总 token 估计和响应 `results` 数。
2. 对目标 endpoint 依次验证 1、100 和 300 个脱敏合成文档；不使用 gold 或原 query。
3. 再用五样本中一次真实最大候选 Search 验证延迟、429/4xx/5xx/timeout 和返回覆盖。
4. 任一 300 档失败、静默截断且破坏相关证据、或预测 TPM/尾延迟越界，则 **取消 `T02+T05` lane**；不在未审批情况下给适配器增加分批、截断或新参数。

这是一项评测机可运行性 gate，不是新的参数搜索。

## 6. 分层执行顺序

```text
L0  身份/能力层
    commit-image-config-model 对齐；health + 现有真实 smoke 复核
            |
L1  T00 五样本基线
    一次完整 Add -> 冻结 store -> 126 Search -> 九类观测与错误分桶
            |
L2  Search-only 共同对照
    C0(local) -> C5(BGE, tau=0, exact)；同一冻结 store
            |
L3  双 lane
    A: T01+T05 exact                         B: T02+T05 sim@0.92
    离线 tau_exact                           离线 tau_sim
            \                                 /
L4  单 session 汇合
    M3 仅在线确认一次 tau_sim+sim+T05；单栈、无竞争复跑
            |
L5  可选 Add 侧
    只有明确 Add 主错误且仍有时间才讨论 T04；prompt T03/T06 最后且另审
            |
L6  交付冻结
    最终 commit 重新构建、四服务 clean boot、离线/回退/评测机 smoke
```

若 L5 接受任何改变写入内容的候选，L2～L4 的 Search 参数必须在新 store 上重新校准。正因如此，prompt 虽可参考成熟规则，但在剩余 24 小时内应保持最低优先级，避免推翻已经完成的 Search 证据。

## 7. 基于现有实测的时间盒

五样本协议会产生 250 次 Add 和 126 次 Search。用回传 smoke 的单次延迟作粗略下界：

```text
Add lower bound    = 250 * 10.445s = 43.5 min
Search lower bound = 126 * 0.229s  = 28.9 s
```

实际还包含冷启动、长输入、限流、结果写盘和诊断，因此：

- T00 五样本完整灌入与基线：**60～90 分钟目标，120 分钟硬止损**。
- C5 + 两条 Search-only lane：共享 store，**每 lane 30～60 分钟**；外部 reranker 429/排队时请求串行、分析并行。
- 汇合与一次真实组合确认：**45～75 分钟**。
- 任何新 Add arm：按 **60～90 分钟/候选** 估算；prompt 候选还需代码审查/重建，默认不进入。

这些时间盒来自当前机器真实 smoke 与固定 250/126 请求数，不是经验拍值。每轮结束后应用实际：

```text
T_remaining = chunks_remaining * measured_Add_P95
            + queries_remaining * measured_Search_P95
            + fixed_restart_and_analysis_buffer
```

若预测超出冻结点，减少候选数量或停止该项；不缩短历史、不删困难题、不提高未经验证的并发。

## 8. T00 结果包

仓库内只保存无正文、无 query、无 gold、无 key 的摘要与配置指纹；含原始评测内容的文件继续放到源码树之外的 0700 目录。

建议结果包：

```text
private-run-dir/
  run_manifest.json
  request_metrics.jsonl
  search_results.jsonl
  retrieval_trace.jsonl
  error_labels.jsonl
  summary.json
  decision.md
```

`summary.json` 至少包含：

- 五层 macro score 与 126 题 micro score；
- 每层正负样本数和最差层；
- Add/Search success、P50/P95/max；
- 旧值率、Forget 泄漏、过遗忘、重复率、空结果率；
- timestamp 传递率；若当前链路实际进行了正规化，再报告正规化覆盖率；同时报告时间锚点错误和 answer-like evidence 比例；
- rerank 前后 MRR/nDCG/Recall；
- score 分位数与候选 breakpoint 数；
- API 错误计数、调用次数/token；
- 下一步推荐和明确 stop reason。

## 9. 审批边界记录

已批准的方法学：

- M1：实际 score breakpoint + 分组 bootstrap 下置信界选阈值。
- M2：`exact+T05` 与 `sim+T05` 分别估计 `tau_exact` / `tau_sim`。
- M3：汇合后只在线确认一次 `tau_sim+sim+T05`，并测固定阈值交互。

未批准且本方案不实施：

- 修改 T02 内部 `0.92`；
- MMR 或其参数；
- 自动 prompt 搜索；
- T07 BM25/fulltext/VEC-CoT；
- 因本文件而自动启动 Docker、调用模型或写入最终 release 配置。

建议的下一条独立审批口令：

```text
批准 T00-5S：由当前主 session 只在冻结五样本上运行 C0，不交给调优 agent；可复用已验证
镜像但必须绑定唯一 runtime revision/image/config/store；产出九类观测、逐层质量、错误分桶和
时间模型后停止回传。不启动 C5、双 lane、Add 候选或 T90。
```

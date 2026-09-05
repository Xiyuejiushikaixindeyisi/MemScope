# MemScope 调优交互与参数建模分析

> 状态：本 session 只产出方案；M1/M2/M3 方法学已批准；不因此自动授权运行实验或测试  
> 日期：2026-09-05  
> 范围：T01～T06；T07 已拒绝；T02 内部 `0.92`、MMR 和自动 prompt 搜索不批准  
> T00 数据与可观测性规范：[T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md](T00_BASELINE_OBSERVABILITY_AND_FIVE_SAMPLE_PLAN.md)

主办方关于时间证据、Add 总结和内网凭证的规则边界与技术核验见：[ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md](ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md)。

## 1. 直接结论

不是所有方案都存在“A 变化后 B 必须改变”的硬依赖，但存在大量 **重新验证/重新校准依赖**：

1. **T05 → T01 是最强参数依赖。** 外部 reranker 改变 `metadata.relativity` 的分数尺度；只要 T01 使用非零阈值，就必须在所选 reranker 上重新校准，不能沿用 cosine 阈值。
2. **T02 ↔ T05 是强流水线交互。** `dedup=sim/mmr` 会先把内部 top-k 扩大三倍，再进入底层 reranker，因此改变 reranker 的候选数、请求负载、得分分布和延迟。
3. **T01 ↔ T02 是强选择交互。** relativity 先过滤，sim/MMR 后去重；并且 T02 改变了进入召回/rerank 的 top-k。`exact` 下的最优阈值不保证适合 `sim`。
4. **T03/T04/T06 → T01/T02/T05 是数据分布依赖。** Add 侧改变记忆文本、数量、分片和 embedding；Search 配置不一定必须换值，但所有结论必须在新存储上复验。
5. **T03 ↔ T04 是 token/抽取交互。** T03 不改变窗口数量，但减少每个窗口的 prompt 固定开销；T04 改变窗口数和每次 LLM 输入内容。两者的最优点可能联动。
6. **T03 → T06 是决策依赖。** 按当前止损策略，只有 T03 无效且系统性抽取错误仍显著时才进入 T06；这不是代码硬依赖，而是避免重复改 prompt 和无法归因。
7. **若另行批准时间正规化/总结候选 → 全部 Search 参数是数据分布依赖。** 主办方只确认该做法允许；一旦候选改变 memory 文本、时间或状态表达，T01/T02/T05 必须在新 store 上重校准。该候选不是当前 Search 路线的前置。

因此正确表达不是“改 A 就一定要改 B”，而是：

- baseline 值可以保持不变；
- 但某些已选出的非默认参数会因另一项变化而失去可迁移性；
- 最终候选必须把强交互项作为组合重新验证。

## 2. 当前真实执行顺序

根据固定 MemOS 代码，Search 主路径可简化为：

```text
T03 / T04 / T06
  -> 决定写入的 memory 文本、数量、分片、embedding
  -> 初始召回 top-k
     （T02=sim/mmr 时先把内部 top-k 放大为 3 倍）
  -> T05 在各 retrieval path 内 rerank
  -> reranker score 写入 metadata.relativity
  -> T01 relativity 阈值过滤
  -> T02 sim/MMR 后处理去重
  -> 排序、状态/来源/用户过滤、exact dedup、公共 top-k 截断
```

代码依据：

- memory-api 将 relativity/dedup/rerank 作为同一请求的参数发送：[memos.py](src/memscope/memory_gateway/memos.py)。
- `sim/mmr` 先触发三倍 top-k，随后执行 threshold、dedup 和最终处理：[search_handler.py](.vendor-src/MemOS/src/memos/api/handlers/search_handler.py)。
- T05 实际在底层 `_maybe_rerank()` 执行，分数在 `_sort_and_trim()` 写入 relativity：[searcher.py](.vendor-src/MemOS/src/memos/memories/textual/tree_text_memory/retrieve/searcher.py)。
- T04 决定窗口，fine 模式按窗口串行调用 LLM；T03 只从每个窗口的 prompt 删除 example：[simple_struct.py](.vendor-src/MemOS/src/memos/mem_reader/simple_struct.py)。

注意：`search_handler.py` 最后调用的 `rerank_knowledge_mem()` 当前没有再次调用传入的 reranker，只按已有 relativity 排序；T05 的真实作用点是更早的 Searcher，而不是最终 formatter。

## 3. T01～T06 交互矩阵

标记：

- **M**：机械流水线交互，组合会直接改变候选或分数。
- **R**：无需自动改另一个值，但必须重新校准/复验。
- **D**：决策依赖，后项只在前项结果满足条件时进入。
- **弱**：可以独立选择，仍需最终回归。

| A \ B | T01 阈值 | T02 去重 | T03 去 example | T04 window | T05 reranker | T06 prompt patch |
|---|---|---|---|---|---|---|
| T01 阈值 | — | **M：顺序与 3×候选池** | **R：分数分布变** | **R：分数分布变** | **M：score 尺度变** | **R：分数分布变** |
| T02 去重 | **M** | — | **R：重复率变** | **R：分片/重复率变** | **M：候选数和幸存项变** | **R：重复率变** |
| T03 去 example | **R** | **R** | — | **M/R：有效 token 预算联动** | **R：文本分布变** | **D/M：同属 prompt 语义** |
| T04 window | **R** | **R** | **M/R** | — | **R：文本粒度变** | **R：prompt 与窗口共同影响抽取** |
| T05 reranker | **M** | **M** | **R** | **R** | — | **R：输入文本分布变** |
| T06 prompt patch | **R** | **R** | **D/M** | **R** | **R** | — |

### 3.1 真正需要“随 A 重选 B”的场景

| A 的变化 | B 的处理 |
|---|---|
| local cosine → external BGE（T05） | 重新拟合 T01；阈值 0 可以保留作控制，但旧的非零阈值作废 |
| exact → sim（T02） | 在 `sim+T05` 分支重新估计 T01；同时重新测 T05 请求规模和 Search 延迟 |
| T03/T04/T06 任一获胜 | 使用最终 Add 存储重新验证 T01/T02/T05；不允许复用旧存储上的最终结论 |
| T03 与 T04 希望同时启用 | 增加组合 cell；不能把两个单项收益相加。24 小时内默认不组合 |
| T06 修改了 example 或 prompt 固定长度 | 明确 T03 的开关语义，并重新检查 T04 的 token/延迟边界 |

## 4. 可以数学化的参数

| 项目 | 参数类型 | 数学化可行性 | 适合的方法 | 24 小时建议 |
|---|---|---:|---|---|
| T01 relativity | 连续阈值 `[0,1]` | **高** | score breakpoint 枚举、概率校准、约束优化 | **立即采用** |
| T02 exact/sim | 离散类别 | 中 | 配对 A/B、2×2 factorial、交互效应 | 采用；不要伪装成连续优化 |
| T02 内部相似阈值 | 固定为 `0.92`，当前非运行时参数 | 低 | 若改代码可做阈值 sweep | 24 小时内不改 |
| T04 window tokens | 整数，但效果在分片边界处跳变 | **中高** | token breakpoint、窗口数/延迟模型、约束搜索 | 有 Add 错误时采用 2～3 点 |
| T03 remove example | 二元变量 | 中 | 配对 bootstrap、McNemar/符号检验 | **最低优先级**；不拟合复杂曲线，另行审批 |
| T05 reranker backend/model | 离散类别；输出连续 score | **高** | 排序指标 + score calibration + 成本约束 | 与 T01 联合建模 |
| T06 prompt 版本 | 离散高维文本变量 | 低/中 | 成熟实践导出的单规则人工 patch、分层错误率模型 | **最低优先级**；不做自动 prompt 搜索，另行审批 |

## 5. T01：不要盲扫阈值，枚举 score breakpoint

对于固定 query 和候选分数，阈值改变结果的时刻只发生在某个实际 score 上，因此无需测试等间隔的几十个阈值。

收集 dev 集上每个候选的：

```text
(query_id, user/session group, memory_id, reranker backend,
 dedup mode, score, rank, relevant/useful label, end-to-end result)
```

候选阈值集合取所有唯一 score 的中点或稳定分位点：

```text
T = {0} ∪ {(s[i] + s[i+1]) / 2}
```

然后对每个阈值离线重算 Precision@K、Recall@K、F-beta、MRR/nDCG、空结果率；若能离线调用同一 Answer/Judge，再以端到端分数为主。

推荐使用硬约束而不是随意给延迟加权：

```text
tau* = argmax_tau  LCB95(Q(tau))

subject to:
  failure_count = 0
  cross_user_or_stale_leak = 0
  empty_rate <= 预先批准的上限
  Search_P95 < 50s
  Search_max < 55s
```

`LCB95` 是按 user/session 分组 bootstrap 得到的质量提升 95% 下置信界。比赛临近时，选择下置信界更高且位于宽平台中部的阈值，比选择样本均值最高的尖峰更稳健。

### 5.1 score 概率校准

若 dev 标注量足够，可拟合：

```text
p(relevant | score) = isotonic(score)
```

或使用 Platt logistic calibration。然后按漏召回和误召回的成本选择概率阈值。数据少时优先 isotonic/直接 breakpoint sweep，不上高维模型。

重要限制：BGE score 是 query/data dependent，校准必须按最终 T05 model、最终 Add 存储和 dedup arm 分别进行；不能从公开经验直接搬一个 `0.3/0.5`。

## 6. T01、T02、T05：最小 factorial 与交互项

令质量函数为：

```text
Q(tau, d, r)

tau = relativity threshold
d   = exact / sim
r   = local / external reranker
```

在 external reranker 固定时，最小四格为：

| Cell | 配置 |
|---|---|
| C5 | `Q(0, exact, external)` |
| A | `Q(tau_exact, exact, external)` |
| B | `Q(0, sim, external)` |
| J | `Q(tau_exact, sim, external)` |

固定同一 `tau_exact` 时，T01×T02 交互量为：

```text
I_12 = Q(tau_exact, sim, external)
       - Q(tau_exact, exact, external)
       - Q(0, sim, external)
       + Q(0, exact, external)
```

- `I_12 ≈ 0`：两个收益近似可加。
- `I_12 < 0`：阈值和去重相互伤害。
- `I_12 > 0`：组合存在协同。

但最终不应直接沿用 `tau_exact`。应在 B 分支的 `sim+external` score 上再做 breakpoint sweep，得到 `tau_sim`，然后只在线确认一次：

```text
J* = Q(tau_sim, sim, external)
```

当前双 Session 的五个主要 cell 可以估计：

```text
T05 主效应（baseline 点） = C5 - C0
T01 | T05                 = A - C5
T02 | T05                 = B - C5
联合最优                  = J* - C5
```

它不能完整估计 T05 与 T01/T02 的所有交互；完整 `2×2×2` 需要八个 cell，24 小时内性价比不足。如果 T05 最终不可用，只补跑 local cosine 下最有希望的一个 fallback cell。

## 7. T04：利用精确分片边界建模

T04 不是平滑参数。窗口只会在累计消息 token 超过 `W` 时改变，因此应先用当前 `_iter_chat_windows()` 对 dev 会话离线计算所有分片断点，再从断点附近选择候选，而不是试 `512/768/1024/1536/...` 的任意网格。

对每个窗口上限 `W`，可无模型调用地得到：

```text
n_windows(j, W)    # 第 j 个 Add 的窗口数
tokens(j, W)       # 每个窗口的输入 token
boundary_risk(j,W) # 指代/事实是否跨窗口
```

fine 模式按窗口串行调用 LLM，因此可拟合简单延迟模型：

```text
T_add(j, W) ≈ a × n_windows(j,W)
            + b × sum_input_tokens(j,W)
            + c × extracted_memory_count(j,W)
```

用 T00 实测拟合 `a/b/c`，再选择 2～3 个同时满足预测 deadline、覆盖不同分片断点的 W 做真实 Add。最终目标仍是质量最大化，并约束 Add P95<105 秒、max<115 秒。

T03 删除 example 不改变 `_iter_chat_windows()` 的窗口数，但会减少每次 LLM 请求的固定 prompt token；因此它可能改变延迟模型中的截距 `a` 和可用上下文余量，而不是机械改变 W。

## 8. T03/T06：二元或小矩阵统计，不做高维自动搜索

T03 是二元配置，最适合在相同样本上做 paired comparison：

- 每个样本记录正向翻转、负向翻转、不变。
- 二元正确/错误可用 McNemar exact test；连续质量分使用按 user/session 分组 bootstrap。
- 同时比较 extraction precision/recall、JSON 成功率、Add token 和延迟。

T06 的自然语言 prompt 空间过大、样本又小，自动 prompt optimization 很容易过拟合。本轮不做自动搜索；若后续另行批准，只允许从 LangMem、Mem0 等成熟实现提炼一个可解释的语义规则，一次只改一处，并用错误簇的分层效果判断。prompt 调优排在所有已批准 Search 方法之后。

## 9. 对双 Session 方案的修正

原双 Session 结构保留，但结果处理应调整为：

### Session A：exact + T05

1. 先以 relativity=0 收集 external reranker score。
2. 离线 breakpoint sweep 得到 `tau_exact`。
3. 只在线确认 1～2 个阈值。

### Session B：sim + T05

1. 以 relativity=0 运行 sim，收集三倍候选路径后的 score 和结果。
2. 对该 arm 单独离线估计 `tau_sim`；不默认复用 Session A 的阈值。
3. Session B 仍以 T02+T05 为主，不在并行阶段增加大量在线阈值请求。

### 汇合 Session

1. 比较 C0、C5、A、B。
2. 使用 `tau_exact` 计算固定阈值的 T01×T02 交互。
3. 在线确认一次 `J*=tau_sim+sim+T05`。
4. 单栈复跑最终候选质量和延迟。

这会把大部分 T01 选参从昂贵的在线多次请求变成离线、可复现的阈值计算，同时保留一次真实联合确认。

## 10. 建模的防过拟合规则

1. 当前按用户批准的五个完整 conversation sample 调优，不能把同一对话的 query 拆成伪独立 tuning/holdout。
2. 五样本同时用于筛选和确认，必须明确标记“非独立 holdout”；若后来审批更大集合，再按 sample 分组做一次冻结验证。
3. 非确定性 Add 候选至少两套独立 store；Search-only 候选在同一冻结 store 上重复两轮。报告 paired delta 和宽置信区间，不只报平均值。
4. 优先简单模型：breakpoint sweep、2×2 factorial、分片边界和线性延迟模型。只有五个 cluster 时不做高维 Bayesian optimization，isotonic 也只作辅助诊断。
5. 任何参数只有在五层关键指标净正、硬 deadline/错误条件通过、评测机 endpoint 可用时才进入 release；不能声称五样本能预测官方分数。
6. 正文、query、memory 和 key 只保存在私密评测目录；仓库仅保存脱敏统计和配置指纹。

## 11. 审批记录

用户已批准以下方法学修订；不等于批准执行模型调用：

```text
M1 已批准：T01 改为基于实际 reranker score 的 breakpoint sweep，并用分组 bootstrap 下置信界选阈值；
M2 已批准：Session A 估计 tau_exact，Session B 在 sim+T05 arm 独立估计 tau_sim；
M3 已批准：汇合后只在线确认一次 tau_sim+sim+T05，并测固定阈值交互项；
未批准：修改 T02 内部 0.92、MMR 或其参数、自动 prompt 搜索。
```

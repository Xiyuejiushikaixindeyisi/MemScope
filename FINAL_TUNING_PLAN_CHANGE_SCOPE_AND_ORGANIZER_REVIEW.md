# 最终调优方案：改动边界与主办方澄清复核

> 状态：供审批；本 session 只产出方案，不运行测试、Docker、模型或评测  
> 日期：2026-09-05  
> 关联：[24H_TUNING_APPROVAL_PLAN.md](24H_TUNING_APPROVAL_PLAN.md) · [主办方澄清复核](ORGANIZER_CLARIFICATIONS_AND_TUNING_IMPACT.md)

## 1. 直接结论

**当前推荐的最终默认路线不要求修改 MemScope/Python 算法代码。**

```text
T00/C0
→ C5（T05 reranker 对照）
→ 双 session：T01+T05 / T02+T05
→ M3 单 session 汇合确认
→ 单栈复验
→ T90 冻结交付
```

其中 T01、T02、T03、T04、T05 都已有运行时配置 seam；当前获批主线只用 T01、T02、T05。实验阶段通过 env/Compose override 切换，不需要改源码，也不应在两个 session 中并行写仓库。

但需要区分三种“修改”：

1. **算法/应用代码：默认 0 项。** T06 是代码 prompt patch，仍未批准且最低优先级；新的确定性时间正规化器也未批准，不进入默认路线。
2. **最终配置：可能有 1 次小改。** 若候选获胜，为使制品可复现，应把最终参数固定到 release 配置/模板或由明确的 organizer env 注入。这是配置提交，不是检索或记忆算法改造。
3. **调优辅助工具：可选。** 精确选择冻结五样本、计算 M1/M2 breakpoint/bootstrap 可以使用仓库外临时目录和一次性分析，不必修改 release 代码；若希望长期复用，再单独审批 harness 脚本改动。

因此，对“是否涉及代码修改”的准确回答是：**主线路径不改算法代码；获胜后可能改受版本控制的 release 配置；只有 T06、主动时间正规化或 reranker 批处理等升级路线才改应用代码，而它们都不在当前授权范围。**

## 2. 逐项变更矩阵

| 项目 | 当前审批边界 | 应用代码 | 配置文件 | 存储重灌 | 说明 |
|---|---|---:|---:|---:|---|
| T00 | 只建立基线和诊断 | 否 | 否 | baseline 干净库 | 不为 T00 自动增加 runtime instrumentation；不可见字段标 `not_observable` |
| M1 | 已批准，按 score breakpoint 选阈值 | 否 | 否 | 否 | 可离线计算；不盲扫固定网格 |
| M2 | 已批准，分别估计 exact/sim arm | 否 | 否 | 否 | 使用已有搜索结果作数学选参 |
| M3 | 已批准，只做一次联合在线确认 | 否 | 否 | 否 | 不是新功能开发 |
| T01 | 与 T05 联合 | 否 | 仅 env | 否 | 已有 `MEMOS_SEARCH_RELATIVITY` |
| T02 | 与 T05 联合；内部 0.92 锁定；无 MMR | 否 | 仅 env | 否 | 已有 `MEMOS_SEARCH_DEDUP` |
| T05 | 双 lane 共同使用，需内网 gate | 否 | 仅 env/凭证注入 | 否 | 适配器已存在；已有 `MOS_RERANKER_BACKEND` |
| T04 | 仅在错误证据明确后另审 | 否 | 仅 env | 是 | 已有 `MEM_READER_CHAT_WINDOW_MAX_TOKENS` |
| T03 | prompt 路线最低优先级、另审 | 否 | 仅 env | 是 | 已有 `MEM_READER_REMOVE_PROMPT_EXAMPLE` |
| T06 | 未批准 | **是** | 可能 | 是 | 单一人工 prompt/规则补丁；不做自动搜索 |
| 确定性相对时间正规化 | 未批准、不是主线前置 | **大概率是** | 可能 | 是 | 当前只确认 timestamp 已传到 MemOS，未确认有可控的确定性正规化层 |
| `sim+T05` 300-document 分批 | 不做 | **是** | 可能 | 否 | 若目标 endpoint 容量不过，当前方案取消该 lane，不临时写 batching |
| T90 | 最终冻结交付 | 通常否 | **可能一次** | 否 | 固定获胜配置、生成现有 ASCII 制品并验证；不另造打包格式 |

## 3. 现有代码为何足以支撑默认路线

- `src/memscope/memory_gateway/memos.py` 已把输入消息的 `timestamp_ms` 转为 UTC ISO `chat_time` 传给 MemOS。主办方澄清并不自动产生“补一个 timestamp 传输功能”的代码任务。
- `compose.yaml` 与 `compose.release.yaml` 已暴露 T01/T02/T03/T04/T05 所需的环境变量。
- `scripts/build_candidate_delivery.py` 已生成 `solution-<12hex>.zip` 和 `memscope-images-<12hex>-linux-amd64.tar`，现有名称已经满足 ASCII 要求。
- `INSTRUCTION.md` 已使用 ASCII 的 `solution/`、`$HOME/memscope-organizer/<candidate>/` 等部署路径。

五样本精确选择有一个工具层限制：当前 `local_proxy_eval.py` 只有 `--max-samples`，没有 `--sample-manifest`。默认无代码方案是在仓库外建立只包含五个选定 JSON 的临时 `eval-root/official/samples/`，由现有 `--eval-root` 运行；不要用 `--max-samples 5` 冒充分层选择。若要把 manifest selector 产品化，再单独审批 harness-only 修改，它不会进入 release 服务。

## 4. 为什么曾把主办方澄清写成硬约束，以及哪里需要纠正

此前的理由有两部分：

1. 主办方对违规边界和交付格式有最终解释权；违反后可能直接导致无效提交或评测机无法启动，收益再高也没有意义。
2. 其时间问题回复消除了一个关键合规歧义：Search evidence 可以含由 Add 输入推导的日期，不等于 Search 在直接答题。

这两个理由只能支持“规则/允许边界是硬约束”，**不能**推出“主办方建议的技术实现是硬约束”。上一版把下面两句话写进硬约束是分类错误：

- “Add 应在写入时主动正规化所有相对时间”；
- “Add 总结/结构化是应采用的最优路线”。

现已改为：

- Search evidence-only、不得抄 gold、不得提交凭证、ASCII 外层命名：**硬 gate**；
- 可以返回正规化日期、可以总结：**许可范围**；
- 是否提前正规化、如何总结、采用哪种 schema：**技术假设，必须对照验证**。

## 5. 独立 check 后的判断

### 时间

LoCoMo 官方数据确实把 session timestamp 作为正式输入字段，论文也用 temporal event graph；Graphiti 等公开实现会以 episode reference time 解析相对表达并区分有效时间。因此“时间锚点必须进入记忆链路”有较强依据。

但以下三种做法都合规，公开资料不能替代本赛题对照来宣判唯一最优者：

```text
A. 原始事实 + 原始相对表达 + session timestamp
B. A + 派生的绝对日期/时间区间
C. 只保存压缩后的正规化 summary
```

当前建议以 A/当前实现为 baseline；B 只在 temporal 错误成为主要失败簇且另行批准后测试；C 风险最高，因为可能丢失原文不确定性和 provenance。

### 总结/结构化

“允许总结”不等于“总结必然增益”。MemOps 重点测 stale value、selective forgetting、unsupported reflection 和 exact provenance，恰好都是有损 summary 容易破坏的维度。任何 summary 候选都应同时检查数字、否定、主体、时间、状态链和来源，不能只看压缩率或 proxy Answer。

### 凭证与内网模型

“预留可配置文件”只证明不能硬编码凭证；它没有承诺课题组会为任意 reranker 提供 model ID、协议或额度。因此 T05 的 release gate 必须是目标内网 endpoint/model/credential 均已确认。未确认就回退现有 `cosine_local`，不能根据主办方一句通用回复假设评测机会替团队补齐依赖。

### 隐藏 Answer

主办方的回复没有消除 Answer 输入结构和行为未公开带来的 proxy gap。调优时应同时看 evidence recall、状态/时间正确性、排序指标和 proxy Answer；任何只提高 judge 分数、却让 evidence 更像直接答案或降低 provenance 的候选都不接受。

## 6. 最终审批边界

建议将当前审批文字固定为：

```text
批准默认无算法代码路线：T00、C5、T01+T05、T02+T05、M1/M2/M3、单栈复验；
T02 内部 0.92 锁定，不含 MMR；不做自动 prompt 搜索；
允许获胜后只修改必要的 release 配置并冻结制品；
不批准 T06、确定性时间正规化、reranker batching 或 harness 产品化改动；
主办方回复仅将合规/提交要求作为硬 gate，技术建议须经数据验证。
```

若后续单独批准 B 类时间候选，它将成为 Add 侧实验：必须新 store 重灌，并使 T01/T02/T05 的旧参数结论失效；不能直接合入当前 Search 主线。

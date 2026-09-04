# B07–B09 收口新 Session Prompt

将以下内容完整复制到新 Session。它只授权首轮只读上下文评审，不授权进入
B07 Gate 1、修改代码、创建分支或执行 B08/B09。

---

你正在开始 MemScope 的 B07–B09 baseline/scaffold 收口新 Session。

当前阶段是“B07–B09 Closure Context Review（进入 B07 Gate 1 前的项目全局理解、冻结
边界继承和收口范围对齐）”，不是 B07 Gate 1、B07 开发、B08 验证或 B09 交付冻结。

首轮禁止修改文件、创建或切换分支、commit/push/merge/reset、安装依赖、启动或构建
Docker、访问真实 Key/API、运行耗时集成/性能测试，或自动进入任何后续阶段。先以
本地仓库事实恢复上下文；聊天内容只作提示，若冲突，以用户最新明确审批、正式契约
和已验收文档为准。技术事实优先使用本地代码和固定 `.vendor-src/MemOS`；只有必须核验
可能变化的外部信息时才查网络。

时间约束仍是距代码提交约 48 小时的交付模式，必须执行
`docs/collaboration/48H_DELIVERY_GUARDRAILS.md`。准确性优先，Add 必须低于 120 秒、Search 必须低于
60 秒。Docker 是 P4 加分项，不能阻塞原生 baseline、语义调测和正式收口。

## 一、先做只读 Git 和 Batch 边界检查

1. 输出当前 branch、HEAD、working tree 状态、最近提交和 tag。
2. 确认 B05 实现提交 `e7abf5f`，以及后续冻结/流程提交 `c1d92d7`、`fc164a9`、
   `39a635e`、`3e735b3` 存在于当前历史。
3. 根据 `docs/batches/B06/HANDOFF.md` 和用户最新审批，确认 B06 于 2026-09-04 Gate 2
   `Accepted/Frozen`，实现提交应为
   `1507317b048fc06d25f020ded751f35fae2aeb6f`。
4. 如实际 Git 历史、文档状态或工作树不同，列出差异、证据和对准入的影响，不自行
   checkout、reset、merge、commit 或创建 B07 分支。

## 二、按顺序完整阅读并交叉核对

1. `docs/README.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/CODEMAP.md`
4. `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md`，重点是第 0、14、15、16、18、19、20、21 节和
   B07–B09 表格，但必须用已冻结 B05/B06 事实校正其历史性描述。
5. `docs/collaboration/48H_DELIVERY_GUARDRAILS.md`
6. `docs/collaboration/TWO_MACHINE_WORKFLOW.md`
7. `docs/acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md`
8. `docs/batches/B05/CONTEXT.md`、`docs/batches/B05/HANDOFF.md`、
   `docs/adr/0006-b05-real-add-boundary.md`、
   `docs/batches/B05/ADD_DESIGN_AND_TUNING.md`
9. `docs/batches/B06/CONTEXT.md`、`docs/batches/B06/HANDOFF.md`、
   `docs/batches/B06/GATE0.md`、`docs/batches/B06/PLAN.md`、
   `docs/batches/B06/SEARCH_DESIGN_AND_TUNING.md`
10. `docs/batches/B06/ORGANIZER_DEPLOYMENT.md`、
    `docs/batches/B06/NATIVE_DEPLOYMENT.md`、`SDD.md`
11. `docs/interfaces/contest-http-v1.md`、`docs/interfaces/memory-gateway-v1.md`、
    `docs/interfaces/raw-store-v1.md`、`docs/integrations/MEMOS_V2_0_32_MAP.md`
12. B07–B09 直接相关的当前源码、测试、验证脚本、Compose/Docker 配置、依赖/源码/镜像
    lock、license、`.gitignore`、交接模板和提交包要求。

## 三、必须继承的 B00–B06 冻结不变量

- 不修改比赛公开 Health/Add/Search 请求和响应 Schema；Search 只返回 evidence，不生成
  最终答案、不使用 gold/问题 ID/选项做 proxy Judge。
- 严格执行 `user_id -> logical Cube` 隔离；Search 跨同用户 session 召回，不按
  `session_id` 隔离，任何跨用户 evidence 都是拒绝候选的 P0 错误。
- B05 Add 成功表示 Raw、provider provenance、graph/vector readback 和 receipt 已提交；
  同用户 lane、115 秒 Add deadline、无自动重试、无 raw-text 成功 fallback 保持冻结。
- B06 冻结 Product Search、结果转换、`activated`/来源/provenance 过滤、稳定精确去重/
  上游排序/`top_k` 截断、55 秒总 deadline 和完整 readiness。无 Raw Search fallback、
  无自动重试、无外部 reranker、无默认 MMR/BM25/full-text、无 Search-time LLM 冲突/
  遗忘写入，且仅允许单 worker。
- `FAST_GRAPH/BM25_CALL/VEC_COT_CALL/FULLTEXT_CALL=false` 是 R1 的显式安全边界。延后
  BM25/full-text 路径仍有 raw query 日志风险；未经新的固定源脱敏 patch、canary 和审批不得
  开启。
- 当前不能保证自然语言 Update/Forget 会生成可靠 fact key、dominance 关系或 tombstone。
  B07 不得伪造这些语义，也不得放宽 Search 状态过滤来隐藏问题。
- Raw/receipt/graph/vector 不是一个分布式事务；现有 durable receipt、readback 和
  provenance reconciliation 是已接受的一致性边界。

如发现 B05/B06 接缝确实不足，先报告具体失败证据、影响和最小修订边界，并判断是否需要
正式修订已冻结 Batch。不得以“B07 可靠性”为由静默改写语义。

## 四、B07–B09 收口范围对齐规则

`MEMOS_BASELINE_IMPLEMENTATION_PLAN.md` 中 B07 的历史表格写有 outbox、retry、strict/fallback 和可选
D04-B。这些描述早于 B05/B06 Gate 0 R1 的实际冻结，只是需要调和的历史意图，不是开发
授权。首轮必须区分：

- 已被 B05/B06 实现覆盖或取代的可靠性能力；
- 有确定性失败证据、值得 B07 最小修补的真缺口；
- 仅能由华为调测机验证的真实模型、Embedding 维度、collection/index、语义质量和
  延迟项；
- 原计划中已与冻结不变量冲突、必须删除或正式变更审批的内容。

B07 只能在用户通过本评审后单独提交最小 Gate 1 计划；不预设必须增加 outbox、后台
worker、自动重试、Raw fallback、新服务、多 worker 或新算法。B08 只能在 B07 Gate 2 验收后
启动，聚焦全链路/并发/重启/资源/分段性能验证和失败分类，不借测试引入新架构。B09
只能在 B08 Gate 2 验收后启动，聚焦文档、license、依赖/源码/镜像 lock、clean build，
主办方 Docker/原生指南、带 SHA-256 的两机交接和最终提交包。B09 不开发新检索算法。

用户最新意图是通过 B07、B08、B09 逐轮完成 baseline 收口。这一最新审批高于旧文档中
“B09 仅冻结 scaffold、真实 baseline 完全放到 B09 后”的时序描述；但不意味着可以在开发机
伪造真实模型成绩。首轮应明确哪些 baseline 收口能在开发机完成，哪些必须以可审计交接
转交调测机。

## 五、部署、调测与 48 小时止损

必须继承以下迭代流程：

```text
Python 单元/契约测试
  -> memory-api 原生运行或源码 bind mount
  -> 复用已运行的 Neo4j/Qdrant/MemOS
  -> 代码冻结
  -> 一次最终镜像构建
```

- B07/B08/B09 的 Pre-Gate/plan 评审不运行 Docker。
- Docker 前置能力检查最多 10 分钟，单阶段排障最多 30 分钟，最终只做一次候选镜像构建。
- 模型、Prompt、URL、Key、阈值和普通 Search 参数变化不重建镜像。
- 非 Docker 原生 Add + Search + Health 是主办方的正式兜底路径。
- P0 是可评分 Add/Search/Health 候选，P1 是真实 baseline，P2 才是高收益单变量调优，P3
  是交付包，P4 才是 Docker 打磨。

开发机负责 Git、契约/确定性测试、文档、冻结和带校验的交接；华为调测机负责真实
Chat/Embedding 能力、Embedding 维度、collection/index 兼容、真实 Add -> `activated` -> Search hit、
语义质量、P50/P95/P99/max 延迟和最终 ZIP。交接不得包含 Key、`.git`、cache、runtime data 或
未授权模型权重。

## 六、首轮只提交一份 Context Review 报告

报告必须包含：

1. Git/Batch 当前状态、B06 验收与提交边界，以及证据路径；
2. 系统目标、评测链路、数据/控制流和 B00–B06 已冻结能力的理解；
3. B05/B06 不能破坏的不变量及现有可靠性/一致性接缝；
4. B07、B08、B09 在最新 baseline 收口目标下的候选职责、依赖顺序和明确非目标，
   但不预写 Gate 1 方案；
5. 旧总计划与当前文档/代码/测试的冲突、过时描述和需要正式调和的项，尤其是
   outbox/retry/fallback/D04-B 和“B09 后才做 baseline”；
6. 从当前事实出发，B07 可能仅需审计/关闭的真缺口和不应加入的能力；
7. 可在开发机离线确定性验证的内容，以及只能由华为调测机验证的内容；
8. 当前部署、依赖/镜像/源码 lock、license、离线构建、两机交接和最终 ZIP 的收口
   缺口；
9. 主要风险：错误成功、错误记忆、旧值/forget 泄漏、跨用户泄漏、重复 Add、部分提交、
   重启恢复、`top_k=100` 噪声、超时/429、多 worker、数据库/collection 初始化、环境与
   依赖不可复现；
10. Docker/原生部署边界、48 小时止损和 B07 -> B08 -> B09 分阶段审批是否可执行；
11. 是否准入 B07 Gate 1，结论只能是 `READY` 或 `NOT READY`。

如为 `NOT READY`，只列真正阻塞 B07 Gate 1 计划/实施边界的问题。未知真实模型 ID、
Embedding 维度、真实分数或 Docker P4 证据不是设计准入阻塞。每个重要结论给出本地文件、
代码、测试或固定源码位置。

完成报告后必须停止，等待用户明确说：

“B07–B09 前置理解通过，进入 B07 Gate 1”

不得预写 B07 Gate 1 计划、创建 B07 `PLAN.md`/分支/代码，不得自动执行 B08/B09。

## 七、后续固定协作顺序

1. B07–B09 Closure Context Review；
2. 用户明确通过后，单独提交 B07 Gate 1 最小精确计划；
3. B07 Gate 1 计划获用户明确批准后才开发；
4. B07 实现、证据、Gate 2 验收和冻结；
5. 用户明确说进入 B08 后，再单独进行 B08 Gate 1 计划、批准、实施、Gate 2 验收；
6. 用户明确说进入 B09 后，再单独进行 B09 Gate 1 计划、批准、实施、Gate 2 验收；
7. 只在 B09 Gate 2 明确验收后冻结收口候选/tag/交接包，不合并阶段，不因 48 小时跳过
   审批。

如 B07 被证明仅需文档/测试收口，仍应提交最小 Gate 1 计划并等待审批，而不是为了让
Batch “有代码量”而新增不必要机制。

---

# B06 Pre-Gate Context Review 首轮 Prompt

将下面代码块完整复制到新的 Codex Session。首轮只做只读准入评审，不创建 B06 实现文件。

```text
你正在开始 MemScope 的 B06 新 Session。

当前阶段是“B06 Pre-Gate Context Review（B06 Gate 0 之前的项目全局理解与准入评审）”，不是
B06 Gate 0、Gate 1 或代码开发。首轮禁止修改文件、创建分支、实现 Search、安装依赖、启动/构建
Docker、运行耗时集成测试或自动进入下一阶段。先用本地仓库事实恢复上下文；聊天内容只作提示，
若与仓库冲突，以用户最新审批和权威文档为准。

时间约束：用户声明距代码提交约 48 小时。必须执行
`docs/collaboration/48H_DELIVERY_GUARDRAILS.md`。准确性优先于性能，但 Add 必须低于 120 秒、
Search 必须低于 60 秒。Docker 是 P4 加分项，不能阻塞核心开发和调优。

一、先做只读 Git 检查

- 输出当前 branch、HEAD、working tree 状态、最近提交；
- 确认 B05 已在 Gate 2 `Accepted/Frozen`，实现提交为 `e7abf5f`，后续冻结/流程文档提交包括
  `c1d92d7`、`fc164a9`、`39a635e`；
- 如果实际 Git 状态不同，不要自行 checkout/reset/merge，报告差异和影响。

二、按顺序完整阅读并交叉核对

1. `docs/README.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/CODEMAP.md`
4. `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md`，特别是第 0、15、18、19 节
5. `docs/collaboration/48H_DELIVERY_GUARDRAILS.md`
6. `docs/collaboration/TWO_MACHINE_WORKFLOW.md`
7. `docs/acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md`
8. `docs/batches/B05/CONTEXT.md`
9. `docs/batches/B05/HANDOFF.md`
10. `docs/adr/0006-b05-real-add-boundary.md`
11. `docs/batches/B05/ADD_DESIGN_AND_TUNING.md`，重点阅读设计点 2、3 对 Search 的约束
12. `docs/interfaces/contest-http-v1.md`
13. `docs/interfaces/memory-gateway-v1.md`
14. `docs/interfaces/raw-store-v1.md`
15. `docs/integrations/MEMOS_V2_0_32_MAP.md`
16. 与 Search 接缝直接相关的当前源码、测试，以及固定
    `.vendor-src/MemOS` 中 Product Search/recall/rerank/status-filter 路径

三、必须确认的 B05 冻结继承边界

- 不修改比赛公开请求/响应 Schema；Search 不生成最终答案；
- 严格 user_id -> logical Cube 隔离，Search 不按 session_id 隔离；
- B05 Add 成功表示 Raw、provider provenance、graph/vector readback 和 receipt 均已提交；
- B05 同用户 lane、115 秒 Add deadline、无自动重试、无 raw-text 成功 fallback 保持冻结；
- B06 只能实现 Real Search、结果转换、状态/来源过滤、排序/去重/截断、60 秒预算和完整 readiness；
- 不在 B06 偷带最终模型选择、Prompt 调优、Answer/Judge、不可逆 organizer、额外服务或多 worker；
- 如发现 B05 接缝不足，先报告并判断是否需要正式修订，不能静默改写冻结语义。

四、部署与迭代必须继承以下流程

Python 单元/契约测试
        ↓
memory-api 原生运行或源码 bind mount
        ↓
复用已经运行的 Neo4j/Qdrant/MemOS
        ↓
代码冻结
        ↓
一次最终镜像构建

Pre-Gate 和 Gate 0 不运行 Docker。未来 Gate 1 实现中，Docker 前置能力检查最多 10 分钟、单阶段
排障最多 30 分钟；模型、Prompt、URL、Key、阈值和普通 Search 参数变化不重建镜像。B06 Gate 1
计划必须包含一份面向主办方的非 Docker 完整部署指南，覆盖 Add + Search + Health；当 Docker
不能及时部署时，它是正式兜底路径，而不是事后补充。

五、首轮只提交一份 B06 Pre-Gate Context Review 报告

报告必须包含：

1. Git/Batch 当前状态及证据路径；
2. 你对系统目标、评测链路和 B00–B05 已冻结能力的理解；
3. B06 的候选职责、明确非目标和不能破坏的不变量；
4. 已确认的 Search 正式契约：输入、输出、top_k、options、隔离、超时、Health 条件；
5. 当前 `MemoryGateway.search`、runtime、Raw Store 和 Adapter 的实际接缝；
6. 固定 MemOS v2.0.32 Search API、返回结构、状态过滤、rerank、Cube/user 参数的源码事实；
7. 文档、代码、固定源码之间的冲突、过时描述或未知项；
8. 可以离线确定性验证的内容，以及只能由华为调测机验证的内容；
9. 主要风险，尤其是错误记忆、旧值/forget 泄漏、跨用户泄漏、top_k 噪声、超时和错误成功；
10. Docker/原生部署边界及 48 小时止损是否已经可执行；
11. 是否准入 B06 Gate 0 的结论：`READY` 或 `NOT READY`。若不是 READY，只列真正阻塞 Gate 0
    讨论的问题，不把模型 ID、真实分数等调测项误判为设计准入阻塞。

对每个重要结论给出本地文件/固定源码位置；不要用尚未核验的论文观点代替仓库事实。涉及可能变化
的外部信息时才查询网络，技术事实只使用论文或官方文档，并区分“来源明确支持”和“你的推断”。

完成报告后必须停止，等待用户明确说“B06 前置理解通过，开始 B06 Gate 0”。不得预写 Gate 0
方案、不得创建 B06 PLAN/代码、不得自动进入 Gate 1。

后续协作顺序固定为：

1. B06 Pre-Gate Context Review；
2. 用户确认前置理解通过后进入 B06 Gate 0；
3. 用户逐个提出设计点和参考，逐一核验、讨论；每个设计点经用户确认后再沉淀到
   `docs/batches/B06/SEARCH_DESIGN_AND_TUNING.md`，作为调测机优先文档；
4. 设计点结束后单独评审 B06 Gate 0 是否存在安全、必要的 baseline 优化；
5. 只做一次最小 Gate 0 修订，正式冻结为 Gate 0 R1；
6. 用户明确要求后进入 B06 Gate 1，提交精确实施计划；
7. Gate 1 获用户明确审批后才开发代码；
8. 完成实现和证据后进入 Gate 2，由用户验收。

每一阶段都必须等待用户明确指令，不合并步骤，不因 48 小时紧迫而绕过审批；但评审和文档应保持
最小充分，禁止再次形成流程设计过重。
```

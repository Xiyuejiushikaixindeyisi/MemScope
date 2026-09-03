# MemScope 文档索引

本文档目录是项目的可审计事实入口。新的开发或调测 Session 不应依赖聊天记忆恢复项目状态。

## 当前状态

- B00～B05：`Accepted/Frozen`；B05 Gate 2 于 2026-09-03 经用户明确验收，Docker
  host-port/cgroup 验证转交具备正常 daemon 的调测机。
- B06：尚未进入，必须在新 Session 中从 Gate 0 开始。
- 当前 GitHub 主线只代表开发机已审计源码；调测机产生的最终候选必须通过回传清单闭环，避免与
  GitHub 版本静默分叉。

## 权威性顺序

信息冲突时按以下顺序处理：

1. 用户最新明确审批；
2. 正式任务书、API 契约和 Schema；
3. 已批准 ADR、当前 Batch 的 `PLAN.md` 与 `HANDOFF.md`；
4. 当前提交的代码和测试；
5. 固定版本第三方源码；
6. `PROJECT_CONTEXT.md`、`CODEMAP.md` 和协作文档；
7. `achieve/` 中的历史材料及聊天记录。

任何未被正式材料证实的资源、大小或评测限制都必须标成“待确认”，不得升级为硬性要求。

## 阅读路径

| 目的 | 必读文档 |
|---|---|
| 恢复当前项目状态 | `PROJECT_CONTEXT.md`、`CODEMAP.md` |
| 开始一个 Batch | `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md` 第 18～19 节、该 Batch 的 `CONTEXT.md`、`PLAN.md` |
| 依赖已验收 Batch | 对应 `HANDOFF.md`、公共接口和 ADR；不要重新加载全部历史实现 |
| 核对比赛要求 | `acceptance/CONTEST_ACCEPTANCE_CHECKLIST.md` 及其中引用的正式材料 |
| 两机开发与调测 | `collaboration/TWO_MACHINE_WORKFLOW.md` |
| 制作或接收交接包 | `collaboration/TRANSFER_MANIFEST_TEMPLATE.md` |
| 记录真实环境调优 | `collaboration/TUNING_REPORT_TEMPLATE.md` |
| B05 Gate 0 R1 决策 | `batches/B05/GATE0.md` |
| B05 Gate 1 已批准实施方案 | `batches/B05/PLAN.md` |
| B05 Add 设计与调测优先事项 | `batches/B05/ADD_DESIGN_AND_TUNING.md` |
| B05 非 Docker 部署兜底 | `batches/B05/NATIVE_DEPLOYMENT.md` |
| B05 冻结上下文 / Gate 2 交接 | `batches/B05/CONTEXT.md`、`batches/B05/HANDOFF.md` |
| 查看固定 MemOS 接线 | `integrations/MEMOS_V2_0_32_MAP.md` |

## 目录职责

- `acceptance/`：已核实的比赛契约、提交要求和待确认项；不保存实现偏好。
- `collaboration/`：开发机、调测机和人机协作规则及模板。
- `batches/`：每个 Batch 的方案、上下文和 Gate 2 交接证据。
- `adr/`：需要长期解释的重要架构决策。
- `interfaces/`：当前有效的外部和内部契约。
- `integrations/`：固定第三方版本的源码路由与兼容性事实。
- `achieve/`：历史归档，不作为默认上下文。

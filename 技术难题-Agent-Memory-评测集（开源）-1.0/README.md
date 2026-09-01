# Agent Memory 评测集（开源）1.0

> **复现状态：** 本目录是公开规则级复现，不声称与不可获得的主办方原始包字节一致。主包采用 `guide_compat` 转换，来源锁定、复现差异和审计结果见 `SOURCE_LOCK.json`、`REPRODUCTION_REPORT.md` 与 `reports/`。

本包面向 **技术难题 · Agent Memory** 初赛，提供：

1. **统一 Add / Search 契约**（`api_contract.md`）
2. **样本 Schema**（`schema/`）
3. **Smoke 样例**（`smoke/`，契约联调，**不计正式分**）
4. **正式评测数据说明**（指向开源仓库，不重复打包全量语料）

## 正式评测数据（须自行克隆）

| 基准 | 仓库 | 用途 |
|------|------|------|
| LoCoMo-Refined | https://github.com/mem-eval-suite/LoCoMo_refined | 长对话 / 跨会话 / 时序问答（约 1382 题） |
| MemOps | https://github.com/MemTensor/MemOps | Remember / Update / Forget / Reflect / Trajectory + 噪声长程 |

建议克隆命令：

```bash
git clone https://github.com/mem-eval-suite/LoCoMo_refined.git
git clone https://github.com/MemTensor/MemOps.git
```

LoCoMo-Refined 关键路径：

- `data/public/conversations.jsonl`
- `data/public/questions.jsonl`
- `data/raw/locomo_refined.json`

MemOps 关键路径：

- `generated_result/4-inject_evidence_with_distractors/*.json`
- （可选）`generated_result/2-evidence_conversation/`（Adjacent 干净证据）

> 上述仓库含完整对话与 gold，可用于本地自测。**官方成绩以赛题组评测机跑分为准。**  
> LoCoMo-Refined 许可为 **CC BY-NC 4.0**，仅限非商业评测与研发使用。

## 正式子集 `official/`（本包已内置）

混合包 **恰好 1000** 道 `search_items`：**500 LoCoMo-Refined + 500 MemOps**。

| 路径 | 说明 |
|------|------|
| `official/samples/locomo_*.json` | LoCoMo 样本（完整会话 `add_mode=full_conversation`） |
| `official/samples/memops_*.json` | MemOps 样本（inject 长程对话 + longitudinal 题） |
| `official/questions.jsonl` | 扁平题面（每行一题，含 `benchmark` 字段） |
| `official/manifest.json` | `counts_by_benchmark` 等统计 |

**LoCoMo 规则**

- 排除 category `3`（open-domain）
- 在 category `1/2/4`（single-hop / temporal / multi-hop）上分层抽样至约 500
- 对话历史来自本地完整 `data/public/conversations.jsonl`（非 WebFetch 截断副本）

**MemOps 规则**

- 上游目录：`generated_result/4-inject_evidence_with_distractors/`
- 仅 `evaluation_setting=longitudinal_operation`
- 排除当前上游新增、但指南未纳入的 `TrajectoryOps`
- 在 Remember / Update / Forget / Reflect 内按文件名稳定排序，分别取满 132 / 98 / 115 / 155 题

重建命令：

```bash
scripts/reproduce.sh \
  /path/to/LoCoMo_refined/data/public \
  /path/to/MemOps/generated_result/4-inject_evidence_with_distractors
```

## 本包目录

```text
技术难题-Agent-Memory-评测集（开源）-1.0/
├── README.md                 # 本文件
├── REPRODUCTION_REPORT.md    # 复现口径、差异和结果
├── PROXY_EVAL.md             # 非官方代理评测说明
├── SOURCE_LOCK.json          # 上游 commit、文件哈希和选择清单
├── manifest.json             # 版本与范围声明
├── api_contract.md           # Add / Search / Health 契约
├── schema/
│   └── sample.schema.json    # 平台侧样本（含 gold）JSON Schema
├── official/                 # 正式 1000 题（LoCoMo-Refined + MemOps 混合）
│   ├── manifest.json
│   ├── questions.jsonl
│   └── samples/              # locomo_*.json + memops_*.json
├── smoke/
│   ├── sample_locomo_style.json
│   ├── sample_memops_update.json
│   └── sample_memops_forget.json
├── reports/                  # 选择、时间、数据质量与校验报告
└── scripts/
    ├── reproduce.sh             # 一键构建+审计+校验
    ├── build_official_mixed.py   # 推荐：混合 1000 题
    ├── temporal_audit.py
    ├── validate_pack.py
    ├── local_proxy_eval.py
    ├── smoke_curl.sh
    └── smoke_curl.ps1
```

## 评测机逻辑（摘要）

```text
对每个 sample：
  for chunk in history_chunks:
      POST /add
  for question in search_items:
      POST /search(query, user_id, top_k=100)
      Answer(memories) → Judge(gold) → score
```

选手只实现记忆服务；Answer / Judge 由主办方固定。

## 本地代理评测（非官方）

本包额外提供一个确定性、无第三方依赖的代理 Answer/Judge，只用于本地回归对比：

```bash
python scripts/local_proxy_eval.py --self-test
python scripts/local_proxy_eval.py --base-url http://127.0.0.1:8080
```

该工具的所有报告都标记 `official=false`，不能与主办方成绩比较。详见 `PROXY_EVAL.md`。

## Smoke 用法

1. 启动本地记忆服务（见调测指南）
2. 执行 `scripts/smoke_curl.ps1` 或 `smoke_curl.sh`
3. 确认 Health / Add / Search 契约通过

## 版本

- 包版本：`1.0`
- 对应赛题：技术难题 TECH-005 Agent Memory
- 初赛客观基准：LoCoMo-Refined + MemOps

# Agent Memory（智能体长期记忆）-调测指南

## 环境准备

### 系统要求

- 操作系统：Windows 10/11 或 Linux（以 INSTRUCTION.md 声明为准；主办方评测环境以赛题组通知为准）
- 运行时：按所选技术栈安装（推荐 Python 3.10+ 或 Node.js 18+）
- Docker（推荐）：用于复现与提交包启动验证
- 网络：若记忆抽取/Embedding 依赖模型服务，须确保评测环境可访问（以赛题组模型资源通知为准）

### 依赖安装

按项目依赖声明安装。FastAPI 最小示例：

```bash
pip install fastapi uvicorn pydantic
```

### 服务启动示例

```bash
# 示例：本地启动（端口以选手实现为准）
uvicorn main:app --host 0.0.0.0 --port 8080

# 或 Docker
docker build -t agent-memory:dev .
docker run --rm -p 8080:8080 agent-memory:dev
```

启动后确认：

```bash
curl -sS http://127.0.0.1:8080/health
```

返回任意 2xx 即表示 Health 可用。

## 资源说明

### 评测数据集

| 资源 | 说明 |
|------|------|
| 本包 `official/` | **初赛正式子集**：**1000** 道题（LoCoMo-Refined **500** + MemOps **500**）；含 `samples/`、`questions.jsonl`、`manifest.json` |
| 本包 `smoke/` | Smoke 样例（契约联调，**不计正式分**） |
| [LoCoMo-Refined](https://github.com/mem-eval-suite/LoCoMo_refined) | 上游全量（本地扩测）；`data/public/conversations.jsonl` + `questions.jsonl` |
| [MemOps](https://github.com/MemTensor/MemOps) | 上游全量（本地扩测）；`generated_result/4-inject_evidence_with_distractors/` 等 |

正式客观分以 `official/` 为准。字段与 Add/Search 映射见本包 `api_contract.md`、`schema/sample.schema.json`。

### 模型资源

- **记忆系统内部模型**（可选）：提取、摘要、Embedding 等，须在 SDD 中说明；正式评测可用模型以赛题组通知为准。
- **Answer / Judge 模型**：由主办方评测环境统一固定，选手 **不实现**、不替换。

### 统一接口

选手须实现：

- `POST /add`
- `POST /search`
- `GET /health`

请求/响应 JSON 见 `api_contract.md`。路径前缀可自定义，但须在 INSTRUCTION.md 中写明完整 URL。

## 调测步骤

### 第一步：契约冒烟（必做）

使用本包 `scripts/smoke_curl.sh`（或等价 PowerShell）对本地服务执行：

1. `GET /health`
2. `POST /add` 写入 `smoke/sample_locomo_style.json` 中的一段 history
3. `POST /search` 用同 `user_id` 查询样例问题
4. 检查响应：`success=true`、三 ID 回显、`data` 为数组且条目含非空 `id`/`content`

失败常见原因：

| 现象 | 排查 |
|------|------|
| Add 返回 202 / 无 `success` 布尔值 | 须同步写入，且 `success` 为 JSON boolean `true` |
| Search 顶层直接是数组 | 须为 `{"data":[...]}` |
| Search 返回最终答案句 | 只返回记忆证据，平台负责 Answer |
| 跨样例串结果 | 检查是否按 `user_id` 隔离 |

### 第二步：同会话召回调测

1. Add 同一 `session_id` 下多轮 user/assistant；
2. Search「刚才提到的关键事实」类问题；
3. 确认 `content` 中含证据片段（不必等于 gold 全文）。

### 第三步：正式子集抽样调测（推荐）

1. 从本包 `official/samples/` 任选 `locomo_*.json` / `memops_*.json`；
2. 按样本内 `add_phase` / history 分块调用 Add（`full_conversation`）；
3. 对同样本 `search_items` 逐题 Search（`top_k=100`）；
4. （可选）对照样本内 gold 或 `official/questions.jsonl` 做本地准确率——**仅自测，非正式成绩**。

建议路径：先 1～2 个样本 → 再扩到数十题 → 最后再考虑跑满 1000 题加压。

### 第四步：跨会话召回调测（LoCoMo 向）

1. 优先用 `official/samples/locomo_*.json`；或从上游 LoCoMo-Refined 任选 1 个 `sample_id`，按 session 分块 Add；
2. 用该样本若干题做 Search；
3. 关注多会话后单跳 / 时序 / 多跳证据是否仍可召回。

### 第五步：更新 / 遗忘 / 噪声调测（MemOps 向）

1. 优先用 `official/samples/memops_*.json`（均为 longitudinal）；或从上游 MemOps inject 选取 `Update` / `Forget`；
2. Add 完整 longitudinal 对话（含 distractor 会话）；
3. Search 状态题，检查是否返回 **最新有效状态** 相关证据，而非仅最近提及的 tentative/旧值；
4. Forget 类：确认遗忘目标不再作为有效证据优先返回，且未明显过删无关记忆。

### 第六步：提交前复现验证

按 **提交包** 结构自检：

1. 仅依据 `INSTRUCTION.md`，在干净环境（或新容器）启动服务；
2. 再跑一遍 Smoke；
3. 确认无需人工交互、端口与鉴权与文档一致。

## 调测结果

### 结果分析

- **正式客观分**：仅由主办方评测机按冻结的 `official/`（1000 题）跑分后给出；
- **本地自测分**：可用 `official/` 或上游全量调参，不保证与官方完全一致（Answer/Judge 版本、超时策略可能不同）；
- 关注：召回证据是否相关、更新后是否仍返回旧值、噪声会话是否淹没有效证据。

### 验证方法

- 契约层：Smoke curl / schema 校验；
- 能力层：本包 `official/` 抽样；可选上游 LoCoMo-Refined / MemOps 加压；
- 交付层：Docker 冷启动 + Health + 一次 Add/Search。

### 归档要求

提交 `solution.zip`，至少包含：

- `INSTRUCTION.md`
- `SDD.md`
- `code/`（及可选 Dockerfile）

由赛题组在评测环境构建启动并完成客观评测。

### 常见问题

| 问题 | 建议 |
|------|------|
| 本地准确率高、担心官方低 | 核对是否硬编码答案；核对 Add 是否同步可检索；核对 `user_id` 是否与评测一致 |
| Embedding 服务内网不通 | 提供纯词法/本地模型回退，或在 INSTRUCTION 中声明依赖并与赛题组确认资源 |
| 长对话 Add 超时 | 支持评测机分 chunk 多次 Add；单次请求控制消息规模 |
| MemOps / LoCoMo 体量大 | 先 Smoke → `official/` 单样本 → 再逐步加压至 1000 题 |

### 参考链接

- 正式子集：本包 `official/`（`manifest.json` / `questions.jsonl` / `samples/`）
- LoCoMo-Refined：https://github.com/mem-eval-suite/LoCoMo_refined
- MemOps：https://github.com/MemTensor/MemOps
- 本包契约：`api_contract.md`
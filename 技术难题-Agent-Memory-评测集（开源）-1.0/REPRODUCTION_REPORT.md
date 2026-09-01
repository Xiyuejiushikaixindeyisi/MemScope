# 评测集复现报告

## 结论

本目录是基于公开上游数据和赛题复现指南生成的规则级复现，不声称与不可获得的主办方原始包字节一致。

主包采用 `guide_compat` 转换模式：不向 LoCoMo Add 消息静默补入 session 日期、图片描述或其他上游旁路字段，也不静默补入 MemOps `candidate_options`。所有已发现的信息损失均在 `reports/` 中审计。

## 冻结数据源

| 数据源 | 固定版本 |
|---|---|
| LoCoMo-Refined | tag `v1.0.0` / commit `887091190789e8d6760e70b9edd696539923dc4f` |
| MemOps | commit `312af65e2c7b6d1b70f062ffa8b4cde32aaf6f35` |

关键上游文件及所选 MemOps 文件的 SHA-256 见 `SOURCE_LOCK.json`。

## 构建规则

### LoCoMo-Refined

- 从 `data/public/questions.jsonl` 和 `conversations.jsonl` 读取；
- 排除 category 3 和 5；
- 按 `(sample_id, qa_id)` 稳定排序；
- category 1/2/4 分别选择 167/167/166 题；
- 使用完整多 session 文本对话；
- 输出 9 个样本、500 题。

### MemOps

当前上游已扩展为 403 个 inject JSON、2006 道 longitudinal 题，并包含指南未纳入的 `TrajectoryOps`。缺少原始 `memops_selected.txt`，因此采用可审计的确定性重建规则：

- 只保留 Remember、Update、Forget、Reflect；
- 只保留 `evaluation_setting=longitudinal_operation`；
- 每个 operation 内按文件名升序；
- 依次取满指南公布的 132/98/115/155 配额。

该规则恰好得到 101 个样本、500 题，并精确复现指南公布的五种 eval-axis 数量。实际文件和 qid 清单见 `reports/build_selection.json`。

## 结果

| 维度 | 结果 |
|---|---:|
| 样本 | 110（9 LoCoMo + 101 MemOps） |
| 题目 | 1000 |
| LoCoMo | 500 |
| MemOps | 500 |
| single-hop / temporal / multi-hop | 167 / 167 / 166 |
| Remember / Update / Forget / Reflect | 132 / 98 / 115 / 155 |

完整统计见 `official/manifest.json`，校验结果见 `reports/VALIDATION_REPORT.json`。

## 兼容性审计

- 167 道 temporal 题中，117 道的证据包含相对时间表达；
- guide-compatible Add 内容中保留的 session 日期为 0；
- 选中 207 道上游标注的多模态 LoCoMo 题；
- 100 道 MemOps 题具有上游 `candidate_options`，主包按指南转换逻辑未复制这些 options。

详见 `reports/temporal_audit.json`、`reports/data_quality_audit.json` 和 `reports/DATA_QUALITY_AUDIT.md`。

## 确定性

同一上游版本连续构建两次后，整个 `official/` JSON/JSONL 集合哈希一致：

```text
0c10252d7b47abecf193b52526b363015bbe63e4eff03bbdbefc784380682bd5
```

## 一键复现

```bash
scripts/reproduce.sh \
  /path/to/LoCoMo_refined/data/public \
  /path/to/MemOps/generated_result/4-inject_evidence_with_distractors
```

## 代理评测

提供 `scripts/local_proxy_eval.py` 作为非官方确定性 Answer/Judge。用途和限制见 `PROXY_EVAL.md`。由于主办方 Answer/Judge、截断和加权规则未公开，代理分数不得称为官方成绩。

## 目录整理

已删除拼写错误的 `mainfest.json`、`official/mainfest.json`、空文件
`official/question.jsonl`、冗余兼容脚本及误混入的 `.cac` 本地配置。有效入口是
`manifest.json`、`official/manifest.json` 和 `official/questions.jsonl`。

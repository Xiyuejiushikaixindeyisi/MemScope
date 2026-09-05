# 开发机真实调优与主办方评测报告模板

> B10 当前流程由开发机完成 baseline 和调优，主办方评审机只加载最终镜像、运行并评分。全程不记录
> Key、IAM token、密码、正文、向量、gold 或 provider 完整响应。

## 1. 候选与环境身份

- 分支 / 40 字符 commit：`<required>`
- 基线 commit：`<required>`
- Host / Docker / Compose：`<required>`
- CPU / 内存 /磁盘：`<required>`
- 数据集 / 切片 / 随机种子：`<required>`
- 非秘密 API/model/dimension 指纹：`<required>`
- Python/MemOS/Neo4j/Qdrant 版本：`<required>`

## 2. API 能力探测

| 能力 | 端点/model | 实测结论 | 限制/错误 |
|---|---|---|---|
| Chat | `<fill>` | `<fill>` | `<fill>` |
| Embedding | `<fill>` | dimension `<fill>` | `<fill>` |
| Rerank（若使用） | `<fill>` | `<fill>` | `<fill>` |
| JSON/tools/reasoning | `<fill>` | `<fill>` | `<fill>` |
| timeout/429 | `<fill>` | `<fill>` | `<fill>` |

## 3. 开发机 baseline

| 指标 | Smoke | 小样本 | holdout | full |
|---|---:|---:|---:|---:|
| 正确/总数或正式代理指标 |  |  |  |  |
| Add P50/P95/P99/max |  |  |  |  |
| Search P50/P95/P99/max |  |  |  |  |
| timeout/429/5xx |  |  |  |  |
| 峰值 CPU/内存/磁盘 |  |  |  |  |

## 4. 单变量实验

每个实验复制一节：

### EXP-`<id>`：`<hypothesis>`

- 基准 candidate：`<required>`
- 唯一主变量及前后值：`<required>`
- 其它固定变量：`<required>`
- 数据切片/随机种子：`<required>`
- 正向/负向翻转与未变化：`<required>`
- 准确率、延迟、调用量、资源和失败率：`<required>`
- 结论：`accept/reject/inconclusive`
- 回退：`<required>`

## 5. 开发机冻结与最终构建

- 选择的候选及理由：`<required>`
- 相对 baseline 累计变化：`<required>`
- 最终非秘密配置：`<required>`
- 已知风险：`<required>`
- solution ZIP / image TAR / manifest SHA-256：`<required>`
- 四张 image ID / custom revision labels：`<required>`
- `build_candidate_delivery.py verify`：`<pass/fail>`

## 6. 主办方返回证据

- 入站 hash/image identity：`<pass/fail>`
- 四服务/Health/Smoke：`<pass/fail + timing>`
- 官方评测器与数据切片：`<required>`
- 官方得分/失败统计：`<required or not produced>`
- 重启/资源证据：`<pass/fail/not run>`
- 环境差异和脱敏错误：`<required>`
- 卷保留：`<required>`

开发机结果与主办方结果分别标注，不得互相冒充。只有与同一 commit、ZIP/TAR hash 和 image ID 绑定
的证据才能用于最终审批。

# 真实环境调测与调优报告模板

> 不记录 Key、IAM token、完整敏感响应或原始私密对话。

## 1. 身份与环境

- 基准 ZIP SHA-256：`<required>`
- 基准 Git commit：`<required>`
- Host / Docker / Compose：`<required>`
- CPU / 内存 / 磁盘 / GPU：`<required>`
- Python、MemOS、Neo4j、Qdrant 版本：`<required>`
- 数据集与固定随机种子：`<required>`

## 2. 网关能力探测

| 能力 | 端点/model ID | 实测结论 | 限制/错误 |
|---|---|---|---|
| Chat | `<fill>` | `<fill>` | `<fill>` |
| Embedding | `<fill>` | 维度 `<fill>` | `<fill>` |
| Rerank | `<fill>` | `<fill>` | `<fill>` |
| tools / JSON | `<fill>` | `<fill>` | `<fill>` |
| reasoning | `<fill>` | `<fill>` | `<fill>` |
| timeout / 429 | `<fill>` | `<fill>` | `<fill>` |

## 3. Docker 二次验收

记录构建、冷启动、Health、Add/Search Smoke、镜像体积、非 root、日志、资源、优雅停机、进程/daemon
重启和持久化结果。扫描结果必须如实记录，批准豁免与“没有发现”分开表述。

## 4. 基线

| 指标 | Smoke | 单样本 | 数十题 | 1000 题 |
|---|---:|---:|---:|---:|
| 正确/总数 |  |  |  |  |
| Add P50/P95/P99 |  |  |  |  |
| Search P50/P95/P99 |  |  |  |  |
| 超时/429/5xx |  |  |  |  |
| 峰值 CPU/内存/磁盘 |  |  |  |  |

按 LoCoMo 单跳、时序、多跳，以及 MemOps Remember/Update/Forget/Reflect/噪声切片记录错误分布。

## 5. 单变量实验

每个实验复制一节：

### EXP-`<id>`：`<hypothesis>`

- 基线 candidate：`<id>`
- 唯一主变量及前后值：`<required>`
- 其它固定变量：`<required>`
- 数据切片/随机种子：`<required>`
- 正向翻转、负向翻转和未变化：`<required>`
- 准确率、延迟、调用量、资源和失败率：`<required>`
- 结论：`accept/reject/inconclusive`
- 回退方式：`<required>`

## 6. 最终候选

- 选择的 candidate 及理由：`<required>`
- 相对基线的累计变化：`<required>`
- 最终脱敏配置：`<required>`
- 已知风险和未关闭问题：`<required>`
- 最终 ZIP 文件名、大小、SHA-256：`<required>`
- 最终源码树或 patch 路径：`<required>`

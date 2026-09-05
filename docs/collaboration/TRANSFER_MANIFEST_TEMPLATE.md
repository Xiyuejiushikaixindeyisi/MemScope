# B10 候选出站与主办方评测回传模板

> 不得填写或附带 Key、IAM token、密码、Authorization header、请求正文、向量或 provider 完整响应。

## A. 开发机最终候选出站

| 字段 | 值 |
|---|---|
| 日期/负责人 | `<required>` |
| 分支 / 40 字符 commit | `<required>` |
| `git status --short` | 必须为空 |
| 目标平台 | `linux/amd64` |
| MemOS tag / commit | `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484` |
| solution ZIP / SHA-256 / bytes | `<required>` |
| four-image TAR / SHA-256 / bytes | `<required>` |
| manifest / SHA-256 | `<required>` |
| 四张 image reference / ID | `<required>` |
| 两张项目镜像 revision label | 必须等于候选 commit |
| 开发机 API 配置指纹 | `<non-secret required>` |
| baseline / tuning 结果 | `<required>` |
| 已执行回归与容器验证 | `<commands + result>` |
| 未验证项/风险 | `<required>` |

### 出站硬门

- [ ] 用户已单独批准最终 artifact 生成；
- [ ] `build_candidate_delivery.py verify` 通过；
- [ ] `SHA256SUMS` 恰好覆盖 ZIP、image TAR 和 manifest；
- [ ] ZIP 内 `RELEASE_LOCK.tsv` 与 manifest 四张镜像完全一致；
- [ ] release Compose 恰好四服务、无 `build:`、全部 `pull_policy: never`；
- [ ] 无 `.git`、cache、runtime data、私有 env 或凭据；
- [ ] MemOS 固定源码 archive hash/展开秘密扫描通过；
- [ ] 主办方 quickstart 和 agent prompt 与实际文件名/命令一致；
- [ ] 没有把开发机分数写成主办方官方分数。

## B. 主办方入站、启动和自检

| 字段 | 值 |
|---|---|
| 接收日期/负责人 | `<required>` |
| 四件套 hash 是否全部匹配 | `yes/no` |
| Host OS / architecture | `<required>` |
| Docker Engine / Compose | `<required>` |
| CPU / memory / free disk | `<required>` |
| 四张 load 后 image ID 是否匹配 | `yes/no` |
| 项目镜像 revision 是否匹配 commit | `yes/no` |
| Compose project / public URL | `<required>` |
| 四服务 running/healthy | `<required>` |
| Neo4j / Qdrant readiness | `<required>` |
| Add/Search Smoke 与耗时 | `<sanitized required>` |
| 跨用户 evidence | 必须为 0 |

## C. 主办方正式评测回传

| 字段 | 值 |
|---|---|
| 候选 commit / ZIP hash / image TAR hash | `<required>` |
| 评测器名称与版本 | `<required>` |
| 数据集/切片/随机种子 | `<required>` |
| 主办方非秘密模型配置 | `<required>` |
| 成功/失败/429/timeout 数 | `<required>` |
| Add、Search P50/P95/P99/max | `<required>` |
| 主办方定义的正式得分 | `<required or not produced>` |
| 峰值 CPU / memory / disk | `<required>` |
| 重启持久化 | `<pass/fail/not run>` |
| 脱敏错误分类 | `<required>` |
| 卷是否保留 | `<required>` |

失败时不要求主办方修改或打包源码；保留容器/卷并回传最小脱敏证据即可。

## D. 开发机回收审计

- [ ] 报告身份与出站 commit、ZIP、TAR、manifest、image ID 一致；
- [ ] 开发机可复现配置/结果差异或明确标为环境差异；
- [ ] 无 gold 泄漏、凭据、正文、向量或完整 provider response；
- [ ] 失败若需代码修改，派生新候选并重新走回归/构建/评测；
- [ ] 用户明确批准后才合入 main、tag、发布或提交最终候选。

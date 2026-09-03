# 调测交接与回传清单模板

> 复制本模板到交接包或调测报告目录后填写；不得填写真实密钥。

## A. 开发机出站清单

| 字段 | 值 |
|---|---|
| 交接日期/负责人 | `<required>` |
| Git repository | `<required>` |
| branch / commit | `<required>` |
| `git status --short` | 必须为空，或逐项解释 |
| MemOS tag / commit | `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484` |
| ZIP 文件名 | `<required>` |
| ZIP 字节数 | `<required>` |
| ZIP SHA-256 | `<required>` |
| 目标 OS / architecture | `<required or pending>` |
| Docker / Compose 最低要求 | `<required>` |
| 已验证测试 | `<commands + results>` |
| 未验证项 | `<required>` |

### 必备内容

- [ ] `INSTRUCTION.md`
- [ ] `SDD.md`
- [ ] 完整源码和依赖锁
- [ ] Docker/Compose 启动入口
- [ ] `.env.example` 或等价的无密钥配置说明
- [ ] `THIRD_PARTY_NOTICES.md` 与许可证
- [ ] Smoke/能力探测脚本
- [ ] 调优指南和真实环境补测项
- [ ] 风险、回退方式和已知豁免

### 洁净性

- [ ] 无 `.git`、缓存、测试输出、运行数据库和日志
- [ ] 无 API Key、IAM token、证书或内部敏感 URL 参数
- [ ] 无未经许可的模型权重或参考代码
- [ ] 新目录构建、启动、Health、Add/Search Smoke 均有结果

## B. 调测机入站记录

| 字段 | 值 |
|---|---|
| 收包日期/负责人 | `<required>` |
| 实收 ZIP SHA-256 | `<required>` |
| 是否匹配出站记录 | `yes/no` |
| Host OS / architecture | `<required>` |
| Docker / Compose | `<required>` |
| CPU / memory / disk / GPU | `<required>` |
| 可达镜像源/包源 | `<required>` |
| 构建结果与耗时 | `<required>` |
| 冷启动与 Health 耗时 | `<required>` |

## C. 调测机回传清单

| 字段 | 值 |
|---|---|
| 基准 ZIP SHA-256 | `<required>` |
| 最终 ZIP 文件名 | `<required>` |
| 最终 ZIP 字节数 | `<required>` |
| 最终 ZIP SHA-256 | `<required>` |
| 最终配置标识 | `<required>` |
| 基线结果 | `<required>` |
| 最终结果 | `<required>` |
| Docker 验收 | `<summary + evidence path>` |
| 未关闭风险 | `<required>` |

### 必须回传

- [ ] 最终 ZIP
- [ ] 最终源码树或相对基准 ZIP 的统一 diff/patch
- [ ] 脱敏配置快照
- [ ] `TUNING_REPORT.md`
- [ ] 模型/API 能力探测报告
- [ ] Docker/资源/Smoke 证据
- [ ] 失败和豁免清单

## D. 开发机回收审计

- [ ] 校验基准和最终 ZIP SHA-256
- [ ] 审查源码、依赖、配置和许可证差异
- [ ] 检查无密钥、无 gold/题号硬编码
- [ ] 将可复现变更回写分支并运行本机 Gate
- [ ] 在 Markdown 中记录最终候选与 Git commit 的对应关系
- [ ] 若无法复现，明确记录“外部生成候选”及原因

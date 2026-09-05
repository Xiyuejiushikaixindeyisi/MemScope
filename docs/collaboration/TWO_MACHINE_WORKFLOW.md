# 开发机与主办方评审机协作规范

> B10 当前规则，2026-09-05 经用户在 Gate 1 批准。它取代此前“调测机安装依赖、构建镜像或生成
> 最终 ZIP”的活动流程；旧 Batch 文档中的描述只保留为历史事实。

## 1. 当前单一演进链

```text
开发机候选分支/commit
  -> 开发机部署服务并接入可达的 OpenAI-compatible API
  -> baseline、单变量调优、回归和候选冻结
  -> 开发机构建 solution ZIP + 四镜像离线 bundle + manifest + SHA256SUMS
  -> 用户受控传递并注入主办方私有配置
  -> 主办方评审机校验、docker load、Compose 启动、自检和正式评测
  -> 脱敏结果回传开发机审计
  -> 用户批准后才合入 main
```

开发机和主办方 API 可以不同，但都必须满足候选实际使用的 OpenAI-compatible Chat/Embedding
协议。一个镜像 TAR 内含四张镜像只是传输形式；运行时仍是 `memory-api`、MemOS、Neo4j、Qdrant
四个容器。

## 2. 开发机职责

- 维护 Git、候选分支、设计、代码、锁、测试、文档和回退点；
- 安装 Python 依赖，构建/运行开发服务，使用开发机可达 API 做能力探测和真实评测；
- baseline 先于调优；单变量实验记录数据切片、配置指纹、得分、延迟、失败率和结论；
- 在最终源码和非秘密运行配置确定后构建两张项目镜像，并把固定 Neo4j/Qdrant 镜像一起保存；
- 生成并验证最终四件套，确保主办方无需 build、pull、Python、uv 或 pip；
- 根据主办方脱敏报告定位问题。任何源码修复都回到开发机新候选，不能要求主办方现场 patch。

模型 URL、Key、model ID、prompt 和阈值是运行/调优配置；普通变化不重建镜像。只有源码、依赖、
Dockerfile 或固定 MemOS patchset 变化才重建受影响镜像。

## 3. 主办方评审机职责

- 提供 Linux x86_64、Docker Engine/Compose v2、磁盘/内存和可达的主办方模型 API；
- 校验 `SHA256SUMS`，加载四镜像 bundle，使用源码目录外的 0600 私有 env 注入凭据；
- 运行 `run_release.sh` 和 `verify_release.sh`，确认四服务 Health、真实 Add/Search 和隔离；
- 把服务 URL 交给主办方官方评测器，按官方数据、并发和评分规则执行评测；
- 回传 commit、hash、image ID、环境、脱敏耗时/错误/分数以及卷保留状态。

主办方评审机不安装项目 Python 依赖，不构建或拉取镜像，不修改源码，不生成另一个候选，也不承担
核心调优。它不依赖公网、registry、package index 或源码站点；唯一运行时网络依赖是主办方已经
提供的内网模型 API，官方评测器及数据集也由主办方预置在本机。失败时保留容器和卷，不运行
`down -v` 或 prune。

## 4. 用户职责

- 通过安全渠道提供两台机器各自的凭据，并决定 IAM/Bearer 的准确鉴权方式；
- 在两台机器之间物理或受控传递 ZIP、镜像 TAR、manifest、校验文件和报告；
- 审批 Batch/Gate、整改范围、最终候选、最终 artifact 生成、合入 main 和对外发布；
- 决定原始 MemScope 源码的许可证或其它合法分发依据。

凭据不进入 Git、ZIP、镜像层、命令行参数、报告或聊天。内部 HTTP 只在用户确认的可信网络配置中
通过 `MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true` 显式启用。

## 5. 候选与合入规则

优化代码必须先在独立候选分支中完成。开发机回归和真实 baseline/tuning 通过、最终镜像绑定准确
commit、主办方自检/正式评测返回可复核证据、用户明确批准后，才允许合入 `main`。不能因为镜像能
启动就自动宣称源码正确、B08 live 证据闭合或获得官方分数。

每次传递至少由以下身份共同定义：

- 40 字符 Git commit；
- solution ZIP 和 image bundle SHA-256；
- `delivery-manifest.json`；
- 四张镜像 reference/image ID；
- 两张项目镜像的 `org.opencontainers.image.revision`；
- 脱敏运行时配置指纹和评测器/数据切片身份。

## 6. API 和评测纪律

主办方当前非秘密事实为 Chat `GLM-V5_1-DX`、Embedding `bge-m3` dimension 1024、HTTP base
`http://aigateway.huawei.com/v1`。标准 Embedding 一般使用 `input` 字段；用户早期示例中的
`messages` 形式不作为候选的硬编码协议。外部 reranker 仅是已知可用端点，当前候选继续使用
`cosine_local`，直到开发机单独验证适配器。

批处理 429 退避属于评测客户端；服务内部保持不自动重放 Add。Add ≥120 秒、Search ≥60 秒、跨用户
evidence、错误成功、数据损坏、凭据暴露、image ID/commit 不一致都直接拒绝候选。

## 7. 主办方入口

最终包必须包含：

- `INSTRUCTION.md`；
- `ORGANIZER_QUICKSTART.md`；
- `ORGANIZER_AGENT_PROMPT.md`；
- `compose.release.yaml`；
- `deploy/organizer.env.example`；
- `scripts/run_release.sh`、`verify_release.sh`、`stop_release.sh`；
- `RELEASE_LOCK.tsv`、源码 manifest、第三方通知和许可证。

这些入口必须与最终文件名一致，并在没有 host Python/uv/pip、没有 registry pull、没有源码 build 的
清洁评审机流程中验证。

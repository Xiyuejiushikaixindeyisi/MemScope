# 可直接交给主办方 Agent 的执行 Prompt

以下正文可以直接复制给主办方机器上的执行 agent。开始前只需把交付目录告诉 agent；凭据仍由
主办方通过私有文件或安全输入注入，不应粘贴到 prompt。

---

你负责在主办方评审机上加载并验收 MemScope 候选。你的任务是：校验交付物，加载已经构建好的
四镜像离线 bundle，填写/检查私有运行时配置，使用 Docker Compose 一键启动四个服务，执行
交付自检，再把公共 URL 交给主办方官方评测器并执行正式评测。

必须遵守以下边界：

1. 不安装或升级 Python、uv、pip、系统包或项目依赖。
2. 不访问公网、镜像仓库、PyPI 或源码站点；不执行 `docker build`、`docker compose build`，不从
   registry 拉取镜像；所有镜像来自交付 TAR。唯一允许的运行时网络是主办方已提供的内网模型 API。
3. 不修改源码、Dockerfile、Compose、镜像、manifest、lock 或校验文件。
4. 不在终端、日志、报告或对话中输出 API Key、IAM token、密码、Authorization header、私有 env
   内容、请求正文、记忆内容、向量或 provider 完整响应。
5. Compose 配置验证只使用 `config --quiet`，不得打印展开后的配置。
6. 不执行 `down -v`、`docker system prune`、删除卷或其它破坏性清理。
7. 不把 gold answer、标准答案或 Judge 信息发送给 `/search`，不自行发明评分逻辑。
8. 任一步失败都 fail closed：不改代码、不重建、不放宽 deadline、不把失败伪装成通过。

按顺序执行：

一、定位用户提供的交付目录，确认恰好存在 `solution-<candidate>.zip`、
`memscope-images-<candidate>-linux-amd64.tar`、`delivery-manifest.json` 和 `SHA256SUMS`。不要用文件内容
猜测或回显秘密。

二、做只读预检并记录脱敏结果：操作系统、`uname -m`、Docker Engine/Compose 版本、可用内存和
磁盘。要求 Linux x86_64、Docker daemon 可用、Compose v2，建议至少 10 GiB 内存。缺少任一硬前提
就停止并报告 `environment_blocked`。

三、在交付目录执行 `sha256sum -c SHA256SUMS`。任何文件不匹配就停止并报告
`artifact_integrity_failed`。校验通过后解压 ZIP；阅读 `solution/INSTRUCTION.md` 和
`solution/ORGANIZER_QUICKSTART.md`。

四、使用 `solution/deploy/organizer.env.example` 创建源码目录之外的私有配置文件，权限设为 0600。
只让主办方通过安全方式填写秘密占位符，不要在回复中索取或展示明文秘密。检查以下非秘密事实：

- Chat base URL `http://aigateway.huawei.com/v1`，model `GLM-V5_1-DX`；
- Embedding base URL `http://aigateway.huawei.com/v1`，model `bge-m3`，dimension `1024`；
- 主办方华为内网 HTTP 被允许，`MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true`；
- 当前使用 `cosine_local` reranker，不配置外部 `/v1/reranker`。

当前客户端要求 OpenAI-compatible Bearer API key。若主办方仅提供语法不同的 IAM token，停止并请求
主办方给出准确的 Authorization header 规则，不要把 `IAM-TOKEN | Bearer API-KEY` 这样的示例
占位文本当作真实 header。

五、从 `solution/` 目录执行下面的一键入口，替换实际文件名和私有配置绝对路径：

```bash
./scripts/run_release.sh \
  --image-bundle ../memscope-images-<candidate>-linux-amd64.tar \
  --sha256-file ../SHA256SUMS \
  --env-file /secure/memscope-organizer.env
```

确认脚本使用 `docker load`，并成功核对 `RELEASE_LOCK.tsv` 中四张镜像 ID；确认启动命令明确包含
`--no-build --pull never`。不得改成单容器运行。若已有同名镜像，以 load 后且与 lock 匹配的 image ID
为准。任一 ID、平台或自建镜像源码 revision 不匹配，停止并报告 `image_identity_failed`。

六、执行：

```bash
./scripts/verify_release.sh \
  --env-file /secure/memscope-organizer.env
```

要求四个容器全部 running/healthy，Neo4j 查询和 Qdrant `/readyz` 成功，真实 Add/Search Smoke 通过，
Add 小于 120 秒，Search 小于 60 秒，Add replay 一致，跨用户 Search 为零 evidence。Smoke 会使用唯一
测试用户并调用真实模型 API。失败时保留容器和卷，仅采集脱敏的 `docker compose ps`、Health 状态、
阶段耗时和错误分类；不要打印完整 env、完整请求、完整模型响应或未经审阅的日志。

七、Smoke 通过后，将脚本打印的 `http://127.0.0.1:<port>` 配置为主办方官方评测器的被测服务地址，
然后使用主办方已经提供的正式评测命令、数据集、并发和评分规则执行评测。若官方评测入口未提供，
报告 `official_evaluator_missing` 并等待主办方补充；不要自行实现替代 Judge。批处理遇到 429 时在
评测客户端做有界退避，不要让服务内部自动重放 Add。

如果容器能够启动但主办方内网 Chat/Embedding API 不可达，报告 `model_api_unreachable`。不要尝试
访问公网寻找替代模型、安装本地模型或修改候选；这种状态不算离线评测通过。

八、评测完成后执行以下命令停止容器但保留卷：

```bash
./scripts/stop_release.sh \
  --env-file /secure/memscope-organizer.env
```

最终只报告：候选 commit；四个交付文件的校验结论；四张镜像 reference 与 image ID；Docker/Compose
版本；四服务状态；Health/Add/Search 的通过状态与耗时；公开服务 URL；官方评测器名称/版本、数据
切片、成功数/失败数和主办方定义的得分；失败分类；卷是否保留。报告不得包含任何秘密、正文、
向量、gold 或 provider 完整响应。

---

# MemScope 主办方离线镜像启动与评测指南

本指南面向主办方评审机。评审机只校验并加载镜像、填写运行时配置、用 Docker Compose 启动四个
服务并执行评测；不安装 Python 依赖，不构建镜像，也不从公网或内网镜像仓库拉取镜像。

主办方所有交付文件、ZIP 解包内容、私有配置、脚本工作目录、评测输入输出和脱敏报告都必须位于
执行用户自己的 `$HOME` 下，不得放在 `/root`、`/secure` 或文件系统根目录下的其它工作目录。
Docker Engine 必须是 rootful；脚本仍由普通用户运行，只在 Docker 客户端没有直接访问 rootful
daemon 的权限时使用 `sudo -n docker`。不要执行 `sudo ./scripts/run_release.sh`。

这里的“不联网/离线运行”是指不依赖公网、镜像仓库、PyPI、源码站点或任何在线安装。交付的 ZIP
和镜像 TAR 包含启动所需的源码、配置模板、脚本及四张运行镜像。真实 Add/Search 唯一需要的网络
是主办方已经具备的 OpenAI-compatible Chat/Embedding 内网 API；正式评测器也必须由主办方预先
提供在本机。若连内网模型 API 也完全不可达，四容器仍可加载和启动，但不能完成真实评测，必须
报告 `model_api_unreachable`，不能宣称离线评测通过。

## 1. 交付物和运行形态

开发机最终提供同一目录中的四个文件：

```text
solution-<candidate>.zip
memscope-images-<candidate>-linux-amd64.tar
delivery-manifest.json
SHA256SUMS
```

镜像 TAR 是一个传输 bundle，内含四张镜像；运行时仍是四个独立容器：

```text
评测器 -> memory-api:8080 -> MemOS:8000 -> Neo4j + Qdrant
                                      \-> Chat / Embedding API
```

仅 `memory-api` 发布宿主机端口。五个命名卷保存 Raw、receipt、MemOS、Neo4j 和 Qdrant 数据。

## 2. 主机前提

- Linux x86_64（amd64）；
- 可用的 rootful Docker Engine 和 Docker Compose v2；不接受 rootless daemon；
- 建议至少 10 GiB 内存；默认四服务内存上限合计 8.5 GiB；
- 足够容纳镜像 TAR、解包内容、四张镜像和评测数据的磁盘空间；
- MemOS 容器能够访问主办方 Chat/Embedding API；
- 不要求访问公网、Docker registry、Python package index 或源码站点；
- 主办方官方评测器及其数据集/命令已在评审机本地可用；
- 宿主机只需常规 shell 工具、`unzip` 和 `sha256sum`，不需要 Python、uv 或 pip。

先以普通用户准备固定目录，并刷新一次 `sudo` 凭据。若该用户已经能直接访问 rootful Docker，
`sudo -v` 之后的脚本仍会优先直接连接同一个 rootful daemon：

```bash
install -d -m 0700 \
  "$HOME/memscope-organizer" \
  "$HOME/.config/memscope" \
  "$HOME/memscope-evaluation"
sudo -v
```

`sudo -v` 只用于后续 Docker 命令提权；不要切换到 root shell，也不要改变 `HOME`。

## 3. 校验和解包

把四个交付文件放到 `$HOME/memscope-organizer/<candidate>/`，然后在该目录执行：

```bash
sha256sum -c SHA256SUMS
unzip solution-<candidate>.zip
cd solution
```

任何 hash 不一致都停止，不加载镜像。`delivery-manifest.json` 记录候选 commit、目标架构、文件 hash
以及四张镜像的 ID；解包后的 `RELEASE_LOCK.tsv` 是启动脚本使用的同一镜像锁。

## 4. 私有运行时配置

配置文件必须放在解包目录之外、仍位于当前用户的 `$HOME` 内，并且只允许当前用户读取：

```bash
umask 077
cp deploy/organizer.env.example "$HOME/.config/memscope/organizer.env"
chmod 0600 "$HOME/.config/memscope/organizer.env"
```

编辑该文件，只替换秘密占位符。不要把真实 Key、IAM token 或 Neo4j 密码写回 ZIP、源码、命令行、
报告或聊天。B10 已知的主办方非秘密配置是：

- Chat：`http://aigateway.huawei.com/v1`，模型 `GLM-V5_1-DX`；
- Embedding：`http://aigateway.huawei.com/v1`，模型 `bge-m3`，维度 `1024`；
- 主办方内网允许 HTTP，因此 `MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true`；
- 当前候选使用本地 cosine reranker，不调用 `/v1/reranker`。

当前客户端按 OpenAI-compatible Bearer API-key 方式工作。若只提供 IAM token 且 Authorization 语法
不同，必须先由主办方明确完整 header 规则，不能把示例中的二选一占位文本直接写入配置。

## 5. 一键加载并启动

从解包后的 `solution/` 目录执行；将文件名替换为实际名称：

```bash
./scripts/run_release.sh \
  --image-bundle ../memscope-images-<candidate>-linux-amd64.tar \
  --sha256-file ../SHA256SUMS \
  --env-file "$HOME/.config/memscope/organizer.env"
```

脚本会再次校验完整交付集、执行 `docker load`、核对四张镜像 ID 和两张自建镜像的源码 revision，
然后执行 Compose `config --quiet` 和 `up --no-build --pull never --wait`。它不会安装依赖、构建、
拉取、访问软件源或删除卷。脚本拒绝 rootless daemon 和 `$HOME` 之外的 solution、env、image TAR、
lock 或 checksum 路径；若直接 Docker 权限不可用，会使用已由 `sudo -v` 授权的 `sudo -n docker`。

若镜像已加载且只需重启，可增加 `--skip-load`；镜像 ID 仍会被核对。

## 6. 上线前 Smoke

```bash
./scripts/verify_release.sh \
  --env-file "$HOME/.config/memscope/organizer.env"
```

验证脚本检查四容器 Health、Neo4j 查询、Qdrant `/readyz`，再从 `memory-api` 容器内执行一次真实
Health、Add/replay、跨 session Search 和跨用户隔离 Smoke。宿主机不运行 Python。输出只包含状态、
耗时和 evidence 数量，不包含请求正文、记忆内容、向量、Key 或 provider 完整响应。

Smoke 会写入一个唯一测试用户的数据，并会调用真实 Chat/Embedding API。Add 必须小于 120 秒，
Search 必须小于 60 秒；任一失败都不得继续正式评测。

## 7. 执行正式评测

Smoke 通过后，把主办方官方评测器的服务地址设为：

```text
http://127.0.0.1:8080
```

若 `MEMSCOPE_PUBLIC_PORT` 被改为其它值，使用脚本最后打印的实际端口。官方评测器按比赛契约调用：

- `GET /health`
- `POST /add`
- `POST /search`

正式评分逻辑和数据集由主办方评测器提供；交付包不伪造 Answer/Judge，也不得把 gold answer 传给
`/search`。批量评测器需要自行执行速率控制，并对 429 做有界退避；服务内部不会自动重放 Add。
评测器的输入、输出、临时文件和脱敏报告统一放在
`$HOME/memscope-evaluation/<candidate>/`，不得写入 `/root` 或系统目录。

## 8. 停止、保留和失败处理

正常停止并保留全部命名卷：

```bash
./scripts/stop_release.sh \
  --env-file "$HOME/.config/memscope/organizer.env"
```

禁止执行 `docker compose down -v`、`docker system prune` 或删除候选卷。失败时保留容器和卷，只记录
候选 commit、交付文件 hash、四张镜像 ID、容器/Health 状态、阶段耗时和脱敏错误分类。不要打印
私有 env、完整 Compose 展开结果、请求正文、向量或 provider 响应；不要在评审机修改源码或重建
镜像。

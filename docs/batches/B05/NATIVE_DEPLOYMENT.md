# B05 非 Docker 部署指南

> 目标：当主办方机器无法使用 Docker/Compose 时，仍能部署与 Docker 基线等价的
> `memory-api + MemOS v2.0.32 + Neo4j + Qdrant` Real Add 服务。
>
> 边界：本指南只覆盖 B05 Add。B06 完成前，公开 `/health` 和 `/search` 返回 503 是预期行为。
>
> 时间约束：先执行 [48 小时交付止损规则](../../collaboration/48H_DELIVERY_GUARDRAILS.md)。Docker
> 预检或排障达到上限后直接使用本指南，不再重复尝试构建。

## 1. 什么时候使用本方案

以下任一情况出现时，直接使用非 Docker 方案，不要继续消耗调优时间修容器环境：

- 无 Docker daemon、无 Compose 插件或没有访问 daemon 的权限；
- rootless Docker 无法发布端口；
- 宿主机不支持 cgroup，容器资源限制无法实际生效；
- 镜像仓库访问持续不稳定，但 Python 包和数据库服务可以正常取得；
- 主办方已经提供可访问的 Neo4j、Qdrant 或统一模型网关。

Docker 与本方案共享相同的代码、MemOS archive、patchset、数据模型和环境变量。切换部署方式
不允许修改 prompt、绕过 readback、打开 scheduler 或把失败降级成 raw-text success。

## 2. 最低环境要求

- Linux x86_64；
- CPython `3.11.x`，不要使用 3.12/3.13；
- 可写的持久化目录，例如 `/srv/memscope/data`；
- Neo4j Community `5.26.6`；
- Qdrant `1.15.3`；
- 能访问 OpenAI-compatible Chat/Embedding API 的 MemOS 进程；
- 建议至少 8 GiB 内存。进程和数据库资源限制由 systemd、主办方平台或其他进程管理器负责。

推荐创建独立、无登录权限的系统用户 `memscope`。MemOS、Neo4j 和 Qdrant 不应直接监听公网；
只有 memory-api 的比赛端口可以对评测端开放。

## 3. 目录约定

下文使用以下变量。请替换为主办方实际路径，不要直接复制占位凭据：

```bash
export MEMSCOPE_REPO=/srv/memscope/repository
export MEMOS_SOURCE=/srv/memscope/memos-v2.0.32
export MEMSCOPE_DATA=/srv/memscope/data
export MEMSCOPE_VENV=/srv/memscope/venv-api
export MEMOS_VENV=/srv/memscope/venv-memos
```

创建目录并确保只有服务用户可写：

```bash
install -d -m 0750 "$MEMSCOPE_DATA" "$MEMSCOPE_DATA/memos-files"
```

Raw Store 和 Gateway receipt 必须是两个不同文件：

```text
/srv/memscope/data/raw.db
/srv/memscope/data/gateway-receipts.db
```

不要把 SQLite 文件放在 NFS、对象存储挂载或其他不保证本地文件锁/WAL 语义的文件系统上。

## 4. 校验并准备固定 MemOS 源码

从仓库根目录执行：

```bash
cd "$MEMSCOPE_REPO/third_party/memos"
sha256sum --check SHA256SUMS
```

期望 archive SHA-256：

```text
9a804fd874932f0a4fd86f75fa4edb48fdd41807417f236bacda49b8664cdf3c
```

解压到一个全新空目录，不要覆盖曾经打过补丁的目录：

```bash
install -d -m 0750 "$MEMOS_SOURCE"
tar --extract --gzip \
  --file "$MEMSCOPE_REPO/third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz" \
  --strip-components=1 \
  --directory "$MEMOS_SOURCE"
```

先验证锁定 preimage，再一次性应用 B04+B05 patchset：

```bash
python3.11 "$MEMSCOPE_REPO/docker/memos/apply_patchset.py" \
  --source "$MEMOS_SOURCE" \
  --verify-only
python3.11 "$MEMSCOPE_REPO/docker/memos/apply_patchset.py" \
  --source "$MEMOS_SOURCE"
```

patchset 故意不可重复应用。任何 hash/anchor mismatch 都必须停止部署并重新取得原始 archive；
不要手工模糊替换或跳过校验。

## 5. 安装两个隔离的 Python 环境

memory-api：

```bash
python3.11 -m venv "$MEMSCOPE_VENV"
"$MEMSCOPE_VENV/bin/python" -m pip install \
  --index-url https://repo.huaweicloud.com/repository/pypi/simple \
  --requirement "$MEMSCOPE_REPO/docker/memory-api/requirements.txt"
"$MEMSCOPE_VENV/bin/python" -m pip install --no-deps "$MEMSCOPE_REPO"
```

MemOS：

```bash
python3.11 -m venv "$MEMOS_VENV"
"$MEMOS_VENV/bin/python" -m pip install \
  --index-url https://repo.huaweicloud.com/repository/pypi/simple \
  --constraint "$MEMSCOPE_REPO/docker/memos/constraints.txt" \
  --requirement "$MEMOS_SOURCE/docker/requirements.txt"
```

华为云源只是显式的下载加速入口，所有包仍由 requirements/constraints 固定版本。如果该源缺包，
可以显式换成主办方审核过的清华源、官方 PyPI 或内部 wheel 仓库；不要配置静默多源 fallback。

## 6. 配置 Neo4j 和 Qdrant

可以使用主办方已有实例，也可以用系统包/独立二进制运行。必须满足：

- Neo4j Bolt 地址仅对 MemOS 可达，例如 `bolt://127.0.0.1:7687`；
- 使用非默认强密码，数据库名为 `neo4j`；
- Qdrant HTTP 地址仅对 MemOS 可达，例如 `127.0.0.1:6333`；
- Qdrant 数据目录持久化；
- Qdrant collection 的向量维度必须与实际 Embedding 模型完全一致；
- 不复用曾由其他维度模型创建的 `neo4j_vec_db` collection。

启动数据库后做最小探测：

```bash
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p '<private-password>' 'RETURN 1;'
curl -fsS http://127.0.0.1:6333/readyz
```

## 7. MemOS 环境文件

创建权限为 `0600` 的 `/srv/memscope/memos.env`。以下值中的模型 ID、URL、Key 和维度必须由
调测/部署人员提供，不能使用示例值上线：

```bash
MEMSCOPE_MODEL_PROFILE=gateway
MEMOS_BASE_PATH=/srv/memscope/data
FILE_LOCAL_PATH=/srv/memscope/data/memos-files

GRAPH_DB_BACKEND=neo4j-community
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD='replace-with-private-password'
NEO4J_DB_NAME=neo4j
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333
EMBEDDING_DIMENSION='replace-with-exact-positive-integer'

MEMRADER_MODEL='replace-with-extractor-model-id'
MEMRADER_API_BASE='https://replace-with-model-gateway/v1'
MEMRADER_API_KEY='replace-with-private-key'
MEMRADER_TIMEOUT_SECONDS=110
MEMREADER_ENABLE_BACKUP=false

MOS_CHAT_MODEL_PROVIDER=openai
MOS_CHAT_MODEL='replace-with-extractor-model-id'
OPENAI_API_BASE='https://replace-with-model-gateway/v1'
OPENAI_API_KEY='replace-with-private-key'

MOS_EMBEDDER_BACKEND=universal_api
MOS_EMBEDDER_PROVIDER=openai
MOS_EMBEDDER_MODEL='replace-with-embedding-model-id'
MOS_EMBEDDER_API_BASE='https://replace-with-model-gateway/v1'
MOS_EMBEDDER_API_KEY='replace-with-private-key'
MOS_EMBEDDER_TIMEOUT=5
MOS_EMBEDDER_BACKUP_CLIENT=false

MEM_READER_BACKEND=simple_struct
MEM_READER_TOKENIZER=word
MEM_READER_CHAT_WINDOW_MAX_TOKENS=1024
MEM_READER_REMOVE_PROMPT_EXAMPLE=false
SIMPLE_STRUCT_ADD_FILTER=false
MEM_READER_SAVE_RAWFILENODE=false
MOS_RERANKER_BACKEND=cosine_local
MOS_FEEDBACK_RERANKER_BACKEND=cosine_local
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
ENABLE_CHAT_API=false
ENABLE_INTERNET=false
ENABLE_ACTIVATION_MEMORY=false
ENABLE_PREFERENCE_MEMORY=false
ENABLE_DINGDING_BOT=false
MOS_ENABLE_SCHEDULER=false
API_SCHEDULER_ON=false
MOS_ENABLE_REORGANIZE=false
MEMSCHEDULER_USE_REDIS_QUEUE=false
MOS_ENABLE_DEFAULT_CUBE_CONFIG=true
NACOS_ENABLE_WATCH=false
```

生产 profile 要求模型 URL 使用 HTTPS，Key 不能是 `EMPTY`，Embedding 维度必须为正整数。
替换全部 `replace-with-*` 值后再启动；原生路径没有容器 entrypoint 代做这项检查。

## 8. memory-api 环境文件

创建权限为 `0600` 的 `/srv/memscope/memory-api.env`：

```bash
APP_PROFILE=memos_add
HOST=0.0.0.0
PORT=8080
LOG_LEVEL=INFO
LOG_FORMAT=json
CONTEST_AUTH_MODE=none
DATABASE_PATH=/srv/memscope/data/raw.db
MEMOS_GATEWAY_RECEIPT_PATH=/srv/memscope/data/gateway-receipts.db
SQLITE_BUSY_TIMEOUT_MS=5000
MEMOS_BASE_URL=http://127.0.0.1:8000
ADD_DEADLINE_SECONDS=115
ADD_WARN_SECONDS=105
MEMOS_DEADLINE_RESERVE_SECONDS=5
MEMOS_CONNECT_TIMEOUT_SECONDS=3
MEMOS_RESPONSE_MAX_BYTES=1048576
```

如果主办方要求 shared key，再设置：

```bash
CONTEST_AUTH_MODE=shared_key
CONTEST_API_KEY='replace-with-organizer-provided-key'
```

## 9. 启动顺序

按以下顺序启动，每个进程固定一个 worker：

1. Neo4j；
2. Qdrant；
3. MemOS；
4. memory-api。

开发/人工验证启动命令：

```bash
set -a
. /srv/memscope/memos.env
set +a
PYTHONPATH="$MEMOS_SOURCE/src" \
  "$MEMOS_VENV/bin/python" -m uvicorn memos.api.server_api:app \
  --host 127.0.0.1 --port 8000 --workers 1
```

另开终端：

```bash
set -a
. /srv/memscope/memory-api.env
set +a
"$MEMSCOPE_VENV/bin/python" -m uvicorn memscope.main:app \
  --host 0.0.0.0 --port 8080 --workers 1
```

正式运行建议由 systemd 或主办方进程管理器托管，并设置：

- 专用非 root 用户；
- `Restart=on-failure`；
- MemOS 在数据库网络探测成功后启动；
- memory-api 在 `GET http://127.0.0.1:8000/health` 返回
  `{"status":"healthy"}` 后启动；
- `TimeoutStopSec=30`；
- stdout/stderr 进入有大小和保留期限制的日志系统；
- 文件权限确保只有服务用户可读环境文件和数据目录。

不要启动多个 memory-api worker。B05 的同用户有序 lane 是进程内语义，多 worker 会破坏该保证。

## 10. 验证

先验证 MemOS 进程：

```bash
curl -fsS http://127.0.0.1:8000/health
```

B05 的 memory-api `/health` 会故意返回 503，因为 B06 Search 尚未实现。这不能用于判定 Add 失败。
使用独立的 socket/process liveness 探针，并执行一次非敏感测试 Add：

```bash
curl -sS -X POST http://127.0.0.1:8080/add \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id":"native-smoke-1",
    "user_id":"native-smoke-user",
    "session_id":"native-smoke-session",
    "messages":[{"role":"user","content":"The preferred test color is green."}]
  }'
```

期望同步返回：

```json
{"success":true,"request_id":"native-smoke-1","user_id":"native-smoke-user","session_id":"native-smoke-session"}
```

使用完全相同请求再调用一次，必须返回相同结果且 provider 不增加重复节点。修改同一 `request_id`
的任一消息后重放，必须返回 409。

## 11. 常见故障

| 现象 | 首先检查 | 禁止做法 |
|---|---|---|
| memory-api 启动失败 | MemOS health、两个 SQLite 路径是否不同且可写 | 改回 core 后宣称服务可用 |
| Add 500 `gateway.protocol_invalid` | MemOS response schema、readback marker、vector_sync | raw-text fallback |
| Add 500 `gateway.timeout`/`add.timeout` | 模型 TTFT/总耗时、网络、115 秒预算 | 把 deadline 提高到 120 秒或以上 |
| Qdrant dimension mismatch | 实际 Embedding 维度和既有 collection | 猜测维度或截断向量 |
| patchset hash mismatch | 是否使用全新固定 archive | 手工忽略 hash |
| 同用户消息顺序异常 | 是否误开多个 worker/副本 | 用 prompt 猜测顺序 |
| `/health` 503 | B05 尚无 Search，属于预期 | 修改成虚假 200 |

## 12. 数据备份与回滚

停止 memory-api 和 MemOS 后，再一致性备份：

- `/srv/memscope/data/raw.db*`；
- `/srv/memscope/data/gateway-receipts.db*`；
- Neo4j 数据库；
- Qdrant storage；
- 当前环境文件的脱敏配置摘要和 MemOS patchset lock。

SQLite 使用 WAL，不能只在进程运行时复制单个 `.db` 文件。优先使用 SQLite backup API，或停止服务后
一并备份 `.db`、`-wal`、`-shm`。

回滚部署版本时保留全部数据，先恢复旧进程/代码并做只读检查。Gateway receipt 不是唯一事实来源；
Raw Store 和带 provenance 的 provider memory 才是审计依据。不要为回滚执行全局数据库清空或 Docker prune。

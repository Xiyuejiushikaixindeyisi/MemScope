# B06 非 Docker 完整部署指南

> 目标：在 Docker/Compose 不可用时，独立部署并验收
> `memory-api + MemOS v2.0.32 + Neo4j + Qdrant` 的 Add、Search 与 Health。
>
> 本指南是正式兜底路径，不是 Docker 失败后的临时降级。执行时遵守
> [48 小时交付止损规则](../../collaboration/48H_DELIVERY_GUARDRAILS.md)：Docker 预检最多 10 分钟，
> 单阶段排障最多 30 分钟，达到上限立即回到本路径。
>
> Docker Compose 与本原生路径共同适用的主办方上线门、存储初始化风险和回退规则见
> [主办方部署与风险控制指南](ORGANIZER_DEPLOYMENT.md)。本文件展开非 Docker 路径的完整命令。

## 1. 固定边界

- Linux x86_64、CPython `3.11.16`、`uv 0.12.9`；
- 固定 MemOS `v2.0.32` commit `185ebdb925911b55c13b7efe666b74e2e292e484`；
- Neo4j Community `5.26.6`、Qdrant `1.15.3`；
- memory-api 和 MemOS 各一个 worker；
- Add hard deadline 115 秒，Search hard deadline 55 秒；
- 不启用自动重试、Raw 成功 fallback、scheduler、reorganizer、外部检索或额外服务；
- 只有 memory-api 比赛端口可对评测端开放，数据库和 MemOS 仅内网/回环可达。

模型 ID、URL、Key、Embedding 维度和真实阈值由部署机探测后填写。不得复制示例占位值上线，也
不得把私钥写入仓库、命令历史或日志。

## 2. 目录和环境

下文假设：

```bash
export MEMSCOPE_REPO=/srv/memscope/repository
export MEMOS_SOURCE=/srv/memscope/memos-v2.0.32
export MEMSCOPE_DATA=/srv/memscope/data
export MEMSCOPE_VENV=/srv/memscope/venv-api
export MEMOS_VENV=/srv/memscope/venv-memos
```

创建本地持久目录：

```bash
install -d -m 0750 "$MEMSCOPE_DATA" "$MEMSCOPE_DATA/memos-files"
```

Raw 和 provider receipt 必须是不同的本地 SQLite 文件：

```text
/srv/memscope/data/raw.db
/srv/memscope/data/gateway-receipts.db
```

不要放在 NFS、对象存储挂载或不保证 SQLite WAL/文件锁语义的文件系统上。

## 3. 校验并准备固定 MemOS

```bash
cd "$MEMSCOPE_REPO/third_party/memos"
sha256sum --check SHA256SUMS
```

固定 archive SHA-256 必须是：

```text
9a804fd874932f0a4fd86f75fa4edb48fdd41807417f236bacda49b8664cdf3c
```

只解压到全新空目录：

```bash
install -d -m 0750 "$MEMOS_SOURCE"
tar --extract --gzip \
  --file "$MEMSCOPE_REPO/third_party/memos/MemoryOS-v2.0.32-185ebdb.tar.gz" \
  --strip-components=1 \
  --directory "$MEMOS_SOURCE"
```

校验 preimage 后一次性应用 B04+B05+B06 patchset：

```bash
python3.11 "$MEMSCOPE_REPO/docker/memos/apply_patchset.py" \
  --source "$MEMOS_SOURCE" --verify-only
python3.11 "$MEMSCOPE_REPO/docker/memos/apply_patchset.py" \
  --source "$MEMOS_SOURCE"
```

任何 archive、hash 或 anchor mismatch 都必须停止；不要手工跳过，也不要对已打补丁目录重复运行。

## 4. 安装两个隔离环境

先确认工具版本：

```bash
python3.11 --version
uv --version
```

memory-api 使用仓库锁文件：

```bash
cd "$MEMSCOPE_REPO"
UV_PROJECT_ENVIRONMENT="$MEMSCOPE_VENV" uv sync --frozen --no-dev
UV_PROJECT_ENVIRONMENT="$MEMSCOPE_VENV" uv sync --frozen --no-dev --offline
```

MemOS 使用固定上游 requirements 和仓库 exact transitive constraints：

```bash
python3.11 -m venv "$MEMOS_VENV"
"$MEMOS_VENV/bin/python" -m pip install \
  --index-url https://repo.huaweicloud.com/repository/pypi/simple \
  --constraint "$MEMSCOPE_REPO/docker/memos/constraints.txt" \
  --requirement "$MEMOS_SOURCE/docker/requirements.txt"
```

包源一次只使用一个明确镜像。镜像缺包或传输失败时，可整体切换到主办方审核的内部仓库、阿里/
清华镜像或官方 PyPI；禁止静默多源 fallback。切换源不允许改变 requirements、constraints 或锁。

## 5. Neo4j 与 Qdrant

可复用主办方已有实例或用系统服务启动固定版本，但必须满足：

- Neo4j Bolt 仅对 MemOS 可达，例如 `bolt://127.0.0.1:7687`；
- 使用非默认强密码，数据库名 `neo4j`；
- Qdrant HTTP 仅对 MemOS 可达，例如 `127.0.0.1:6333`，数据目录持久化；
- collection `neo4j_vec_db` 的维度与真实 Embedding 输出严格一致；
- 不复用由另一维度/模型创建的同名 collection。

```bash
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p '<private-password>' 'RETURN 1;'
curl -fsS http://127.0.0.1:6333/readyz
```

## 6. MemOS 配置

创建权限 `0600` 的 `/srv/memscope/memos.env`：

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
FAST_GRAPH=false
BM25_CALL=false
VEC_COT_CALL=false
FULLTEXT_CALL=false
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

## 7. memory-api 配置

创建权限 `0600` 的 `/srv/memscope/memory-api.env`：

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
SEARCH_DEADLINE_SECONDS=55
SEARCH_WARN_SECONDS=50
MEMOS_SEARCH_MODE=fast
MEMOS_SEARCH_RELATIVITY=0.0
MEMOS_SEARCH_DEDUP=exact
MEMOS_SEARCH_RERANK=true
```

如主办方要求 shared key，再将模式改为 `shared_key` 并通过私有环境文件提供
`CONTEST_API_KEY`。模型、URL、Key、阈值和普通 Search 参数都是运行配置，修改后只重启相关进程，
不重建代码或镜像。

## 8. 启动顺序

顺序固定为 Neo4j → Qdrant → MemOS → memory-api，每个 Python 服务一个 worker。

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

memory-api 启动时会在一个最多 10 秒的共享预算内检查 MemOS `/health` 并执行一次隔离、无写的
Product Search capability probe。probe 失败时进程启动失败；不得改回 core profile 或跳过 probe 后
宣称 ready。

正式运行使用 systemd 或主办方进程管理器，设置专用非 root 用户、`Restart=on-failure`、
`TimeoutStopSec=30`、有界日志保留，并确保环境文件和数据目录仅服务用户可读写。

## 9. Add + Search + Health 验收

先确认内部依赖：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8080/health
```

预期分别是 `{"status":"healthy"}` 和 `{"status":"ok"}`。公共 Health 200 表示 Raw、receipt、当前
MemOS health 和启动 Search probe 均可用，但仍不能替代真实 Add/Search smoke。

使用仓库验证器创建唯一测试用户，执行 Add replay、跨 session Search 和跨用户隔离：

```bash
cd "$MEMSCOPE_REPO"
"$MEMSCOPE_VENV/bin/python" scripts/verify_b06_candidate.py \
  --base-url http://127.0.0.1:8080 --require-hit
```

若启用 shared key，通过进程环境提供 `CONTEST_API_KEY`，不要放在参数中。成功输出只包含状态、耗时、
结果数量和字符计数，不输出记忆正文。必须同时满足 Add `<120s`、Search `<60s`、另一用户零 evidence。

另外用完全相同的 `request_id` 和 payload 重放 Add，响应必须相同且 provider 不新增节点；修改同一
request ID 的消息后重放必须返回 409。检查成功 evidence 的 provider metadata 为 `activated`，不得
以 `resolving` 作为 B06 可见结果。

## 10. 故障定位和止损

| 现象 | 首先检查 | 禁止做法 |
|---|---|---|
| memory-api 启动失败 | MemOS health、Search probe、两个 SQLite 路径 | 跳过 probe 或改 core 后宣称 ready |
| Health 503 | Raw/receipt WAL、当前 MemOS health | 只看 socket 存活 |
| Add timeout/500 | 模型延迟、readback、115 秒预算 | 自动重试、提高到 120 秒、Raw fallback |
| Search timeout/500 | Embedding、Graph/Qdrant、55 秒预算、Product error | 把异常变成空 200 |
| Search 空结果 | user→Cube、`activated`、provenance、relativity | 跨 Cube fallback 或填充低质量结果 |
| Add 成功但仅 resolving | 保存证据并停止 | Search 放行 resolving；须正式修订 B05 接缝 |
| Qdrant dimension mismatch | 实际 embedding 维度和 collection | 猜测维度、截断向量 |
| collection 已存在但配置不明 | Qdrant collection config、数据卷来源 | 让首个正式 Add 试错 |
| Neo4j 索引缺失/未 ONLINE | `SHOW INDEXES`、MemOS 初始化 warning | 只以 MemOS health 判定成功 |
| patch hash mismatch | 全新固定 archive | 忽略 hash 或手工模糊替换 |
| 日志出现 canary 原文 | 是否运行固定 B06 patchset | 继续使用该候选或上传日志 |

日志只能记录长度/hash、候选计数、阶段耗时和 typed error。验收日志若出现 query、options、memory
content、完整 provider response、URL 中凭据或 Key，该候选立即淘汰。

## 11. 回退与数据

- 停止 memory-api，再停止 MemOS；数据库由其各自服务管理；
- 回退代码时保留 Raw、receipt、Neo4j 和 Qdrant 数据快照，不执行全局清理；
- B05 冻结点是 `e7abf5f8140f61cda5d3cee8b17ef8dbd3b0d062`；回退不等于把 B06 写入的数据
  物理删除；
- Embedding 模型/维度变化前，比赛无正式数据时切换到全新的专属 Neo4j/Qdrant 持久目录或卷；已有
  正式数据时必须经过迁移/重嵌入评审，禁止原地混用。固定 collection 名不能靠另建未接线的名称
  实现切换；
- Docker 问题不阻塞本路径。只有模型/数据库能力、固定源码冲突或 B05 `resolving` 语义冲突才是
  核心部署阻塞。

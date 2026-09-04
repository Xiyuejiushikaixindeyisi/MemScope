# B06 主办方部署与存储初始化风险控制

> 受众：接收最终候选并负责启动、验收和开放比赛端口的主办方运维人员。
>
> 本文统一规定 Docker Compose 与非 Docker 原生两条正式路径的上线门。原生安装、环境变量和
> 进程启动的完整命令见 [NATIVE_DEPLOYMENT.md](NATIVE_DEPLOYMENT.md)。Docker 排障受
> [48 小时交付止损规则](../../collaboration/48H_DELIVERY_GUARDRAILS.md)约束：预检最多 10 分钟，
> 单阶段排障最多 30 分钟；到时立即转原生路径，不能阻塞 Add/Search 验收。

## 1. 共同事实与上线硬门

Neo4j、Qdrant 和 MemOS 就绪不是同一个状态：

- Neo4j 服务创建默认 `neo4j` 数据库；MemOS 在 graph backend 初始化时尝试创建向量/属性索引；
- MemOS 在 Qdrant 中创建固定名称 `neo4j_vec_db`；已有同名 collection 时上游会跳过创建，但不会
  强制拒绝错误维度；
- Neo4j 部分索引创建异常在固定 MemOS 中只记录 warning；
- MemOS `/health` 只证明进程可响应，memory-api 启动 Search probe 只证明有界无写检索可调用；两者
  都不能替代一次真实 Add→Search 写读闭环。

无论选择哪条部署路径，开放公共 `8080` 前都必须满足：

1. 最终 Embedding URL、Key 和模型已经实测，实际向量长度等于 `EMBEDDING_DIMENSION`；不得按模型
   名猜测、截断或补零。
2. 首次正式部署使用候选专属的 Neo4j/Qdrant 持久存储，不复用 mock、开发环境或其它 Embedding
   模型的数据。
3. Neo4j `RETURN 1` 和 Qdrant `/readyz` 成功；只监听端口不算就绪。
4. `neo4j_vec_db` 存在、distance 为 cosine、维度等于实测值。
5. Neo4j `memory_vector_index` 和所需属性索引存在且为 `ONLINE`；`POPULATING`、`FAILED`、缺失或
   初始化 warning 均不得放行。
6. memory-api `/health` 返回精确 `{"status":"ok"}`，并且
   `scripts/verify_b06_candidate.py --require-hit` 完整通过。
7. 验证结果同时满足 Add `<120s`、Search `<60s`、Add replay 幂等、跨 session 可检索和跨用户零
   evidence。

任何一项失败都保持 fail-closed：不开放端口，不把异常转换为空 `200`，不启用 Raw/Cube fallback，
不自动重试 Add，不修改 115/55 秒内部 deadline 掩盖问题。

## 2. Docker Compose 路径

### 2.1 适用条件与数据隔离

仅在 10 分钟预检确认 daemon/Compose、host port、cgroup、磁盘和固定镜像来源可用后选择本路径。
Neo4j 和 Qdrant 是两个独立的固定上游镜像，Compose 首次启动会自动创建容器、网络和命名卷；宿主机
不需要另行安装数据库软件。

最终候选使用唯一且固定的 Compose project name，例如 `memscope-b06-final`。这会产生该候选专属的
`neo4j_data`、`neo4j_logs`、`qdrant_data`、`memos_data` 和 `memscope_data` 卷，避免碰到同机旧栈。
不得在验收或回退时运行 `down -v`。

将 `deploy/compose.env.example` 复制到仓库外权限 `0600` 的私有文件，替换全部占位符。校验配置时
使用 quiet 模式，避免插值后的 Key 被打印：

```bash
docker compose -p memscope-b06-final \
  --env-file /srv/memscope/compose.env config --quiet
```

代码冻结后只做一次最终 `memory-api`/`memos` 镜像构建。模型、URL、Key、阈值和普通 Search 参数变化
只修改私有环境文件并重启相关服务，不重建镜像；Embedding 模型/维度变化必须同时切换到全新存储
或经过迁移评审。

交付物是源码候选而不是已签名镜像时，在代码冻结后执行一次：

```bash
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  build memory-api memos
```

### 2.2 分阶段启动与检查

使用同一个 project name 和 env 文件执行：

```bash
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  up -d neo4j qdrant
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  up -d memos
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  up -d memory-api
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env ps
```

每一步都等待对应 health 成功并检查有界日志后再继续。Compose 的 Qdrant healthcheck 目前只验证
TCP 端口，因此还必须从内部网络请求 `/readyz`；Neo4j 必须执行 Cypher，而不是只看容器状态。
验收结束前通过防火墙/安全组限制 `8080` 仅验收来源可达：

```bash
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  exec -T neo4j sh -c \
  'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" "RETURN 1;"'
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  exec -T memos python -c \
  "import urllib.request; print(urllib.request.urlopen('http://qdrant:6333/readyz', timeout=3).read().decode())"
```

从评测端实际可达的位置运行受控真实闭环，使可能的懒初始化发生在唯一测试用户上：

```bash
python3 scripts/verify_b06_candidate.py \
  --base-url http://127.0.0.1:8080 --require-hit
```

闭环通过后再核对最终存储结构：

```bash
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  exec -T memos python -c \
  "import urllib.request; print(urllib.request.urlopen('http://qdrant:6333/collections/neo4j_vec_db', timeout=3).read().decode())"
docker compose -p memscope-b06-final --env-file /srv/memscope/compose.env \
  exec -T neo4j sh -c \
  'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" "SHOW INDEXES YIELD name, type, state, options RETURN name, type, state, options;"'
```

Neo4j/Qdrant 未发布宿主端口；上述检查从内部网络执行。核对 Qdrant response 中的 collection status、
distance 与 dimension，不得为了检查而临时把数据库端口暴露到公网。

只有第 1 节全部成立才开放端口。容器 restart 后必须复核 Health；更换模型/存储或从快照恢复后必须
重新执行完整 smoke。

## 3. 非 Docker 原生路径

### 3.1 适用条件与数据隔离

Docker 预检失败、端口/cgroup 不可靠或排障达到时间盒后，直接采用
[完整原生部署指南](NATIVE_DEPLOYMENT.md)。主办方必须提供固定版本 Neo4j `5.26.6-community` 和
Qdrant `1.15.3`，可以复用经核验的系统服务，也可以新建；不能因为 Docker 不可用而跳过数据库。

首次正式部署使用候选专属持久目录。若复用已有服务，必须先证明目标数据库/collection 没有其它
Embedding 模型数据，并确认服务账号具有创建节点、collection 和索引的权限。Raw/receipt SQLite
仍使用独立的本地 WAL 文件，不放在 NFS 或对象存储挂载上。

### 3.2 分阶段启动与检查

严格执行原生指南中的 Python/MemOS 固定版本校验和环境配置，然后按以下顺序启动：

```text
Neo4j -> Qdrant -> MemOS（一个 worker） -> memory-api（一个 worker）
```

验收结束前通过防火墙/安全组限制 `8080` 仅验收来源可达；Neo4j、Qdrant 和 MemOS 始终只允许服务
内网或回环访问。

数据库检查使用服务自己的接口：

```bash
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p '<private-password>' 'RETURN 1;'
curl -fsS http://127.0.0.1:6333/readyz
curl -fsS http://127.0.0.1:6333/collections/neo4j_vec_db
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p '<private-password>' \
  'SHOW INDEXES YIELD name, type, state, options RETURN name, type, state, options;'
```

然后执行原生指南第 9 节的 Health 和真实 Add/Search verifier。systemd 或主办方进程管理器只能使用
`Restart=on-failure` 恢复进程；它不能把失败的业务请求当作可安全重放的请求。

## 4. 不兼容数据、失败和回退

若同名 Qdrant collection 或 Neo4j vector index 与最终模型/维度不兼容：

1. 停止 memory-api，再停止 MemOS；
2. 保存不含正文、向量和凭据的配置指纹、结构状态、阶段耗时及 typed error；
3. 保留 Neo4j、Qdrant、Raw 和 receipt 数据快照；
4. 尚无正式数据时，改用全新的专属 Compose project/命名卷或原生持久目录重新初始化；
5. 已有正式数据时，进入独立迁移/全量重嵌入评审，不得删除、覆盖或混用。

当前固定 MemOS 写死 collection 名 `neo4j_vec_db`。仅额外创建一个其它名称的 collection 不会自动
切换读写目标。回退代码也不等于安全删除 B06 写入的数据；禁止全局清理和未经确认的 `down -v`。

主办方最终保存的最小证据为：候选 commit/ZIP hash、Compose project 或原生持久目录标识、非密钥
模型/维度指纹、Neo4j/Qdrant 版本与结构状态、公共 verifier 输出、启动/回退结论。不得保存或回传
query、memory content、向量、Key 或完整 provider response。

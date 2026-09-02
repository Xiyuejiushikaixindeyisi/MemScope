# B00 工程基础代码方案

> 状态：Accepted/Frozen，2026-09-02 Gate 2 已验收
> Batch：B00  
> 基线提交：`4a57925aaee6559fe9c48d174357861c8a8a10d4`  
> 建议分支：`batch/b00-engineering-foundation`  
> 方案依据：已批准的 Global Context Brief，以及 `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md` 第 18、19 节  
> 边界：批准仅授权 B00 实施，不授权进入 B01

## 1. 目标

B00 只建立后续 B01～B09 可以稳定依赖的工程底座：

1. 建立 Python 3.11、`src/` layout 和可复现的依赖锁；
2. 建立集中、强类型、可测试的 Settings；
3. 建立默认 JSON 的结构化日志，并保证配置和错误日志不泄漏敏感值；
4. 建立小而稳定的内部异常模型；
5. 建立可注入 Settings 的 FastAPI app factory 和可由 Uvicorn 启动的最小 ASGI 应用；
6. 建立 Ruff、Mypy、Pytest、分支覆盖率和无 Key 默认测试入口；
7. 建立 `PROJECT_CONTEXT.md`、`CODEMAP.md`、ADR 和 Batch 交接文档骨架；
8. 让 B00 产物在无 API/Key、无数据库、无 MemOS 服务时可安装、可测试、可启动、可回滚。

## 2. 非目标

B00 明确不实现：

- 比赛 `/health`、`/add`、`/search` 路由及其 Pydantic 契约；
- 比赛鉴权、请求 ID、HTTP 错误映射或 Answer/Judge 行为；
- Raw Store、SQLite、FTS、迁移、幂等、outbox 或恢复任务；
- `MemoryGateway`、Fake/Real MemOS Client 或 Mock Model API；
- MemCube、Qdrant、Neo4j、Docker Compose、MemOS vendoring；
- 模型 API、Embedding、Rerank、真实 Key 或 capability probe；
- LoCoMo/MemOps 样本执行、代理评分或任何提分启发式；
- B01 及以后 Batch 的公共接口预实现；
- 对未知决赛功能进行猜测性抽象。

最小应用不会伪造 Health：B00 中 `/health`、`/add`、`/search` 必须不存在；B01 才定义赛事 HTTP 契约。

## 3. 前置条件与依赖

### 3.1 Hard dependencies

- 用户明确批准本 Gate 1 方案；
- 实施前再次确认主仓库基线、工作区和 MemOS tag/commit；
- B00 使用 Python 3.11；当前机器只有 Python 3.10.12，因此编码/测试前需要用户批准后准备隔离的 Python 3.11 工具链；
- 依赖解析和锁文件生成需要固定版本的包管理工具及可用包源；若网络或包源不可用，暂停在依赖准备阶段，不用未审计文件绕过；
- MemOS 保持 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`，B00 不修改它。

### 3.2 Soft dependencies

以下缺失不阻塞 B00：

- 主办方 Chat/Embedding/Rerank API 与 Key；
- 正式硬件、超时、并发和失败策略；
- Compose、网络和正式构建限制；
- 决赛交付要求。

这些信息只影响后续 baseline、部署冻结或决赛规划，不在 B00 中猜测默认值。

### 3.3 上游兼容事实

- MemOS v2.0.32 声明支持 Python 3.10～3.13；项目基线选择 Python 3.11；
- MemOS 自托管使用单 worker Uvicorn，并在后续阶段依赖 Neo4j 与 Qdrant；
- MemOS 使用 Apache-2.0；后续 vendoring 必须保留许可证、NOTICE/归属和修改说明；
- B00 不安装、导入或启动 MemOS。

## 4. 工具链与依赖决策

### 4.1 Python 与依赖管理

- Python：`>=3.11,<3.12`；
- 项目布局：`src/memscope`；
- 包管理与锁：固定 `uv 0.12.9`，提交 `uv.lock`，所有测试和运行命令使用 `uv run`；
- 构建后端：固定 `uv_build 0.12.9`，与包管理器保持同一工具链；
- 禁止宽松、未锁定的运行时安装；`uv sync --frozen` 必须成功；
- 后续容器和离线提交如何携带工具与 wheel，由 B04/B09 在主办方条件明确后冻结。

选择 `uv` 的原因是单一跨平台锁文件、快速创建隔离环境和严格 frozen 安装。`0.12.9` 已根据 Astral 官方 2026-09-01 发布记录核验，包含安装安全和凭据脱敏相关修复；它不成为服务运行时业务依赖。

### 4.2 直接依赖

运行时直接依赖与 MemOS v2.0.32 已锁版本对齐，以降低未来协议进程或共享工具环境中的兼容风险：

| 依赖 | 提议版本 | 用途 | 初步许可证口径 |
|---|---:|---|---|
| FastAPI | 0.115.14 | ASGI app factory；B00 不注册赛事路由 | MIT |
| Pydantic | 2.11.7 | 类型模型和校验 | MIT |
| pydantic-settings | 2.10.1 | 集中环境配置 | MIT |
| Uvicorn | 0.35.0 | 单 worker 本地启动 | BSD-3-Clause |

开发/测试依赖：

| 依赖 | 提议版本 | 用途 |
|---|---:|---|
| HTTPX | 0.28.1 | ASGI 测试客户端 |
| Pytest | 8.4.1 | 测试框架 |
| pytest-asyncio | 0.23.8 | 后续异步测试基础 |
| pytest-cov | 6.3.0 | 分支覆盖率 |
| Ruff | 0.11.13 | lint 与格式化 |
| Mypy | 1.17.1 | 严格静态类型检查 |

锁定时必须检查实际元数据、传递依赖和许可证。若版本无法在 Python 3.11 上解析、许可证与初步口径不符或出现依赖冲突，必须暂停并回到 Gate 1；不得静默换版本。

结构化日志使用标准库 `logging`，不为 B00 引入额外日志框架。

## 5. 预计文件与允许修改范围

### 5.1 Gate 1 已创建

- `docs/batches/B00/PLAN.md`
- `docs/batches/B00/CONTEXT.md`
- `MEMOS_BASELINE_IMPLEMENTATION_PLAN.md`：仅包含本轮已获用户要求的决赛扩展性和外部待确认项。

### 5.2 B00 审批后预计新增

```text
.python-version
.env.example
README.md
pyproject.toml
uv.lock
src/
└── memscope/
    ├── __init__.py
    ├── app.py
    ├── errors.py
    ├── logging_config.py
    ├── main.py
    └── settings.py
tests/
├── conftest.py
├── smoke/
│   └── test_minimal_app.py
└── unit/
    ├── test_app.py
    ├── test_errors.py
    ├── test_logging_config.py
    └── test_settings.py
docs/
├── PROJECT_CONTEXT.md
├── CODEMAP.md
├── adr/
│   └── 0001-python-toolchain-and-layout.md
└── batches/B00/
    └── HANDOFF.md             # 仅在 Gate 2 交付时创建
```

### 5.3 B00 审批后预计修改

- `.gitignore`：补充构建产物、包元数据和本地工具缓存；保留 `.env.example`、`.vendor-src/` 和敏感文件规则；
- `docs/batches/B00/PLAN.md` / `CONTEXT.md`：只允许同步已批准修订、实际测试命令和上下文变化；
- `docs/PROJECT_CONTEXT.md` / `CODEMAP.md`：只记录当前有效事实与已实现结构。

### 5.4 禁止修改

- `.vendor-src/MemOS/**`；
- `docs/achieve/**`；
- 评测集、`official/**`、Smoke 样本和代理评测脚本；
- 比赛任务书、调测指南和 API 契约；
- B01～B09 方案或代码；
- 任何 Key、`.env`、运行数据、缓存或虚拟环境。

如实现必须越过上述范围，立即暂停并重新评审。

## 6. 模块职责与依赖方向

```text
memscope.main
    └── memscope.app.create_app
          ├── memscope.settings.AppSettings
          ├── memscope.logging_config.configure_logging
          └── memscope.errors

tests ──> 上述公共入口
```

约束：

- `settings` 和 `errors` 不依赖 FastAPI；
- `logging_config` 只依赖标准库和 Settings 的只读值；
- `app` 可以依赖 FastAPI，但不得包含比赛业务或存储逻辑；
- `main` 只负责组装默认 Settings 并暴露 ASGI `app`；
- 所有后续业务模块通过 app factory 显式装配，不读取隐式全局配置；
- B00 启动不得进行网络、数据库、文件写入或模型调用。

## 7. 外部 API、内部接口和数据模型

### 7.1 外部 API

B00 不承诺赛事 HTTP API。FastAPI 自带的 OpenAPI/文档路由只用于证明 ASGI 应用可运行，不视为比赛契约。`/health`、`/add`、`/search` 在 B00 应返回 404。

### 7.2 内部公共入口

计划提供以下最小入口：

```python
class AppSettings(BaseSettings): ...

def load_settings() -> AppSettings: ...

def configure_logging(settings: AppSettings) -> None: ...

class MemScopeError(RuntimeError): ...
class ConfigurationError(MemScopeError): ...

def create_app(settings: AppSettings | None = None) -> FastAPI: ...

app: FastAPI
```

接口语义：

- `load_settings` 从环境和可选本地 `.env` 加载，返回完整校验后的不可随意扩展配置对象；
- `create_app(settings)` 支持测试显式注入；未传入时只通过 `load_settings` 获取配置；
- `configure_logging` 可重复调用但不得叠加 handler；
- `MemScopeError` 至少包含稳定 `code`、安全 `message` 和 `retryable`；B00 不定义 HTTP 映射；
- 启动配置错误转换为不包含原始环境值的 `ConfigurationError`。

### 7.3 Settings 字段

| 环境变量 | 类型/允许值 | 默认值 | B00 语义 |
|---|---|---|---|
| `APP_PROFILE` | `core` | `core` | B00 只接受 `core`；其它 profile 在对应 Batch 交付前 fail fast |
| `HOST` | 非空 IP/主机字符串 | `0.0.0.0` | Uvicorn bind host |
| `PORT` | 1～65535 整数 | `8080` | Uvicorn bind port |
| `LOG_LEVEL` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` | `INFO` | 大小写规范化后校验 |
| `LOG_FORMAT` | `json/console` | `json` | 正式默认 JSON，本地可选 console |

B00 不提前加入数据库、MemOS、模型、鉴权或 fallback 变量。后续变量按对应 Batch 评审增加。`.env.example` 仅包含非密钥安全示例和注释。

### 7.4 日志模型

JSON 日志至少包含：

- `timestamp`：UTC ISO-8601；
- `level`；
- `logger`；
- `event`；
- `error_code`、`retryable`：仅错误事件存在。

不默认序列化异常 context、Settings 原始输入或任意对象。字段名包含 `key`、`token`、`secret`、`authorization`、`password` 时必须拒绝或输出 `[REDACTED]`。B00 不记录原始对话内容。

## 8. 不变量

1. 配置只有一个权威入口，业务模块不得直接调用 `os.getenv()`；
2. 无效配置在应用 ready 前失败，不以静默默认值继续；
3. 配置错误和日志不得暴露环境变量原始敏感值；
4. 重复配置日志不会产生重复 handler 或重复记录；
5. 默认启动不依赖网络、数据库、MemOS 或任何 Key；
6. app factory 可被测试独立创建，不依赖模块重载；
7. `/health`、`/add`、`/search` 在 B00 不存在；
8. 运行代码使用完整类型标注；Mypy strict 通过；
9. 锁文件与 `pyproject.toml` 同步，`uv sync --frozen` 不改文件；
10. 测试只统计本项目代码，不统计 `.vendor-src` 和评测数据；
11. 导入和启动不写工作区或用户目录；
12. 不提交 Secret、虚拟环境、缓存或运行产物。

## 9. 正常流程、异常流程和状态转换

### 9.1 正常启动

```text
进程启动
  → load_settings
  → 完整校验与规范化
  → configure_logging（幂等）
  → create_app
  → ASGI ready
  → Uvicorn 单 worker 提供服务
  → 收到终止信号后无状态退出
```

### 9.2 异常启动

```text
配置缺失/格式非法/组合不支持
  → 生成脱敏 ConfigurationError
  → 记录单条安全错误
  → 非零退出
  → 不绑定端口、不进入部分 ready 状态
```

日志初始化异常直接 fail fast。B00 没有外部调用，因此没有网络重试、熔断或降级路径。

### 9.3 状态模型

```text
UNINITIALIZED → CONFIG_VALIDATED → LOGGING_READY → APP_READY → STOPPED
       └────────────── validation failure ──────────────→ FAILED
```

B00 不持久化运行状态；重启等价于重新执行确定性初始化。

## 10. 超时、重试、降级、幂等和恢复

- 超时：没有外部 I/O 超时；启动 Smoke 最多等待 5 秒，防止测试挂死；
- 重试：无；配置或初始化失败必须显式失败；
- 降级：无；不得将无效配置降级为貌似可用的应用；
- 幂等：日志配置必须进程内幂等；app factory 多次创建互不污染；
- 恢复：无持久状态；修正配置后重启；
- 进程：开发和 baseline 默认单 worker，B00 不实现多 worker 协调。

## 11. 可扩展点与延后实现

B00 只保留真实变化边界：

- app factory 后续注册路由和生命周期依赖；
- Settings 后续按 Batch 增加数据库、MemOS、模型和故障策略；
- `MemScopeError` 后续由 B01 映射为 HTTP 错误；
- JSON 日志后续增加 request/user/cube 相关的脱敏关联字段；
- `PROJECT_CONTEXT`、`CODEMAP` 和 ADR 为决赛未知需求提供可恢复上下文。

本轮不定义 `MemoryGateway`、`RawStore`、`Clock` 等尚无调用方的协议；它们在首次真实使用的 Batch 评审，避免空抽象。

## 12. 测试与质量矩阵

| 层级 | B00 用例 | 通过标准 |
|---|---|---|
| 单元：Settings | 默认值、环境覆盖、大小写规范化、非法端口、非法枚举、不支持 profile、显式注入 | 所有分支确定性通过；错误不含原始敏感值 |
| 单元：日志 | JSON 可解析、必填字段、等级、异常、脱敏、重复初始化 | 无重复 handler/记录，无敏感值 |
| 单元：异常 | 稳定 code/message/retryable、继承关系、安全字符串化 | 不依赖 FastAPI，不泄漏 context |
| 单元：app factory | 显式 Settings、默认 Settings、多实例隔离、元数据 | 不做外部 I/O，不产生共享可变状态 |
| 内部契约 | 上述公共入口可从固定模块导入；签名和类型检查 | B01 可只依赖公开入口 |
| ASGI 集成 | HTTPX 访问 OpenAPI；赛事三个路径均为 404 | 最小应用可响应且未越界实现 B01 |
| 启动 Smoke | Uvicorn 单 worker 启动、5 秒内可连接、SIGTERM 正常退出 | 无 Key、无外部服务即可运行 |
| 故障 | 非法环境、日志配置非法、端口配置越界 | ready 前失败且非零退出 |
| 文件系统 | 启动与测试前后比较工作区受控路径 | 不生成未忽略运行数据；不写源码目录 |
| 性能 Smoke | 记录 import/app 创建耗时，验证初始化无外部 I/O | 仅建立本地基线；正式阈值等待硬件信息 |

质量门禁：

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

覆盖率规则：

- `branch = true`；
- 只统计 `src/memscope`；
- 总语句覆盖率不低于 95%；
- 总分支覆盖率不低于 90%；
- Settings、日志脱敏和启动失败关键分支必须直接覆盖，不得仅靠总覆盖率掩盖。

## 13. 风险与缓解

| 风险 | 影响 | 缓解/停止条件 |
|---|---|---|
| 当前没有 Python 3.11 和 uv | 无法按目标环境生成锁并测试 | 审批后在隔离环境准备；未获安装授权前不执行 |
| 包源或网络不可用 | 无法解析锁或干净安装 | 停止并请求受信任镜像/wheelhouse；不临时放宽版本 |
| 工具版本与 Python 冲突 | B00 不可复现 | 锁解析失败即回到 Gate 1，不静默升级/降级 |
| B00 提前定义业务接口 | B01 被错误约束 | 测试赛事路径 404；禁止新增业务模块 |
| 日志泄漏未来 Key/对话 | 合规和安全风险 | 默认 allowlist 字段、敏感字段脱敏、专项测试 |
| Settings 一次加入过多变量 | 非法组合和维护成本增加 | B00 只加入五个启动必需变量 |
| 过度抽象未知决赛需求 | 复杂度上升、交付变慢 | 只抽象已有两个实现或明确变化边界；新需求重新评审 |
| 本机性能不能代表评测机 | 错误冻结阈值 | B00 仅记录本地启动基线，不冻结正式 P95 |
| 依赖许可证遗漏 | 提交合规风险 | B00 记录直接依赖；B09 生成完整第三方通知 |

## 14. 回滚方式

B00 不包含数据库迁移或持久数据。回滚采用非破坏性的 Git revert：

1. 保留总实施方案中已确认的项目约束；
2. revert B00 代码和工程配置提交；
3. 删除仅由该提交引入、且确认无用户数据的本地虚拟环境属于开发机清理，不纳入自动脚本；
4. 回到基线提交后重新提交 Gate 1。

禁止使用 `git reset --hard` 或覆盖用户工作区。

## 15. Gate 1 待审批点

请审批以下整体决策：

1. Python 3.11 + `src/` layout；
2. 固定 uv/uv_build 0.12.9、提交 `uv.lock`；
3. 与 MemOS lock 对齐的 FastAPI/Pydantic/Uvicorn 直接版本；
4. 标准库 JSON logging，不引入 structlog；
5. B00 Settings 仅包含 `APP_PROFILE/HOST/PORT/LOG_LEVEL/LOG_FORMAT`；
6. B00 最小应用不实现 `/health`，赛事三个路径保持 404；
7. 95% 语句、90% 分支覆盖率与 Mypy strict；
8. 上述新增/修改文件范围；
9. 审批后允许创建 `batch/b00-engineering-foundation`；
10. 安装或准备 Python 3.11、uv 和锁定依赖仍属于审批后的实施动作，本轮不执行。

任一项需要调整时，应先修订本方案，再进入代码。

## 16. Definition of Done

B00 只有同时满足以下条件才可进入 Code Review：

- 在批准的 B00 分支完成，实际文件未超出允许范围；
- Python 3.11 环境中 `uv sync --frozen` 从干净环境成功；
- Ruff format/check、Mypy strict、Pytest 全部通过；
- 覆盖率达到 95% 语句、90% 分支，关键错误路径有直接测试；
- 无 Key、无 MemOS、无 Qdrant、无 Neo4j、无数据库即可启动；
- Uvicorn 单 worker 在 5 秒 Smoke 窗口内 ready，并可正常终止；
- `/health`、`/add`、`/search` 均未实现；
- 无效配置在 ready 前脱敏失败；日志配置幂等且敏感字段不泄漏；
- 启动和测试不进行外部网络/模型调用，不写运行数据到源码目录；
- `README.md` 给出环境准备、冻结安装、质量检查和最小启动命令；
- `PROJECT_CONTEXT.md`、`CODEMAP.md`、ADR 与实现一致；
- 依赖用途、固定版本和许可证检查有记录；
- `git diff --check` 通过，工作区无意外缓存、Secret 或运行产物；
- 交付 Gate 2 所需的 `HANDOFF.md`、实际测试命令/结果/耗时/覆盖率和已知限制；
- 用户完成 Gate 2 验收前，不开始 B01。

## 17. 重新评审触发器

除总方案第 18、19 节的通用触发器外，B00 出现以下情况必须暂停：

- 需要 Python 3.11 以外的目标版本；
- 更换包管理器、构建后端或任一直接依赖版本；
- 新增运行服务、数据库、容器或外部网络调用；
- 提前实现赛事路由或 B01+ 业务；
- 修改 MemOS 源码/tag/commit；
- 日志或 Settings 公共语义需要实质变化；
- 无法达到冻结安装、类型检查或覆盖率门禁；
- 修改范围超出第 5 节。

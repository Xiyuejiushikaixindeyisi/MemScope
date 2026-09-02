# B00 Gate 2 Handoff

> 状态：Code Review，等待用户 Gate 2 验收
> Gate 1 文档提交：`099e659447680eac973bc8efc20e05ece9f4078d`
> 实现提交：`ff2484b7732671c3c96f35ad3dd25b4da108618c`
> 分支：`batch/b00-engineering-foundation`
> 日期：2026-09-02

## 1. 交付能力

B00 已建立：

- CPython 3.11.16、uv/uv_build 0.12.9 和完整 `uv.lock`；
- `src/memscope` Python 包布局；
- 集中、冻结、强类型的 B00 Settings；
- 默认 JSON、可选 console 的幂等日志配置；
- transport-independent `MemScopeError` / `ConfigurationError`；
- 可注入 Settings 的 FastAPI app factory 和默认 ASGI composition root；
- Ruff、Mypy strict、Pytest、分支覆盖率和真实 Uvicorn 启停 Smoke；
- `PROJECT_CONTEXT.md`、`CODEMAP.md` 和工具链 ADR。

服务在无 Key、无数据库、无 MemOS、无 Qdrant、无 Neo4j 时可安装、导入、测试和启动。

## 2. 方案条目与实现位置

| Gate 1 条目 | 实现位置 |
|---|---|
| Python、依赖与质量工具 | `.python-version`、`pyproject.toml`、`uv.lock` |
| Settings | `src/memscope/settings.py`、`.env.example` |
| 内部异常 | `src/memscope/errors.py` |
| 结构化日志 | `src/memscope/logging_config.py` |
| 最小应用与组装入口 | `src/memscope/app.py`、`src/memscope/main.py` |
| 单元、ASGI、故障与进程 Smoke | `tests/unit/`、`tests/smoke/` |
| 开发说明 | `README.md` |
| 稳定上下文和依赖导航 | `docs/PROJECT_CONTEXT.md`、`docs/CODEMAP.md` |
| 工具链长期决策 | `docs/adr/0001-python-toolchain-and-layout.md` |

## 3. 公共接口

下游 B01 可以依赖：

```python
from memscope.app import create_app
from memscope.errors import ConfigurationError, MemScopeError
from memscope.logging_config import configure_logging
from memscope.settings import AppSettings, load_settings
```

以及默认 ASGI 入口：

```text
memscope.main:app
```

保证：

- `create_app(settings)` 支持显式 Settings 注入；
- `load_settings()` 把 Pydantic 原始输入错误转换为只含字段名的安全错误；
- `configure_logging()` 可重复调用且只维护一个 MemScope handler；
- `MemScopeError` 提供稳定 `code`、安全 `message` 和 `retryable`；
- Settings 与 errors 不依赖 FastAPI。

下游不得依赖 formatter 私有字段、logger handler 类型、Pydantic 内部 source 顺序或 app factory
内部语句顺序。

## 4. 不变量与错误语义

- B00 配置只有 Settings 一个入口；运行模块没有直接 `os.getenv()`；
- 无效配置在 ASGI ready 前以 `configuration.invalid` 非重试错误失败；
- 配置错误不包含原始环境值；日志只输出 allowlist 字段；
- 默认启动不访问网络、数据库、模型或外部服务，不写源码目录；
- 重复日志配置不累积 handler；多次 app factory 创建不共享 Settings 状态；
- B00 无持久状态、重试、熔断或降级；修复配置后重新启动；
- 默认单 worker；多 worker 一致性不属于 B00；
- `/health`、`/add`、`/search` 均保持 404，由 B01 定义。

## 5. 配置

| 变量 | 默认值 | B00 允许值/范围 |
|---|---|---|
| `APP_PROFILE` | `core` | 仅 `core` |
| `HOST` | `0.0.0.0` | trim 后非空字符串 |
| `PORT` | `8080` | 1～65535 |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL，不区分输入大小写 |
| `LOG_FORMAT` | `json` | json/console |

数据库、MemOS、模型、鉴权和 fallback 变量未提前加入。

## 6. 测试结果

执行环境：CPython 3.11.16、uv 0.12.9、Linux x86_64。

| 门禁 | 结果 |
|---|---|
| `uv lock --check --offline` | 通过，32 packages，1 ms |
| 干净临时环境 frozen sync + 项目构建 | 通过；29 个锁定 wheel 预载后 `uv sync --frozen --offline` 成功 |
| `uv run ruff format --check .` | 通过，14 files already formatted |
| `uv run ruff check .` | 通过，All checks passed |
| `uv run mypy src tests` | 通过，14 source files |
| `uv run pytest` | 通过，27 passed，1.64 s |
| 语句覆盖率 | 110/110，100% |
| 分支覆盖率 | 19/20，95% |
| 综合 coverage.py 覆盖率 | 99.23% |
| Uvicorn Smoke | 5 秒窗口内 ready；OpenAPI 200；SIGTERM 后完整 shutdown 日志 |
| 赛事路径边界 | `/health`、`/add`、`/search` 全部 404 |
| `git diff --check` | 通过 |

Uvicorn 0.35 在完成 graceful shutdown 日志后保留 SIGTERM 返回码 `-15`；Smoke 同时要求返回码为
0 或 `-SIGTERM` 且日志包含 `Application shutdown complete`，避免把强制终止误判为成功。

## 7. 性能基线

本机单进程、无外部服务的轻量测量：

| 指标 | 结果 |
|---|---:|
| `memscope.app` import | 322.628 ms |
| app factory P50（100 次） | 0.022 ms |
| app factory P95（100 次） | 0.078 ms |
| app factory max（100 次） | 0.882 ms |

这些数据只用于后续本机回归，不代表主办方硬件或正式 Adapter P95。

## 8. 依赖与许可证检查

运行时直接依赖固定为：

- FastAPI 0.115.14：包元数据 classifier 为 MIT；
- Pydantic 2.11.7：MIT；
- Pydantic Settings 2.10.1：MIT；
- Uvicorn 0.35.0：BSD-3-Clause。

开发依赖元数据：HTTPX BSD-3-Clause、Pytest/Pytest-Cov/Ruff/Mypy MIT、pytest-asyncio
Apache-2.0。完整传递依赖通知仍由 B09 生成，本轮没有 vendoring MemOS。

## 9. 偏差与环境问题

无批准范围、公共接口、数据模型、运行服务或一致性语义偏差。

环境侧发现：当前执行器的网络代理允许 `curl`/pip 下载，但 `uv` 直接访问索引会无输出阻塞。
处理方式是从 `uv.lock` 导出精确版本，pip 仅下载固定 wheel 到 `/tmp`，再由 uv 在 offline/frozen
模式安装和构建。仓库未提交 wheel、缓存或代理配置；正常环境仍使用 README 中的
`uv sync --frozen`。

非沙箱测试首次因禁止本地 socket 失败；按执行器规则在授权环境重跑后，真实 localhost Uvicorn
Smoke 通过。这不是应用故障。

## 10. 已知限制和后续依赖

- 尚无比赛 Health/Add/Search 接口；
- 尚无 HTTP 错误模型和比赛鉴权；
- 尚无 Raw Store、幂等、Cube、Gateway、MemOS 或容器；
- 尚无真实 API/Key，不能验证语义抽取、召回或 baseline 得分；
- 正式硬件、超时、并发、失败策略和部署限制仍待组委会确认；
- 当前只有 `core` profile；其它 profile 在对应 Batch 前 fail fast；
- JSON 日志仅允许 B00 固定字段，request/user/cube 关联字段需后续评审加入。

## 11. Gate 2 验收结论请求

B00 已满足 Gate 1 Definition of Done，现请求用户进行 Gate 2 验收。验收前状态保持
`Code Review`；只有用户明确接受后才更新为 `Accepted/Frozen`。不会自动进入 B01。

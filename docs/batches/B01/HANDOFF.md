# B01 Gate 2 Handoff

> 状态：Code Review，等待用户 Gate 2 验收
> Gate 1 文档提交：`df0d8611079bf3605cd66f920a9fac2e5f223541`
> 实现提交：`160a46cbbd62dcc9d1aa34bf80f36459541b9d1c`
> 分支：`batch/b01-api-contract`
> 日期：2026-09-02

## 1. 交付能力

B01 已交付：

- `GET /health`、`POST /add`、`POST /search` 三条规范比赛路径；
- strict Pydantic 入站契约、显式出站模型和 OpenAPI Schema；
- framework-independent、异步 `ContestOperations` 应用端口及冻结内部 DTO；
- 默认 `UnavailableContestOperations`，未装配后端时绝不伪造 ready、Add 或 Search 成功；
- 默认关闭的共享 Key 鉴权，支持 Bearer、Token 和 X-Api-Key 三种互斥载体；
- 统一脱敏的 401/404/405/422/500/503 错误 envelope；
- 只记录固定 HTTP 元数据和总耗时的结构化日志；
- 单元、契约、故障、取消、OpenAPI、ASGI 和真实 Uvicorn Smoke 测试。

B01 不需要模型 Key、数据库、MemOS、Qdrant、Neo4j 或外部网络。

## 2. 方案条目与实现位置

| Gate 1 条目 | 实现位置 |
|---|---|
| 外部请求/响应模型 | `src/memscope/api/models.py` |
| 可选共享 Key 鉴权 | `src/memscope/api/auth.py`、`src/memscope/settings.py` |
| HTTP 错误和安全日志 | `src/memscope/api/errors.py`、`src/memscope/logging_config.py` |
| Health/Add/Search Adapter | `src/memscope/api/routes.py` |
| 内部应用端口和 DTO | `src/memscope/operations.py` |
| app factory 组装 | `src/memscope/app.py` |
| 契约、故障和取消测试 | `tests/contract/test_contest_api.py` |
| 模型、鉴权、错误和端口单测 | `tests/unit/test_api_*.py`、`tests/unit/test_operations.py` |
| 真实进程边界 | `tests/smoke/test_minimal_app.py` |
| 长期接口和决策 | `docs/interfaces/contest-http-v1.md`、`docs/adr/0002-contest-adapter-boundary.md` |

## 3. 下游公共接口

B02/B03 可以依赖：

```python
from memscope.app import create_app
from memscope.operations import (
    AddCommand,
    ContestOperations,
    MemoryEvidence,
    MemoryMessage,
    SearchQuery,
    ServiceUnavailableError,
)
```

app factory 保持 B00 调用兼容，并增加 keyword-only 注入：

```python
create_app(settings=None, *, operations=None)
```

`ContestOperations` 的 `is_ready`、`add`、`search` 都是 async。它是 HTTP Adapter 到应用编排层的
端口，不是后续 MemOS `MemoryGateway`。下游不得依赖 FastAPI 闭包、handler 注册顺序、Pydantic
私有 Schema、`application.state` 或 tests-only recorder。

赛事 HTTP 的稳定定义见 `docs/interfaces/contest-http-v1.md`。

## 4. 保证的不变量

- Health 无鉴权；只有完整 operations ready 时返回 200 `{"status":"ok"}`；
- Add 只有在 awaited operation 正常完成后返回 200 和 JSON boolean `success=true`；
- Add 三 ID 原样回传，消息顺序、role、content 和 timestamp 不改写；
- Search 只返回证据，不接收 gold、不生成答案、不按 session 过滤；
- Search 保留应用层顺序，最多返回 `top_k` 条，缺失 score/created_at 时不输出 null 字段；
- strict 类型拒绝隐式字符串/数字/boolean 转换；未知入站字段忽略但不传入内部端口；
- 默认运行时三条合法比赛调用均为 503，而不是 404、伪 200 或空结果降级；
- 请求 body、Key、query、options、业务 ID、消息和 evidence content 不进入错误或应用日志；
- Settings 仍是唯一环境入口，无效鉴权组合在 ASGI ready 前脱敏失败；
- B01 无数据库、网络、后台任务、持久状态或可变的请求级全局状态。

## 5. 错误、超时和故障语义

| 场景 | 结果 |
|---|---|
| 请求 JSON/类型/字段非法 | 422 `request.invalid`，不调用 operations |
| 共享 Key 缺失、畸形、错误或多载体 | 401 `auth.invalid`，不泄漏具体原因 |
| 路径不存在 / 方法错误 | 404 `http.not_found` / 405 `http.method_not_allowed` |
| 默认未装配、not ready 或 readiness 探测异常 | 503 `service.unavailable` |
| 未专门映射的安全 `MemScopeError` | 500，保留声明的安全 code/message/retryable |
| 未知异常 | 500 `internal.error`，不返回异常值 |
| 请求取消 | 取消向 operations 传播，不转换成成功响应 |

B01 不增加超时、不重试 Add、不将 Search 失败降级为空数组、不实现持久幂等或恢复。上述策略在首次
拥有真实 I/O 或 Raw Store 的 Batch 单独评审。

## 6. 配置

B00 配置继续有效，B01 新增：

| 变量 | 默认 | 语义 |
|---|---|---|
| `CONTEST_AUTH_MODE` | `none` | `none` 或 `shared_key` |
| `CONTEST_API_KEY` | absent | `shared_key` 时必填；none 时必须为空 |

Health 始终无鉴权。Key 使用 `SecretStr` 和 constant-time 比较；`safe_summary()` 只显示
`contest_api_key_configured` boolean。

## 7. 测试与质量结果

执行环境：CPython 3.11.16、现有 B00 `.venv`、Linux x86_64。

| 门禁 | 结果 |
|---|---|
| `uv lock --check --offline` | 通过，32 packages；`uv.lock` 未变化 |
| `ruff format --check .` | 通过，25 files already formatted |
| `ruff check .` | 通过，All checks passed |
| `mypy src tests` | 通过，25 source files |
| `pytest` | 通过，107 passed，2.02 s |
| 语句覆盖率 | 395/398，99.25% |
| 分支覆盖率 | 71/72，98.61% |
| coverage.py 综合覆盖率 | 99.15% |
| B01 HTTP/API 模块 | 除结构型 Protocol 方法外，新增可执行模块均达到 100% 语句覆盖 |
| 真实 Uvicorn Smoke | 启动、三路径注册、默认 Health 503、SIGTERM 完整 shutdown 均通过 |
| `git diff --check` | 通过 |

完整测试未读取正式样本、API Key、数据库或外网。

## 8. Adapter 性能基线

进程内 ASGITransport、立即完成的 tests-only operations、每路径预热 25 次后测量 500 次：

| 路径 | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|
| Health | 0.293 ms | 0.413 ms | 0.664 ms | 9.461 ms |
| Add | 0.520 ms | 0.725 ms | 0.976 ms | 1.274 ms |
| Search | 0.506 ms | 0.661 ms | 0.747 ms | 1.155 ms |

这只衡量本机 HTTP Adapter，不代表正式硬件、并发或未来存储/MemOS 延迟。三条路径 P95 均低于
主计划暂定的 50 ms Adapter 目标。

## 9. 依赖、许可证和安全

- 未修改 `pyproject.toml` 或 `uv.lock`；
- 未新增直接或传递依赖；
- 未修改 MemOS，仍为 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`；
- 未写入或提交 `.env`、Key、缓存、运行数据或正式样本；
- 沿用 B00 已核验的 FastAPI/Pydantic/Uvicorn/HTTPX 等许可证口径。

## 10. 偏差与环境问题

无批准范围、公共接口、状态码、同步语义或依赖偏差。

实现澄清：外部 Pydantic JSON array 使用 list 接收，再显式转换为内部 tuple。最初直接对 tuple 使用
全局 strict 会拒绝合法 JSON array；修正后既保持 JSON 契约，也保持内部冻结 DTO。这不改变批准的
外部或内部语义。

环境侧：沙箱默认禁止 localhost socket，真实 Uvicorn Smoke 在授权环境执行。单独运行该 Smoke 时，
测试本身通过但项目级 coverage 低于 95% 而使命令非零；使用 `--no-cov` 复核单项后，最终完整
`pytest` 在授权环境以 107/107 和 99.15% coverage 通过。

## 11. 已知限制和后续依赖

- 默认 B01 不是可跑正式评测的 memory service；B02/B03 提供 operations 实现前保持 503；
- 尚无 Raw Store、持久幂等、user/cube 映射或跨用户存储隔离；
- 尚无 Fake/Real Memory Gateway、MemOS、Qdrant、Neo4j 或模型；
- 尚未证明 Add 持久化、重启恢复、Add 后立即 Search 或真实排序质量；
- 尚未冻结请求大小、超时、并发、失败降级和正式部署策略；
- 当前 `official/` 仍只是本地规则重建与代理回归集；
- 主办方 API/Key、硬件/超时/并发、Compose/网络/构建和决赛要求仍未知。

## 12. Gate 2 验收结论请求

B01 已满足批准的 Definition of Done，现请求用户进行 Gate 2 验收。验收前保持 `Code Review`；
只有用户明确接受后才更新为 `Accepted/Frozen`。不会自动创建 B02 分支或进入 B02。

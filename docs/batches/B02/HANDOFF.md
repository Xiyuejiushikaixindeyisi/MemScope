# B02 Gate 2 Handoff

> 状态：Accepted/Frozen，2026-09-02 用户已完成 Gate 2 验收
> Gate 1 文档提交：`71b8fb7`
> 实现提交：`fede40d03bd4f7a21c87499a498b15a9a8581412`
> 分支：`batch/b02-raw-identity`
> 日期：2026-09-02

## 1. 交付能力

B02 已交付：

- framework-independent async `RawStore` port 和 stdlib `sqlite3` 实现；
- canonical Add v1、持久 payload SHA-256 幂等和 typed conflict；
- 稳定、带版本前缀的逻辑 Cube ID 和 message ID；
- 原子保存 Add request、完整有序 raw messages、user/Cube reservation 和 durable outbox；
- NEW/PENDING/COMPLETED replay 分类和成功 response 持久恢复；
- 五表 SQLite Schema v1、复合外键/唯一/check 约束和必要 B-tree 索引；
- forward-only embedded migrations、checksum ledger、future/gap/tamper fail-closed；
- 每操作独占短连接、WAL、FULL synchronous、FK ON 和 bounded busy timeout；
- 重启、同/双实例并发、锁竞争、事务故障、取消收敛、腐化和跨 user 隔离测试；
- 集中数据库配置和不记录路径、SQL、hash、ID 或内容的日志 allowlist。

B02 不需要模型 Key、MemOS、Qdrant、Neo4j、外网或正式样本。

## 2. 方案条目与实现位置

| Gate 1 条目 | 实现位置 |
|---|---|
| RawStore port 和冻结 value objects | `src/memscope/raw_store/protocol.py`、`models.py` |
| typed safe errors | `src/memscope/raw_store/errors.py` |
| canonical payload、Cube/message identity | `src/memscope/raw_store/identity.py` |
| Schema v1 和 checksum migrations | `src/memscope/raw_store/migrations.py` |
| SQLite 短连接、事务、replay 和读取 | `src/memscope/raw_store/sqlite.py` |
| 数据库路径、busy timeout、日志字段 | `src/memscope/settings.py`、`logging_config.py`、`.env.example` |
| 迁移、持久化、并发和故障测试 | `tests/component/test_raw_store_*.py` |
| identity、models、Settings 和 logging tests | `tests/unit/test_raw_*.py` 及既有测试扩展 |
| 稳定接口与架构决策 | `docs/interfaces/raw-store-v1.md`、`docs/adr/0003-*.md` |

## 3. 下游公共接口

B03 及后续编排可以依赖：

```python
from memscope.raw_store import (
    AddDisposition,
    IdempotencyConflictError,
    PersistedAdd,
    PreparedAdd,
    RawStore,
    SqliteRawStore,
    StoredAddResponse,
)
```

打开 SQLite 实现：

```python
store = await SqliteRawStore.open(
    settings.database_path,
    busy_timeout_ms=settings.sqlite_busy_timeout_ms,
)
```

正式语义见 `docs/interfaces/raw-store-v1.md`。下游不得依赖私有 connection、SQL、表访问顺序、
thread-pool 实现细节或 tests-only corruption helpers。

## 4. 保证的不变量

- canonical payload 覆盖 schema、三个 exact ID、消息顺序及每条 exact role/content/timestamp；
- 同 request ID + 不同 payload 始终 typed conflict 且不修改原记录；
- 同 payload pending replay 不写入、不更新时间、不假装成功；
- completed replay 返回经过结构和 identity 验证的原成功 response；
- 首次 prepare 的 request/messages/Cube/outbox 在一个 `BEGIN IMMEDIATE` 事务中提交或回滚；
- complete 的 response/request/outbox 在一个事务中完成，重复相同 complete 是 no-op；
- 同 user/session 的多个 chunk 使用连续 session positions；并发 chunk 以写事务顺序决定先后；
- user/Cube、message/request/user/session 和 outbox/request/Cube 由复合约束绑定；
- `load_add` 同时要求 exact user 和 request，错误 user 不得到记录；
- migration checksum、版本或数据库完整性异常不进入 ready；
- 任何公开错误和结构化日志都不包含赛事 ID、消息、hash、SQL、路径或 SQLite 文本；
- SQLite 内部提供 local exactly-once；与未来 MemOS 只准备 at-least-once 恢复，不声称 distributed exactly-once。

## 5. 事务、并发和取消

每个阻塞操作在 `asyncio.to_thread` worker 内创建、配置并关闭自己的 SQLite connection。连接不跨线程
共享，同实例并发也由 SQLite 锁、约束和事务裁决，而不是进程内 mutex。

协程取消不能停止已经进入 worker 的 sqlite 调用。该 worker 仍完成 commit/rollback 并关闭自己的
connection；调用方以相同 request ID 重试后收敛到唯一 NEW/PENDING/COMPLETED 状态。组件测试覆盖了
锁等待期间取消、释放锁和 retry 后无重复行。

外部 MemOS 成功而 complete 前崩溃时，outbox 保持 pending。B07 才实现 worker、lease、attempt、
退避、重试和 readback。

## 6. 配置与默认运行时

| 变量 | 默认 | 校验 |
|---|---|---|
| `DATABASE_PATH` | `data/memory.db` | 非空文件路径；拒绝 `:memory:` 和 `file:` URI |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | 100～60000 ms |

Settings 构造不访问文件系统，safe summary 只显示 relative/absolute 路径种类和 timeout。容器内
`/data/memory.db` 由 B04 profile 显式设置，不在 B02 冻结 Compose。

B02 没有修改 `app.py`、`operations.py` 或 API routes，也没有组装 Raw Store。默认 Uvicorn 的 Health、
Add、Search 继续明确返回 503；这是因为 Search 和完整 operations 尚不可用，不是 B02 故障。

## 7. 测试与质量结果

执行环境：CPython 3.11.16、SQLite 3.53.1、既有 B00 `.venv`、Linux x86_64。

| 门禁 | 结果 |
|---|---|
| `uv lock --check --offline` | 通过，32 packages；`uv.lock` 未变化 |
| `ruff format --check .` | 通过，36 files already formatted |
| `ruff check .` | 通过，All checks passed |
| `mypy src tests` | 通过，36 source files |
| `pytest` | 通过，213 passed，5.68 s |
| 总体语句覆盖率 | 909/928，97.95% |
| 总体分支覆盖率 | 205/212，96.70% |
| coverage.py 综合覆盖率 | 97.72% |
| B02 Raw Store 语句覆盖率 | 497/513，96.88% |
| B02 Raw Store 分支覆盖率 | 126/132，95.45% |
| B01 回归 | HTTP/鉴权/错误/OpenAPI/真实 Uvicorn Smoke 全部通过；默认仍 503 |

测试只使用 pytest/system temporary directories，未创建仓库 `data/`，未读取 Key、正式样本、完整
MemOS 源码或外网。

## 8. SQLite 本机性能与尺寸

测量方式：每组 100 个唯一 request；文件 SQLite、WAL + FULL、每操作短连接；先全部 prepare，再依次
duplicate、complete、load。数据为本机 warm-run，不是正式硬件承诺，也不作为 CI hard assertion。

| messages/request | operation | P50 | P95 | P99 |
|---:|---|---:|---:|---:|
| 1 | prepare / duplicate / complete / load | 17.356 / 0.803 / 17.398 / 0.680 ms | 25.331 / 1.404 / 19.791 / 1.641 ms | 28.083 / 1.518 / 23.857 / 1.758 ms |
| 20 | prepare / duplicate / complete / load | 19.660 / 0.698 / 16.902 / 0.589 ms | 22.697 / 1.655 / 20.220 / 1.514 ms | 23.975 / 1.753 / 23.126 / 1.645 ms |
| 100 | prepare / duplicate / complete / load | 24.076 / 0.539 / 15.718 / 0.969 ms | 27.162 / 1.686 / 18.223 / 2.065 ms | 28.324 / 1.913 / 19.632 / 2.149 ms |

100 requests 完成后的主 DB 大小分别为 184,320、815,104、3,457,024 bytes。测量点没有 live
connection，WAL/SHM 已自动 checkpoint/移除，均为 0 bytes。写入约 16～27 ms 主要体现当前
`synchronous=FULL` 正确性优先取值；在主办方硬件/超时明确前不降低 durability。

## 9. 依赖、许可证和安全

- 未修改 `pyproject.toml` 或 `uv.lock`，未新增直接/传递依赖；
- 仅使用 Python 标准库 sqlite3/asyncio/hashlib/json/threading；
- 未修改 MemOS，仍为 `v2.0.32` / `185ebdb925911b55c13b7efe666b74e2e292e484`；
- 未写入或提交 SQLite DB/WAL/SHM、`.env`、Key、日志、缓存或正式样本；
- 所有 SQL 中赛事输入均使用参数绑定；migration/PRAGMA 插值只使用代码内版本和已校验整数；
- 沿用 B00 已核验的项目依赖许可证，不产生新第三方 notice。

## 10. 偏差与环境问题

无批准范围、Schema、identity、事务、依赖或默认 HTTP 语义偏差。

实施阶段的设计强化：Gate 1 最终核对已把 connection 策略冻结为“每操作独占短连接”，并为 Schema
加入复合外键一致性约束；实现与批准后的文档一致。

受限 Codex sandbox 中，最小 `asyncio.to_thread(lambda: 42)` 无法唤醒 event loop。普通线程正常，且同一
测试在非受限执行环境立即通过。因此所有依赖 `to_thread` 的组件/全量测试在获批的正常执行环境运行；
该环境同时满足 B01 localhost Uvicorn Smoke。此问题不是 SQLite 或 MemScope 测试失败。

## 11. 已知限制和后续依赖

- 默认运行时仍不是可执行正式评测的 memory service；B03 以前保持 503；
- 无 Fake/Real Memory Gateway、MemOS user/Cube/ACL、Qdrant、Neo4j 或模型调用；
- durable outbox 尚无 worker/lease/retry/readback，pending 只可持久读取；
- 无 FTS/Raw Search、Search evidence、融合、排序或立即可检索证明；
- B02 typed conflict 尚未映射为 HTTP 409；首次 operations 集成 Batch 负责；
- 逻辑 Cube ID 尚未对 MemOS provider ID 限制做真实验证；B05 负责；
- 尚未冻结请求大小、正式超时/并发/失败降级或容器路径；
- 当前 `official/` 仍只是本地规则重建与代理回归集；
- 主办方 API/Key、硬件/超时/并发、Compose/网络/构建和决赛要求仍未知。

## 12. Gate 2 验收结论

用户于 2026-09-02 明确批准 B02 Gate 2 验收。B02 状态更新为 `Accepted/Frozen`。后续 Batch
只允许依赖本 Handoff、`raw-store-v1.md` 及公开 `memscope.raw_store` 接口明示的不变量，不得依赖
SQLite 私有 connection、SQL 或表访问顺序。本次验收同时授权进入 B03 Gate 1 代码方案设计，但不授权
创建 B03 分支或实施 B03 代码。

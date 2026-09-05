# 本地代理 Answer/Judge

`scripts/local_proxy_eval.py` 是一个确定性、无第三方依赖的本地回归工具，明确不是主办方评测器。

## 工作方式

1. 按评测协议调用 Health、Add、Search；
2. Add 按 20 条消息或 2000 词近似分块；
3. Proxy Answer 从 Search 返回内容中选择与问题词法最相关的至多三个证据片段；
4. Proxy Judge 使用规范化包含关系、token F1、数字冲突检查及 MemOps `must_include` / `must_not_include`；
5. 输出总体与 benchmark、operation、eval axis 切片。

Search 请求不包含 gold。gold 只在 Search 返回后交给本地 Proxy Judge。

结果包含问题、gold 和返回 evidence，应作为敏感评测数据保存。`--output-dir` 必填，必须位于源码树
之外；工具创建 0700 目录和 0600 文件。凭据只从指定环境变量读取，不接受命令行明文。客户端可做
最小请求间隔控制，并仅对 429 做有界指数退避；这不改变服务内部“不自动重放 Add”的语义。

## 运行服务并评分

```bash
python scripts/local_proxy_eval.py \
  --base-url http://127.0.0.1:8080 \
  --output-dir "$HOME/memscope-evaluation/development/proxy-baseline"
```

若被测服务启用了 Bearer shared key：

```bash
export MEMSCOPE_EVAL_API_KEY='<set through a secure shell mechanism>'
python scripts/local_proxy_eval.py \
  --base-url http://127.0.0.1:8080 \
  --auth-mode bearer \
  --credential-env MEMSCOPE_EVAL_API_KEY \
  --min-interval-seconds 0.2 \
  --max-rate-limit-retries 4 \
  --output-dir "$HOME/memscope-evaluation/development/proxy-baseline"
```

不要把真实值直接写在示例命令或 shell history 中；上面的值只是占位说明。

只跑少量样本：

```bash
python scripts/local_proxy_eval.py \
  --base-url http://127.0.0.1:8080 \
  --max-samples 2 \
  --output-dir "$HOME/memscope-evaluation/development/proxy-smoke"
```

对已经保存的 Search 结果重新评分：

```bash
python scripts/local_proxy_eval.py \
  --input-results "$HOME/memscope-evaluation/development/proxy-baseline/search_results.jsonl" \
  --output-dir "$HOME/memscope-evaluation/development/proxy-rescored"
```

自测：

```bash
python scripts/local_proxy_eval.py --self-test
```

所有汇总文件均含 `"official": false`。代理准确率只适合比较同一环境下的检索版本，不能与官方分数或排行榜比较。

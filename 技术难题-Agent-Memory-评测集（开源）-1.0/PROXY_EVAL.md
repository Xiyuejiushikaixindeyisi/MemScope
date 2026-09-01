# 本地代理 Answer/Judge

`scripts/local_proxy_eval.py` 是一个确定性、无第三方依赖的本地回归工具，明确不是主办方评测器。

## 工作方式

1. 按评测协议调用 Health、Add、Search；
2. Add 按 20 条消息或 2000 词近似分块；
3. Proxy Answer 从 Search 返回内容中选择与问题词法最相关的至多三个证据片段；
4. Proxy Judge 使用规范化包含关系、token F1、数字冲突检查及 MemOps `must_include` / `must_not_include`；
5. 输出总体与 benchmark、operation、eval axis 切片。

Search 请求不包含 gold。gold 只在 Search 返回后交给本地 Proxy Judge。

## 运行服务并评分

```bash
python scripts/local_proxy_eval.py \
  --base-url http://127.0.0.1:8080 \
  --output-dir reports/proxy_eval
```

只跑少量样本：

```bash
python scripts/local_proxy_eval.py \
  --base-url http://127.0.0.1:8080 \
  --max-samples 2
```

对已经保存的 Search 结果重新评分：

```bash
python scripts/local_proxy_eval.py \
  --input-results reports/proxy_eval/search_results.jsonl \
  --output-dir reports/proxy_eval_rescored
```

自测：

```bash
python scripts/local_proxy_eval.py --self-test
```

所有汇总文件均含 `"official": false`。代理准确率只适合比较同一环境下的检索版本，不能与官方分数或排行榜比较。

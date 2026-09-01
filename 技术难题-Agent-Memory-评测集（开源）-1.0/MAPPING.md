# Mapping notes: open benchmarks → platform sample schema

## LoCoMo-Refined → sample

| LoCoMo-Refined | 本赛 sample |
|----------------|-------------|
| `sample_id` / conversation id | `sample_id` / `source.source_id` |
| `sessions[].messages` | `add_phase.sessions[].messages`（`role`/`content`；时间可从 `date_time` 推导毫秒） |
| 同一对话下所有 session | 同一 `isolation.user_id`，不同 `session_id` |
| `questions.jsonl` 的 `question` | `search_items[].question` |
| `answer`（list[str]） | `search_items[].gold_answer` |
| `qa_id` | `search_items[].qid` |
| `evidence` / `evidence_messages` | 可选写入 `gold_rubric` / 诊断字段（正式跑分以 gold_answer 为主） |

排除：开放域常识题、原 category 5 对抗题（不计初赛正式分）。

## MemOps → sample

| MemOps | 本赛 sample |
|--------|-------------|
| 注入后 `conversations` / segments | `add_phase.sessions`（可按 segment 或 session 切） |
| `answer[].question` | `search_items[].question` |
| `expected_answer` | `gold_answer` |
| `judge_rubric` | `gold_rubric` |
| `gold_provenance` | 可选诊断 |
| `operation_type` / `difficulty_knobs` | `eval_axis` / `source` 元数据 |
| Longitudinal distractors | 作为额外 session 一并 Add |

优先纳入：`Update` / `Forget` / `Remember` 的 longitudinal_operation 设定。

## 评测机注意

- gold **不**传入 Search；
- `top_k=100`；
- Answer / Judge 固定，选手不可替换。
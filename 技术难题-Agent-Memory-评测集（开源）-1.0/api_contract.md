# Add / Search / Health 统一契约

路径可自定义，须在 `INSTRUCTION.md` 写明。下列为 **请求/响应 JSON 字段**（与 AML Textual 轨对齐）。

## Health

```http
GET /health
```

任意 **2xx** 即表示就绪。无鉴权即可。

## Add

### 请求 `POST /add`

```json
{
  "request_id": "eval:run_demo:locomo:conv-26:chunk-0",
  "user_id": "eval:run_demo:locomo:conv-26",
  "session_id": "eval:run_demo:locomo:conv-26:session-1",
  "messages": [
    {
      "role": "user",
      "content": "…",
      "timestamp": 1704067200000
    },
    {
      "role": "assistant",
      "content": "…",
      "timestamp": 1704067208000
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `request_id` | ✅ | 本次写入唯一 ID；响应须原样回传 |
| `user_id` | ✅ | 检索隔离键；Add/Search 必须一致 |
| `session_id` | ✅ | 来源会话标识；Search **不**按此过滤 |
| `messages` | ✅ | 有序消息；每条含 `role` + 非空 `content`；`timestamp` 可选（Unix 毫秒） |

评测机 **不发送**：`metadata`、`app_id`、`agent_id`、`async_mode`。

分块：单会话默认一次 Add；超过约 20 条消息或 2000 词时按边界切分为多个 chunk。

### 响应 `HTTP 200`

```json
{
  "success": true,
  "request_id": "eval:run_demo:locomo:conv-26:chunk-0",
  "user_id": "eval:run_demo:locomo:conv-26",
  "session_id": "eval:run_demo:locomo:conv-26:session-1"
}
```

| 约束 | 说明 |
|------|------|
| `success` | 必须是布尔值 `true`（不是字符串） |
| 三 ID | 与请求 **完全一致** |
| 同步 | 返回前须持久化且可被 Search 检索 |
| 禁止 | `202`、task id、异步轮询；不要求返回 `memory_ids` |

## Search

### 请求 `POST /search`

```json
{
  "query": "What is the current SSH port?",
  "user_id": "eval:run_demo:locomo:conv-26",
  "top_k": 100,
  "options": ["A. …", "B. …"]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `query` | ✅ | 评测题原文；不得改写为答案，不得使用金标 |
| `user_id` | ✅ | 只在该用户记忆范围内检索 |
| `top_k` | ✅ | 正式评测固定 **100**；返回条数不得超过此值 |
| `options` | 可选 | 选择题才传；开放题不传 |

评测机 **不发送**：`filters`、`rerank`、`keyword_search`。

### 响应 `HTTP 200`

```json
{
  "data": [
    {
      "id": "mem_1",
      "content": "remembered fact text",
      "score": 0.87,
      "created_at": "2026-07-01T12:00:00Z"
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `data` | ✅ | 对象内的数组；不要 `items` 包装；不要顶层直接数组 |
| `data[].id` | ✅ | 非空字符串 |
| `data[].content` | ✅ | 非空字符串；将交给平台 Answer 模型 |
| `data[].score` | 可选 | 数值，越大越相关 |
| `data[].created_at` | 可选 | ISO 时间 |

无结果：`{"data":[]}`。须在返回前完成相关性排序；平台按返回顺序最多读取 `top_k` 条。

**禁止**：Search 直接生成最终答案，或把 gold 伪装成记忆。

## 鉴权

支持 `Authorization: Bearer <token>`、`Authorization: Token <token>`、`X-Api-Key: <key>`；Smoke 可用无鉴权。正式评测密钥由赛题组配置。

## 错误

使用标准 HTTP 状态码。格式错误（即使 HTTP 200 但缺必填字段）会导致该阶段评测失败。
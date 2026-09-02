# Contest HTTP Interface v1

> Owner: B01
> Authority: approved B01 plan plus the repository's current rules-level `api_contract.md`
> Local data status: rules reconstruction and proxy regression set, not organizer-byte-verified

## Public paths

| Method and path | Authentication | Success |
|---|---|---|
| `GET /health` | none | 200 `{"status":"ok"}` only when complete operations are ready |
| `POST /add` | optional shared key | 200 after the injected Add operation completes |
| `POST /search` | optional shared key | 200 with ranked evidence from the injected Search operation |

The default B01 composition has no memory implementation and returns 503 for otherwise valid calls.
ASGI process startup is not equivalent to memory readiness.

## Add

Required request fields are `request_id`, `user_id`, `session_id`, and a non-empty `messages`
array. Every message requires nonblank `role` and `content`; `timestamp` is an optional strict Unix
millisecond integer. Values and message order are preserved. Unknown input fields are ignored.

Only an awaited, successful application operation permits this exact response shape:

```json
{
  "success": true,
  "request_id": "exact request value",
  "user_id": "exact request value",
  "session_id": "exact request value"
}
```

B01 transfers `request_id`; persistent idempotency and immediate retrieval are implemented and
verified by later batches.

## Search

Required request fields are nonblank `query`, nonblank `user_id`, and strict integer `top_k` in
1～100. `options` may be absent, null, or a string array and is passed through without answer
selection. Search never accepts gold, filters by session, or generates a final answer.

The response is `{"data": [...]}`. Each evidence item has nonblank `id` and `content`; finite
`score` and timezone-aware ISO `created_at` are optional and omitted when absent. Application order
is preserved. Adapter output is safety-truncated to `top_k` but is not reranked, deduplicated,
rewritten, or supplemented.

## Authentication

`CONTEST_AUTH_MODE=none` is the default. `shared_key` requires `CONTEST_API_KEY` at startup and
accepts exactly one of:

- `Authorization: Bearer <key>`
- `Authorization: Token <key>`
- `X-Api-Key: <key>`

Multiple, missing, malformed, or incorrect credentials receive the same 401 response. Health stays
unauthenticated. Keys are constant-time compared and excluded from configuration summaries, errors,
and logs.

## Errors

Errors use standard HTTP status codes and a sanitized envelope:

```json
{"error":{"code":"request.invalid","message":"Request validation failed","retryable":false}}
```

Stable mappings are 401 `auth.invalid`, 404 `http.not_found`, 405
`http.method_not_allowed`, 422 `request.invalid`, 503 `service.unavailable`, and 500
`internal.error` for unknown failures. Known internal errors retain only their declared safe
code/message/retryable fields. Raw validation details, bodies, credentials, queries, content, IDs,
and exception values are never returned or logged.

## Internal application port

`memscope.operations.ContestOperations` defines asynchronous `is_ready`, `add`, and `search`
methods over frozen framework-independent dataclasses. It is an Adapter-to-application boundary,
not the later MemOS `MemoryGateway`. HTTP and Pydantic types must not cross this boundary.

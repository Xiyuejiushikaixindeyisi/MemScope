# Mock Model API v1

> Owner: B03  
> Scope: isolated no-key HTTP protocol substitute for tests

## Supported subset

The Mock is an independent ASGI application, started as
`memscope.mock_model_api.main:app`. It implements only:

| Method/path | Contract |
|---|---|
| `GET /health` | 200 `{"status":"ok"}` |
| `POST /v1/chat/completions` | non-streaming, nonblank model, ordered nonblank role/content messages |
| `POST /v1/embeddings` | nonblank model and string or non-empty string-array input |

Common unknown request fields are accepted and ignored. `stream=true` is rejected with a sanitized
422. Chat returns deterministic envelope metadata and factory-configured canonical JSON content,
defaulting to `{"memories":[]}`. Embeddings preserve input order and default to dimension 16.

This is OpenAI-shaped, not a claim of complete OpenAI or MemOS compatibility. It implements no
Rerank, streaming, tools, token arrays, tokenizer accounting or semantic model behavior. B05 must
first map the pinned MemOS client before extending the subset.

## Deterministic embedding

`mock-sha256-vector-v1` hashes domain-separated UTF-8 input plus a big-endian counter, consumes
big-endian uint32 values, maps them to `[-1,1]`, and L2-normalizes the requested dimensions. It
does not use Python's randomized `hash()`. Golden-vector tests freeze cross-process behavior.

## Test-only failures

One internal header, `X-MemScope-Mock-Failure`, accepts exactly one allowlisted value:

- `rate_limit`: sanitized 429;
- `upstream_error`: sanitized 500;
- `timeout`: bounded configured delay, then a normal response unless the client cancels;
- `invalid_json`: HTTP 200 with deliberately malformed JSON;
- `dimension_mismatch`: embeddings return one extra dimension.

Unknown, duplicated or endpoint-inapplicable values return sanitized 400. Failure controls never
come from prompt/input content. The Mock does not log request bodies, model names, vectors or fault
header values and must never be started in the organizer profile.

## Configuration and limits

`create_mock_model_app` validates `chat_content`, embedding dimension 1–4096, and timeout delay
10–5000 ms at construction. The default entry point uses fixed safe values and requires no key,
network or persistent state. It proves HTTP parsing and client failure classification, not model
quality, extraction correctness, production latency or provider compatibility.


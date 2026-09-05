# B10 Gate 2 model API integration

> Status: minimal integration patch implemented; formal baseline and tuning remain blocked pending
> service-level verification and a separate user instruction.

## Approved development profile

The development profile uses the Zhipu general API, not the Coding Plan endpoint:

```text
LLM base:       https://open.bigmodel.cn/api/paas/v4
LLM model:      glm-5.1
Thinking:       disabled
Response:       json_object
Embedding base: https://api.siliconflow.cn/v1
Embedding:      BAAI/bge-m3
Stored vector:  1024 dimensions
Request field:  omit dimensions
Reranker:       cosine_local (external reranker remains opt-in)
```

The development and organizer profiles are intentionally different. The organizer keeps the supplied
Huawei `GLM-V5_1-DX` and `bge-m3` gateway configuration, sends the existing embedding dimension field,
does not inject Zhipu-specific request fields, and keeps local cosine reranking.

## Private configuration

Never put a real key in the repository. Create a mode-0600 file outside the checkout:

```bash
install -d -m 0700 "$HOME/.config/memscope"
test -e "$HOME/.config/memscope/development.env" || \
  install -m 0600 deploy/development-api.env.example \
  "$HOME/.config/memscope/development.env"
"${EDITOR:-vim}" "$HOME/.config/memscope/development.env"
```

Do not print the file, source it with shell tracing enabled, commit it, copy it into an image, or pass a
key as a command-line argument.

## Preflight

The default command only verifies that the configured LLM and embedding model IDs are visible. It does
not call an inference endpoint:

```bash
uv run python scripts/preflight_model_apis.py \
  --env-file "$HOME/.config/memscope/development.env"
```

After explicitly reviewing cost, the bounded smoke makes one LLM request with at most 32 output tokens
and one single-input embedding request:

```bash
uv run python scripts/preflight_model_apis.py \
  --env-file "$HOME/.config/memscope/development.env" \
  --allow-inference
```

To test SiliconFlow reranking without changing either Compose backend from `cosine_local`, populate the
optional reranker URL/key/model fields in the private file and add `--include-reranker`. This adds one
three-document, top-two rerank request. The script prints only named pass/fail checks; it never prints keys,
request bodies, response bodies, generated text or vectors.

## Runtime behavior

- `MEMRADER_THINKING_TYPE` accepts empty, `enabled` or `disabled`.
- `MEMRADER_RESPONSE_FORMAT` accepts empty or `json_object`.
- `EMBEDDING_DIMENSION` remains the database and response validation contract.
- `MOS_EMBEDDER_SEND_DIMENSIONS=false` prevents the BGE-M3 request from sending the unsupported
  `dimensions` field.
- A returned embedding count or dimension mismatch fails the request without logging vectors or provider
  response bodies.
- External reranking requires an explicit backend, URL, model and `MOS_RERANKER_API_KEY`. The adapter
  generates the Bearer header internally, sends `top_n` and `return_documents=false`, retries HTTP
  429/503/504 and transport failures within the configured bound, and propagates the final failure.
- Reranker logs contain only character/document counts, HTTP status and the provider trace ID. Query and
  document text are not logged. Unexpected, duplicate or non-finite result fields fail closed.

Official protocol references:

- Zhipu general API: <https://docs.bigmodel.cn/cn/api/introduction>
- Zhipu thinking: <https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode>
- Zhipu structured output: <https://docs.bigmodel.cn/cn/guide/capabilities/struct-output>
- SiliconFlow embeddings: <https://docs.siliconflow.cn/docs/api/embeddings-post>
- SiliconFlow rerank: <https://docs.siliconflow.cn/docs/api/rerank-post>

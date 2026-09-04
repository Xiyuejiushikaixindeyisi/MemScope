# MemScope build and run instructions

This document is the non-interactive operator entry point for the MemScope Agent Memory submission.
The service implements `GET /health`, `POST /add` and `POST /search`; it returns memory evidence and
does not generate final answers.

## 1. Package layout

After extracting the formal archive, use:

```text
solution/
├── INSTRUCTION.md
├── SDD.md
├── THIRD_PARTY_NOTICES.md
├── LICENSES/
└── code/
```

Run repository commands from `solution/code`. When using a source checkout directly, run them from
the repository root instead.

## 2. Fixed requirements

- Linux x86_64 and CPython 3.11; the accepted development version is CPython `3.11.16`.
- `uv 0.12.9` for the locked native memory-api environment.
- Docker Engine with Compose v2 for the Compose path, or separately managed Neo4j
  `5.26.6-community`, Qdrant `1.15.3` and MemOS `v2.0.32` for the native path.
- At least 8 GiB host memory is recommended for the default Compose ceilings.
- An OpenAI-compatible Chat endpoint and Embedding endpoint reachable from MemOS.

The actual Chat model, Embedding model and Embedding dimension must be probed on the deployment
machine. Never infer the dimension from a model name and never reuse a Qdrant collection created for
a different model or dimension.

## 3. Configuration and credentials

Create a private environment file outside the source tree:

```bash
install -m 0600 deploy/compose.env.example /srv/memscope/compose.env
```

Replace every `replace-with-*` value. Required private/runtime-specific values are:

- `NEO4J_PASSWORD`
- `MEMRADER_MODEL`, `MEMRADER_API_BASE`, `MEMRADER_API_KEY`
- `MOS_EMBEDDER_MODEL`, `MOS_EMBEDDER_API_BASE`, `MOS_EMBEDDER_API_KEY`
- `EMBEDDING_DIMENSION`

The URLs must use HTTPS in the real `gateway` profile. Do not write credentials into source files,
Compose YAML, command-line arguments, reports or logs. If inbound authentication is required, add
these values only to the private environment file:

```bash
CONTEST_AUTH_MODE=shared_key
CONTEST_API_KEY=replace-with-organizer-provided-private-key
```

With `CONTEST_AUTH_MODE=none`, Add and Search require no authorization header. With `shared_key`,
clients may use the configured key through `Authorization: Bearer`, `Authorization: Token` or
`X-Api-Key`. Health is always unauthenticated.

## 4. Compose build and startup

### One-command Linux deployment

On a Linux x86_64 host with `uv 0.12.9`, Docker Engine and Compose v2 already installed, validate,
synchronize, build, start and health-check the complete stack with:

```bash
./scripts/deploy_linux.sh --env-file /srv/memscope/compose.env
```

If the private file does not exist, the script creates its parent directory, installs
`deploy/compose.env.example` there with mode `0600`, and opens `${VISUAL:-$EDITOR}` or a standard
terminal editor. Existing files are never overwritten. Before continuing, the file must contain no
example placeholders, use HTTPS model endpoints and specify the exact positive
`EMBEDDING_DIMENSION`. The script does not install Docker, invent model settings, print credentials
or remove persistent volumes. For staged diagnosis, use `--check-only` or `--build-only`; run
`./scripts/deploy_linux.sh --help` for all options.

### Manual equivalent

First validate interpolation without printing the resolved configuration:

```bash
docker compose -p memscope-final \
  --env-file /srv/memscope/compose.env config --quiet
```

Build the two local images once from the frozen source candidate:

```bash
docker compose -p memscope-final \
  --env-file /srv/memscope/compose.env build memory-api memos
```

Start the stack non-interactively:

```bash
docker compose -p memscope-final \
  --env-file /srv/memscope/compose.env up -d
docker compose -p memscope-final \
  --env-file /srv/memscope/compose.env ps
```

Only memory-api publishes a host port. The default public origin is `http://127.0.0.1:8080`; set
`MEMSCOPE_PUBLIC_PORT` in the private environment file when a different host port is required.
Neo4j, Qdrant and MemOS remain on private Compose networks.

Do not use `docker compose down -v`: the named volumes contain Raw, receipt, graph and vector state.
A normal stop is:

```bash
docker compose -p memscope-final \
  --env-file /srv/memscope/compose.env stop
```

## 5. Native fallback

Docker is optional and must not block a scoreable native deployment. The complete native procedure
is in `docs/batches/B06/NATIVE_DEPLOYMENT.md`; storage admission and index/collection checks are in
`docs/batches/B06/ORGANIZER_DEPLOYMENT.md`.

The required order is:

```text
Neo4j -> Qdrant -> one MemOS worker -> one memory-api worker
```

The memory-api environment is installed from the frozen lock:

```bash
UV_PROJECT_ENVIRONMENT=/srv/memscope/venv-api uv sync --frozen --no-dev
```

After configuring the two distinct local SQLite paths and the private MemOS origin, start exactly
one memory-api worker:

```bash
/srv/memscope/venv-api/bin/python -m uvicorn memscope.main:app \
  --host 0.0.0.0 --port 8080 --workers 1
```

Use the complete native guide to unpack and verify the bundled MemOS source, apply the locked
patchset and configure its model and storage dependencies. Do not start memory-api with the
`memos_add` profile until MemOS, Neo4j and Qdrant are ready.

## 6. Public endpoints and readiness

For an origin `http://HOST:PORT`, the complete URLs are:

- Health: `GET http://HOST:PORT/health`
- Add: `POST http://HOST:PORT/add`
- Search: `POST http://HOST:PORT/search`

Readiness requires the exact response:

```bash
curl -fsS http://127.0.0.1:8080/health
```

```json
{"status":"ok"}
```

Health alone does not prove model writes, Embedding compatibility or Search visibility. Before
opening the endpoint to evaluation, run the public candidate verifier with an isolated test user:

```bash
python3 scripts/verify_b06_candidate.py \
  --base-url http://127.0.0.1:8080 --require-hit
```

Then execute all three B08 phases from `docs/batches/B08/SYSTEM_VERIFICATION.md`, including an
operator-controlled restart and sanitized resource observations. Add must remain below 120 seconds,
Search below 60 seconds, and cross-user evidence must remain zero.

## 7. Failure and recovery rules

- A failed or timed-out Add/Search is not converted to HTTP 200 or an empty successful result.
- The service does not automatically retry a public request and does not use Raw text as a Search
  fallback.
- `request_id` replay must use identical content; conflicting reuse returns HTTP 409.
- Keep one memory-api worker and one MemOS worker. Multiple workers are unsupported.
- Preserve candidate-specific Raw, receipt, Neo4j and Qdrant storage across normal restart.
- If the Embedding model or dimension changes, use a new candidate-specific database/collection or
  perform an explicitly reviewed migration.

See `SDD.md` for architecture and known semantic limitations. No development-machine report claims
a real Huawei model score or successful live-system verification without returned tuning evidence.

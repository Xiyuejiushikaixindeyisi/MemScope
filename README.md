# MemScope

MemScope is an independently deployable long-term-memory service for the Agent Memory competition.
It exposes `GET /health`, `POST /add` and `POST /search`, stores evidence through a fixed
MemOS/Neo4j/Qdrant stack, and never generates the final answer or Judge result.

B00–B09 remain the frozen historical baseline at
`4ed49dd06dbb38b3faa46de3c77e446ffcc07b96`. B10 Gate 1 implemented a new pre-tuning closure on
`batch/b10-baseline-closure`; B10 Gate 2, tuning, final artifact generation and merge to `main` are
not yet approved/completed.

## Current machine boundary

The development machine owns source changes, dependencies, service deployment, reachable-API tests,
baseline evaluation, tuning and image construction. The organizer review machine only:

```text
verify hashes -> load four-image bundle -> inject private config
  -> Compose starts memory-api + MemOS + Neo4j + Qdrant -> smoke -> official evaluation
```

The image TAR is one offline transport bundle, not one runtime container. The organizer does not
install Python/uv/pip, build images or pull images. Start with
[`INSTRUCTION.md`](INSTRUCTION.md), [`ORGANIZER_QUICKSTART.md`](ORGANIZER_QUICKSTART.md), or the
directly reusable [`ORGANIZER_AGENT_PROMPT.md`](ORGANIZER_AGENT_PROMPT.md).

## Development

The locked toolchain is CPython 3.11.16 and uv 0.12.9:

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Development Compose may install packages and build the two project images:

```bash
./scripts/deploy_linux.sh --env-file /secure/memscope-development.env
```

`compose.yaml` is development-only. Builds use exactly one explicit HTTPS package index; private env
files are excluded from Docker context. Model URL/Key/model/prompt/threshold changes do not require
rebuilding images.

## Organizer release

The final release will contain a source ZIP, one four-image Linux/amd64 TAR, JSON manifest and
`SHA256SUMS`. `compose.release.yaml` contains no build definition and never pulls. From the extracted
`solution/`, the organizer uses:

```bash
./scripts/run_release.sh \
  --image-bundle ../memscope-images-<candidate>-linux-amd64.tar \
  --sha256-file ../SHA256SUMS \
  --env-file /secure/memscope-organizer.env

./scripts/verify_release.sh --env-file /secure/memscope-organizer.env
```

The public origin defaults to `http://127.0.0.1:8080`; MemOS uses internal port 8000. Stop without
deleting volumes using `scripts/stop_release.sh`. Final artifacts are generated only after tuning and
separate user approval; Gate 1/Gate 2 outputs are previews, never final packages.

## Architecture and guarantees

```text
Evaluator -> memory-api -> Raw SQLite + Gateway receipt SQLite
                        -> MemOS -> Neo4j + Qdrant
                                 -> OpenAI-compatible Chat/Embedding APIs
```

Add is synchronous, per-user serialized, idempotent by `request_id`, deadline-bounded and not
automatically retried. Search is cross-session per user, strictly isolated across users, filters
inactive/invalid provenance and returns ranked evidence only. Real smoke must keep Add below 120
seconds and Search below 60 seconds.

The baseline reranker is local cosine. The user-supplied organizer profile is Chat
`GLM-V5_1-DX`, Embedding `bge-m3` dimension 1024, via trusted Huawei-intranet HTTP. The external
reranker endpoint is not enabled until its exact wire contract is separately tested.

Known limitations—including natural-language Update/Forget publication, non-atomic cross-store
writes and semantic contradiction handling—are explicit in [`SDD.md`](SDD.md). Deterministic tests
do not claim an official score or organizer live pass.

## Project map and governance

- [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md): current facts and Gate state;
- [`docs/CODEMAP.md`](docs/CODEMAP.md): module ownership and dependency direction;
- [`docs/batches/B10/PLAN.md`](docs/batches/B10/PLAN.md): approved B10 implementation boundary;
- [`docs/collaboration/TWO_MACHINE_WORKFLOW.md`](docs/collaboration/TWO_MACHINE_WORKFLOW.md): current
  development/organizer workflow;
- [`docs/interfaces/contest-http-v1.md`](docs/interfaces/contest-http-v1.md): public contract.

No public license has been selected for original MemScope source. See `LICENSE_STATUS.md` and
`THIRD_PARTY_NOTICES.md`; the fixed MemOS source is distributed under Apache-2.0.

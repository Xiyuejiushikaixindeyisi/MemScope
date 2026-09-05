# MemScope build, run and evaluation instructions

This is the non-interactive entry point for the MemScope Agent Memory submission. The public service
implements `GET /health`, `POST /add` and `POST /search`; it returns memory evidence and does not
generate the final answer.

## 1. Delivery contract

The development machine produces these files only after the tuned candidate is frozen:

```text
solution-<candidate>.zip
memscope-images-<candidate>-linux-amd64.tar
delivery-manifest.json
SHA256SUMS
```

The image TAR is one transport bundle containing four images. It is not a single-container runtime.
The organizer loads it and Compose starts `memory-api`, MemOS, Neo4j and Qdrant as four containers
with five persistent named volumes.

After extracting the ZIP, the operator-facing layout is:

```text
solution/
├── INSTRUCTION.md
├── ORGANIZER_QUICKSTART.md
├── ORGANIZER_AGENT_PROMPT.md
├── SDD.md
├── THIRD_PARTY_NOTICES.md
├── LICENSE_STATUS.md
├── RELEASE_LOCK.tsv
├── SOURCE_MANIFEST.json
├── compose.release.yaml
├── deploy/organizer.env.example
├── scripts/{run_release.sh,verify_release.sh,stop_release.sh}
├── LICENSES/
└── code/
```

`compose.release.yaml` contains no `build:` section and applies `pull_policy: never` to every
service. `RELEASE_LOCK.tsv` binds the four local references to exact Docker image IDs and binds the
two project images to the candidate Git revision label.

## 2. Organizer machine: load and run only

Required host software is Linux x86_64, Docker Engine, Docker Compose v2, Bash, `unzip` and
`sha256sum`. At least 10 GiB RAM is recommended because the default service ceilings total 8.5 GiB.
The organizer does not install Python/uv/pip, build an image or pull an image.

The Docker Engine must be rootful on both development and organizer machines. Run the operator
scripts as the ordinary user; they use direct access to the rootful daemon when available and fall
back to non-interactive `sudo` for Docker commands only. Never run a complete script with `sudo`.
On the organizer machine, the delivery, extracted solution, private configuration, evaluation
inputs/outputs and reports must all remain below that ordinary user's `$HOME`; do not use `/root`,
`/secure` or another top-level system working directory.

“Offline” in this delivery contract means the organizer needs no public Internet, image registry,
Python package index, source host or dependency download. The four runtime images and all startup
files arrive in the delivered ZIP/TAR set. The only runtime network dependency is the organizer's
already-available OpenAI-compatible Chat/Embedding API (Huawei intranet for the supplied profile).
The official evaluator must likewise already exist on the organizer machine. With absolutely no
network path to any configured model API, the containers can start, but real Add/Search evaluation
cannot complete; that state must be reported as `model_api_unreachable`, not as an offline pass.

Place all four delivered files in `$HOME/memscope-organizer/<candidate>/`, then run as the ordinary
user (use `sudo -v` once before the operator script if direct rootful-Docker access is unavailable):

```bash
sha256sum -c SHA256SUMS
unzip solution-<candidate>.zip
```

Create a private runtime configuration outside the extracted source and replace secret placeholders:

```bash
umask 077
install -d -m 0700 "$HOME/.config/memscope" "$HOME/memscope-evaluation/<candidate>"
cp solution/deploy/organizer.env.example "$HOME/.config/memscope/organizer.env"
chmod 0600 "$HOME/.config/memscope/organizer.env"
```

Never put a real Key, IAM token or Neo4j password in source, Compose YAML, an image layer, a command
argument, a report or a chat transcript. The supplied organizer template records the confirmed
non-secret Huawei internal model facts and explicitly permits its HTTP endpoints.

Load, identity-check and start all four services with one command:

```bash
cd solution
./scripts/run_release.sh \
  --image-bundle ../memscope-images-<candidate>-linux-amd64.tar \
  --sha256-file ../SHA256SUMS \
  --env-file "$HOME/.config/memscope/organizer.env"
```

The script validates hashes and private-file permissions, runs `docker load`, verifies all image
IDs/revision labels, runs Compose `config --quiet`, and starts with `--no-build --pull never --wait`.
None of these deployment steps contacts a registry or package source.

Before official evaluation, run the real model smoke:

```bash
./scripts/verify_release.sh --env-file "$HOME/.config/memscope/organizer.env"
```

The verifier checks four healthy containers, Neo4j and Qdrant readiness, Add replay, cross-session
Search and cross-user isolation. It runs Python already packaged inside `memory-api`; there is no host
Python dependency. Output is limited to status, timing and evidence counts. The smoke writes one
unique synthetic user and calls the real Chat/Embedding endpoints.

Point the organizer's official evaluator at the printed origin, normally
`http://127.0.0.1:8080`. Do not pass gold answers to `/search` and do not replace the official Judge
with a package-local implementation. The evaluation client owns batch throttling and bounded 429
backoff; the service does not automatically replay Add.
Keep the evaluator's datasets, temporary files, outputs and sanitized report under
`$HOME/memscope-evaluation/<candidate>/`.

Stop containers and preserve all named volumes with:

```bash
./scripts/stop_release.sh --env-file "$HOME/.config/memscope/organizer.env"
```

Never run `down -v`, `docker system prune`, a build or a pull on the organizer machine. Complete
operator steps and the directly reusable agent prompt are in `ORGANIZER_QUICKSTART.md` and
`ORGANIZER_AGENT_PROMPT.md`.

## 3. Organizer runtime configuration

The supplied Huawei organizer profile uses:

- Chat base/model: `http://aigateway.huawei.com/v1`, `GLM-V5_1-DX`;
- Embedding base/model/dimension: `http://aigateway.huawei.com/v1`, `bge-m3`, `1024`;
- `MEMSCOPE_ALLOW_INSECURE_MODEL_HTTP=true`, limited to the trusted organizer intranet;
- local `cosine_local` reranking; the advertised `/v1/reranker` API is not called by this baseline.

The current MemOS clients use OpenAI-compatible Bearer API-key authentication. If the organizer
provides only an IAM token with different header syntax, obtain the exact rule before deployment;
never paste the sample alternative syntax itself into a header.

Only `memory-api` publishes a host port. Change `MEMSCOPE_PUBLIC_PORT` in the private env file if
8080 is unavailable. Add must finish below 120 seconds and Search below 60 seconds. Keep exactly one
memory-api worker and one MemOS worker.

## 4. Development-machine build and tuning

The development machine—not the organizer—owns Python dependency installation, source changes,
service deployment against its reachable OpenAI-compatible APIs, baseline evaluation, tuning and
image construction. The development Compose entry remains `compose.yaml`:

```bash
uv sync --frozen
sudo -v
./scripts/deploy_linux.sh --env-file "$HOME/.config/memscope/development.env"
```

Builds use exactly one explicit HTTPS Python package index. Override the default only with a
credential-free URL in the private development configuration:

```text
MEMSCOPE_PIP_INDEX_URL=https://approved.example/simple
```

API URL, Key, model, prompt and Search-threshold changes are runtime/tuning inputs and do not require
an image rebuild. Iterate with native/source-mounted processes where practical; build the final
images once after source and non-secret configuration are frozen.

The final builder requires a clean Git checkout whose HEAD equals the literal 40-character candidate
commit. It either builds the two project images or explicitly reuses images already labeled with that
commit, verifies the two pinned upstream images, then creates the ZIP, four-image TAR, manifest and
checksums outside the repository:

```bash
python3 scripts/build_candidate_delivery.py build \
  --source-root . \
  --output-dir "$HOME/memscope-final/<candidate>" \
  --candidate-commit <40-character-commit> \
  --build-images \
  --pull-upstream \
  --package-index https://approved.example/simple

python3 scripts/build_candidate_delivery.py verify \
  --delivery-dir "$HOME/memscope-final/<candidate>"
```

`--pull-upstream` is an explicit development-machine action and fetches only the digest-pinned
Neo4j/Qdrant references. Use `--reuse-images` only when both project images were already built from
the exact candidate commit. The builder refuses dirty/mismatched Git state, unsafe paths, in-tree
output and overwrite. It expands and scans the fixed MemOS source archive; reviewed upstream test
fixtures are accepted only when both the archive hash and path/classification set remain exact.

Do not execute the final builder or call an artifact final during B10 Gate 1/Gate 2. Final artifact
generation occurs only after real development-machine evaluation/tuning and separate user approval.

## 5. Failure and recovery rules

- A failed or timed-out Add/Search is not converted to HTTP 200 or an empty successful result.
- Identical `request_id` replay returns the completed result; conflicting reuse returns HTTP 409.
- Preserve Raw, receipt, MemOS, Neo4j and Qdrant volumes across normal restart.
- Never reuse vector/graph storage after changing the Embedding model or dimension without an
  explicitly reviewed migration.
- On organizer failure, retain containers/volumes and return only commit, hashes, image IDs, health,
  timings and sanitized error classifications. Do not rebuild or patch the candidate in place.

Architecture, persistence and semantic limitations are documented in `SDD.md`. The project does not
claim an official score or organizer-runtime pass until returned evidence identifies this exact
candidate and image set.

# B08 system verification runbook

This runbook verifies an already-running candidate. It never authorizes the verifier to start,
restart, stop or delete services. Use a unique test namespace and a candidate-specific persistent
store. Do not run against unrelated production user data.

## 1. Admission

Before testing, record the exact 40-character candidate commit, deployment path, non-secret model
IDs, Embedding dimension, MemOS/Neo4j/Qdrant/Python versions and storage identity. Confirm exactly
one memory-api worker and that `/health` is reachable from the evaluation client.

The base URL must be an HTTP(S) origin without embedded credentials. If authentication is enabled,
provide `CONTEST_API_KEY` only in the process environment; the verifier never includes it in state,
reports or errors.

## 2. Exercise

```bash
python3 scripts/verify_b08_system.py \
  --base-url http://127.0.0.1:8080 \
  --candidate-commit <40-character-commit> \
  --report /secure/b08-exercise.json \
  exercise --samples 5 --concurrency 2 --require-hit
```

The command performs exact Health, initial/replay/cross-session Add, Search, cross-user isolation,
expected 422/409 checks, concurrent exact replays, low-concurrency isolated Adds and repeated
Searches. It makes each request once: 429, timeout, 5xx or transport failure is classified and fails
the run without automatic retry.

The workload bounds are intentionally conservative: samples `1..30` and concurrency `1..8`.
Increase neither during first admission. P50/P95/P99/max are nearest-rank smoke observations, not a
formal performance baseline.

## 3. Restart checkpoint

Prepare a private checkpoint outside the repository:

```bash
python3 scripts/verify_b08_system.py \
  --base-url http://127.0.0.1:8080 \
  --candidate-commit <40-character-commit> \
  --report /secure/b08-before-restart.json \
  prepare-restart --state /secure/b08-restart-state.json
```

The state file is created with mode `0600`, contains only synthetic B08 data, has an integrity hash
and never contains the contest API key. Preserve the same Raw, receipt, Neo4j and Qdrant storage.

An operator then performs one controlled restart. For native deployment, gracefully stop and start
the single memory-api process and MemOS process using the existing process manager and unchanged
configuration. For an already-admitted Compose deployment, use `docker compose restart memory-api
memos`; never use `down -v` and never remove volumes.

After readiness recovers:

```bash
python3 scripts/verify_b08_system.py \
  --base-url http://127.0.0.1:8080 \
  --candidate-commit <40-character-commit> \
  --report /secure/b08-after-restart.json \
  verify-restart --state /secure/b08-restart-state.json
```

The final phase requires an identical Add acknowledgement, at least one pre-restart evidence ID,
and zero evidence for the isolated user. The verifier does not infer that an operator actually
restarted services; the operator must record the restart command/time and process/container identity
in the evidence bundle.

## 4. Storage and resource observations

Record without dumping memory content, vectors, credentials or provider responses:

- one-worker process/container identity before and after restart;
- CPU and RSS/working-set observations during exercise;
- Raw/receipt and service-storage disk usage before and after exercise;
- Qdrant `neo4j_vec_db` dimension, distance and readiness;
- Neo4j database readiness and required index names/states;
- configured and observed container CPU/memory/PID ceilings when Docker is used;
- cold/readiness recovery duration and any OOM, restart or health failure.

Native examples may use `ps -o pid,ppid,nlwp,rss,vsz,etime,cmd -p <pid>` and `du -sh` on the exact
candidate directories. Docker examples may use `docker stats --no-stream` and narrowly scoped
`docker inspect`. Commands that interpolate environment variables or print Compose configuration
must not be captured because they may expose keys; use `docker compose config --quiet` only.

Existing Add `<120s`, Search `<60s`, single-worker and configured Compose ceilings are hard gates.
No new CPU/RSS/disk threshold is invented in B08; other resource values are reported observations.

## 5. Failure classification

| Classification | Examples | Result |
|---|---|---|
| `validation` | unsafe CLI input, HTTP 422 | expected only for the deliberate validation probe |
| `conflict` | exact request ID with changed content, HTTP 409 | expected only for the deliberate conflict probe |
| `rate_limited` | HTTP/provider 429 | fail; no retry |
| `timeout` | client or typed Add/Search/Gateway timeout | fail |
| `provider_unavailable` | connection/provider/storage unavailable | fail |
| `protocol_invalid` | invalid JSON/body/evidence or typed invariant | fail |
| `readiness_unavailable` | public 503 | fail |
| `isolation_breach` | cross-user evidence | P0 fail |
| `duplicate_recovery_invariant` | changed replay or lost evidence identity | P0 fail |
| `unclassified` | any other failure | fail and stop for review |

Do not turn a failure into empty HTTP 200, Raw fallback, a retry loop, a worker or an unreviewed
production patch. Preserve the reports and request a revision from the Batch that owns the failed
semantic boundary.

## 6. Docker/native time box

Use native/source execution or reuse an existing admitted stack first. Docker receives a ten-minute
capability preflight and at most thirty minutes for the stage. B08 changes no runtime source, so it
does not justify a new image build. If host ports, cgroups, images or the daemon are unsuitable,
record the fact and transfer the runbook to the capable tuning machine.

## 7. Gate 2 evidence bundle

Return the three mode-0600 JSON reports, candidate commit, restart record, sanitized resource/storage
observations and a conclusion for every classification above. Report file hashes may be committed;
the synthetic restart state, credentials, raw logs and runtime databases must not be committed.

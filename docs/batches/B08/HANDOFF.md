# B08 system verification handoff

> Status: Gate 2 review open; not Accepted/Frozen; deployed-system evidence assigned to tuning machine
>
> Gate 1 approved by explicit user message on 2026-09-04
>
> Gate 2 review entered by explicit user message on 2026-09-04
>
> Base commit: `d281aa03b5b90f9e9903033fd9f1fc822011a490`
>
> Branch: `batch/b08-system-verification`
>
> Deterministic candidate commit: `44ce4a7be3e052fa839692bb3dc2c4c8b149ecb4`

## 1. Delivered candidate

B08 adds a standard-library, public-HTTP system verifier with `exercise`, `prepare-restart` and
`verify-restart` phases. It measures bounded stage latency, exercises low concurrency, verifies
validation/conflict behavior, protects restart state with mode 0600 and an integrity digest, and
emits reports without API keys, request/query content, full responses or raw user IDs.

The verifier never starts, restarts, stops or deletes services and never retries a failed request.
Operator-controlled restart and resource/storage capture are defined in `SYSTEM_VERIFICATION.md`.

## 2. Deterministic evidence

The verifier unit suite uses a loopback-only `ThreadingHTTPServer` fixture. The system suite uses the
public ASGI Adapter with real `SqliteRawStore`, `GatewayReceiptStore`, `MemosMemoryGateway` and
`MemoryOperations`, while provider I/O is deterministic `httpx.MockTransport`.

Covered behavior:

- exact Health and complete public Add/Search responses;
- concurrent exact Add convergence with one provider Add;
- same-user cross-session visibility and separate-user result isolation;
- component reconstruction over persistent Raw/receipt files, exact replay and retained evidence;
- partial provenance fail-closed with no provider Add;
- public 429, timeout and invalid-JSON classifications that never become empty success;
- CLI origin/workload bounds, percentile math, report redaction and restart-state integrity.

## 3. Quality evidence

| Check | Result |
|---|---|
| B08 verifier unit tests | 4 passed in 1.15 seconds |
| B08 + B07 focused tests | 10 passed in 2.64 seconds |
| Full pytest | 552 passed in 17.20 seconds |
| Statements | 2,232 / 2,296; 97.21% |
| Branches | 579 / 610; 94.92% |
| Combined branch-aware coverage | 96.73%; required minimum 95% |
| Ruff format/check | passed; 80 Python files |
| Mypy `src tests scripts` | passed; 79 source files |

The managed sandbox forbids loopback socket creation and blocks Python 3.11 `asyncio.to_thread()`
completion wakeups. Those tests ran outside that restriction while remaining offline and using only
127.0.0.1, pytest temporary files, ASGITransport and MockTransport. `UV_CACHE_DIR` was redirected to
`/tmp`; dependency declarations and locks did not change.

## 4. Zero production impact

There is no diff below `src/`, in database migrations, `pyproject.toml`, `uv.lock`, `compose.yaml`,
Dockerfiles or MemOS patch/lock files. Public/internal contracts, deadlines, settings, single-worker
deployment and B05–B07 recovery/search semantics are unchanged.

## 5. Missing live evidence

A read-only listener check on 2026-09-04 found no candidate services on ports 8080, 8000, 7474 or
6333. No Docker build/start and no real provider/model request was performed. Therefore this
handoff does not claim:

- a deployed native or Compose `exercise` pass;
- operator restart and persistence on a real service topology;
- real-model Add producing `activated` memory followed by Search hit;
- live P50/P95/P99/max, CPU/RSS/disk, Qdrant collection or Neo4j index evidence;
- zero live 429/timeout/5xx/unclassified failures.

The user explicitly entered Gate 2 review on 2026-09-04 while preserving this limitation. B08
**cannot be judged Accepted/Frozen under the ordinary standard** because real deployed-system
`exercise`, restart-persistence and resource evidence is missing. Producing that evidence is
assigned to the tuning machine. The review therefore remains open; entering review is not an
acceptance decision, and deterministic tests do not substitute for live system evidence.

## 6. Next action

Run `SYSTEM_VERIFICATION.md` on the Huawei tuning machine or another admitted native/Compose
candidate using the exact source commit. Return the three JSON reports plus sanitized
restart/resource observations and their hashes. The development-machine reviewer must validate the
returned candidate identity and evidence before making a later Accepted/Frozen or rejected
decision. Any cross-user evidence, changed replay, lost evidence identity, Add at least 120 seconds,
Search at least 60 seconds or unclassified failure blocks Gate 2 and must not be repaired inside B08
without a revised plan.

B09 cannot begin while this review is open and before explicit B08 Gate 2 acceptance.

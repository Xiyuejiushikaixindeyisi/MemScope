# B07 reliability closure handoff

> Status: Gate 2 Accepted/Frozen by explicit user approval on 2026-09-04
>
> Gate 1 approved by explicit user message on 2026-09-04
>
> Base commit: `ee4a8720ec400642fa5925350c0c441b2cabfbb6`
>
> Branch: `batch/b07-reliability-closure`
>
> Candidate commit: `e30fa91d332e2945f27185b5a5f3248cc5ebe680`

## 1. Delivered scope

B07 closes one evidence gap without adding a production mechanism. A new deterministic component
suite composes the real `SqliteRawStore`, `GatewayReceiptStore`, `MemosMemoryGateway` and
`MemoryOperations`, then reconstructs those components against the same temporary SQLite files to
prove the accepted B05 recovery boundary survives a full process-style restart.

The candidate also reconciles the historical B07–B09 table with the accepted B05/B06 R1 decisions.
The older outbox worker, automatic retry, Raw fallback and optional D04-B wording is no longer an
implementation authorization. B08 remains system verification; B09 remains reproducible delivery
and baseline evidence closure.

## 2. Recovery evidence

`tests/component/test_b07_reliability_boundary.py` proves:

1. **Receipt completed, Raw pending:** provider Add/readback and receipt completion succeed, an
   injected SQLite trigger rejects Raw completion, then reconstructed components complete Raw from
   the durable receipt with zero provider calls.
2. **Provider committed, response lost:** the first Add records a pending Raw request and receipt
   after a simulated transport loss. Reconstructed components find the complete exact provenance,
   complete both ledgers and never repeat `/product/add`.
3. **Recovered result is searchable:** the recovered activated, supported-type, vector-synchronized
   and attributable memory passes the real B06 Search conversion and is returned as expected.
4. **Partial provenance:** a one-of-two result set raises `gateway.protocol_invalid`; Raw and receipt
   remain pending and no Add, repair or destructive request occurs.
5. **Rate limiting:** each explicit application Add receives one reconciliation read and one
   provider Add attempt. There is no internal retry; only a second external replay causes a second
   attempt, and both durable ledgers remain pending after 429.

All HTTP behavior uses in-process `httpx.MockTransport`. All persistent state uses pytest
`tmp_path`; no network, key, real provider, model, Docker daemon or repository runtime data is used.

## 3. Quality evidence

Environment: CPython 3.11.16, uv 0.12.9 and the unchanged frozen dependency set. `UV_CACHE_DIR` was
redirected to `/tmp` because the managed sandbox makes the user uv cache read-only. SQLite tests ran
outside the restricted execution sandbox because that sandbox blocks Python 3.11
`asyncio.to_thread()` completion wakeups; they still used only local temporary files and
MockTransport.

| Check | Result |
|---|---|
| Focused B07 component suite | 4 passed in 0.26 seconds |
| B05/B06 reliability regression selection | 141 passed in 3.54 seconds |
| Full pytest | 546 passed in 8.51 seconds |
| Statements | 2,232 / 2,296; 97.21% |
| Branches | 579 / 610; 94.92% |
| Combined branch-aware coverage | 96.73%; required minimum 95% |
| Ruff format/check | passed; 77 Python files checked |
| Mypy `src tests scripts` | passed; 76 source files |

`git diff --check` passes. There is no diff below `src/`, in `pyproject.toml`, `uv.lock`,
`compose.yaml`, `docker/`, migrations or fixed-source locks.

## 4. Contract and runtime impact

- Public and internal schemas/interfaces are unchanged.
- Raw and receipt database schemas are unchanged.
- Add remains synchronous with the same lane/deadline behavior and no automatic retry/fallback.
- Search filtering, ordering, `top_k`, readiness and deadline behavior are unchanged.
- Runtime settings, dependencies, Compose/Docker and MemOS fixed-source patches are unchanged.
- Single-worker deployment remains mandatory.

The absence of a production diff is intentional: composed fault evidence confirmed that the B05/B06
mechanisms already implement the approved recovery boundary.

## 5. Remaining limitations

B07 does not prove real Huawei model capability, Embedding dimension, `activated` publication under
real extraction, semantic accuracy, latency distribution, resource limits or Docker host behavior.
It does not make natural-language Update/Forget reliable, add semantic contradiction removal, or
make Raw/receipt/graph/vector state one transaction. These remain explicit system/tuning and design
boundaries rather than hidden success claims.

The accepted empty-result crash window also remains unchanged: if a process dies after a valid
provider Add with no extracted memories but before receipt completion, exact provider readback
cannot distinguish that committed-empty outcome from not-yet-attempted state. B07 does not add a
worker, marker or retry protocol to change this accepted B05 limitation.

## 6. Gate 2 acceptance and B08 input

B07 Gate 2 was explicitly accepted/frozen by the user on 2026-09-04. Deterministic composition is
accepted as sufficient for this Batch; no production reliability mechanism is warranted without
failing evidence.

The user also explicitly entered B08 Gate 1. B08 may therefore submit its own plan for full-path,
concurrency, restart, resource and segmented latency verification. It must inherit the same
no-automatic-retry, no-Raw-fallback, single-worker and fail-closed boundaries and cannot begin
implementation until that separate plan is approved.

# B09 reproducible delivery handoff

> Status: Gate 2 review open; not Accepted/Frozen
>
> Gate 1 approved by explicit user message on 2026-09-04
>
> Gate 2 review entered by explicit user message on 2026-09-04
>
> Base commit: `2498c904e97ab36d85a8596898996243460dae6f`
>
> Branch: `batch/b09-delivery-closure`
>
> Implementation candidate: `fe246c0ba59a39a108850f6e35126114c0a20716`

## 1. Delivered scope

B09 adds the organizer-facing `INSTRUCTION.md`, aligns `SDD.md` through the B08/B09 boundary,
clarifies third-party licensing, and adds a standard-library deterministic archive builder/verifier.
No production module, public/internal contract, database, dependency, Compose/Docker runtime or
fixed MemOS source/patch changed.

The builder has separate explicit allowlists:

- `handoff` carries auditable source, tests, public evaluation assets, deployment/verification
  runbooks and two-machine templates for the tuning machine;
- `submission` emits the formal `solution/` hierarchy with instructions, SDD, notices, MemOS
  license and runtime/build source, while excluding tests, Batch history and evaluation data.

It rejects unsafe paths, symbolic links, selected credential patterns, in-tree output and existing
targets. ZIP timestamps, member ordering and modes are normalized. Each archive embeds exact member
sizes/SHA-256 values and emits a separate whole-ZIP SHA-256 sidecar.

## 2. Deterministic artifact evidence

All artifacts below are temporary previews built from clean candidate `fe246c0...`; they are not the
final handoff or submission release and are not committed.

| Mode | Independent builds | Entries | Bytes | Matching SHA-256 |
|---|---:|---:|---:|---|
| handoff | 2 | 305 | 22,424,863 | `1ec051876a3098476adfb49422b46cffe37984d5f248cbb6aee8ba367fb6b6f7` |
| submission | 2 | 67 | 10,536,049 | `af647cd751b6378f1d9aa2417b874107d5a8eddef3e20a7bdf8a7b58e0473960` |

Both pairs were built in distinct output directories. All four archives passed independent
manifest/member/path verification against their sidecars. A submission preview was extracted into
a new temporary directory; its required `solution/` structure and extracted Compose static config
passed.

## 3. Quality and lock evidence

| Check | Result |
|---|---|
| B09 delivery unit tests | 4 passed in 0.12 seconds |
| Full pytest | 556 passed in 19.30 seconds |
| Statements | 2,232 / 2,296; 97.21% |
| Branches | 579 / 610; 94.92% |
| Combined branch-aware coverage | 96.73%; required minimum 95% |
| Ruff format/check | passed; 82 Python files |
| Mypy `src tests scripts` | passed; 81 source files |
| Compose source + extracted submission `config --quiet` | passed; no service started |
| MemOS `SHA256SUMS` | passed; fixed 10 MiB archive |
| Fresh MemOS patchset `--verify-only` | passed against all locked preimages |
| Actual handoff/submission source selection + secret scan | passed |

The full suite ran outside the managed restriction because existing SQLite/asyncio tests require
local thread wakeups; it remained local/offline and used temporary files, 127.0.0.1 and deterministic
transports. `UV_CACHE_DIR` was redirected to `/tmp`.

The clean extracted `uv sync --frozen --offline --no-dev` first stopped because the development
cache lacked the locked `pydantic-core==2.33.2` wheel. A subsequent network-enabled
`uv sync --frozen --no-dev` downloaded the exact locked wheel and built MemScope successfully in an
independent `/tmp` environment. Locks and dependency declarations did not change. The candidate is
therefore clean-build verified with a package source, not claimed fully offline-installable.

## 4. Licensing result

The MemOS Apache-2.0 license is included both beside its bundled source archive and at the formal
submission's `solution/LICENSES/MemOS-Apache-2.0.txt`. Python packages and OCI images remain subject
to upstream terms and are resolved during build rather than copied from the development environment.

No license has been selected for original MemScope source. B09 does not invent a legal grant; the
third-party notice explicitly records this boundary.

## 5. External evidence still pending

B08 is frozen under the tuning-machine live-evidence transfer exception. This B09 candidate does
not claim:

- live B08 `exercise`, restart-persistence or resource evidence;
- a real Chat/Embedding capability, exact production dimension or activated Search hit;
- a semantic baseline, official score or tuning gain;
- a final Docker build/start, image result or host-port/cgroup result;
- a tuning-machine final submission ZIP.

The handoff manifest records those pending claims. The tuning machine must follow `DELIVERY.md`,
`SYSTEM_VERIFICATION.md` and the two-machine workflow, then return the final ZIP/hash,
source/config differences and sanitized evidence.

## 6. Gate 2 decision and post-acceptance action

The user explicitly entered B09 Gate 2 review on 2026-09-04. The review is open; entering review is
not an acceptance or freeze decision. A later Gate 2 acceptance must not be interpreted as external
live/baseline acceptance.

No final ZIP, release or tag has been created. Only after explicit B09 Gate 2 acceptance should the
exact frozen commit build the named handoff archive and sidecar. Upload, remote push, final tuning
submission and project-license selection remain separate actions requiring their own authority.

Rollback is a normal revert of B09 documentation, script and tests; it does not touch services,
volumes or provider data.

# B04 Gate 2 handoff (draft)

> Status: static implementation evidence complete; runtime gate not yet executed
> Branch: `batch/b04-runtime-infra`
> Date: 2026-09-02

## Delivered

B04 now has a one-command, three-container runtime definition for pinned MemOS, Neo4j Community
and Qdrant. It bundles the complete fixed MemOS source and license, pins all base images by OCI
index digest, requires an external Neo4j secret, exposes no host ports, uses an internal runtime
network and persists each stateful component in named volumes.

The B04 configuration intentionally cannot perform Add/Search: model endpoints are explicit local
no-call placeholders and optional model-dependent features are disabled. This prevents a shallow
`/health` response from being represented as semantic readiness.

## Verification status

| Gate | Status | Evidence |
|---|---|---|
| Source archive checksum/completeness | passed | SHA-256 `9a804f...cdf3c`; second `git archive` was byte-identical |
| B04 static manifest tests | passed | 7/7 tests |
| Image/reference lock consistency | passed | `SOURCE_LOCK.json` + unit test; OCI index digests checked against Docker Hub API |
| YAML syntax | passed | Ruby Psych parse; exact three-service assertion |
| Ruff format/lint | passed | 60 files formatted; no lint findings |
| Mypy | passed | 59 existing sources + strict verifier/test check |
| Full pytest | passed | 325 passed in 7.67s; 98.25% combined coverage |
| Project dependency files | unchanged | no diff in `pyproject.toml` or `uv.lock`; `uv` executable unavailable on this host |
| Compose config/build | blocked on current host | Docker CLI/daemon absent |
| Cold start and aggregate readiness | blocked on current host | Docker CLI/daemon absent |
| Restart persistence | blocked on current host | Docker CLI/daemon absent |
| Qdrant fault detection/recovery | blocked on current host | Docker CLI/daemon absent |

## Required external Gate 2 command

Run on a clean Linux host with Docker Engine and Compose v2:

```bash
python scripts/verify_b04_runtime.py --report /tmp/b04-runtime-report.json
```

Attach the JSON report plus `docker version`, `docker compose version`, host architecture and any
failure logs. Do not approve Gate 2 until every lifecycle check passes. The script cleans only its
randomly named `memscope_b04_gate_*` Compose project and named volumes.

## Known limits

- Build is source-reproducible but not offline: registry, Debian packages and pinned Python
  packages must be reachable or cached.
- The bootstrap embedding dimension 16 is not a model choice. B05 must set the real fixed dimension
  and recreate disposable B04 volumes if it changes.
- B04 provides no contest public endpoint, Real Gateway, model credential, Add/Search or quality
  result.
- Named volumes cover restart/recreation on one Docker host, not cross-host backup/migration.
- A one-image/one-container delivery would require a new architecture decision.

## Gate conclusion

Not yet eligible for B04 Gate 2 acceptance. Static evidence and the real container lifecycle report
must replace the pending rows before user review. B05 is not authorized by this handoff.
